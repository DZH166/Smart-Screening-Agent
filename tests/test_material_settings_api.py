"""Material preparation remains an independent, authenticated admin facility."""
import pytest
import os

from hsd_tool import server
from hsd_tool.material_settings import MaterialSettings
from test_admin_settings_api import settings_app, call, login_admin

API = "/api/admin/material-settings"
MODEL = "doubao-seedream-synthetic-test"
KEY = "synthetic-ark-secret-not-a-real-key"


class SyntheticProtector:
    def encrypt(self, value):
        return b"synthetic-encrypted:" + value[::-1]

    def decrypt(self, value):
        assert value.startswith(b"synthetic-encrypted:")
        return value[len(b"synthetic-encrypted:"):][::-1]


@pytest.fixture(autouse=True)
def private_store(monkeypatch):
    def build(folder):
        # This fixture substitutes encryption only; it still supplies the same
        # private settings-directory mode required by the real Linux host.
        if os.name == "posix":
            folder.chmod(0o700)
        return MaterialSettings(folder, protector=SyntheticProtector(), environ={})
    monkeypatch.setattr(server, "MaterialSettings", build)


def get(context, client, path=API):
    return call(context, client, path, method="GET")


def post(context, client, payload, **options):
    payload = {"provider": "volcengine_ark", **payload}
    if payload.get("action") == "set_config":
        payload.setdefault("model_id", MODEL)
    return call(context, client, API, payload=payload, **options)


def test_employee_and_anonymous_cannot_configure_material_service(settings_app):
    c = settings_app
    browser = c.app.test_client()
    for path in (API, "/static/material-settings.js", "/static/material-settings.html"):
        assert get(c, browser, path).status_code == 401
    assert '管理员登录'.encode() in get(c, browser, "/admin/material").data
    if c.mode != "local":
        assert call(c, browser, "/api/lan/login", payload={"code": "synthetic-admin-settings-employee-code"}).status_code == 200
    assert post(c, browser, {"action": "set_config", "api_key": KEY, "expected_revision": 0}).status_code == 401


def test_admin_key_is_saved_without_echo_or_changing_deepseek(settings_app):
    c = settings_app
    browser = c.app.test_client()
    login_admin(c, browser)
    page = get(c, browser, "/admin/material")
    assert page.status_code == 200 and b"window.HSD_TOKEN" in page.data
    assert get(c, browser, "/static/material-settings.js").status_code == 200
    before = c.app.config["HSD_MANAGER"].ai_settings.runtime()
    response = post(c, browser, {"action": "set_config", "api_key": KEY, "expected_revision": 0})
    assert response.status_code == 200
    value = response.json
    assert set(value["settings"]) == {"provider", "model_id", "enabled", "configured", "revision", "warning", "key_persistence"}
    assert value["settings"]["configured"] and not value["validation_ready"]
    assert KEY.encode() not in response.data and "no-store" in response.headers["Cache-Control"]
    assert c.app.config["HSD_MATERIAL_SETTINGS"].runtime()["ark_key"] == KEY
    assert c.app.config["HSD_MANAGER"].ai_settings.runtime() == before
    assert c.app.config["HSD_MANAGER"].jobs == {}


def test_revision_protects_enable_remove_and_stale_pages(settings_app):
    c = settings_app
    browser = c.app.test_client()
    login_admin(c, browser)
    def change(action, revision, **fields):
        return post(c, browser, {"action": action, "expected_revision": revision, **fields})
    created = change("set_config", 0, api_key=KEY)
    assert created.status_code == 200
    revision = created.json["settings"]["revision"]
    assert change("remove_key", 0).status_code == 409
    enabled = change("set_enabled", revision, enabled=True)
    assert enabled.status_code == 200 and enabled.json["settings"]["enabled"]
    deleted = change("remove_key", enabled.json["settings"]["revision"])
    assert deleted.status_code == 200
    assert not deleted.json["settings"]["configured"] and not deleted.json["settings"]["enabled"]


@pytest.mark.parametrize("bad", ({}, {"action": []}, {"action": "anything", "expected_revision": 0},
    {"action": "set_config", "api_key": KEY, "expected_revision": 0, "endpoint": "https://untrusted.invalid"},
    {"action": "set_enabled", "enabled": "yes", "expected_revision": 0},
    {"action": "remove_key", "expected_revision": True}))
def test_invalid_settings_are_rejected(settings_app, bad):
    c = settings_app
    browser = c.app.test_client()
    login_admin(c, browser)
    assert post(c, browser, bad).status_code == 400
    assert not get(c, browser).json["settings"]["configured"]


