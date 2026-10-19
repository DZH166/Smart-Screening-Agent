"""Durable review traces preserve every planned case and every retry run."""
import json
from pathlib import Path
import pytest
from PIL import Image

from hsd_tool.ai_client import ReviewError
from hsd_tool.ai_usage import empty_usage
from test_ai_integration_audit import model_answer, workflow_manager
from test_ai_service import qualified_batch, run_ai
from test_service import wait_export


def test_review_checkpoints_planned_cases_before_io_and_completed_cases_between_calls(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = workflow_manager(tmp_path, monkeypatch)
    observed = []

    class Client:
        def __init__(self, key):
            self.count = 0

        def review(self, content):
            self.count += 1
            paths = list(Path(job["_ai_records_dir"]).glob("ai_observations_*.json"))
            assert len(paths) == 1
            observed.append(json.loads(paths[0].read_text("utf-8")))
            return model_answer(f"f{self.count:04}")

    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        workflow.review_job(manager, "audit")
        assert len(observed) == 2
        assert observed[0]["planned_case_ids"] == ["r2", "r3"]
        assert [case["error"] for case in observed[0]["cases"]] == ["not_called_yet"] * 2
        assert observed[1]["cases"][0]["decision"]["verdict"] == "same"
        assert observed[1]["cases"][1]["error"] == "not_called_yet"
        artifact = job["_ai_observation_runs"][0]
        assert artifact is job["_ai_observation_artifact"]
        assert all("error" not in case for case in artifact["cases"])
    finally:
        manager.close()


def test_retry_does_not_discard_failed_run_or_circuit_break_skips(tmp_path, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = workflow_manager(tmp_path, monkeypatch)

    class FailedClient:
        def __init__(self, key):
            pass

        def review(self, content):
            raise ReviewError("authentication", "测试接口无权限", {
                **empty_usage(), "requests": 1, "failures": 1, "unknown_usage_requests": 1})

    class WorkingClient:
        def __init__(self, key):
            self.count = 0

        def review(self, content):
            self.count += 1
            return model_answer(f"f{self.count:04}")

    try:
        monkeypatch.setattr(workflow, "DeepSeekClient", FailedClient)
        workflow.review_job(manager, "audit")
        first = json.loads(json.dumps(job["_ai_observation_artifact"]))
        assert [case["error"] for case in first["cases"]] == [
            "authentication", "not_called_after_authentication"]
        monkeypatch.setattr(workflow, "DeepSeekClient", WorkingClient)
        workflow.review_job(manager, "audit")
        assert len(job["_ai_observation_runs"]) == 2
        assert job["_ai_observation_runs"][0] == first
        assert job["_ai_observation_runs"][1]["run_id"] != first["run_id"]
        assert len(list(Path(job["_ai_records_dir"]).glob("ai_observations_*.json"))) == 2
        assert job["ai_review"]["usage"]["requests"] == 3
        assert job["ai_review"]["usage"]["cost_incomplete"]
    finally:
        manager.close()


def test_export_preserves_failed_run_and_successful_retry(qualified_batch, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = qualified_batch
    working_client = workflow.DeepSeekClient

    class FailedClient:
        def __init__(self, key):
            pass

        def review(self, content):
            raise ReviewError("authentication", "测试接口无权限", {
                **empty_usage(), "requests": 1, "failures": 1,
                "unknown_usage_requests": 1})

    monkeypatch.setattr(workflow, "DeepSeekClient", FailedClient)
    run_ai(manager, job)
    monkeypatch.setattr(workflow, "DeepSeekClient", working_client)
    run_ai(manager, job)
    assert job["stats"]["ai_auto"] == 1
    manager.export("sample", expected_revision=job["revision"])
    exported = wait_export(manager)
    assert exported["status"] == "done", exported["error"]
    report = json.loads((Path(job["_records_dir"]) / "处理记录.json").read_text("utf-8"))
    runs = report["ai_observation_runs"]
    assert len(runs) == 2 and runs[0]["run_id"] != runs[1]["run_id"]
    assert runs[0]["cases"][0]["error"] == "authentication"
    assert runs[1]["cases"][0]["decision"]["verdict"] == "same"
    assert report["ai_review"]["usage"]["unknown_usage_requests"] == 1


def test_changed_unexported_rival_source_invalidates_ai_export(qualified_batch):
    manager, job = qualified_batch
    manager.resolve("sample", "r3", None)
    run_ai(manager, job)
    assert job["stats"]["ai_auto"] == 1
    Path(job["files"][1]["source_path"]).write_bytes(b"changed unexported comparison original")
    manager.export("sample", expected_revision=job["revision"])
    result = wait_export(manager)
    assert result["status"] == "ready"
    assert "原文件发生了变化" in result["error"]
    assert result["output_dir"] is None


@pytest.mark.parametrize("change", ["top_preview", "unexported_rival_preview", "qualification"])
def test_ai_proof_changes_during_export_abort_staged_output(qualified_batch, monkeypatch, change):
    import hsd_tool.workbook as workbook
    manager, job = qualified_batch
    manager.resolve("sample", "r3", None)
    run_ai(manager, job)
    assert job["stats"]["ai_auto"] == 1
    original_write = workbook.write_numbered_workbook

    def change_during_export(*args):
        original_write(*args)
        if change == "qualification":
            manager.ai_validation.path.unlink()
        else:
            index = 0 if change == "top_preview" else 1
            Image.new("RGB", (240, 60), "orange").save(job["files"][index]["preview_path"])

    monkeypatch.setattr(workbook, "write_numbered_workbook", change_during_export)
    manager.export("sample", expected_revision=job["revision"])
    result = wait_export(manager)
    assert result["status"] == "ready" and result["error"]
    assert result["output_dir"] is None
    output = Path(job["_output_root"])
    assert not output.exists() or not list(output.iterdir())


@pytest.mark.parametrize("change", ["modified", "deleted", "implementation"])
def test_changed_input_during_request_is_not_clean_validation_evidence(qualified_batch, monkeypatch, change):
    import hsd_tool.ai_workflow as workflow
    manager, job = qualified_batch
    original_client = workflow.DeepSeekClient

    class ChangesSource(original_client):
        def review(self, content):
            reply = super().review(content)
            if change == "implementation":
                signatures = dict(workflow.ValidationRegistry._implementation())
                signatures["matching"] = "0" * 64
                monkeypatch.setattr(workflow.ValidationRegistry, "_implementation", staticmethod(lambda: signatures))
            else:
                source = Path(job["files"][1 if change == "deleted" else 0]["source_path"])
                if change == "deleted":
                    source.unlink()
                else:
                    source.write_bytes(b"changed during actual comparison")
            return reply

    monkeypatch.setattr(workflow, "DeepSeekClient", ChangesSource)
    run_ai(manager, job)
    observation = job["_ai_observation_artifact"]["cases"][0]
    assert observation["decision"]["verdict"] == "same"
    assert observation["usage"]["requests"] == 1
    assert observation["error"] == "case_invalidated_after_request"
    assert observation["validation_eligible"] is False
    assert job["rows"][0]["reason_code"] != "ai_validated_identity"
    assert job["stats"]["ai_auto"] == 0
