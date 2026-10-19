"""Controlled AI case overlap, using artificial local data and no provider IO."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
import shutil
import uuid

from PIL import Image

from hsd_tool.ai_client import ReviewError
from hsd_tool.ai_key_pool import ApiKeyPool, KeyPoolUnavailable
from hsd_tool.ai_settings import AiSettings
from hsd_tool.ai_usage import empty_usage
from hsd_tool.service import sha256
from test_ai_integration_audit import model_answer, workflow_manager


def synthetic_batch(tmp_path, monkeypatch, count=3):
    manager, job = workflow_manager(tmp_path, monkeypatch)
    for index, color in enumerate(("green", "yellow", "purple", "orange"), 3):
        if len(job["rows"]) >= count:
            break
        work = Path(job["_work_dir"])
        preview, query, source = [work / f"{kind}-{index}.{suffix}" for kind, suffix in
                                  (("preview", "png"), ("query", "png"), ("source", "ai"))]
        Image.new("RGB", (240, 60), color).save(preview)
        Image.new("RGB", (480, 120), color).save(query)
        source.write_bytes(f"synthetic independent source {index}".encode())
        identity = f"f{index:04}"
        job["files"].append({"id": identity, "preview_path": str(preview), "source_path": str(source),
                             "source_sha256": sha256(source), "page_count": 1, "issue": None})
        job["rows"].append({"id": f"r{index+1}", "row_number": index+1, "number": "", "issue": None,
                           "image_path": str(query), "_status": "review", "_file_id": None,
                           "_reason": "合成并发测试", "candidates": [{"file_id": identity, "score": .9}],
                           "evidence": dict(job["rows"][0]["evidence"])})
    manager.ai_settings = AiSettings(tmp_path / "isolated-settings", protector=None, environ={})
    manager.ai_settings.save_pool({"expected_revision": 0, "add": [
        {"api_key": "sk-parallel-artificial-key-a"}, {"api_key": "sk-parallel-artificial-key-b"}]})
    manager.ai_settings.save({"enabled": True})
    manager.ai_key_pool = ApiKeyPool(manager.ai_settings)
    manager._plan(job)
    return manager, job


def identity(content):
    return json.loads(content[0]["text"])["candidate_ids"][0]


def test_independent_cases_overlap_two_and_commit_stable_case_order(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = synthetic_batch(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    state = {"active": 0, "peak": 0, "calls": [], "returned": []}

    class Client:
        def __init__(self, key):
            pass
        def review(self, content):
            candidate = identity(content)
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
                state["calls"].append(candidate)
            if candidate in {"f0001", "f0002"}:
                barrier.wait(timeout=3)
            if candidate == "f0001":
                time.sleep(.03)
            with lock:
                state["active"] -= 1
                state["returned"].append(candidate)
            return model_answer(candidate)

    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        workflow.review_job(manager, "audit")
        assert state["peak"] == 2
        assert state["returned"].index("f0002") < state["returned"].index("f0001")
        assert job["_ai_observation_artifact"]["planned_case_ids"] == ["r2", "r3", "r4"]
        assert [item["decision"]["candidate_id"] for item in job["_ai_observations"]] == ["f0001", "f0002", "f0003"]
        assert manager.ai_usage.snapshot()["requests"] == manager.ai_key_pool.snapshot()["usage"]["requests"] == 3
        assert job["ai_review"]["usage"]["requests"] == 3
        assert job["stats"]["ai_auto"] == 0 and job["stats"]["review"] == 3
        assert manager.ai_debug.snapshot()["active"] == []
        assert manager.ai_debug.snapshot()["events"][-1]["stage"] == "run_finished"
    finally:
        manager.close()


def test_shared_candidate_cases_are_not_run_in_parallel(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = synthetic_batch(tmp_path, monkeypatch, count=2)
    job["rows"][0]["candidates"].append({"file_id": "f0002", "score": .65})
    state = {"active": 0, "peak": 0}
    lock = threading.Lock()

    class Client:
        def __init__(self, key):
            pass
        def review(self, content):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(.02)
            with lock:
                state["active"] -= 1
            return model_answer(identity(content))

    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        workflow.review_job(manager, "audit")
        assert state["peak"] == 1
        assert job["ai_review"]["reviewed"] == 2
    finally:
        manager.close()


def test_late_reply_cannot_overwrite_changed_revision_or_user_choice(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = synthetic_batch(tmp_path, monkeypatch, count=2)
    manager.ai_case_workers = 1
    calls = []

    class Client:
        def __init__(self, key):
            pass
        def review(self, content):
            calls.append(identity(content))
            with manager.job_operation("audit"), manager.lock:
                row = job["rows"][0]
                row.update(_status="skipped", status="skipped", _file_id=None,
                           _reason="员工已跳过", _accepted_by="human")
                job["revision"] += 1
                job["status"] = "ready"
            return model_answer(identity(content))

    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        workflow.review_job(manager, "audit")
        row = job["rows"][0]
        assert row["_status"] == "skipped" and row["_accepted_by"] == "human"
        assert row.get("ai_review") is None
        assert calls == ["f0001"]
        assert job["revision"] == 1 and job["status"] == "ready"
        assert job["_ai_observations"][0]["error"] == "case_invalidated_after_request"
        assert job["_ai_observations"][0]["validation_eligible"] is False
        assert manager.ai_usage.snapshot()["requests"] == 1
        assert manager.ai_debug.snapshot()["active"] == []
    finally:
        manager.close()


def test_rate_limit_drains_started_case_and_prevents_other_key_escape(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = synthetic_batch(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)
    limited = threading.Event()
    calls = []
    lock = threading.Lock()

    class Client:
        def __init__(self, key):
            pass
        def review(self, content):
            candidate = identity(content)
            with lock:
                calls.append(candidate)
            barrier.wait(timeout=3)
            if candidate == "f0001":
                limited.set()
                raise ReviewError("rate_limit", "合成限流", {**empty_usage(), "requests": 1, "failures": 1})
            assert limited.wait(timeout=3)
            time.sleep(.02)
            return model_answer(candidate)

    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        workflow.review_job(manager, "audit")
        assert set(calls) == {"f0001", "f0002"}
        assert job["_ai_observations"][0]["error"] == "rate_limit"
        assert job["_ai_observations"][1]["decision"]["verdict"] == "same"
        assert job["_ai_observations"][2]["error"] == "not_called_after_rate_limit"
        assert job["ai_review"]["usage"]["requests"] == 2
        assert manager.ai_usage.snapshot()["requests"] == 2
        assert manager.ai_key_pool.snapshot()["cooldown_seconds"] > 0
        try:
            manager.ai_key_pool.acquire()
            raise AssertionError("another key must not escape shared account cooldown")
        except KeyPoolUnavailable:
            pass
        assert manager.ai_debug.snapshot()["events"][-1]["stage"] == "run_finished"
        assert manager.ai_debug.snapshot()["active"] == []
    finally:
        manager.close()


def test_coordinator_failure_preserves_all_started_charges_and_checkpoints(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = synthetic_batch(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)
    class Client:
        def __init__(self, key):
            pass
        def review(self, content):
            barrier.wait(timeout=3)
            return model_answer(identity(content))
    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    original = manager._plan
    count = [0]
    def failing_plan(value):
        count[0] += 1
        if count[0] == 2:
            raise RuntimeError("synthetic local coordinator fault")
        return original(value)
    monkeypatch.setattr(manager, "_plan", failing_plan)
    try:
        try:
            workflow.review_job(manager, "audit")
        except RuntimeError:
            pass
        assert manager.ai_usage.snapshot()["requests"] == 2
        assert manager.ai_key_pool.snapshot()["usage"]["requests"] == 2
        assert job["ai_review"]["usage"]["requests"] == 2
        artifact = json.loads(next(Path(job["_ai_records_dir"]).glob("ai_observations_*.json")).read_text("utf-8"))
        assert len(artifact["cases"]) == 3
        assert all(item.get("error") != "not_called_yet" for item in artifact["cases"])
        assert sum(item.get("usage", {}).get("requests", 0) for item in artifact["cases"]) == 2
        assert manager.ai_debug.snapshot()["active"] == []
    finally:
        manager.close()


def test_two_employee_batches_share_global_two_slots_and_queued_batch_gets_a_turn(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir(); second_dir.mkdir()
    manager, first = synthetic_batch(first_dir, monkeypatch, count=3)
    second_manager, second = synthetic_batch(second_dir, monkeypatch, count=2)
    second_manager.close()
    second["id"] = "audit-two"
    manager.jobs["audit-two"] = second
    original_content = workflow.prepare_content
    def marked_content(case, row, files):
        # An explicit artificial marker only for this fake-client scheduling
        # test; production preparation and protocol are not modified.
        tag = "B" if str(second_dir) in row["image_path"] else "A"
        return original_content(case, row, files) + [{"type": "text", "text": "synthetic-batch-" + tag}]
    monkeypatch.setattr(workflow, "prepare_content", marked_content)
    first_pair_started, release = threading.Event(), threading.Event()
    lock = threading.Lock()
    state = {"active": 0, "peak": 0, "calls": []}
    class Client:
        def __init__(self, key):
            pass
        def review(self, content):
            tag = content[-1]["text"][-1]
            candidate = identity(content)
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
                state["calls"].append((tag, candidate))
                if len(state["calls"]) == 2:
                    first_pair_started.set()
            if tag == "A" and candidate in {"f0001", "f0002"}:
                assert release.wait(timeout=4)
            with lock:
                state["active"] -= 1
            return model_answer(candidate)
    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        with ThreadPoolExecutor(max_workers=2) as batches:
            a = batches.submit(workflow.review_job, manager, "audit")
            assert first_pair_started.wait(timeout=3)
            b = batches.submit(workflow.review_job, manager, "audit-two")
            deadline = time.monotonic() + 3
            while manager.ai_case_pool._work_queue.qsize() < 2 and time.monotonic() < deadline:
                time.sleep(.005)
            assert manager.ai_case_pool._work_queue.qsize() >= 2
            release.set()
            a.result(timeout=5); b.result(timeout=5)
        assert state["peak"] == 2
        assert state["calls"].index(("B", "f0001")) < state["calls"].index(("A", "f0003"))
        assert manager.ai_usage.snapshot()["requests"] == 5
        assert first["ai_review"]["usage"]["requests"] == 3
        assert second["ai_review"]["usage"]["requests"] == 2
        assert manager.ai_key_pool.snapshot()["usage"]["requests"] == 5
        assert manager.ai_debug.snapshot()["active"] == []
    finally:
        release.set()
        manager.close()


def test_attempt_failures_are_checkpointed_before_retry_and_retained_in_artifact(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    from hsd_tool.ai_client import DeepSeekClient
    from test_ai_client import DECISION, Opener, http_error, response
    manager, job = synthetic_batch(tmp_path, monkeypatch, count=2)
    manager.ai_case_workers = 1
    # First case: 401 then success on the second key. Second: 503 then success
    # on the same remaining key. All transport responses are artificial.
    transport = Opener([http_error(401), response(), http_error(503), response({**DECISION, "candidate_id": "f0002"})])
    inspected = []
    def pause(_):
        artifact = json.loads(next(Path(job["_ai_records_dir"]).glob("ai_observations_*.json")).read_text("utf-8"))
        inspected.append(artifact)
    def factory(key):
        return DeepSeekClient(key, opener=transport, sleeper=lambda _: None)
    monkeypatch.setattr(workflow, "DeepSeekClient", factory)
    import hsd_tool.ai_dispatch as dispatch
    original_init = dispatch.ManagedReviewClient.__init__
    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.sleep = pause
    monkeypatch.setattr(dispatch.ManagedReviewClient, "__init__", init)
    try:
        workflow.review_job(manager, "audit")
        histories = [item["attempt_history"] for item in job["_ai_observations"]]
        assert [[attempt["code"] for attempt in history] for history in histories] == [
            ["authentication", "ok"], ["provider_error", "ok"]]
        assert inspected[0]["cases"][0]["attempt_history"][0]["code"] == "authentication"
        assert inspected[1]["cases"][1]["attempt_history"][0]["code"] == "provider_error"
        assert manager.ai_usage.snapshot()["requests"] == job["ai_review"]["usage"]["requests"] == 4
        assert manager.ai_key_pool.snapshot()["usage"]["requests"] == 4
        assert job["ai_review"]["usage"]["unknown_usage_requests"] == 1
        serialized = json.dumps(job["_ai_observation_artifact"])
        assert "sk-parallel-artificial" not in serialized
        assert "Authorization" not in serialized
    finally:
        manager.close()


def test_private_attempt_history_survives_close_and_cache_cleanup_without_previews_or_secrets(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = synthetic_batch(tmp_path, monkeypatch, count=2)
    original_work = Path(job["_work_dir"])
    identifier = uuid.uuid4().hex
    cache_work = manager.data_dir / "jobs" / identifier
    cache_work.parent.mkdir(exist_ok=True)
    shutil.move(str(original_work), str(cache_work))
    (cache_work / ".hsd-job").write_text(identifier, "ascii")
    job["id"], job["_work_dir"] = identifier, str(cache_work)
    for file in job["files"]:
        for name in ("source_path", "preview_path"):
            file[name] = str(cache_work / Path(file[name]).name)
    for row in job["rows"]:
        row["image_path"] = str(cache_work / Path(row["image_path"]).name)
    manager.jobs = {identifier: job}
    class Client:
        def __init__(self, key):
            pass
        def review(self, content):
            return model_answer(identity(content))
    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    workflow.review_job(manager, identifier)
    records = Path(job["_ai_records_dir"])
    assert records == manager.data_dir / "task_records" / identifier / "ai_runs"
    manager.close()
    assert not cache_work.exists()
    artifacts = list(records.glob("ai_observations_*.json"))
    assert len(artifacts) == 1
    text = artifacts[0].read_text("utf-8")
    artifact = json.loads(text)
    assert len(artifact["planned_case_ids"]) == 2
    assert all(item["attempt_history"][0]["code"] == "ok" for item in artifact["cases"])
    assert "sk-parallel-artificial" not in text
    assert "data:image" not in text and "iVBORw0" not in text
    def strings(value):
        if isinstance(value, dict):
            return [item for child in value.values() for item in strings(child)]
        if isinstance(value, list):
            return [item for child in value for item in strings(child)]
        return [value] if isinstance(value, str) else []
    assert not any(str(manager.data_dir).casefold() in value.casefold() for value in strings(artifact))
    assert "source_path" not in text and "preview_path" not in text
