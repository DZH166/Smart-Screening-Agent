"""Service qualification-to-export checks, using local artificial data only.

The qualification fixture is unit-test data, not a live validation claim.  Its
signed record and mock API replies exist exclusively in pytest temporary paths.
"""
import json
from pathlib import Path

from PIL import Image
import pytest

from hsd_tool.ai_policy import CHECKS
from hsd_tool.ai_usage import empty_usage
from hsd_tool.service import sha256
from test_ai_policy import measured_evidence, validation_data, competition_for, alignment_for
from test_service import prepared, wait_export


@pytest.fixture
def qualified_batch(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, ["", "KEEP0023"], start=17)
    for index, (file, color) in enumerate(zip(job["files"], ("red", "blue")), 1):
        file["id"] = f"f{index:04}"
        Image.new("RGB", (240, 60), color).save(file["preview_path"])
        file["page_count"] = 1
        job["rows"][index - 1]["_file_id"] = file["id"]
    row = job["rows"][0]
    row.update(_status="review", _file_id=None, _reason="独特特征不足，需二次复核。",
               _reason_code="not_verified", evidence=measured_evidence(),
               candidates=[{"file_id": "f0001", "score": .92}, {"file_id": "f0002", "score": .65}])
    row["evidence"]["competition"] = competition_for(row, job["files"])
    row["evidence"]["alignment"] = alignment_for(row, job["files"])
    job.update(revision=0, timings={})
    manager._plan(job)
    labels, observations = validation_data()
    # The same tested builder and signature registry are used as production,
    # while the manifest is explicitly an artificial unit-test fixture.
    assert manager.ai_validation.activate(observations, labels)["qualified"]
    monkeypatch.setattr(manager.ai_settings, "runtime", lambda: {"enabled": True, "api_key": "unit-key-unused"})
    import hsd_tool.ai_workflow as workflow
    class Client:
        def __init__(self, key, **kwargs):
            pass
        def review(self, content):
            return {"model": "revision-verified", "request_id": "unit-service-unused-request",
                    "usage": {**empty_usage(), "requests": 1, "successes": 1, "prompt_tokens": 25},
                    "decision": {"verdict": "same", "candidate_id": "f0001", "reason": "原图全幅一致且候选唯一。",
                                 "checks": {key: True for key in CHECKS}, "differences": []}}
    monkeypatch.setattr(workflow, "DeepSeekClient", Client)
    try:
        yield manager, job
    finally:
        manager.close()


def run_ai(manager, job):
    from hsd_tool.ai_workflow import review_job
    review_job(manager, "sample")
    # The background caller owns the ready transition in the running app.
    job["status"] = "ready"


def test_qualified_positive_can_be_ai_auto_and_export_without_manual_confirmation(qualified_batch):
    manager, job = qualified_batch
    source_hashes = {file["id"]: sha256(file["source_path"]) for file in job["files"]}
    workbook_hash = sha256(job["_workbook_path"])
    run_ai(manager, job)
    row = job["rows"][0]
    assert row["status"] == "auto" and row["_accepted_by"] == "ai"
    assert job["stats"]["ai_auto"] == 1 and job["stats"]["review"] == 0
    assert row["planned_number"] == "HSD0017" and job["stats"]["confirmed"] == 0
    manager._plan(job)
    assert job["stats"]["ai_auto"] == 1  # effective state survives revalidation
    manager.export("sample", expected_revision=job["revision"])
    result = wait_export(manager)
    assert result["status"] == "done", result["error"]
    folder = Path(result["output_dir"])
    report = json.loads((Path(job["_records_dir"]) / "处理记录.json").read_text("utf-8"))
    assert report["stats"]["ai_auto"] == 1 and report["exported"] == 2 and report["new_numbers"] == 1
    assert report["mapping"][0]["confirmation"] == "AI复核通过"
    assert sorted(path.name for path in (folder / "已编号AI").iterdir()) == ["HSD0017.ai", "KEEP0023.ai"]
    assert sha256(job["_workbook_path"]) == workbook_hash
    assert all(sha256(file["source_path"]) == source_hashes[file["id"]] for file in job["files"])


