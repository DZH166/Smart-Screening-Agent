"""Batch employee decisions are atomic; they never grant AI qualification."""
import copy
from pathlib import Path

import pytest

from test_service import prepared


def reviewing(tmp_path, numbers=None, start=1):
    manager, job = prepared(tmp_path, numbers or ["", "", ""], start)
    for row in job["rows"]:
        row.update(_status="review", _file_id=None, candidates=[{"file_id": "f" + row["id"][1:], "score": .9}])
    manager._plan(job)
    return manager, job


def selection(*indices):
    return [{"row_id": f"r{i}", "file_id": f"f{i}"} for i in indices]


def test_batch_confirms_as_human_and_undo_restores_group(tmp_path):
    manager, job = reviewing(tmp_path)
    try:
        result = manager.resolve_batch("sample", selection(2, 3))
        assert result["stats"]["confirmed"] == 2
        assert result["stats"]["auto"] == result["stats"]["ai_auto"] == 0
        assert [r["planned_number"] for r in result["rows"]] == ["HSD0001", "HSD0002", ""]
        assert all(r["_accepted_by"] == "human" for r in job["rows"][:2])
        assert len(job["_history"]) == 1 and result["revision"] == 1
        result = manager.undo("sample")
        assert result["stats"]["confirmed"] == 0 and result["stats"]["review"] == 3
        assert result["last_undone_count"] == 2 and result["revision"] == 2
    finally:
        manager.close()


@pytest.mark.parametrize("invalid", [[], {}, [None], [{"row_id": "r2"}],
    selection(2, 2), [{"row_id": "r2", "file_id": "f2"}, {"row_id": "r3", "file_id": "f2"}], selection(2, 99)])
def test_invalid_group_does_not_partially_confirm(tmp_path, invalid):
    manager, job = reviewing(tmp_path)
    try:
        before = copy.deepcopy(job["rows"])
        with pytest.raises(ValueError):
            manager.resolve_batch("sample", invalid)
        assert job["rows"] == before and not job.get("_history") and not job.get("revision")
    finally:
        manager.close()


@pytest.mark.parametrize("problem", ["duplicate_preview", "ownership_conflict", "source_issue", "incomplete_candidate_validation"])
def test_hard_anomaly_requires_individual_review(tmp_path, problem):
    manager, job = reviewing(tmp_path)
    try:
        job["rows"][1]["evidence"] = {"failed_checks": [problem]}
        with pytest.raises(ValueError, match="单独"):
            manager.resolve_batch("sample", selection(2, 3))
        assert job["stats"]["confirmed"] == 0
        assert not manager.snapshot("sample")["rows"][1]["bulk_confirm_eligible"]
    finally:
        manager.close()


@pytest.mark.parametrize("numbers,start", [(["DUP", "dup", ""], 1), (["", "", ""], 9999)])
def test_number_conflicts_rollback_entire_group(tmp_path, numbers, start):
    manager, job = reviewing(tmp_path, numbers, start)
    try:
        with pytest.raises(ValueError, match="冲突"):
            manager.resolve_batch("sample", selection(2, 3))
        assert job["stats"]["confirmed"] == 0
    finally:
        manager.close()


def test_existing_assignment_and_changed_source_are_not_bypassed(tmp_path):
    manager, job = reviewing(tmp_path)
    try:
        manager.resolve("sample", "r4", "f2")
        with pytest.raises(ValueError, match="使用"):
            manager.resolve_batch("sample", selection(2, 3))
        manager.resolve("sample", "r4", None)
        Path(job["files"][1]["source_path"]).write_bytes(b"changed")
        with pytest.raises(ValueError, match="变化"):
            manager.resolve_batch("sample", selection(2, 3))
        assert job["stats"]["confirmed"] == 0
    finally:
        manager.close()


def test_batch_preserves_existing_number_and_later_single_undo(tmp_path):
    manager, job = reviewing(tmp_path, ["OLD01", "", ""])
    try:
        manager.resolve_batch("sample", selection(2, 3))
        manager.resolve("sample", "r4", None)
        assert manager.undo("sample")["stats"]["confirmed"] == 2
        assert job["rows"][0]["planned_number"] == "OLD01"
        assert manager.undo("sample")["stats"]["confirmed"] == 0
    finally:
        manager.close()


@pytest.mark.parametrize("revision", [None, True, 0.0, "0", -1])
def test_local_batch_cannot_omit_integer_revision(tmp_path, revision):
    from hsd_tool.server import create_app
    app = create_app(tmp_path / "app", token="synthetic-token")
    manager, job = reviewing(tmp_path)
    try:
        app.config["HSD_MANAGER"].jobs["sample"] = job
        response = app.test_client().post("/api/jobs/sample/resolve-batch", base_url="http://127.0.0.1",
            headers={"X-HSD-Token": "synthetic-token"}, json={"expected_revision": revision, "items": selection(2, 3)})
        assert response.status_code == 409
        assert job["stats"]["confirmed"] == 0
    finally:
        manager.close(); app.config["HSD_MATERIAL_MANAGER"].close(); app.config["HSD_MANAGER"].close()
