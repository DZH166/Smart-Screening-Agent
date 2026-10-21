"""The UI fixture must stay synthetic, isolated, and able to show real failures."""
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ui_fixture", ROOT / "tools" / "ui_fixture_server.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    return MODULE.create_fixture_app(ROOT / "hsd_tool" / "static")


def test_fixture_is_explicitly_synthetic_and_remote_access_denied():
    app = fixture()
    client = app.test_client()
    html = client.get("/?scenario=review&count=500&mode=employee").text
    assert "界面测试数据" in html
    assert "synthetic-test-token" in html
    assert "非业务验收" in html
    assert client.get("/api/config", environ_base={"REMOTE_ADDR": "192.168.99.111"}).status_code == 403
    config = client.get("/api/config").json
    job = client.get("/api/jobs/" + config["active_job_id"]).json
    assert len(job["rows"]) == 500
    assert all(row["status"] == "review" for row in job["rows"])
    assert job["stats"]["ai_auto"] == 0
    assert "D:/" not in str(job)


def test_fixture_jobs_images_and_results_cannot_cross_sessions():
    app = fixture()
    first, second = app.test_client(), app.test_client()
    first.get("/?scenario=done")
    second.get("/?scenario=review")
    identifier = first.get("/api/config").json["active_job_id"]
    assert first.get(f"/api/jobs/{identifier}").status_code == 200
    assert second.get(f"/api/jobs/{identifier}").status_code == 404
    assert second.get(f"/api/jobs/{identifier}/image/row/r1").status_code == 404
    assert second.get(f"/api/jobs/{identifier}/download").status_code == 400
    downloaded = first.get(f"/api/jobs/{identifier}/download")
    assert downloaded.status_code == 200
    assert downloaded.mimetype == "application/zip"


def test_fixture_confirm_skip_undo_and_revision_conflict():
    client = fixture().test_client()
    client.get("/?scenario=review&count=3&delay=0")
    identifier = client.get("/api/config").json["active_job_id"]
    prefix = f"/api/jobs/{identifier}"
    resolved = client.post(prefix + "/resolve", json={"row_id": "r1", "file_id": "f1", "expected_revision": 1}).json
    assert resolved["rows"][0]["status"] == "confirmed"
    assert resolved["can_undo"]
    conflict = client.post(prefix + "/resolve", json={"row_id": "r2", "file_id": None, "expected_revision": 1})
    assert conflict.status_code == 409
    assert client.get(prefix).json["rows"][1]["status"] == "review"
    skipped = client.post(prefix + "/resolve", json={"row_id": "r2", "file_id": None, "expected_revision": 2}).json
    assert skipped["rows"][1]["status"] == "skipped"
    undone = client.post(prefix + "/undo", json={"expected_revision": 3}).json
    assert undone["rows"][1]["status"] == "review"
    assert undone["last_undone_row_id"] == "r2"


def test_fixture_failed_save_never_changes_records_and_retry_succeeds():
    client = fixture().test_client()
    client.get("/?scenario=save-failed&delay=0")
    identifier = client.get("/api/config").json["active_job_id"]
    prefix = f"/api/jobs/{identifier}"
    payload = {"row_id": "r1", "file_id": "f1", "expected_revision": 1}
    assert client.post(prefix + "/resolve", json=payload).status_code == 503
    assert client.get(prefix).json["rows"][0]["status"] == "review"
    assert client.post(prefix + "/resolve", json=payload).json["rows"][0]["status"] == "confirmed"


def test_fixture_has_no_real_ai_and_employee_admin_calls_stay_denied():
    client = fixture().test_client()
    client.get("/?scenario=ai-failed&delay=0")
    identifier = client.get("/api/config").json["active_job_id"]
    assert client.post(f"/api/jobs/{identifier}/ai-review", json={}).status_code == 503
    assert client.post("/api/ai/settings", json={"enabled": True}).status_code == 403
    assert client.get("/api/ai/usage").status_code == 403
    assert client.post(f"/api/jobs/{identifier}/open-output", json={}).status_code == 403


def test_fixture_cancel_waits_then_settles_without_export():
    client = fixture().test_client()
    client.get("/?scenario=matching&delay=0")
    identifier = client.get("/api/config").json["active_job_id"]
    path = f"/api/jobs/{identifier}"
    assert client.post(path + "/cancel", json={}).status_code == 409
    stopped = client.post(path + "/cancel", json={"expected_revision": 1}).json
    assert stopped["status"] == "cancelling" and stopped["cancel_requested"]
    assert client.post(path + "/export", json={}).status_code == 409
    assert client.get(path).json["status"] == "cancelling"
    assert client.get(path).json["status"] == "cancelling"
    assert client.get(path).json["status"] == "cancelled"
    assert client.get(path + "/download-status").status_code == 400


def test_fixture_download_preflight_success_then_readable_stream_failure():
    for scenario, code in (("download-failed", 400), ("download-auth", 401)):
        client = fixture().test_client()
        client.get(f"/?scenario={scenario}&delay=0")
        identifier = client.get("/api/config").json["active_job_id"]
        path = f"/api/jobs/{identifier}"
        assert client.get(path + "/download-status").json["ready"]
        failed = client.get(path + "/download?frame=1")
        assert failed.status_code == code and failed.json["error"].startswith("模拟")


def test_fixture_upload_recovery_and_stop_remain_owned_and_idempotent():
    app = fixture()
    first, other = app.test_client(), app.test_client()
    first.get("/?scenario=upload-lost&delay=0")
    other.get("/?scenario=upload-lost&delay=0")
    headers = {"X-HSD-Upload-ID": "00000000-0000-4000-8000-000000000001"}
    status = "/api/jobs/upload-status/" + headers["X-HSD-Upload-ID"]
    assert first.post("/api/jobs/upload", headers=headers).status_code == 503
    accepted = first.get(status).json
    assert accepted["state"] == "completed" and accepted["job_id"]
    repeated = first.post("/api/jobs/upload", headers=headers).json
    assert repeated["id"] == accepted["job_id"] and repeated["reused"]
    assert other.get(status).status_code == 404
    assert other.post(status + "/cancel", json={}).status_code == 404
    first.get("/?scenario=upload-pending&delay=0")
    headers["X-HSD-Upload-ID"] = "00000000-0000-4000-8000-000000000002"
    status = "/api/jobs/upload-status/" + headers["X-HSD-Upload-ID"]
    assert first.post("/api/jobs/upload", headers=headers).status_code == 503
    assert first.get(status).json["state"] == "pending"
    assert first.post(status + "/cancel", json={}).json["cancellation_requested"]
    first.get(status)
    assert first.get(status).json["state"] == "cancelled"
    missing = "/api/jobs/upload-status/00000000-0000-4000-8000-000000000003"
    assert first.post(missing + "/cancel", json={}).json["state"] == "cancelled"
