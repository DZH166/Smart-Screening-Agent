"""Generated task recovery and upload races; no provider or real credentials."""
from concurrent.futures import Future
from io import BytesIO
import json
from pathlib import Path
import threading
import time

import pytest

from hsd_tool.cloud_tasks import CloudTaskStore, UploadClaims
from hsd_tool.cloud_retention import CloudRetention
from hsd_tool.server import create_app
from hsd_tool.cloud_server import CloudAccess
from test_cloud_retention import manager_at, add_upload, JOB
from test_cloud_server import ORIGIN, CODE, TOKEN, cloud_request, login
from test_employee_api import workbook_bytes, zip_bytes
from test_employee_api import employee_app as lan_app, login as lan_login, upload as lan_upload, request as lan_request
from test_service import prepared
from test_employee_service import wait_finished
from hsd_tool.service import JobManager, sha256


@pytest.fixture
def saved(tmp_path):
    manager = manager_at(tmp_path / "service")
    store = CloudTaskStore(manager, ORIGIN)
    manager.task_persistence = store
    retention = CloudRetention(manager, {}, retention_seconds=100)
    token = store.new_token(); owner = store.owner(token)
    job = add_upload(manager)
    job.update(_owner_id=owner, rows=[], files=[], _history=[], warnings=[], revision=3,
               _comparison_bindings={}, _input_digest="synthetic-input", start_number=1)
    manager._check_import_sources = lambda job: None
    manager._verify_comparison_sources = lambda job, **kwargs: None
    manager._verify_export_records = lambda job: None
    retention.register(JOB); store.save_job(job)
    return manager, store, retention, job, token, owner


@pytest.mark.parametrize("state", ["ready", "done", "error", "cancelled"])
def test_private_checkpoint_restores_only_owner_without_scheduling(saved, state):
    manager, store, retention, job, token, owner = saved
    job["status"] = state; store.save_job(job)
    previous_expiry = retention._records[JOB]["expires_at"]
    manager.jobs.clear()
    restarted = CloudTaskStore(manager, ORIGIN)
    assert restarted.owner(token) == owner
    with pytest.raises(KeyError):
        restarted.restore(JOB, restarted.owner(restarted.new_token()), retention)
    restored = restarted.restore(JOB, owner, retention)
    assert restored["status"] == state and restored["revision"] == 3
    assert restored["_image_assets"] == {} and restored["restored"]
    assert retention._records[JOB]["expires_at"] == previous_expiry


def test_interrupted_busy_checkpoint_becomes_error_and_never_resumes(saved):
    manager, store, retention, job, _, owner = saved
    job["status"] = "matching"; store.save_job(job)
    manager.jobs.clear()
    restarted = CloudRetention(manager, {}, retention_seconds=100)
    restarted.sweep(delete=False)
    previous_expiry = restarted._records[JOB]["expires_at"]
    result = store.restore(JOB, owner, restarted)
    assert result["status"] == "error" and "服务中断" in result["error"]
    assert restarted._records[JOB]["expires_at"] == previous_expiry


@pytest.mark.parametrize("tamper", ["owner", "path", "signature", "implementation"])
def test_changed_checkpoint_cannot_restore_or_rebaseline(saved, tamper):
    manager, store, retention, job, _, owner = saved
    manager.jobs.clear()
    path = store._state_path(JOB)
    envelope = json.loads(path.read_text("utf-8"))
    if tamper == "owner":
        envelope["payload"]["owner"] = "a" * 64
    elif tamper == "path":
        envelope["payload"]["job"]["_work_dir"] = {"$hsd_path": ["..", "other-site"]}
    elif tamper == "implementation":
        envelope["payload"]["implementation"] = "a" * 64
    else:
        envelope["signature"] = "0" * 64
    path.write_text(json.dumps(envelope), "utf-8")
    with pytest.raises(ValueError):
        store.restore(JOB, owner, retention)
    assert JOB not in manager.jobs and path.exists() and retention.job_leases == {}


def test_signed_path_traversal_and_changed_sources_fail_closed(saved):
    manager, store, retention, job, _, owner = saved
    manager.jobs.clear()
    payload = store._read(store._state_path(JOB))
    payload["job"]["_work_dir"] = {"$hsd_path": ["..", "other-site"]}
    store._write(store._state_path(JOB), payload)
    with pytest.raises(ValueError):
        store.restore(JOB, owner, retention)
    store.save_job(job)
    def changed(job, **kwargs):
        raise ValueError("comparison changed")
    manager._verify_comparison_sources = changed
    assert store.restore(JOB, owner, retention)["status"] == "error"