def test_origin_token_and_admin_logout_still_apply(settings_app):
    c = settings_app
    browser = c.app.test_client()
    login_admin(c, browser)
    payload = {"action": "set_config", "api_key": KEY, "expected_revision": 0}
    assert post(c, browser, payload, origin="https://wrong.invalid").status_code == 403
    assert post(c, browser, payload, token=None).status_code == 403
    assert post(c, browser, payload, origin=None).status_code in {400, 403}
    assert call(c, browser, "/admin/logout", payload={}).status_code == 200
    assert get(c, browser).status_code == 401


def test_old_fal_page_and_other_provider_cannot_save_ark_configuration(settings_app):
    c = settings_app
    browser = c.app.test_client()
    login_admin(c, browser)
    for payload in (
        {"action": "set_key", "api_key": KEY, "expected_revision": 0},
        {"action": "set_config", "api_key": KEY, "model_id": MODEL, "expected_revision": 0},
        {"provider": "fal", "action": "set_config", "api_key": KEY, "model_id": MODEL, "expected_revision": 0},
    ):
        assert call(c, browser, API, payload=payload).status_code == 400
    assert not get(c, browser).json["settings"]["configured"]


def test_model_only_edit_keeps_secret_and_no_jobs_are_started(settings_app):
    c = settings_app
    browser = c.app.test_client()
    login_admin(c, browser)
    result = post(c, browser, {"action": "set_config", "api_key": KEY, "model_id": MODEL, "expected_revision": 0})
    revision = result.json["settings"]["revision"]
    result = post(c, browser, {"action": "set_config", "api_key": "", "model_id": "ep-synthetic-image", "expected_revision": revision})
    assert result.status_code == 200
    assert result.json["settings"]["provider"] == "volcengine_ark"
    assert result.json["settings"]["model_id"] == "ep-synthetic-image"
    assert KEY.encode() not in result.data
    assert c.app.config["HSD_MATERIAL_SETTINGS"].runtime()["ark_key"] == KEY
    assert not result.json["validation_ready"] and not c.app.config["HSD_MANAGER"].jobs
    page = get(c, browser, "/admin/material").data
    assert '火山方舟'.encode() in page and b'fal API Key' not in page


def test_reveal_requires_admin_page_token_and_valid_origin(settings_app):
    c = settings_app
    browser = c.app.test_client()
    path = "/api/admin/material-key?revision=1"
    assert get(c, browser, path).status_code == 401
    if c.mode != "local":
        assert call(c, browser, "/api/lan/login", payload={"code": "synthetic-admin-settings-employee-code"}).status_code == 200
        assert get(c, browser, path).status_code == 401
    login_admin(c, browser)
    assert post(c, browser, {"action": "set_config", "api_key": KEY, "expected_revision": 0}).status_code == 200
    for options in ({"token": None}, {"token": "wrong"}, {"origin": "https://wrong.invalid"}):
        rejected = call(c, browser, path, method="GET", **options)
        assert rejected.status_code == 403 and KEY.encode() not in rejected.data
    result = get(c, browser, path)
    assert result.status_code == 200
    assert result.json == {"provider": "volcengine_ark", "revision": 1, "api_key": KEY}
    assert result.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in result.headers
    assert KEY.encode() not in get(c, browser).data
    assert call(c, browser, "/admin/logout", payload={}).status_code == 200
    assert get(c, browser, path).status_code == 401


@pytest.mark.parametrize("query", ["", "?revision=true", "?revision=-1", "?revision=1&revision=1",
    "?revision=0&other=1", "?revision=" + "9" * 40])
def test_bad_reveal_query_is_rejected_without_a_secret(settings_app, query):
    c = settings_app
    browser = c.app.test_client()
    login_admin(c, browser)
    assert get(c, browser, "/api/admin/material-key" + query).status_code == 400


def test_reveal_is_readonly_and_cannot_return_a_rotated_or_removed_key(settings_app):
    c = settings_app
    browser = c.app.test_client()
    login_admin(c, browser)
    store = c.app.config["HSD_MATERIAL_SETTINGS"]
    store.save_ark_key(KEY, model_id=MODEL, expected_revision=0)
    before = store.path.read_bytes()
    assert get(c, browser, "/api/admin/material-key?revision=1").json["api_key"] == KEY
    assert store.path.read_bytes() == before and store.snapshot()["revision"] == 1
    second = "synthetic-second-ark-key-not-real"
    store.save_ark_key(second, expected_revision=1)
    stale = get(c, browser, "/api/admin/material-key?revision=1")
    assert stale.status_code == 409 and KEY.encode() not in stale.data and second.encode() not in stale.data
    assert get(c, browser, "/api/admin/material-key?revision=2").json["api_key"] == second
    store.remove_ark_key(expected_revision=2)
    missing = get(c, browser, "/api/admin/material-key?revision=3")
    assert missing.status_code == 400 and second.encode() not in missing.data
    assert c.app.config["HSD_MANAGER"].jobs == {}
