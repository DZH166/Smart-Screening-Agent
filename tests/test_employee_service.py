"""LAN workers share host AI settings while keeping uploads/results per task."""
import threading
import json
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from hsd_tool.service import JobManager, sha256
from test_service import prepared


def wait_finished(manager, identifier="sample"):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = manager.snapshot(identifier)
        if result["status"] not in {"queued", "importing", "matching", "ai_review", "exporting"}:
            return result
        time.sleep(.01)
    raise AssertionError("background operation timed out")


def test_employee_jobs_queue_without_overwriting_host_preferences(tmp_path, monkeypatch):
    manager, existing = prepared(tmp_path, [""])
    calls = []
    monkeypatch.setattr(manager.pool, "submit", lambda *args: calls.append(args))
    existing["status"] = "matching"
    payload = {"workbook_path": existing["_workbook_path"], "source_path": existing["_source_path"],
        "output_root": existing["_output_root"], "start_number": 123}
    try:
        first = manager.create(payload, owner_id="employee-a", downloadable=True,
            display_names={"workbook_name": "员工上传.xlsx", "source_name": "员工原稿.zip"})
        second = manager.create(payload, owner_id="employee-b", downloadable=True)
        assert len(calls) == 2
        assert manager.snapshot(first)["status"] == "queued"
        assert manager.snapshot(first)["queue_position"] == 2
        assert manager.snapshot(second)["queue_position"] == 3
        assert manager.snapshot(first)["workbook_name"] == "员工上传.xlsx"
        assert manager.snapshot(first)["source_name"] == "员工原稿.zip"
        assert not manager.settings_path.exists()
        assert "_owner_id" not in manager.snapshot(first)
        assert "_downloadable" not in manager.snapshot(first)
        with pytest.raises(ValueError, match="仍在处理"):
            manager.create(payload)
        existing["status"] = "ready"
        manager._start_operation(first, "importing", "reading")
        assert manager.snapshot(second)["queue_position"] == 2
        manager.jobs[first]["status"] = "ready"
        assert manager.snapshot(second)["queue_position"] == 1
    finally:
        manager.close()


def test_employee_queue_uses_one_worker(tmp_path, monkeypatch):
    manager, existing = prepared(tmp_path, [""])
    entered, release = threading.Event(), threading.Event()
    completed = []
    def process(identifier):
        manager._start_operation(identifier, "importing", "reading")
        if not completed:
            entered.set()
            assert release.wait(5)
        completed.append(identifier)
        manager.jobs[identifier]["status"] = "ready"
    monkeypatch.setattr(manager, "_process", process)
    payload = {"workbook_path": existing["_workbook_path"], "source_path": existing["_source_path"],
        "output_root": existing["_output_root"], "start_number": 1}
    try:
        first = manager.create(payload, owner_id="a")
        assert entered.wait(5)
        second = manager.create(payload, owner_id="b")
        assert manager.snapshot(second)["status"] == "queued"
        assert manager.snapshot(second)["queue_position"] == 2
        assert completed == []
        release.set()
        assert wait_finished(manager, second)["status"] == "ready"
        assert completed == [first, second]
    finally:
        release.set()
        manager.close()


def test_shared_ai_configuration_is_separate_from_employee_paths(tmp_path):
    shared = tmp_path / "host"
    manager = JobManager(tmp_path / "employees", settings_dir=shared)
    try:
        assert manager.ai_settings.path.parent == shared
        assert manager.ai_usage.path.parent == shared
        assert manager.ai_validation.directory == shared
        assert manager.settings_path.parent == tmp_path / "employees"
        assert not manager.ai_config()["validation"]["qualified"]
    finally:
        manager.close()


