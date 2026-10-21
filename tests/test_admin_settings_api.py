"""Only authenticated administrators may change the shared AI switch.

Generated credentials only; no provider requests, real keys or qualifications.
"""
from types import SimpleNamespace

import pytest

from hsd_tool import admin_auth
from hsd_tool.cloud_server import CloudAccess
from hsd_tool.lan import LanAccess
from hsd_tool.server import create_app


TOKEN = "synthetic-admin-settings-token"
CODE = "synthetic-admin-settings-employee-code"
USERNAME = "synthetic-operator"
PASSWORD = "synthetic-password"
ENDPOINT = "/api/admin/settings"


@pytest.fixture(params=["cloud", "lan", "local"])
def settings_app(request, tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("HSD_CREDENTIAL_KEY_FILE", raising=False)
    monkeypatch.setattr(admin_auth, "verify_credentials", lambda name, secret: (name, secret) == (USERNAME, PASSWORD))
    mode = request.param
    options = {}
    if mode == "cloud":
        origin, peer = "https://hsd.example.test:8443", "127.0.0.1"
        credentials = SimpleNamespace(verify=admin_auth.verify_credentials)
        options["cloud"] = CloudAccess(origin, CODE, admin_credentials=credentials)
    elif mode == "lan":
        origin, peer = "http://192.168.0.160:8830", "192.168.0.25"
        inputs = tmp_path / "inputs"
        inputs.mkdir()
        options["lan"] = LanAccess("192.168.0.160/24", inputs, tmp_path / "outputs", code=CODE)
    else:
        origin, peer = "http://localhost", "127.0.0.1"
    app = create_app(tmp_path / "data", token=TOKEN, settings_dir=tmp_path / "settings", **options)
    app.config.update(TESTING=True)
    if mode == "lan":
        app.config["HSD_PORT"] = 8830
    yield SimpleNamespace(app=app, origin=origin, peer=peer, mode=mode)
    app.config["HSD_MANAGER"].close()


def call(context, client, path=ENDPOINT, *, payload=None, token=TOKEN, origin=True, method="POST"):
    headers = {}
    if token is not None:
        headers["X-HSD-Token"] = token
    if origin is True:
        headers["Origin"] = context.origin
    elif origin is not None:
        headers["Origin"] = origin
    if context.mode == "cloud":
        headers.update({"X-Forwarded-For": "203.0.113.25", "X-Forwarded-Proto": "https"})
    return client.open(path, method=method, base_url=context.origin, headers=headers,
        environ_overrides={"REMOTE_ADDR": context.peer},
        **({"json": payload, "content_type": "application/json"} if method == "POST" else {}))


def login_admin(context, client):
    result = call(context, client, "/admin/login", payload={"username": USERNAME, "password": PASSWORD})
    assert result.status_code == 200


def payload_for(context, *, enabled=True):
    return {"enabled": enabled, "expected_revision": context.app.config["HSD_MANAGER"].ai_settings.snapshot()["key_revision"]}


def test_anonymous_and_employee_cannot_change_shared_ai_switch(settings_app):
    context = settings_app
    client = context.app.test_client()
    payload = payload_for(context)
    assert call(context, client, payload=payload).status_code == 401
    if context.mode != "local":
        assert call(context, client, "/api/lan/login", payload={"code": CODE}).status_code == 200
        assert call(context, client, payload=payload).status_code == 401
    assert not context.app.config["HSD_MANAGER"].ai_settings.snapshot()["enabled"]


def test_authenticated_admin_toggle_has_revision_and_does_not_grant_employee_access(settings_app):
    context = settings_app
    client = context.app.test_client()
    login_admin(context, client)
    payload = payload_for(context)
    result = call(context, client, payload=payload)
    assert result.status_code == 200
    assert set(result.json) == {"settings", "pool"}
    assert result.json["settings"]["enabled"] is True
    assert result.json["settings"]["key_revision"] == payload["expected_revision"] + 1
    assert result.headers["Cache-Control"] == "no-store"
    assert USERNAME not in result.get_data(as_text=True) and PASSWORD not in result.get_data(as_text=True)
    stale = call(context, client, payload={"enabled": False, "expected_revision": payload["expected_revision"]})
    assert stale.status_code == 409
    assert context.app.config["HSD_MANAGER"].ai_settings.snapshot()["enabled"] is True
    current = payload_for(context, enabled=False)
    result = call(context, client, payload=current)
    assert result.status_code == 200 and result.json["settings"]["enabled"] is False
    assert result.json["settings"]["key_revision"] == current["expected_revision"] + 1
    if context.mode != "local":
        assert call(context, client, "/api/config", method="GET").status_code == 401
        assert call(context, client, "/api/ai/settings", payload={"enabled": True}).status_code in {401, 403}


@pytest.mark.parametrize("payload", [
    {}, {"enabled": True}, {"expected_revision": 0}, {"enabled": "true", "expected_revision": 0},
    {"enabled": 1, "expected_revision": 0}, {"enabled": None, "expected_revision": 0},
    {"enabled": True, "expected_revision": False}, {"enabled": True, "expected_revision": -1},
    {"enabled": True, "expected_revision": 1.0}, {"enabled": True, "expected_revision": "0"},
    {"enabled": True, "expected_revision": 0, "api_key": "synthetic-must-not-be-saved"},
    {"enabled": True, "expected_revision": 0, "clear_key": True},
    {"enabled": True, "expected_revision": 0, "mode": "validated"}, [], None,
])
def test_admin_settings_rejects_invalid_fields_without_saving(settings_app, monkeypatch, payload):
    context = settings_app
    client = context.app.test_client()
    login_admin(context, client)
    saves = []
    monkeypatch.setattr(context.app.config["HSD_MANAGER"].ai_settings, "save", lambda payload: saves.append(payload))
    result = call(context, client, payload=payload)
    assert result.status_code == 400 and saves == []
    assert "synthetic-must-not-be-saved" not in result.get_data(as_text=True)


@pytest.mark.parametrize("token,origin", [(None, True), ("wrong", True), (TOKEN, None),
    (TOKEN, "https://evil.example.test"), (TOKEN, "null")])
def test_admin_switch_requires_csrf_and_exact_origin(settings_app, token, origin):
    context = settings_app
    client = context.app.test_client()
    login_admin(context, client)
    result = call(context, client, payload=payload_for(context), token=token, origin=origin)
    assert result.status_code == 403
    assert not context.app.config["HSD_MANAGER"].ai_settings.snapshot()["enabled"]


@pytest.mark.parametrize("status", ["queued", "importing", "matching", "ai_review", "exporting"])
def test_busy_employees_block_admin_switch(settings_app, monkeypatch, status):
    context = settings_app
    manager = context.app.config["HSD_MANAGER"]
    manager.jobs["synthetic-other-employee"] = {"status": status, "_owner_id": "another-browser"}
    client = context.app.test_client()
    login_admin(context, client)
    saves = []
    monkeypatch.setattr(manager.ai_settings, "save", lambda payload: saves.append(payload))
    result = call(context, client, payload=payload_for(context))
    assert result.status_code == 400 and "正在处理" in result.json["error"]
    assert saves == []


def test_failed_settings_write_is_not_reported_as_success(settings_app, monkeypatch):
    context = settings_app
    client = context.app.test_client()
    login_admin(context, client)
    def fail(payload):
        raise ValueError("本次设置未保存")
    monkeypatch.setattr(context.app.config["HSD_MANAGER"].ai_settings, "save", fail)
    result = call(context, client, payload=payload_for(context))
    assert result.status_code == 400 and "未保存" in result.json["error"]
    assert not context.app.config["HSD_MANAGER"].ai_settings.snapshot()["enabled"]
