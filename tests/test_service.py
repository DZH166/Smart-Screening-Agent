import json
import time
import zipfile
from pathlib import Path

import pytest

from hsd_tool.service import JobManager, sha256
from hsd_tool.server import create_app


def simple_xlsx(path, values):
    rows = []
    for index, value in enumerate(values, 2):
        cell = f'<c r="A{index}" t="inlineStr"><is><t>{value}</t></is></c>' if value else ""
        rows.append(f'<row r="{index}">{cell}<c r="B{index}" t="inlineStr"><is><t>picture</t></is></c></row>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="测试" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(rows) + '</sheetData></worksheet>')
        z.writestr("xl/media/preserve.bin", b"picture-unchanged")


def prepared(tmp_path, numbers, start=1):
    manager = JobManager(tmp_path / "state")
    workbook = tmp_path / "sample.xlsx"
    simple_xlsx(workbook, numbers)
    work = tmp_path / "state" / "jobs" / "sample"
    work.mkdir(parents=True)
    files, rows = [], []
    for index, number in enumerate(numbers, 2):
        source = work / f"f{index}.ai"
        source.write_bytes(f"original-ai-data-{index}".encode())
        preview = work / f"f{index}.png"
        preview.write_bytes(b"preview")
        files.append({"id": f"f{index}", "name": source.name, "relative_path": source.name,
                      "source_path": str(source), "source_sha256": sha256(source), "preview_path": str(preview), "issue": ""})
        rows.append({"id": f"r{index}", "row_number": index, "number": number, "image_path": str(preview), "issue": "",
                     "_status": "auto", "_file_id": f"f{index}", "_reason": "same image", "candidates": []})
    job = {"id": "sample", "status": "ready", "progress": {}, "error": None,
           "sheet_name": "测试", "workbook_name": workbook.name, "source_name": "ai", "start_number": start,
           "prefix": "HSD", "rows": rows, "files": files, "warnings": [], "output_dir": None, "report": None,
           "stats": {}, "_workbook_path": str(workbook), "_snapshot_workbook": str(workbook), "_source_path": str(work),
           "_output_root": str(tmp_path / "output"), "_work_dir": str(work), "_reserved": [n for n in numbers if n],
           "_input_digest": sha256(workbook)}
    manager.jobs["sample"] = job
    manager._plan(job)
    return manager, job


def wait_export(manager):
    end = time.monotonic() + 10
    while manager.snapshot("sample")["status"] == "exporting" and time.monotonic() < end:
        time.sleep(0.02)
    return manager.snapshot("sample")


def test_preserve_numbers_and_skip_reserved(tmp_path):
    manager, job = prepared(tmp_path, ["00001", "HSD0001", "", ""])
    assert [r["planned_number"] for r in job["rows"]] == ["00001", "HSD0001", "HSD0002", "HSD0003"]
    manager.resolve("sample", "r4", None)
    assert job["rows"][2]["planned_number"] == ""
    assert job["rows"][3]["planned_number"] == "HSD0002"


def test_conflicts_and_overflow_stay_pending(tmp_path):
    manager, job = prepared(tmp_path, ["DUP", "dup", "", ""], 9999)
    assert [r["status"] for r in job["rows"]] == ["review", "review", "auto", "review"]
    assert job["rows"][2]["planned_number"] == "HSD9999"
    assert job["rows"][3]["planned_number"] == ""


@pytest.mark.parametrize("number", ["../outside", "CON", "name.", "bad:name", "bad\\name"])
def test_unsafe_existing_number_never_used_as_path(tmp_path, number):
    manager, job = prepared(tmp_path, [number])
    assert job["stats"]["exportable"] == 0
    with pytest.raises(ValueError):
        manager.export("sample")


def test_file_cannot_belong_to_two_rows(tmp_path):
    manager, job = prepared(tmp_path, ["", ""])
    with pytest.raises(ValueError, match="已对应"):
        manager.resolve("sample", "r3", "f2")
    manager.resolve("sample", "r2", None)
    manager.resolve("sample", "r3", "f2")
    assert job["rows"][1]["status"] == "confirmed"


def test_non_destructive_export_and_pending_report(tmp_path):
    manager, job = prepared(tmp_path, ["00023", "", ""])
    before = sha256(job["_workbook_path"])
    manager.resolve("sample", "r4", None)
    manager.export("sample")
    result = wait_export(manager)
    assert result["status"] == "done", result["error"]
    folder = Path(result["output_dir"])
    assert sorted(p.name for p in (folder / "已编号AI").iterdir()) == ["00023.ai", "HSD0001.ai"]
    assert sha256(folder / "已编号AI" / "00023.ai") == job["files"][0]["source_sha256"]
    assert sha256(job["_workbook_path"]) == before
    with zipfile.ZipFile(folder / "sample_已编号.xlsx") as z:
        assert z.read("xl/media/preserve.bin") == b"picture-unchanged"
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
        assert "HSD0001" in sheet and "HSD0002" not in sheet
    report = json.loads((folder / "处理记录.json").read_text("utf-8"))
    assert report["exported"] == 2 and report["new_numbers"] == 1 and report["pending"] == 1


def test_changed_source_aborts_export_without_partial_result(tmp_path):
    manager, job = prepared(tmp_path, [""])
    Path(job["files"][0]["source_path"]).write_bytes(b"changed-after-preview")
    manager.export("sample")
    result = wait_export(manager)
    assert result["status"] == "ready"
    assert "发生了变化" in result["error"]
    assert not list(Path(job["_output_root"]).iterdir())


def test_failed_staging_creation_does_not_delete_existing_directory(tmp_path):
    manager, job = prepared(tmp_path, [""])
    staging = Path(job["_output_root"]) / ".HSD处理中_sample"
    staging.mkdir(parents=True)
    marker = staging / "existing.txt"
    marker.write_text("preserve", "utf-8")
    manager.export("sample")
    assert wait_export(manager)["status"] == "ready"
    assert marker.read_text("utf-8") == "preserve"


def test_local_api_rejects_cross_origin_and_missing_token(tmp_path):
    app = create_app(tmp_path / "api", token="testing-token")
    client = app.test_client()
    assert client.post("/api/jobs", json={}).status_code == 403
    assert client.post("/api/jobs", json={}, headers={"X-HSD-Token": "testing-token", "Origin": "https://elsewhere.test"}).status_code == 403
    assert client.post("/api/jobs", json={}, headers={"X-HSD-Token": "testing-token"}).status_code == 400
    assert client.get("/api/config", headers={"Host": "evil.test"}).status_code == 403
    assert client.get("/api/config").status_code == 200


def test_image_api_cannot_access_outside_job(tmp_path):
    manager, job = prepared(tmp_path, [""])
    job["rows"][0]["image_path"] = job["_workbook_path"]
    with pytest.raises(KeyError):
        manager.image_path("sample", "row", "r2")


def test_locked_partial_cleanup_returns_to_ready(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    Path(job["files"][0]["source_path"]).write_bytes(b"changed")
    def locked(path):
        raise PermissionError("locked")
    monkeypatch.setattr("hsd_tool.service.shutil.rmtree", locked)
    manager.export("sample")
    result = wait_export(manager)
    assert result["status"] == "ready"
    assert "暂被占用" in result["error"]


def test_unsaved_preferences_do_not_leave_unstarted_job(tmp_path, monkeypatch):
    manager, old = prepared(tmp_path, [""])
    seen = []
    def failed(job):
        raise PermissionError("settings locked")
    monkeypatch.setattr(manager, "_save_config", failed)
    monkeypatch.setattr(manager.pool, "submit", lambda *args: seen.append(args))
    identifier = manager.create({"workbook_path": old["_workbook_path"], "source_path": old["_source_path"],
                                 "output_root": old["_output_root"], "start_number": 1})
    assert seen and manager.jobs[identifier]["warnings"]


def test_output_inside_source_is_rejected(tmp_path):
    manager, old = prepared(tmp_path, [""])
    source = tmp_path / "user_ai"
    source.mkdir()
    with pytest.raises(ValueError, match="源文件夹内部"):
        manager.create({"workbook_path": old["_workbook_path"], "source_path": str(source),
                        "output_root": str(source / "results"), "start_number": 1})


def test_stats_separate_skipped_from_pending_review(tmp_path):
    """A skipped row is decided on, so it must leave the pending-review count."""
    manager, job = prepared(tmp_path, ["", ""], start=1)
    assert job["stats"]["needs_attention"] == 0
    assert job["stats"]["auto"] == 2
    job["rows"][0]["_status"] = "review"
    manager._plan(job)
    assert job["stats"]["review"] == 1
    assert job["stats"]["needs_attention"] == 1
    manager.resolve("sample", "r2", None)
    assert job["stats"]["skipped"] == 1
    assert job["stats"]["needs_attention"] == 0
    assert job["stats"]["exportable"] == 1
    assert job["stats"]["total"] == 2


def test_created_job_exposes_the_output_target(tmp_path):
    """The summary screen states where results will be written, so it is public."""
    manager, old = prepared(tmp_path, [""])
    target = tmp_path / "library"
    target.mkdir()
    identifier = manager.create({"workbook_path": old["_workbook_path"], "source_path": old["_source_path"],
                                 "output_root": str(target), "start_number": 1})
    snapshot = manager.snapshot(identifier)
    assert snapshot["output_target"] == str(target)