def test_employee_download_is_only_verified_output_and_preserves_inputs(tmp_path):
    manager, job = prepared(tmp_path, ["KEEP023", "", ""])
    job.update(_owner_id="employee", _downloadable=True)
    workbook_before = sha256(job["_workbook_path"])
    source_before = {f["id"]: sha256(f["source_path"]) for f in job["files"]}
    manager.resolve("sample", "r4", None)
    try:
        with pytest.raises(KeyError):
            manager.download_asset("sample")
        manager.export("sample")
        snapshot = wait_finished(manager)
        assert snapshot["status"] == "done", snapshot["error"]
        assert snapshot["download_ready"]
        assert snapshot["download_name"] == "HSD编号结果.zip"
        path, digest = manager.download_asset("sample")
        assert digest == sha256(path)
        assert path.parent == Path(job["_work_dir"])
        output = Path(snapshot["output_dir"])
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            expected = {str(p.relative_to(output.parent)).replace("\\", "/")
                for p in output.rglob("*") if p.is_file()}
            assert set(names) == expected
            assert all(".." not in Path(name).parts for name in names)
            assert archive.read(output.name + "/已编号AI/KEEP023.ai") == Path(job["files"][0]["source_path"]).read_bytes()
            assert archive.read(output.name + "/已编号AI/HSD0001.ai") == Path(job["files"][1]["source_path"]).read_bytes()
            assert len(names) == 3
            assert all(name.endswith((".ai", ".xlsx")) for name in names)
            pending = (Path(job["_records_dir"]) / "待处理清单.csv").read_text("utf-8-sig")
            assert "已跳过" in pending
            report = json.loads((Path(job["_records_dir"]) / "处理记录.json").read_text("utf-8"))
            assert report["pending_rows"][0]["status"] == "skipped"
            assert len(report["decision_records"]) == 3
            assert not any(name.endswith("source.xlsx") or "/matching/" in name or "settings" in name for name in names)
        assert sha256(job["_workbook_path"]) == workbook_before
        assert {f["id"]: sha256(f["source_path"]) for f in job["files"]} == source_before
    finally:
        manager.close()