@pytest.mark.parametrize("revoke", ["deleted", "tampered", "changed_implementation"])
def test_qualification_revocation_downgrades_ai_auto_during_plan_and_export(qualified_batch, monkeypatch, revoke):
    manager, job = qualified_batch
    run_ai(manager, job)
    assert job["stats"]["ai_auto"] == 1
    registry = manager.ai_validation
    if revoke == "deleted":
        registry.path.unlink()
    elif revoke == "tampered":
        payload = json.loads(registry.path.read_text("utf-8"))
        payload["record"]["categories"] = ["geometry_review"]
        registry.path.write_text(json.dumps(payload), "utf-8")
    else:
        monkeypatch.setattr(registry, "_implementation", lambda: {"unit": "changed"})
    manager._plan(job)
    row = job["rows"][0]
    assert row["status"] == "review" and row["file_id"] is None and row["planned_number"] == ""
    assert job["stats"]["ai_auto"] == 0 and job["stats"]["review"] == 1
    manager.export("sample")
    result = wait_export(manager)
    assert result["status"] == "done", result["error"]
    folder = Path(result["output_dir"])
    assert [path.name for path in (folder / "已编号AI").iterdir()] == ["KEEP0023.ai"]
    report = json.loads((Path(job["_records_dir"]) / "处理记录.json").read_text("utf-8"))
    assert report["pending"] == 1 and report["new_numbers"] == 0
    assert report["pending_rows"][0]["status"] == "review"


def test_profile_model_mismatch_cannot_promote_a_positive_reply(qualified_batch, monkeypatch):
    manager, job = qualified_batch
    original_load = manager.ai_validation.load
    monkeypatch.setattr(manager.ai_validation, "load", lambda: {**original_load(), "model": "different-revision"})
    run_ai(manager, job)
    assert job["rows"][0]["status"] == "review"
    assert job["rows"][0]["ai_review"]["reason_code"] == "validation_mismatch"
    assert job["stats"]["ai_auto"] == 0


def test_model_cannot_automatically_take_an_owned_alternative(qualified_batch, monkeypatch):
    import hsd_tool.ai_workflow as workflow
    manager, job = qualified_batch
    class AlternativeClient:
        def __init__(self, key, **kwargs):
            pass
        def review(self, content):
            return {"model": "revision-verified", "request_id": "unit-owned-alternative-request",
                    "usage": {**empty_usage(), "requests": 1, "successes": 1},
                    "decision": {"verdict": "same", "candidate_id": "f0002", "reason": "model proposes another candidate",
                                 "checks": {key: True for key in CHECKS}, "differences": []}}
    monkeypatch.setattr(workflow, "DeepSeekClient", AlternativeClient)
    run_ai(manager, job)
    assert job["ai_review"]["eligible"] == 1 and job["ai_review"]["reviewed"] == 1
    assert job["stats"]["ai_auto"] == 0 and job["rows"][0]["status"] == "review"
    assert job["rows"][0]["ai_review"]["reason_code"] == "candidate_change_requires_review"
    assert job["rows"][1]["status"] == "auto" and job["rows"][1]["file_id"] == "f0002"
    manager.export("sample")
    result = wait_export(manager)
    assert result["status"] == "done", result["error"]
    assert [path.name for path in (Path(result["output_dir"]) / "已编号AI").iterdir()] == ["KEEP0023.ai"]


def test_changed_preview_invalidates_previous_ai_auto_at_export(qualified_batch):
    manager, job = qualified_batch
    run_ai(manager, job)
    assert job["stats"]["ai_auto"] == 1
    Image.new("RGB", (240, 60), "orange").save(job["files"][0]["preview_path"])
    manager.export("sample")
    result = wait_export(manager)
    assert result["status"] == "done", result["error"]
    folder = Path(result["output_dir"])
    assert not (folder / "已编号AI" / "HSD0017.ai").exists()
    assert (folder / "已编号AI" / "KEEP0023.ai").exists()
    assert job["rows"][0]["reason_code"] == "stale_case"


def test_expired_qualification_removes_ai_export_permission(qualified_batch, monkeypatch):
    from datetime import datetime, timedelta
    import hsd_tool.ai_registry as registry_module
    manager, job = qualified_batch
    run_ai(manager, job)
    assert job["stats"]["ai_auto"] == 1
    class LaterClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=8)
    monkeypatch.setattr(registry_module, "datetime", LaterClock)
    manager._plan(job)
    assert job["stats"]["ai_auto"] == 0 and job["rows"][0]["status"] == "review"
    assert manager.ai_validation.snapshot()["mode"] == "evaluation"


def test_ai_auto_does_not_bypass_original_source_hash_check(qualified_batch):
    manager, job = qualified_batch
    run_ai(manager, job)
    assert job["stats"]["ai_auto"] == 1
    Path(job["files"][0]["source_path"]).write_bytes(b"original changed after AI review")
    manager.export("sample")
    result = wait_export(manager)
    assert result["status"] == "ready" and "发生了变化" in result["error"]
    output = Path(job["_output_root"])
    assert not output.exists() or not list(output.iterdir())
