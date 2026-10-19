"""Resource queues and narrow task locks, using synthetic blocking events."""
import threading
import time
import copy
from pathlib import Path

import pytest

from test_employee_service import wait_finished
from test_service import prepared


def payload(job):
    return {"workbook_path": job["_workbook_path"], "source_path": job["_source_path"],
            "output_root": job["_output_root"], "start_number": 1}


def test_ai_wait_does_not_block_next_cpu_batch_or_another_export(tmp_path, monkeypatch):
    manager, ready = prepared(tmp_path, [""])
    ready.update(_owner_id="ready-owner", _downloadable=True)
    ai_entered, release = threading.Event(), threading.Event()
    cpu_finished = []
    def review(identifier):
        if len(cpu_finished) == 1:
            ai_entered.set()
            assert release.wait(5)
    def cpu(identifier):
        manager._start_operation(identifier, "matching", "synthetic CPU")
        manager.jobs[identifier]["_started_perf"] = time.perf_counter()
        cpu_finished.append(identifier)
        with manager.lock:
            manager.jobs[identifier]["status"] = "queued"
            manager._submit(manager.jobs[identifier], manager._after_match_ai)
    monkeypatch.setattr(manager, "_process", cpu)
    monkeypatch.setattr(manager, "_review_ai", review)
    try:
        first = manager.create(payload(ready), owner_id="first")
        assert ai_entered.wait(5)
        second = manager.create(payload(ready), owner_id="second")
        assert wait_finished(manager, second)["status"] == "ready"
        assert cpu_finished == [first, second]
        assert manager.snapshot(first)["status"] == "ai_review"
        with pytest.raises(ValueError):
            manager.resolve(first, "r2", None)
        with pytest.raises(ValueError):
            manager.undo(first)
        with pytest.raises(ValueError):
            manager.export(first)
        manager.export("sample")
        assert wait_finished(manager)["status"] == "done"
        assert manager.snapshot(first)["status"] == "ai_review"
    finally:
        release.set()
        manager.close()


def test_waiting_per_job_operation_counts_busy_and_does_not_block_other_task(tmp_path):
    manager, _ = prepared(tmp_path, [""])
    manager.jobs["other"] = {"id": "other", "status": "ready"}
    attempted, acquired, other_acquired = threading.Event(), threading.Event(), threading.Event()
    def same():
        attempted.set()
        with manager.job_operation("sample"):
            acquired.set()
    def other():
        with manager.job_operation("other"):
            other_acquired.set()
    try:
        with manager.job_operation("sample"):
            waiter = threading.Thread(target=same)
            waiter.start()
            assert attempted.wait(2)
            deadline = time.monotonic()+2
            while manager._active_operations < 2 and time.monotonic() < deadline:
                time.sleep(.001)
            assert manager._active_operations == 2 and manager.has_active_operations()
            independent = threading.Thread(target=other)
            independent.start()
            assert other_acquired.wait(2)
            independent.join(2)
            assert not acquired.is_set()
        waiter.join(2)
        assert acquired.is_set() and manager._active_operations == 0
    finally:
        manager.close()


def test_close_drains_accepted_cpu_handoffs_and_internal_ai_operations(tmp_path, monkeypatch):
    manager, ready = prepared(tmp_path, [""])
    entered, release = threading.Event(), threading.Event()
    ai_finished = []
    def ai(identifier):
        manager._start_operation(identifier, "ai_review", "synthetic AI")
        with manager.job_operation(identifier, internal=True):
            ai_finished.append(identifier)
            manager.jobs[identifier]["status"] = "ready"
    def cpu(identifier):
        manager._start_operation(identifier, "matching", "synthetic CPU")
        entered.set()
        assert release.wait(5)
        with manager.lock:
            manager.jobs[identifier]["status"] = "queued"
            manager._submit(manager.jobs[identifier], ai)
    monkeypatch.setattr(manager, "_process", cpu)
    first = manager.create(payload(ready), owner_id="first")
    assert entered.wait(2)
    second = manager.create(payload(ready), owner_id="second")
    closer = threading.Thread(target=manager.close)
    closer.start()
    deadline = time.monotonic()+2
    while not manager._closing and time.monotonic() < deadline:
        time.sleep(.001)
    try:
        with pytest.raises(ValueError, match="退出"):
            manager.create(payload(ready), owner_id="new")
        with pytest.raises(ValueError, match="退出"):
            with manager.job_operation("sample"):
                pass
        release.set()
        closer.join(5)
        assert not closer.is_alive()
        assert set(ai_finished) == {first, second}
        assert manager.jobs == {} and manager._active_operations == 0
    finally:
        release.set()
        closer.join(5)