def test_expired_or_implementation_changed_task_never_restores(saved):
    manager, store, retention, _, _, owner = saved
    manager.jobs.clear()
    store.implementation = "new-implementation"
    with pytest.raises(KeyError):
        store.restore(JOB, owner, retention)
    retention._records[JOB]["expires_at"] = time.time() - 1
    with pytest.raises(KeyError):
        store.restore(JOB, owner, retention)


def test_allowlist_excludes_keys_arrays_and_runtime_objects(saved):
    _, store, _, job, _, _ = saved
    job.update(_prepared_matching=object(), api_key="must-never-persist", _settings={"secret": "private"})
    job["_comparison_bindings"] = {str(Path(job["_work_dir"]) / "preview.png"): "digest"}
    store.save_job(job)
    payload = store._read(store._state_path(JOB))
    encoded = json.dumps(payload)
    assert "must-never-persist" not in encoded and "_prepared_matching" not in encoded
    assert "_settings" not in encoded and "$hsd_path" in encoded
    assert str(store.data).replace("\\", "\\\\") not in encoded


def test_upload_reservation_cancellation_race_and_owner_binding():
    claims = UploadClaims(); identifier = "1" * 32
    assert claims.reserve(identifier, "alice")["state"] == "reserved"
    assert claims.reserve(identifier, "alice")["state"] == "pending"
    with pytest.raises(KeyError):
        claims.reserve(identifier, "bob")
    assert claims.cancel(identifier, "alice")["cancellation_requested"]
    with pytest.raises(ValueError):
        claims.commit(identifier, "alice", JOB)
    claims.finish(identifier, "alice")
    assert claims.lookup(identifier, "alice")["state"] == "cancelled"
    identifier = "2" * 32
    assert claims.cancel(identifier, "alice")["state"] == "cancelled"
    assert claims.reserve(identifier, "alice")["state"] == "cancelled"


def test_crashed_pending_upload_allows_only_original_owner_retry(saved):
    manager, store, _, _, _, owner = saved
    identifier = "3" * 32
    store.reserve(identifier, owner)
    restarted = CloudTaskStore(manager, ORIGIN)
    with pytest.raises(KeyError):
        restarted.reserve(identifier, "b" * 64)
    assert restarted.reserve(identifier, owner)["state"] == "reserved"


def test_signed_abandoned_upload_expires_after_retry_but_live_transfer_is_protected(saved):
    manager, store, _, _, _, owner = saved
    identifier = "9" * 32
    store.reserve(identifier, owner)
    abandoned = manager.data_dir / "uploads" / ("a" * 32); abandoned.mkdir()
    (abandoned / ".hsd-upload").write_text(abandoned.name, "ascii")
    (abandoned / "partial.bin").write_bytes(b"synthetic partial transfer")
    store.bind_directory(identifier, owner, abandoned)
    future = time.time() + 259201
    store.sweep_uploads(now=future)
    assert abandoned.exists(), "an active transfer cannot be cleaned"
    restarted = CloudTaskStore(manager, ORIGIN)
    assert restarted.reserve(identifier, owner)["state"] == "reserved"
    restarted.sweep_uploads(now=future)
    assert not abandoned.exists(), "retry must not lose signed ownership of old partial files"


def test_cancellation_is_reserved_before_late_body_and_has_no_job(tmp_path, monkeypatch):
    app = create_app(tmp_path / "data", cloud=CloudAccess(ORIGIN, CODE), token=TOKEN,
                     settings_dir=tmp_path / "settings")
    manager = app.config["HSD_MANAGER"]
    monkeypatch.setattr(manager, "_submit", lambda *_: pytest.fail("cancelled upload submitted work"))
    try:
        client = app.test_client(); login(client)
        identifier = "a" * 32
        response = cloud_request(client, f"/api/jobs/upload-status/{identifier}/cancel", method="POST", payload={})
        assert response.json["state"] == "cancelled"; response.close()
        response = cloud_request(client, "/api/jobs/upload", method="POST", proxy_headers={"X-HSD-Upload-ID": identifier},
                                 data=b"multipart body is never parsed", content_type="multipart/form-data; boundary=x")
        assert response.status_code == 409; response.close()
        assert not manager.jobs and not list(app.config["HSD_UPLOADS"].input_root.iterdir())
    finally:
        manager.close()


