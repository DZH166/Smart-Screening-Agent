"""Real multipart and session-bound downloads with a synthetic provider."""
from io import BytesIO
import uuid
from types import SimpleNamespace

import pytest

from hsd_tool.lan import LanAccess
from hsd_tool.server import create_app
from test_material_service import Settings, Provider, png


HOST, REMOTE, TOKEN = "192.168.0.160", "192.168.0.25", "synthetic-material-token"
ORIGIN, CODE = f"http://{HOST}:8805", "synthetic-employee-code"


def call(client, path, *, method="GET", payload=None, token=TOKEN, origin=ORIGIN, **kwargs):
    headers = kwargs.pop("headers", {})
    if token is not None:
        headers["X-HSD-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    if payload is not None:
        kwargs["json"] = payload
    return client.open(path, method=method, base_url=ORIGIN, headers=headers,
                       environ_overrides={"REMOTE_ADDR": REMOTE}, **kwargs)


def login(client):
    assert call(client, "/api/lan/login", method="POST", payload={"code": CODE}).status_code == 200


@pytest.fixture
def application(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    lan = LanAccess(f"{HOST}/24", inputs, tmp_path / "outputs", code=CODE)
    app = create_app(tmp_path / "state", token=TOKEN, lan=lan, settings_dir=tmp_path / "settings")
    app.config.update(TESTING=True, HSD_PORT=8805)
    manager = app.config["HSD_MATERIAL_MANAGER"]
    manager.settings = Settings()
    manager.quality_hook = None
    provider = Provider()
    manager.provider_factory = lambda config: provider
    manager.ai_settings = None  # Isolated provider control; never calls either real API.
    yield app, manager, provider
    provider.release.set(); manager.close(); app.config["HSD_MANAGER"].close()


def upload(client, *, request_id=None, **kwargs):
    headers = {"X-HSD-Upload-ID": request_id or uuid.uuid4().hex}
    return call(client, "/api/material/jobs", method="POST", headers=headers,
                data={"files": [(BytesIO(png()), "../同名图片.png"), (BytesIO(png()), "同名图片.png")]},
                content_type="multipart/form-data", **kwargs)


def test_employee_real_multipart_upload_review_and_download(application):
    app, manager, provider = application
    client = app.test_client(); login(client)
    request_id = uuid.uuid4().hex
    response = upload(client, request_id=request_id)
    assert response.status_code == 200, response.json
    identifier = response.json["id"]
    manager.futures[identifier].result(20)
    assert provider.calls == 2
    assert app.config["HSD_ACTIVE_UPLOADS"] == 0
    assert list(manager.upload_root.iterdir()) == []
    status = call(client, f"/api/material/upload-status/{request_id}")
    assert status.json == {"state": "completed", "job_id": identifier}
    result = call(client, f"/api/material/jobs/{identifier}")
    assert result.status_code == 200
    state = result.json
    assert state["stats"]["downloadable"] == 2 and state["stats"]["needs_review"] == 0
    assert state["sources"][0]["name"] == "同名图片.png"
    assert state["sources"][0]["id"] != state["sources"][1]["id"]
    assert call(client, state["sources"][0]["image_url"]).status_code == 200
    item = state["items"][0]
    assert call(client, f"/api/material/jobs/{identifier}/download/{item['id']}").status_code == 200
    assert item["status"] == "generated" and "review" not in item
    resolved = call(client, f"/api/material/jobs/{identifier}/resolve", method="POST", payload={
        "expected_revision": state["revision"], "item_id": item["id"], "action": "confirm"})
    assert resolved.status_code == 200
    assert resolved.json["stats"]["ready"] == 1
    downloaded = call(client, resolved.json["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.data.startswith(b"PK")
    assert "no-store" in downloaded.headers["Cache-Control"]
    assert "synthetic-private-key" not in str(state)
    frame = call(client, resolved.json["download_url"] + "?frame=1")
    assert frame.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in frame.headers["Content-Security-Policy"]


def test_material_endpoints_require_employee_and_csrf(application):
    app, manager, provider = application
    anonymous = app.test_client()
    assert call(anonymous, "/api/material/config").status_code == 401
    client = app.test_client(); login(client)
    assert upload(client, token=None).status_code == 403
    assert upload(client, origin="https://foreign.invalid").status_code == 403
    assert provider.calls == 0


def test_other_browser_cannot_read_preview_resolve_or_download(application):
    app, manager, provider = application
    client = app.test_client(); login(client)
    identifier = upload(client).json["id"]
    manager.futures[identifier].result(20)
    state = call(client, f"/api/material/jobs/{identifier}").json
    other = app.test_client(); login(other)
    assert call(other, f"/api/material/jobs/{identifier}").status_code == 404
    assert call(other, state["sources"][0]["image_url"]).status_code == 404
    assert call(other, state["items"][0]["image_url"]).status_code == 404
    assert call(other, f"/api/material/jobs/{identifier}/download").status_code == 404
    assert call(other, f"/api/material/jobs/{identifier}/resolve", method="POST", payload={
        "expected_revision": state["revision"], "item_id": state["items"][0]["id"], "action": "confirm"}).status_code == 404


def test_refine_and_before_preview_are_owner_csrf_revision_and_hash_guarded(application):
    app, manager, provider = application
    client = app.test_client(); login(client)
    identifier = upload(client).json["id"]
    manager.futures[identifier].result(20)
    state = call(client, f"/api/material/jobs/{identifier}").json
    item = state["items"][0]
    endpoint = f"/api/material/jobs/{identifier}/refine"
    payload = {"expected_revision": state["revision"], "item_id": item["id"]}
    assert call(client, endpoint, method="POST", payload=payload, token=None).status_code == 403
    assert call(client, endpoint, method="POST", payload={**payload, "instruction": "unexpected"}).status_code == 400
    other = app.test_client(); login(other)
    assert call(other, endpoint, method="POST", payload=payload).status_code == 404
    accepted = call(client, endpoint, method="POST", payload=payload)
    assert accepted.status_code == 200
    manager.futures[identifier].result(20)
    assert provider.calls == 3  # Two source extractions plus one refinement.
    current = call(client, f"/api/material/jobs/{identifier}").json
    refined = next(row for row in current["items"] if row["refined"])
    assert len(current["items"]) == 2 and refined["downloadable"]
    assert call(client, endpoint, method="POST", payload=payload).status_code == 409
    before = refined["previous_image"]["image_url"]
    assert call(other, before).status_code == 404
    assert call(client, item["image_url"]).status_code == 404
    response = call(client, before)
    assert response.status_code == 200 and "private" in response.headers["Cache-Control"]
    cached = call(client, before, headers={"If-None-Match": response.headers["ETag"]})
    assert cached.status_code == 304
    assert call(client, refined["previous_image"]["thumbnail_url"]).status_code == 200
    assert call(client, before + "?variant=unknown").status_code == 400
    assert call(client, before + "?variant=thumb&variant=full").status_code == 400
    path = manager._directory(identifier) / (refined["id"] + ".png")
    path.write_bytes(b"changed")
    assert call(client, before, headers={"If-None-Match": response.headers["ETag"]}).status_code == 400


def test_duplicate_upload_request_does_not_repeat_provider_work(application):
    app, manager, provider = application
    client = app.test_client(); login(client)
    request_id = uuid.uuid4().hex
    identifier = upload(client, request_id=request_id).json["id"]
    manager.futures[identifier].result(20)
    duplicate = upload(client, request_id=request_id)
    assert duplicate.json == {"id": identifier, "reused": True}
    assert provider.calls == 2


def test_upload_cancel_and_foreign_claim_ownership(application):
    app, manager, provider = application
    client = app.test_client(); login(client)
    request_id = uuid.uuid4().hex
    stopped = call(client, f"/api/material/upload-status/{request_id}/cancel", method="POST", payload={})
    assert stopped.json["state"] == "cancelled"
    assert upload(client, request_id=request_id).status_code == 409
    other = app.test_client(); login(other)
    assert call(other, f"/api/material/upload-status/{request_id}").status_code == 404
    assert provider.calls == 0


def test_material_task_identifier_not_treated_as_numbering_job(application):
    app, manager, provider = application
    client = app.test_client(); login(client)
    identifier = upload(client).json["id"]
    manager.futures[identifier].result(20)
    assert identifier not in app.config["HSD_MANAGER"].jobs
    assert call(client, f"/api/material/jobs/{identifier}").status_code == 200
    assert call(client, f"/api/jobs/{identifier}").status_code == 404


def test_host_cannot_exit_during_material_work_or_transfer(application, monkeypatch):
    app, manager, _ = application
    monkeypatch.setattr(manager, "has_active_operations", lambda: True)
    client = app.test_client()
    response = client.post("/api/shutdown", json={}, base_url="http://127.0.0.1:8805",
        headers={"X-HSD-Token": TOKEN, "Origin": "http://127.0.0.1:8805"},
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert response.status_code == 400
    assert not app.config["HSD_STOPPING"]


def test_cloud_material_owner_recovers_after_relogin_and_restart(tmp_path, monkeypatch):
    from hsd_tool.cloud_server import CloudAccess
    from test_cloud_server import ORIGIN as cloud_origin, CODE as cloud_code, TOKEN as cloud_token, cloud_request, login as cloud_login
    monkeypatch.delenv("HSD_CREDENTIAL_KEY_FILE", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = Provider()
    def make_app():
        app = create_app(tmp_path / "data", token=cloud_token, cloud=CloudAccess(cloud_origin, cloud_code),
                         settings_dir=tmp_path / "settings")
        app.config.update(TESTING=True, HSD_RETENTION=SimpleNamespace(register=lambda identifier: None))
        material = app.config["HSD_MATERIAL_MANAGER"]
        material.settings, material.quality_hook = Settings(), None
        material.provider_factory = lambda config: provider
        material.ai_settings = None  # Synthetic provider, no real external requests.
        return app
    app = make_app(); client = app.test_client(); cloud_login(client)
    identifier = None
    request_id = uuid.uuid4().hex
    try:
        response = cloud_request(client, "/api/material/jobs", method="POST", proxy_headers={"X-HSD-Upload-ID": request_id},
              data={"files": (BytesIO(png()), "原图.png")}, content_type="multipart/form-data")
        assert response.status_code == 200, response.json
        identifier = response.json["id"]
        app.config["HSD_MATERIAL_MANAGER"].futures[identifier].result(20)
        before = cloud_request(client, f"/api/material/jobs/{identifier}").json
        store = app.config["HSD_UPLOAD_CLAIMS"]
        recovery = client.get_cookie(store.cookie_name, domain="hsd.example.test")
        assert recovery
        # A new employee session in this same browser keeps the private owner.
        cloud_login(client)
        assert cloud_request(client, f"/api/material/jobs/{identifier}").json["id"] == identifier
        stranger = app.test_client(); cloud_login(stranger)
        assert cloud_request(stranger, before["sources"][0]["image_url"]).status_code == 404
    finally:
        app.config["HSD_MATERIAL_MANAGER"].close(); app.config["HSD_MANAGER"].close()
    restarted = make_app()
    try:
        recovered = restarted.test_client()
        recovered.set_cookie(restarted.config["HSD_UPLOAD_CLAIMS"].cookie_name, recovery.value,
                             domain="hsd.example.test", secure=True, httponly=True)
        cloud_login(recovered)
        after = cloud_request(recovered, f"/api/material/jobs/{identifier}")
        assert after.status_code == 200 and after.json["items"] == before["items"]
        claim = cloud_request(recovered, f"/api/material/upload-status/{request_id}")
        assert claim.json == {"state": "completed", "job_id": identifier}
        assert provider.calls == 1
    finally:
        restarted.config["HSD_MATERIAL_MANAGER"].close(); restarted.config["HSD_MANAGER"].close()