def test_packaging_failure_retries_same_export_without_renumbering(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    original = manager._package_download
    def failed(*args):
        raise OSError("unit test full disk")
    monkeypatch.setattr(manager, "_package_download", failed)
    try:
        manager.export("sample")
        snapshot = wait_finished(manager)
        assert snapshot["status"] == "ready"
        assert not snapshot["download_ready"]
        assert "full disk" in snapshot["error"]
        completed = Path(job["_completed_export"]["path"])
        original_digest = sha256(completed / "已编号AI/HSD0001.ai")
        monkeypatch.setattr(manager, "_package_download", original)
        manager.export("sample")
        assert wait_finished(manager)["status"] == "done"
        assert Path(job["output_dir"]) == completed
        assert len(list(Path(job["_output_root"]).iterdir())) == 1
        assert sha256(completed / "已编号AI/HSD0001.ai") == original_digest
    finally:
        manager.close()


def test_retry_refuses_changed_exported_contents(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    original = manager._package_download
    monkeypatch.setattr(manager, "_package_download", lambda *args: (_ for _ in ()).throw(OSError("unit fail")))
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "ready"
        output = Path(job["_completed_export"]["path"])
        (output / "已编号AI/HSD0001.ai").write_bytes(b"changed")
        monkeypatch.setattr(manager, "_package_download", original)
        manager.export("sample")
        result = wait_finished(manager)
        assert result["status"] == "ready"
        assert not result["download_ready"]
        assert "发生变化" in result["error"]
        assert not (Path(job["_work_dir"]) / "HSD编号结果.zip").exists()
        assert not list(Path(job["_work_dir"]).glob(".download-*"))
    finally:
        manager.close()


def test_packaging_retry_still_rechecks_original_sources(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    original = manager._package_download
    monkeypatch.setattr(manager, "_package_download", lambda *args: (_ for _ in ()).throw(OSError("unit fail")))
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "ready"
        Path(job["files"][0]["source_path"]).write_bytes(b"changed after first export")
        monkeypatch.setattr(manager, "_package_download", original)
        manager.export("sample")
        result = wait_finished(manager)
        assert result["status"] == "ready"
        assert "源文件发生了变化" in result["error"]
        assert not result["download_ready"]
    finally:
        manager.close()


def test_packaging_remains_background_exporting_until_archive_is_ready(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    entered, release = threading.Event(), threading.Event()
    original = manager._package_download
    def delayed(*args):
        entered.set()
        assert release.wait(5)
        original(*args)
    monkeypatch.setattr(manager, "_package_download", delayed)
    try:
        manager.export("sample")
        assert entered.wait(5)
        snapshot = manager.snapshot("sample")
        assert snapshot["status"] == "exporting"
        assert not snapshot["download_ready"]
        with pytest.raises(KeyError):
            manager.download_asset("sample")
        release.set()
        assert wait_finished(manager)["download_ready"]
    finally:
        release.set()
        manager.close()


def test_download_rejects_escaped_asset_or_modified_archive(tmp_path):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "done"
        archive, _ = manager.download_asset("sample")
        outside = tmp_path / "outside.zip"
        outside.write_bytes(archive.read_bytes())
        job["_download_path"] = str(outside)
        with pytest.raises(KeyError):
            manager.download_asset("sample")
        job["_download_path"] = str(archive)
        archive.write_bytes(b"tampered")
        with pytest.raises(ValueError, match="发生变化"):
            manager.download_asset("sample")
    finally:
        manager.close()


def test_packager_rejects_output_escape_and_symbolic_links(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    output = Path(job["_output_root"]) / "result"
    output.mkdir(parents=True)
    item = output / "sample_已编号.xlsx"
    item.write_bytes(b"output")
    (output / "已编号AI").mkdir()
    (output / "已编号AI/HSD0001.ai").write_bytes(b"output-ai")
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        with pytest.raises(ValueError, match="位置异常"):
            manager._output_manifest(job, outside)
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: p == item or original(p))
        with pytest.raises(ValueError, match="链接"):
            manager._output_manifest(job, output)
    finally:
        manager.close()


def test_download_rejects_sibling_job_directory(tmp_path):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "done"
        sibling = manager.data_dir / "jobs" / "other-employee"
        sibling.mkdir()
        original = Path(job["_download_path"])
        destination = sibling / original.name
        destination.write_bytes(original.read_bytes())
        job.update(_work_dir=str(sibling), _download_path=str(destination))
        with pytest.raises(ValueError, match="目录异常"):
            manager.download_asset("sample")
    finally:
        manager.close()


def test_work_directory_rejects_windows_reparse_attribute(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    work = Path(job["_work_dir"])
    original = Path.lstat
    monkeypatch.setattr(Path, "is_symlink", lambda p: False)
    monkeypatch.setattr(Path, "lstat", lambda p, *args, **kwargs:
        SimpleNamespace(st_file_attributes=0x400) if p == work else original(p, *args, **kwargs))
    try:
        with pytest.raises(ValueError, match="目录异常"):
            manager._task_work_root(job)
    finally:
        # Restore filesystem predicates before closing triggers marked-cache cleanup.
        monkeypatch.undo()
        manager.close()


def test_employee_ai_retry_queues_but_local_retry_keeps_busy_guard(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    monkeypatch.setattr(manager.ai_settings, "snapshot", lambda: {"enabled": True, "configured": True})
    calls = []
    monkeypatch.setattr(manager.ai_pool, "submit", lambda *args: calls.append(args))
    manager.jobs["busy"] = {"status": "matching"}
    try:
        with pytest.raises(ValueError, match="仍有任务"):
            manager.review_ai("sample")
        job["_owner_id"] = "employee"
        manager.review_ai("sample")
        assert manager.snapshot("sample")["status"] == "queued"
        assert manager.snapshot("sample")["queue_position"] == 1
        assert manager.snapshot("sample")["queue_stage"] == "ai"
        assert calls[0][0] == manager._run_task
        assert calls[0][1:] == (manager._rerun_ai, "sample")
    finally:
        manager.close()


def test_download_whitelist_ignores_unplanned_extra_files(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    job["_ai_observation_runs"] = [{"planned_case_ids": ["synthetic"], "cases": [{"error": "synthetic-failure"}]}]
    original = manager._package_download
    def inject(current, directory):
        (directory / "not-planned.ai").write_bytes(b"must never be downloaded")
        (directory / "private.json").write_text('{"private":"not in ZIP"}')
        original(current, directory)
    monkeypatch.setattr(manager, "_package_download", inject)
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "done"
        path, _ = manager.download_asset("sample")
        with zipfile.ZipFile(path) as archive:
            assert set(archive.namelist()) == {
                Path(job["output_dir"]).name + "/已编号AI/HSD0001.ai",
                Path(job["output_dir"]).name + "/sample_已编号.xlsx"}
        report = json.loads((Path(job["_records_dir"]) / "处理记录.json").read_text("utf-8"))
        assert report["ai_observation_runs"] == job["_ai_observation_runs"]
        assert len(report["decision_records"]) == 1
    finally:
        manager.close()


def test_retry_rejects_modified_internal_validation_records(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    original = manager._package_download
    monkeypatch.setattr(manager, "_package_download", lambda *args: (_ for _ in ()).throw(OSError("synthetic disk error")))
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "ready"
        (Path(job["_records_dir"]) / "处理记录.json").write_text('{"tampered":true}')
        monkeypatch.setattr(manager, "_package_download", original)
        manager.export("sample")
        result = wait_finished(manager)
        assert result["status"] == "ready" and "验证记录发生变化" in result["error"]
        assert not result["download_ready"]
    finally:
        manager.close()


def test_private_records_survive_normal_shutdown_and_disposable_cache_cleanup(tmp_path):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    identifier = "a" * 32
    cache = manager.data_dir / "jobs" / identifier
    cache.mkdir()
    (cache / ".hsd-job").write_text(identifier)
    (cache / "disposable.bin").write_bytes(b"temporary")
    persistent = manager.record_directory(identifier, "ai_runs") / "failed-run.json"
    persistent.write_text('{"planned_case_ids":["one"],"cases":[{"error":"synthetic"}]}')
    manager.export("sample")
    assert wait_finished(manager)["status"] == "done"
    report = Path(job["_records_dir"]) / "处理记录.json"
    before = report.read_bytes()
    assert report.is_relative_to(manager.data_dir / "task_records")
    manager.close()
    assert not cache.exists()
    assert report.read_bytes() == before and persistent.is_file()


def test_private_record_paths_reject_unsafe_ids_and_section_links(tmp_path, monkeypatch):
    manager, _ = prepared(tmp_path, [""])
    try:
        for identifier in ("../outside", "a/b", "a\\b", "", ".", ".."):
            with pytest.raises(ValueError, match="目录异常"):
                manager.task_records_root(identifier)
        with pytest.raises(ValueError, match="类型无效"):
            manager.record_directory("sample", "../outside")
        section = manager.record_directory("sample", "export_records")
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == section or original(path))
        with pytest.raises(ValueError, match="目录异常"):
            manager.record_directory("sample", "export_records")
    finally:
        monkeypatch.undo()
        manager.close()


def test_record_tampering_during_packaging_cannot_become_new_timing_baseline(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    original = manager._package_download
    def tamper(current, directory):
        original(current, directory)
        (Path(current["_records_dir"]) / "处理记录.json").write_text('{"changed":true}')
    monkeypatch.setattr(manager, "_package_download", tamper)
    try:
        manager.export("sample")
        result = wait_finished(manager)
        assert result["status"] == "ready" and "验证记录发生变化" in result["error"]
        assert not result["download_ready"]
        with pytest.raises(KeyError):
            manager.download_asset("sample")
    finally:
        manager.close()