def test_lan_cancel_between_parse_and_commit_never_submits_or_keeps_inputs(lan_app, monkeypatch):
    app = lan_app
    manager = app.config["HSD_MANAGER"]
    claims = app.config["HSD_UPLOAD_CLAIMS"]
    submitted = []
    monkeypatch.setattr(manager, "_submit", lambda *args: submitted.append(args))
    original_commit = claims.commit
    def cancel_at_commit(identifier, owner, job_id):
        # Event boundary: the body has been validated, manager.create has
        # allocated its UUID, but no background operation may yet be accepted.
        assert job_id in manager.jobs and not submitted
        claims.cancel(identifier, owner)
        return original_commit(identifier, owner, job_id)
    monkeypatch.setattr(claims, "commit", cancel_at_commit)
    client = app.test_client(); lan_login(client)
    response = lan_upload(client)
    assert response.status_code == 400 and "停止" in response.json["error"]
    response.close()
    assert submitted == [] and manager.jobs == {} and manager._job_locks == {}
    assert not list(app.config["HSD_UPLOADS"].input_root.iterdir())
    assert not list((manager.data_dir / "jobs").iterdir())


def test_expired_task_cleans_while_unrelated_future_runs_and_reserves_scan(saved, monkeypatch):
    manager, _, retention, _, _, _ = saved
    manager._inflight_futures.add(Future())
    manager.task_has_work = lambda identifier: False
    original = retention._targets
    observed = []
    def targets(payload):
        acquired = []
        def acquire_other_thread():
            with manager.lock:
                acquired.append(True)
        thread = threading.Thread(target=acquire_other_thread); thread.start(); thread.join(timeout=1)
        observed.append(bool(acquired))
        assert JOB in manager._expiring_tasks
        return original(payload)
    monkeypatch.setattr(retention, "_targets", targets)
    expiry = retention._records[JOB]["expires_at"] + 1
    assert retention.sweep(now=expiry) == [JOB]
    assert observed == [True] and not manager._expiring_tasks


def test_new_lease_during_cleanup_scan_prevents_delete(saved, monkeypatch):
    manager, _, retention, _, _, _ = saved
    original = retention._targets
    def targets(payload):
        result = original(payload)
        retention.job_leases[JOB] = 1
        return result
    monkeypatch.setattr(retention, "_targets", targets)
    assert retention.sweep(now=retention._records[JOB]["expires_at"] + 1) == []
    assert JOB in manager.jobs and not manager._expiring_tasks


def test_https_upload_idempotency_relogin_and_auth_boundary(tmp_path, monkeypatch):
    app = create_app(tmp_path / "data", cloud=CloudAccess(ORIGIN, CODE), token=TOKEN,
                     settings_dir=tmp_path / "settings")
    app.config["TESTING"] = True
    manager = app.config["HSD_MANAGER"]
    monkeypatch.setattr(manager, "_submit", lambda *_: None)
    retention = CloudRetention(manager, app.config["HSD_JOB_LEASES"])
    app.config["HSD_RETENTION"] = retention
    identifier = "4" * 32
    try:
        client = app.test_client(); login(client)
        def upload(client):
            return cloud_request(client, "/api/jobs/upload", method="POST", proxy_headers={"X-HSD-Upload-ID": identifier},
                data={"start_number": "1", "workbook": (BytesIO(workbook_bytes()), "table.xlsx"),
                      "source": (BytesIO(zip_bytes({"pattern.ai": b"synthetic"})), "source.zip")}, content_type="multipart/form-data")
        first = upload(client); assert first.status_code == 200, first.json
        job_id = first.json["id"]; first.close()
        second = upload(client); assert second.json == {"id": job_id, "reused": True}; second.close()
        assert len(manager.jobs) == 1
        result = cloud_request(client, f"/api/jobs/upload-status/{identifier}")
        assert result.json == {"state": "completed", "job_id": job_id}; result.close()
        cookie_name = app.config["HSD_UPLOAD_CLAIMS"].cookie_name
        assert client.get_cookie(cookie_name, domain="hsd.example.test").http_only
        cloud_request(client, "/api/lan/logout", method="POST", payload={}).close(); login(client)
        response = cloud_request(client, f"/api/jobs/{job_id}"); assert response.status_code == 200; response.close()
        stranger = app.test_client(); login(stranger)
        response = cloud_request(stranger, f"/api/jobs/upload-status/{identifier}"); assert response.status_code == 404; response.close()
        response = upload(stranger); assert response.status_code == 404; response.close()
        anonymous = app.test_client()
        response = cloud_request(anonymous, f"/api/jobs/{job_id}/download?frame=1")
        assert response.status_code == 401 and response.headers["X-Frame-Options"] == "SAMEORIGIN"
        response.close()
    finally:
        manager.close()


