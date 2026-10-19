"""Large-input IO shortcuts keep independent byte-integrity validation."""
from pathlib import Path
import zipfile

import pytest

import hsd_tool.service as service
from hsd_tool.service import sha256
from test_service import prepared
from test_employee_service import wait_finished


def create_uploaded_job(tmp_path, monkeypatch):
    manager, template = prepared(tmp_path, [""])
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("sample.ai", b"test-ai")
    payload = {"workbook_path": template["_workbook_path"], "source_path": str(archive),
               "output_root": template["_output_root"], "start_number": 1}
    digests = {"workbook": sha256(payload["workbook_path"]), "source": sha256(archive)}
    monkeypatch.setattr(manager.pool, "submit", lambda *args: None)
    monkeypatch.setattr("hsd_tool.workbook.inspect_workbook", lambda *args: {
        "sheet_name": "测试", "rows": [{"id": "r2", "row_number": 2, "number": ""}]})
    monkeypatch.setattr("hsd_tool.matching.scan_and_match", lambda *args, **kwargs: {
        "files": [], "matches": []})
    monkeypatch.setattr(manager, "_review_ai", lambda *args: None)
    return manager, payload, digests


def test_uploaded_hash_saves_only_redundant_reads(tmp_path, monkeypatch):
    manager, payload, digests = create_uploaded_job(tmp_path, monkeypatch)
    calls = []
    original = service.sha256
    monkeypatch.setattr(service, "sha256", lambda path: (calls.append(Path(path)), original(path))[1])
    try:
        identifier = manager.create(payload, owner_id="employee", downloadable=True, input_digests=digests)
        digests["workbook"] = "0" * 64  # stored metadata is not a caller-owned mutable dict
        manager._process(identifier)
        assert wait_finished(manager, identifier)["status"] == "ready"
        assert Path(payload["workbook_path"]) not in calls
        assert calls.count(Path(payload["source_path"])) == 1  # post-scan independent check retained
        assert sum(path.name == "source.xlsx" for path in calls) == 1
        assert "_upload_digests" not in manager.snapshot(identifier)
    finally:
        manager.close()


@pytest.mark.parametrize("changed", ["workbook", "source"])
def test_uploaded_hash_rejects_changes_before_worker_starts(tmp_path, monkeypatch, changed):
    manager, payload, digests = create_uploaded_job(tmp_path, monkeypatch)
    try:
        identifier = manager.create(payload, owner_id="employee", downloadable=True, input_digests=digests)
        key = "workbook_path" if changed == "workbook" else "source_path"
        with Path(payload[key]).open("ab") as stream:
            stream.write(b"changed after upload")
        manager._process(identifier)
        assert manager.jobs[identifier]["status"] == "error"
        assert "发生了变化" in manager.jobs[identifier]["error"]
    finally:
        manager.close()


def test_local_mode_ignores_json_digest_injection(tmp_path, monkeypatch):
    manager, payload, digests = create_uploaded_job(tmp_path, monkeypatch)
    payload["input_digests"] = {"workbook": "0" * 64, "source": "0" * 64}
    calls = []
    original = service.sha256
    monkeypatch.setattr(service, "sha256", lambda path: (calls.append(Path(path)), original(path))[1])
    try:
        identifier = manager.create(payload)
        manager._process(identifier)
        assert wait_finished(manager, identifier)["status"] == "ready"
        assert Path(payload["workbook_path"]) in calls
        assert calls.count(Path(payload["source_path"])) == 2
        with pytest.raises(ValueError, match="校验信息无效"):
            manager.create(payload, input_digests=digests)
        with pytest.raises(ValueError, match="校验信息无效"):
            manager.create(payload, owner_id="employee", downloadable=True,
                           input_digests={"workbook": "invalid", "source": "0" * 64})
    finally:
        manager.close()


def test_export_manifest_reuses_independently_verified_ai_hash(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    calls = []
    original = service.sha256
    monkeypatch.setattr(service, "sha256", lambda path: (calls.append(Path(path)), original(path))[1])
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "done"
        copied = Path(job["output_dir"]) / "已编号AI/HSD0001.ai"
        assert sum(p.name == copied.name and p.parent.name == "已编号AI" for p in calls) == 1
        assert job["_completed_export"]["manifest"]["已编号AI/HSD0001.ai"] == original(copied)
    finally:
        manager.close()


def test_tamper_between_copy_and_manifest_is_not_new_baseline(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    original = manager._output_manifest

    def tamper(job, directory, verified_outputs=None):
        (directory / "已编号AI/HSD0001.ai").write_bytes(b"tampered after independent verify")
        return original(job, directory, verified_outputs)

    monkeypatch.setattr(manager, "_output_manifest", tamper)
    try:
        manager.export("sample")
        snapshot = wait_finished(manager)
        assert snapshot["status"] == "ready"
        assert not snapshot["download_ready"]
        assert "发生变化" in snapshot["error"]
    finally:
        manager.close()