def test_close_keeps_pools_open_until_an_accepted_export_finishes_submission(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    entered, release = threading.Event(), threading.Event()
    shutdown_started = threading.Event()
    errors = []
    original_plan, original_shutdown = manager._plan, manager.pool.shutdown

    def planning(current):
        entered.set()
        assert release.wait(5)
        original_plan(current)

    def shutdown(*args, **kwargs):
        shutdown_started.set()
        return original_shutdown(*args, **kwargs)

    def invoke(operation):
        try:
            operation()
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(manager, "_plan", planning)
    monkeypatch.setattr(manager.pool, "shutdown", shutdown)
    exporter = threading.Thread(target=invoke, args=(lambda: manager.export("sample"),))
    closer = threading.Thread(target=invoke, args=(manager.close,))
    try:
        exporter.start()
        assert entered.wait(2)
        closer.start()
        deadline = time.monotonic()+2
        while not manager._closing and time.monotonic() < deadline:
            time.sleep(.001)
        assert manager._closing and manager._active_operations == 1
        assert not shutdown_started.wait(.05)
        release.set()
        exporter.join(5)
        closer.join(5)
        assert not exporter.is_alive() and not closer.is_alive()
        assert not errors
        assert shutdown_started.is_set()
        assert job["status"] == "done" and job["report"]["exported"] == 1
        assert manager.jobs == {} and manager._active_operations == 0
        assert (Path(job["output_dir"]) / "已编号AI" / "HSD0001.ai").is_file()
    finally:
        release.set()
        exporter.join(5)
        if closer.ident is not None:
            closer.join(5)
        else:
            manager.close()


def test_unhandled_worker_failure_releases_cpu_and_marks_failed_job(tmp_path, monkeypatch):
    manager, ready = prepared(tmp_path, [""])
    seen = []
    def cpu(identifier):
        manager._start_operation(identifier, "matching", "synthetic CPU")
        seen.append(identifier)
        if len(seen) == 1:
            raise RuntimeError("synthetic worker failure")
        manager.jobs[identifier]["status"] = "ready"
    monkeypatch.setattr(manager, "_process", cpu)
    try:
        first = manager.create(payload(ready), owner_id="first")
        second = manager.create(payload(ready), owner_id="second")
        assert wait_finished(manager, first)["status"] == "error"
        assert wait_finished(manager, second)["status"] == "ready"
        assert seen == [first, second]
    finally:
        manager.close()


def test_snapshot_waits_for_consistent_plan_without_holding_global_lock(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    entered, release, snapshot_done = threading.Event(), threading.Event(), threading.Event()
    original = manager._plan
    def delayed(current):
        entered.set()
        assert release.wait(5)
        original(current)
    monkeypatch.setattr(manager, "_plan", delayed)
    changed, snapshots = [], []
    writer = threading.Thread(target=lambda: changed.append(manager.resolve("sample", "r2", None)))
    reader = threading.Thread(target=lambda: (snapshots.append(manager.snapshot("sample")), snapshot_done.set()))
    try:
        writer.start()
        assert entered.wait(2)
        reader.start()
        assert not snapshot_done.wait(.05)
        assert manager.lock.acquire(timeout=.5)
        manager.lock.release()
        release.set()
        writer.join(2)
        reader.join(2)
        assert snapshot_done.is_set()
        assert snapshots[0]["rows"][0]["status"] == "skipped"
        assert snapshots[0]["stats"]["skipped"] == 1 and snapshots[0]["stats"]["exportable"] == 0
    finally:
        release.set()
        writer.join(2)
        reader.join(2)
        manager.close()


@pytest.mark.parametrize("enabled", [False, True])
def test_local_result_does_not_wait_for_occupied_ai_batch_pool(tmp_path, monkeypatch, enabled):
    manager, template = prepared(tmp_path, [""])
    release = threading.Event()
    started = [threading.Event(), threading.Event()]
    blockers = [manager.ai_pool.submit(lambda event=event: (event.set(), release.wait(5))) for event in started]
    assert all(event.wait(2) for event in started)
    monkeypatch.setattr(manager.ai_settings, "runtime", lambda: {
        "enabled": enabled, "api_key": "synthetic-unused" if enabled else ""})
    monkeypatch.setattr("hsd_tool.workbook.inspect_workbook", lambda *args: {
        "sheet_name": "测试", "rows": copy.deepcopy(template["rows"]), "reserved_numbers": []})
    monkeypatch.setattr("hsd_tool.matching.scan_and_match", lambda *args, **kwargs: {
        "files": copy.deepcopy(template["files"]),
        "matches": [{"row_id": "r2", "status": "auto", "file_id": "f2", "candidates": [], "reason": "synthetic reliable match"}]})
    try:
        identifier = manager.create(payload(template), owner_id="fast-local")
        result = wait_finished(manager, identifier)
        assert result["status"] == "ready" and result["stats"]["auto"] == 1
        assert not any(blocker.done() for blocker in blockers)
        stages = [event["stage"] for event in manager.ai_debug.snapshot()["events"] if event.get("job_id") == identifier]
        assert stages == ["run_started", "no_cases" if enabled else "disabled", "run_finished"]
    finally:
        release.set()
        manager.close()


@pytest.mark.parametrize("operation", ["_after_match_ai", "_rerun_ai"])
@pytest.mark.parametrize("transition", ["error", "cancelled", "new_token", "replacement", "removed"])
def test_late_ai_phase_cannot_restore_ready_over_a_newer_state(tmp_path, monkeypatch, operation, transition):
    manager, job = prepared(tmp_path, [""])
    replacement = None
    def changed(identifier):
        nonlocal replacement
        if transition in {"error", "cancelled"}:
            job["status"] = transition
        elif transition == "new_token":
            job["_operation_token"] = "newer-operation"
        elif transition == "replacement":
            replacement = copy.deepcopy(job)
            replacement.update(status="ready", error="replacement preserved")
            manager.jobs[identifier] = replacement
        else:
            del manager.jobs[identifier]
    monkeypatch.setattr(manager, "_review_ai", changed)
    try:
        getattr(manager, operation)("sample")
        if transition in {"error", "cancelled"}:
            assert job["status"] == transition
        elif transition == "new_token":
            assert job["status"] == "ai_review"
        elif transition == "replacement":
            assert manager.jobs["sample"] is replacement
            assert replacement["status"] == "ready" and replacement["error"] == "replacement preserved"
        else:
            assert "sample" not in manager.jobs
    finally:
        manager.close()


@pytest.mark.parametrize("operation", ["_after_match_ai", "_rerun_ai"])
def test_unexpected_ai_escape_becomes_error_without_ready_transition(tmp_path, monkeypatch, operation):
    manager, job = prepared(tmp_path, [""])
    observed = []
    original = manager._end_ai_operation
    def escaped(identifier):
        raise RuntimeError("synthetic unexpected AI escape")
    def end(identifier, expected, token, error=None):
        observed.append((job["status"], type(error).__name__))
        original(identifier, expected, token, error)
        observed.append((job["status"], None))
    monkeypatch.setattr(manager, "_review_ai", escaped)
    monkeypatch.setattr(manager, "_end_ai_operation", end)
    try:
        getattr(manager, operation)("sample")
        assert observed == [("ai_review", "RuntimeError"), ("error", None)]
        assert "synthetic unexpected" in job["error"]
    finally:
        manager.close()


def test_stale_worker_exception_callback_does_not_overwrite_new_operation(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    entered, release = threading.Event(), threading.Event()
    def cpu(identifier):
        manager._start_operation(identifier, "matching", "synthetic")
        entered.set()
        assert release.wait(5)
        raise RuntimeError("late old worker failure")
    monkeypatch.setattr(manager, "_process", cpu)
    try:
        with manager.lock:
            job["status"] = "queued"
            manager._submit(job, cpu)
        assert entered.wait(2)
        with manager.job_operation("sample"):
            job.update(_operation_token="newer-operation", status="ai_review", error=None)
        release.set()
        manager.pool.submit(lambda: None).result(timeout=3)
        assert job["status"] == "ai_review" and job["error"] is None
    finally:
        release.set()
        manager.close()
