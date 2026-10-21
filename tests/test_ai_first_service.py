"""AI-first service integration with artificial inputs and a mocked provider.

Local matcher results here are explicit test doubles, not algorithm evidence or
AI qualification. The real binding verifier, service queues, numbering, source
checks, private audit, workbook writer and download packager remain active.
"""
import copy
from dataclasses import dataclass
import json
from pathlib import Path
import threading
import time
import zipfile

import pytest

import hsd_tool.ai_first as first
import hsd_tool.matching as matching
from hsd_tool.service import JobManager, sha256
from hsd_tool.ai_usage import empty_usage
from test_ai_first import Opener, batch, payload
from test_service import simple_xlsx


@dataclass
class Scenario:
    manager: JobManager
    workbook: Path
    source: Path
    output: Path
    rows: list
    files: list
    events: list
    hints: list
    opener: Opener
    local_statuses: list
    before_match: object = None
    after_match: object = None

    def create(self):
        return self.manager.create({"workbook_path": str(self.workbook), "source_path": str(self.source),
                                    "output_root": str(self.output), "start_number": 7},
                                   owner_id="synthetic-employee", downloadable=True)


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    managers = []
    def build(count=2, *, statuses=None, enabled=True, numbers=None, response=None):
        directory = tmp_path / f"scenario-{len(managers)}"
        directory.mkdir()
        manager = JobManager(directory / "state")
        managers.append(manager)
        manager.ai_settings.save({"enabled": enabled, "api_key": "public-artificial-service-credential"})
        rows, files = batch(directory, count)
        for index, row in enumerate(rows):
            row["number"] = (numbers or [""] * count)[index]
        for file in files:
            file["relative_path"] = file["name"]
        workbook = directory / "synthetic.xlsx"
        simple_xlsx(workbook, [row["number"] for row in rows])
        source = directory / "synthetic.zip"
        with zipfile.ZipFile(source, "w") as archive:
            for file in files:
                archive.writestr(file["name"], Path(file["source_path"]).read_bytes())
        value = Scenario(manager, workbook, source, directory / "output", rows, files, [], [],
                         Opener(response), statuses or ["auto"] * count)
        transport = first.RetrievalClient
        monkeypatch.setattr(first, "RetrievalClient",
                            lambda key, attempts=1: transport(key, attempts=attempts, opener=value.opener))

        def inspect(path, image_directory):
            value.events.append("inspect")
            return {"rows": copy.deepcopy(rows), "sheet_name": "测试",
                    "reserved_numbers": [row["number"] for row in rows if row["number"]]}

        def prepare(source_path, input_rows, directory, progress=None):
            value.events.append("prepare")
            bindings = {str(Path(item["image_path"]).resolve()): sha256(item["image_path"]) for item in input_rows}
            for item in files:
                for field in ("preview_path", "source_path"):
                    bindings[str(Path(item[field]).resolve())] = sha256(item[field])
            return matching.PreparedMatching(copy.deepcopy(input_rows), copy.deepcopy(files), [], {}, {}, bindings)

        def result():
            return {"files": copy.deepcopy(files), "warnings": [], "matches": [
                {"row_id": row["id"], "status": status,
                 "file_id": files[index]["id"] if status == "auto" else None,
                 "reason": "Explicit artificial local matcher result", "reason_code": "synthetic_local_result",
                 "evidence": {"method": "features", "failed_checks": []},
                 "diagnostics": {"origin": "test_double_not_business_verification"},
                 "candidates": [{"file_id": files[index]["id"], "score": .95}]}
                for index, (row, status) in enumerate(zip(rows, value.local_statuses))]}

        def verify(prepared, progress=None, *, proposals=None, **kwargs):
            value.events.append("verify")
            value.hints.append(copy.deepcopy(proposals or {}))
            if value.before_match is not None:
                value.before_match(prepared)
            matching._verify_prepared_bindings(prepared)
            matched = result()
            if value.after_match is not None:
                value.after_match(prepared)
            matching._verify_prepared_bindings(prepared)
            return matched

        def local(*args, **kwargs):
            value.events.append("legacy-local")
            return result()

        monkeypatch.setattr("hsd_tool.workbook.inspect_workbook", inspect)
        monkeypatch.setattr(matching, "prepare_matching", prepare)
        monkeypatch.setattr(matching, "match_prepared", verify)
        monkeypatch.setattr(matching, "scan_and_match", local)
        monkeypatch.setattr(manager, "_review_ai", lambda identifier: value.events.append("legacy-pair-review"))
        return value

    yield build
    for manager in managers:
        manager.close()