@pytest.mark.parametrize("completed", [False, True])
def test_actual_service_checkpoint_restores_review_or_download_without_ai(tmp_path, completed):
    manager, job = prepared(tmp_path, ["KEEP001", ""])
    manager._preserve_cache = True
    identifier, batch = "6" * 32, "7" * 32
    old_work = Path(job["_work_dir"])
    new_work = old_work.with_name(identifier); old_work.rename(new_work)
    upload = manager.data_dir / "uploads" / batch; upload.mkdir(parents=True)
    (upload / ".hsd-upload").write_text(batch, "ascii")
    (new_work / ".hsd-job").write_text(identifier, "ascii")
    workbook = upload / "workbook.xlsx"
    workbook.write_bytes(Path(job["_workbook_path"]).read_bytes())
    snapshot = new_work / "source.xlsx"; snapshot.write_bytes(workbook.read_bytes())
    source = upload / "source.zip"; source.write_bytes(zip_bytes({"pattern.ai": b"synthetic source container"}))
    for item in job["files"] + job["rows"]:
        for key in ("source_path", "preview_path", "image_path"):
            if item.get(key):
                item[key] = str(new_work / Path(item[key]).relative_to(old_work))
    job.update(id=identifier, _upload_managed=True, _upload_dir=str(upload),
               _workbook_path=str(workbook), _snapshot_workbook=str(snapshot), _source_path=str(source),
               _source_archive_digest=sha256(source), _work_dir=str(new_work),
               _output_root=str(manager.data_dir / "employee_outputs" / batch), _downloadable=True,
               _comparison_bindings={str(path): sha256(path) for path in new_work.glob("f*")},
               revision=0)
    manager.jobs = {identifier: job}
    store = CloudTaskStore(manager, ORIGIN); manager.task_persistence = store
    owner = store.owner(store.new_token()); job["_owner_id"] = owner
    retention = CloudRetention(manager, {}); retention.register(identifier); store.save_job(job)
    try:
        if completed:
            manager.export(identifier, 0)
            assert wait_finished(manager, identifier)["status"] == "done", job["error"]
        manager.close()
        restarted = JobManager(manager.data_dir, preserve_cache=True)
        try:
            restored_store = CloudTaskStore(restarted, ORIGIN); restarted.task_persistence = restored_store
            restored_retention = CloudRetention(restarted, {}); restored_retention.sweep(delete=False)
            restored = restored_store.restore(identifier, owner, restored_retention)
            assert restored["status"] == ("done" if completed else "ready"), restored.get("error")
            assert not restarted._inflight_futures
            if completed:
                path, digest = restarted.download_asset(identifier)
                assert path.exists() and sha256(path) == digest
            else:
                restarted.export(identifier, 0)
                assert wait_finished(restarted, identifier)["status"] == "done"
        finally:
            restarted.close()
    finally:
        if not manager._closing:
            manager.close()


def test_process_restart_cookie_needs_login_then_restores_only_original_browser(tmp_path, monkeypatch):
    data, settings = tmp_path / "data", tmp_path / "settings"
    app = create_app(data, cloud=CloudAccess(ORIGIN, CODE), token=TOKEN, settings_dir=settings)
    manager = app.config["HSD_MANAGER"]
    monkeypatch.setattr(manager, "_submit", lambda *_: None)
    app.config["HSD_RETENTION"] = CloudRetention(manager, app.config["HSD_JOB_LEASES"])
    client = app.test_client(); login(client)
    response = cloud_request(client, "/api/jobs/upload", method="POST", data={
        "start_number": "1", "workbook": (BytesIO(workbook_bytes()), "table.xlsx"),
        "source": (BytesIO(zip_bytes({"pattern.ai": b"synthetic"})), "source.zip")}, content_type="multipart/form-data")
    identifier = response.json["id"]; response.close()
    manager.jobs[identifier].update(status="error", error="synthetic controlled failure")
    manager.task_persistence.save_job(manager.jobs[identifier])
    cookie_name = manager.task_persistence.cookie_name
    cookie = client.get_cookie(cookie_name, domain="hsd.example.test").value
    manager.close()
    restarted = create_app(data, cloud=CloudAccess(ORIGIN, CODE), token=TOKEN, settings_dir=settings)
    new_manager = restarted.config["HSD_MANAGER"]
    retention = CloudRetention(new_manager, restarted.config["HSD_JOB_LEASES"])
    restarted.config["HSD_RETENTION"] = retention
    retention.sweep(delete=False)
    try:
        browser = restarted.test_client(); browser.set_cookie(cookie_name, cookie, domain="hsd.example.test")
        result = cloud_request(browser, f"/api/jobs/{identifier}"); assert result.status_code == 401; result.close()
        login(browser)
        result = cloud_request(browser, f"/api/jobs/{identifier}")
        assert result.status_code == 200 and result.json["status"] == "error"; result.close()
        other = restarted.test_client(); login(other)
        result = cloud_request(other, f"/api/jobs/{identifier}"); assert result.status_code == 404; result.close()
        assert not new_manager._inflight_futures
    finally:
        new_manager.close()