def idle(manager, identifier, *, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with manager.lock:
            job = manager.jobs[identifier]
            if job["status"] in {"ready", "error", "done"} and not manager._inflight_futures:
                return job
        time.sleep(.005)
    pytest.fail("Artificial service flow did not settle")


def test_preparation_budget_keeps_complete_local_results_without_provider_calls(scenario, monkeypatch):
    value = scenario(count=2)
    monkeypatch.setattr(first, 'MAX_PREPARED_IMAGE_BYTES', 1)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job['status'] == 'ready' and job['stats']['auto'] == 2
    assert job['ai_retrieval']['error_code'] == 'resource_limit'
    assert not value.opener.calls and job['ai_retrieval']['usage']['requests'] == 0
    assert any('内存预算' in warning for warning in job['warnings'])
    assert 'verify' in value.events


def test_enabled_private_capability_routes_prepare_retrieve_then_independent_cpu_verification(scenario):
    value = scenario(count=1)
    assert value.manager.ai_settings.runtime()["matching_workflow"] == "ai_first"
    assert "matching_workflow" not in value.manager.ai_settings.snapshot()
    def response(request, body):
        value.events.append("provider")
        return payload(body)
    value.opener.outcome = response
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert value.events[:2] == ["inspect", "prepare"]
    assert sorted(value.events[2:]) == ["provider", "verify"]
    assert job["status"] == "ready" and job["matching_mode"] == "ai_first"
    assert job["stats"]["auto"] == 1 and job["stats"]["ai_auto"] == 0
    assert job["rows"][0]["planned_number"] == "HSD0007"
    assert job["rows"][0]["reason_code"] == "synthetic_local_result"
    assert job["rows"][0]["ai_retrieval"]["outcome"] == "suggestion"
    assert "_ai_envelope" not in job["rows"][0] and "_accepted_by" not in job["rows"][0]
    assert job["ai_retrieval"]["usage"]["requests"] == value.manager.ai_usage.snapshot()["requests"] == 1
    assert value.manager.ai_validation.load() == {}
    assert value.hints == [{}]  # Local proof runs independently of model order.
    records = list(value.manager.record_directory(identifier, "ai_first_runs").glob("ai_first_*.json"))
    assert len(records) == 1
    artifact = json.loads(records[0].read_text("utf-8"))
    assert artifact["status"] == "completed" and artifact["automatic_passes"] == 0
    assert not artifact["qualification_granted"]


def test_disabled_ai_keeps_original_local_flow_without_any_retrieval_request(scenario):
    value = scenario(count=1, enabled=False)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert value.events == ["inspect", "legacy-local", "legacy-pair-review"]
    assert job["matching_mode"] == "local" and job["stats"]["auto"] == 1
    assert "ai_retrieval" not in job and value.opener.calls == []
    assert value.manager.ai_usage.snapshot()["requests"] == 0


def test_model_same_cannot_turn_local_review_into_exportable_status(scenario):
    value = scenario(count=1, statuses=["review"])
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "ready" and job["rows"][0]["ai_retrieval"]["verdict"] == "same"
    assert job["stats"]["auto"] == job["stats"]["ai_auto"] == job["stats"]["exportable"] == 0
    assert job["stats"]["review"] == 1 and job["rows"][0]["planned_number"] == ""
    with pytest.raises(ValueError, match="还没有可导出"):
        value.manager.export(identifier)


def test_conflicting_model_hints_do_not_force_assignment_or_block_independent_local_proofs(scenario):
    value = scenario(count=2)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "ready" and job["stats"]["auto"] == 2
    assert value.hints == [{}]  # The provider deliberately chose one file twice.
    assert [row["file_id"] for row in job["rows"]] == ["f0001", "f0002"]
    assert all(row["ai_retrieval"]["reason_code"] == "retrieval_conflict" for row in job["rows"])
    assert job["_ai_first_result"]["ownership_conflicts"]


def test_wrong_model_proposal_does_not_replace_local_review_candidate_or_assign_numbers(scenario):
    value = scenario(count=2, statuses=["review", "review"])
    identifier = value.create()
    job = idle(value.manager, identifier)
    wrong = next(row for row in job["rows"] if row["ai_retrieval"]["candidate_id"] != row["candidates"][0]["file_id"])
    assert wrong["status"] == "review" and wrong["file_id"] is None and wrong["planned_number"] == ""
    assert wrong["candidates"][0]["file_id"] != wrong["ai_retrieval"]["candidate_id"]
    assert job["stats"]["review"] == 2 and job["stats"]["auto"] == 0


def test_invalid_model_response_falls_back_to_local_result_and_keeps_failed_attempt(scenario):
    def invalid(request, body):
        answer = payload(body)
        answer["choices"][0]["message"]["content"] = '{"matches": []}'
        return answer
    value = scenario(count=1, response=invalid)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "ready" and job["stats"]["auto"] == 1
    assert job["ai_retrieval"]["status"] == "failed" and value.hints == [{}]
    assert "ai_retrieval" not in job["rows"][0]
    attempt = job["_ai_first_runs"][0]["groups"][0]["attempt_history"][0]
    assert attempt["code"] == "invalid_decision" and attempt["usage"]["failures"] == 1
    assert value.manager.ai_usage.snapshot()["requests"] == job["ai_retrieval"]["usage"]["requests"] == 1


@pytest.mark.parametrize("target", ["workbook", "snapshot", "source_archive", "preview", "query", "ai_source"])
def test_changes_during_provider_wait_never_produce_ready_auto_results(scenario, target):
    value = scenario(count=1)
    def response(request, body):
        with value.manager.lock:
            job = next(iter(value.manager.jobs.values()))
            selected = {"workbook": value.workbook, "snapshot": Path(job["_snapshot_workbook"]),
                        "source_archive": value.source,
                        "preview": Path(value.files[0]["preview_path"]),
                        "query": Path(value.rows[0]["image_path"]),
                        "ai_source": Path(value.files[0]["source_path"])}[target]
        selected.write_bytes(b"synthetic changed input while provider was waiting")
        return payload(body)
    value.opener.outcome = response
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "error" and "变化" in job["error"]
    assert not job["stats"].get("exportable")
    assert value.manager.ai_usage.snapshot()["requests"] == 1
    with pytest.raises(ValueError, match="不能导出"):
        value.manager.export(identifier)
    artifacts = list(value.manager.record_directory(identifier, "ai_first_runs").glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text("utf-8"))
    assert artifact["groups"][0]["usage"]["requests"] == 1
    assert artifact["groups"][0]["decision"]["matches"]


def test_change_during_local_verification_is_checked_again_before_commit(scenario):
    value = scenario(count=1)
    value.after_match = lambda prepared: value.workbook.write_bytes(b"changed during local verification")
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "error" and "源表格发生变化" in job["error"]
    assert not job["stats"].get("exportable")


def test_late_ai_response_cannot_override_newer_revision_or_current_state(scenario):
    value = scenario(count=1)
    def response(request, body):
        with value.manager.lock:
            job = next(iter(value.manager.jobs.values()))
            job["revision"] += 1
            job.update(status="ready", progress={"message": "synthetic newer task state"})
            job["rows"][0]["manual_marker"] = "preserve newer choice"
        return payload(body)
    value.opener.outcome = response
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["revision"] == 1 and job["status"] == "ready"
    assert job["progress"]["message"] == "synthetic newer task state"
    assert job["rows"][0]["manual_marker"] == "preserve newer choice"
    assert "_ai_first_result" not in job and "_status" not in job["rows"][0]
    assert job["stats"] == {}
    assert value.manager.ai_usage.snapshot()["requests"] == 1
    artifact_path = next(value.manager.record_directory(identifier, "ai_first_runs").glob("*.json"))
    artifact = json.loads(artifact_path.read_text("utf-8"))
    assert artifact["status"] == "stale" and artifact["groups"][0]["status"] == "completed"


def test_late_cpu_result_cannot_restore_auto_over_newer_revision(scenario):
    value = scenario(count=1)
    def newer(prepared):
        with value.manager.lock:
            job = next(iter(value.manager.jobs.values()))
            job["revision"] += 1
            job.update(status="ready", progress={"message": "preserve later CPU-stage edit"})
            job["rows"][0]["manual_marker"] = "newer"
    value.after_match = newer
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["revision"] == 1 and job["progress"]["message"] == "preserve later CPU-stage edit"
    assert job["rows"][0]["manual_marker"] == "newer"
    assert "_status" not in job["rows"][0] and job["stats"] == {}


def test_close_waits_for_ai_to_cpu_handoff_and_keeps_private_retrieval_audit(scenario):
    value = scenario(count=1)
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    errors = []
    def response(request, body):
        entered.set()
        assert release.wait(5)
        return payload(body)
    value.opener.outcome = response
    identifier = value.create()
    assert entered.wait(5)
    job = value.manager.jobs[identifier]
    def closing():
        try:
            value.manager.close()
        except BaseException as error:
            errors.append(error)
        finally:
            closed.set()
    thread = threading.Thread(target=closing, daemon=True)
    thread.start()
    deadline = time.monotonic() + 2
    while not value.manager._closing and time.monotonic() < deadline:
        time.sleep(.005)
    assert value.manager._closing and not closed.is_set()
    release.set()
    assert closed.wait(5), "AI → CPU handoff must finish before executors close"
    thread.join(1)
    assert errors == [] and job["status"] == "ready" and "verify" in value.events
    assert job["stats"]["auto"] == 1 and value.manager.jobs == {}
    assert not value.manager._inflight_futures and value.manager._active_operations == 0
    records = value.manager.data_dir / "task_records" / identifier / "ai_first_runs"
    artifact = json.loads(next(records.glob("*.json")).read_text("utf-8"))
    assert artifact["status"] == "completed" and artifact["usage"]["requests"] == 1


def test_real_barrier_proves_api_wait_and_cpu_verification_execute_concurrently(scenario):
    value = scenario(count=1)
    barrier = threading.Barrier(2)
    crossed = []
    def local(prepared):
        barrier.wait(timeout=3)
        crossed.append("cpu")
    def response(request, body):
        barrier.wait(timeout=3)
        crossed.append("api")
        return payload(body)
    value.before_match = local
    value.opener.outcome = response
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "ready", job["error"]
    assert sorted(crossed) == ["api", "cpu"] and job["stats"]["auto"] == 1
    assert value.hints == [{}]


def test_cpu_failure_cannot_be_replaced_by_successful_model_same(scenario):
    value = scenario(count=1)
    barrier = threading.Barrier(2)
    def local(prepared):
        barrier.wait(timeout=3)
        raise ValueError("synthetic CPU verification failure")
    def response(request, body):
        barrier.wait(timeout=3)
        return payload(body)
    value.before_match = local
    value.opener.outcome = response
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "error" and "CPU verification failure" in job["error"]
    assert not job["stats"].get("exportable") and "_status" not in job["rows"][0]
    assert value.manager.ai_usage.snapshot()["requests"] == 1
    with pytest.raises(ValueError, match="不能导出"):
        value.manager.export(identifier)


@pytest.mark.parametrize("target", ["preview", "workbook", "source_archive"])
def test_join_rechecks_inputs_after_cpu_finished_while_api_was_still_waiting(scenario, target):
    value = scenario(count=1)
    def response(request, body):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with value.manager.lock:
                job = next(iter(value.manager.jobs.values()))
                finished = job.get("_cpu_leg", {}).get("state") == "finished"
            if finished:
                break
            time.sleep(.005)
        assert finished, "CPU must already have completed its two source checks"
        selected = {"preview": Path(value.files[0]["preview_path"]),
                    "workbook": value.workbook, "source_archive": value.source}[target]
        selected.write_bytes(b"synthetic input edit after CPU proof completed")
        return payload(body)
    value.opener.outcome = response
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "error" and "变化" in job["error"]
    assert not job["stats"].get("exportable") and value.manager.ai_usage.snapshot()["requests"] == 1


def test_cpu_queue_counts_running_parallel_leg_once_for_other_employee_imports(scenario):
    value = scenario(count=1)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def local(prepared):
        calls.append("cpu")
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
    value.before_match = local
    first_id = value.create()
    assert entered.wait(3)
    second_id = value.create()
    third_id = value.create()
    try:
        first_job = value.manager.jobs[first_id]
        assert first_job["status"] == "ai_review" and first_job["_cpu_leg"]["state"] == "running"
        second = value.manager.snapshot(second_id)
        third = value.manager.snapshot(third_id)
        assert second["queue_stage"] == third["queue_stage"] == "cpu"
        assert second["queue_position"] == 2 and third["queue_position"] == 3
    finally:
        release.set()
    assert all(idle(value.manager, identifier)["status"] == "ready" for identifier in (first_id, second_id, third_id))


def test_close_drains_cpu_child_even_when_ai_has_already_returned(scenario):
    value = scenario(count=1)
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    errors = []
    def local(prepared):
        entered.set()
        assert release.wait(3)
    value.before_match = local
    identifier = value.create()
    assert entered.wait(3)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with value.manager.lock:
            job = value.manager.jobs[identifier]
            returned = "_ai_first_result" in job
        if returned:
            break
        time.sleep(.005)
    assert returned and job["status"] == "ai_review"
    def closing():
        try:
            value.manager.close()
        except BaseException as error:
            errors.append(error)
        finally:
            closed.set()
    thread = threading.Thread(target=closing, daemon=True)
    thread.start()
    deadline = time.monotonic() + 1
    while not value.manager._closing and time.monotonic() < deadline:
        time.sleep(.005)
    assert value.manager._closing and not closed.is_set()
    release.set()
    assert closed.wait(3)
    thread.join(1)
    assert errors == [] and job["status"] == "ready" and job["stats"]["auto"] == 1
    assert value.manager.jobs == {} and not value.manager._inflight_futures


def test_optional_pair_review_remains_available_and_does_not_mix_retrieval_usage(scenario, monkeypatch):
    value = scenario(count=1, statuses=["review"])
    identifier = value.create()
    job = idle(value.manager, identifier)
    snapshot = value.manager.snapshot(identifier)
    assert snapshot["ai_review"]["can_retry"]
    assert snapshot["ai_review"]["usage"]["requests"] == 0
    assert snapshot["ai_retrieval"]["usage"]["requests"] == 1
    retrieval_usage = copy.deepcopy(job["ai_retrieval"]["usage"])
    def pair_review(task_id):
        # Explicit fixture accounting; no provider request is made here.
        artificial_usage = empty_usage()
        artificial_usage.update(requests=2, successes=2)
        value.manager.ai_usage.add(artificial_usage)
        current_job = value.manager.jobs[task_id]
        current_job["ai_review"]["usage"] = artificial_usage
        current_job["_ai_runs"] = current_job.get("_ai_runs", 0) + 1
    monkeypatch.setattr(value.manager, "_review_ai", pair_review)
    value.manager.review_ai(identifier)
    job = idle(value.manager, identifier)
    assert job["status"] == "ready" and job["stats"]["review"] == 1
    assert job["ai_retrieval"]["usage"] == retrieval_usage
    assert job["ai_review"]["usage"]["requests"] == 2
    assert value.manager.ai_usage.snapshot()["requests"] == 3


def test_private_audit_write_failure_is_visible_without_retrying_paid_response(scenario, monkeypatch):
    value = scenario(count=1)
    original_mkstemp = first.tempfile.mkstemp
    def fail_record(*args, **kwargs):
        if kwargs.get("prefix") == ".ai-first-":
            raise OSError("synthetic private audit disk failure")
        return original_mkstemp(*args, **kwargs)
    monkeypatch.setattr(first.tempfile, "mkstemp", fail_record)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "ready" and job["stats"]["auto"] == 1
    warning = "候选检索记录未能完整保存，请保留本批任务并联系管理员。"
    assert warning in job["warnings"] and warning in value.manager.snapshot(identifier)["warnings"]
    assert len(value.opener.calls) == value.manager.ai_usage.snapshot()["requests"] == 1


def test_lifetime_usage_save_failure_is_visible_and_batch_usage_keeps_received_charge(scenario, monkeypatch):
    value = scenario(count=1)
    def fail_usage(incoming):
        raise OSError("synthetic lifetime ledger failure")
    monkeypatch.setattr(value.manager.ai_usage, "add", fail_usage)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "ready" and job["stats"]["auto"] == 1
    assert "候选检索累计用量保存未完成，费用可能不完整。" in job["warnings"]
    assert len(value.opener.calls) == job["ai_retrieval"]["usage"]["requests"] == 1
    assert job["ai_retrieval"]["usage"]["prompt_tokens"] == 30


def test_real_ledger_atomic_replace_failure_sets_visible_warning_without_losing_known_batch_charge(scenario, monkeypatch):
    value = scenario(count=1)
    original_replace = first.os.replace
    ledger_path = value.manager.ai_usage.path
    failures = []
    def fail_only_ledger(source, destination, *args, **kwargs):
        if Path(destination) == ledger_path:
            failures.append(True)
            raise OSError("synthetic ledger replace fault with untrusted local diagnostic")
        return original_replace(source, destination, *args, **kwargs)
    monkeypatch.setattr(first.os, "replace", fail_only_ledger)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert failures and value.manager.ai_usage.warning
    assert job["status"] == "ready" and job["stats"]["auto"] == 1
    assert "候选检索累计用量保存未完成，费用可能不完整。" in job["warnings"]
    assert not any("untrusted local diagnostic" in warning for warning in job["warnings"])
    usage = job["ai_retrieval"]["usage"]
    assert len(value.opener.calls) == usage["requests"] == 1
    assert usage["prompt_tokens"] == 30 and usage["completion_tokens"] == 10 and usage["estimated_usd"] > 0
    assert value.manager.ai_usage.snapshot()["requests"] == 1  # Unsaved increment is retained in memory.
    record = Path(job["_ai_first_result"]["record_path"])
    artifact = json.loads(record.read_text("utf-8"))
    assert artifact["usage"]["requests"] == 1
    assert "候选检索累计用量保存未完成，费用可能不完整。" in artifact["warnings"]


def test_checkpoint_failure_has_honest_visible_warning_without_claiming_persistence(scenario, monkeypatch):
    value = scenario(count=1)
    retrieve = first.retrieve
    def failing_checkpoint(*args, **kwargs):
        def fail(artifact):
            raise OSError("synthetic state callback failure")
        kwargs["checkpoint"] = fail
        return retrieve(*args, **kwargs)
    monkeypatch.setattr(first, "retrieve", failing_checkpoint)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "ready" and job["stats"]["auto"] == 1
    assert "候选检索状态更新未完成，请联系管理员核对记录。" in job["warnings"]
    assert not any("完整尝试仍保留" in warning for warning in job["warnings"])
    assert len(value.opener.calls) == value.manager.ai_usage.snapshot()["requests"] == 1


def test_untrusted_provider_warning_is_not_promoted_to_employee_warning(scenario, monkeypatch):
    value = scenario(count=1)
    def synthetic_retrieval(manager, identifier, rows, files, **kwargs):
        usage = empty_usage()
        artifact = {"source": "synthetic_test_double", "warnings": [
            "remote provider arbitrary warning containing private text", "unknown warning"]}
        return {"status": "failed", "proposals": [], "usage": usage,
                "artifact": artifact, "error_code": "review_unavailable"}
    monkeypatch.setattr(first, "retrieve", synthetic_retrieval)
    identifier = value.create()
    job = idle(value.manager, identifier)
    assert job["status"] == "ready" and job["stats"]["auto"] == 1
    assert not any("remote provider" in warning or "unknown warning" == warning for warning in job["warnings"])
    assert value.opener.calls == [] and value.manager.ai_usage.snapshot()["requests"] == 0


def test_export_zip_contains_only_numbered_ai_and_one_workbook_full_ai_audit_stays_private(scenario):
    value = scenario(count=1)
    input_hash = sha256(value.workbook)
    source_hash = sha256(value.source)
    identifier = value.create()
    job = idle(value.manager, identifier)
    value.manager.export(identifier, expected_revision=job["revision"])
    job = idle(value.manager, identifier)
    assert job["status"] == "done", job["error"]
    archive_path, archive_hash = value.manager.download_asset(identifier)
    assert sha256(archive_path) == archive_hash
    with zipfile.ZipFile(archive_path) as archive:
        names = ["/".join(Path(name).parts[1:]) for name in archive.namelist()]
        assert sorted(names) == ["synthetic_已编号.xlsx", "已编号AI/HSD0007.ai"]
        original_ai = Path(value.files[0]["source_path"]).read_bytes()
        ai_member = next(name for name in archive.namelist() if name.endswith("HSD0007.ai"))
        assert archive.read(ai_member) == original_ai
        workbook_member = next(name for name in archive.namelist() if name.endswith(".xlsx"))
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(archive.read(workbook_member))) as workbook:
            assert workbook.read("xl/media/preserve.bin") == b"picture-unchanged"
            assert b"HSD0007" in workbook.read("xl/worksheets/sheet1.xml")
    record_path = Path(job["_records_dir"]) / "处理记录.json"
    record = json.loads(record_path.read_text("utf-8"))
    assert record["matching_mode"] == "ai_first" and record["stats"]["ai_auto"] == 0
    assert record["ai_retrieval"]["usage"]["requests"] == 1
    assert record["ai_first_runs"][0]["groups"][0]["attempt_history"]
    assert record["decision_records"][0]["ai_retrieval"]["outcome"] == "suggestion"
    assert sha256(value.workbook) == input_hash and sha256(value.source) == source_hash
    record_digest = sha256(record_path)
    value.manager.close()
    assert record_path.exists() and sha256(record_path) == record_digest
