"""The admin console requires its own account and works from any LAN computer."""
from pathlib import Path

import pytest

from hsd_tool import admin_auth
from hsd_tool.server import create_app

ACCOUNT = "15159156156"
# Tests never embed the real password. Flow tests stub verification; the stored
# digest is checked only when a local, git-ignored copy of the secret exists.
LOCAL_SECRET = Path(__file__).with_name(".admin-password")
ORIGIN = "http://localhost"
ADMIN_PAGES = ("/admin", "/api/admin/overview", "/api/admin/debug")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    application = create_app(tmp_path / "data", token="admin-login-token-not-real")
    application.config.update(TESTING=True)
    yield application
    application.config["HSD_MANAGER"].close()


@pytest.fixture
def stub_credentials(monkeypatch):
    monkeypatch.setattr(admin_auth, "verify_credentials",
                        lambda username, password: (username, password) == (ACCOUNT, "stub-password"))


def post_login(client, username=ACCOUNT, password="stub-password", origin=ORIGIN):
    return client.post("/admin/login", json={"username": username, "password": password},
                       headers={"Origin": origin} if origin else {})


def test_admin_page_serves_the_login_form_when_signed_out(app):
    response = app.test_client().get("/admin")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert '<form id="login"' in page
    assert "API Key" not in page


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_endpoints_are_closed_before_login(app, path):
    response = app.test_client().get(path)
    if path.startswith("/api/admin/"):
        assert response.status_code == 401
    else:
        assert response.status_code == 200 and '<form id="login"' in response.get_data(as_text=True)


def test_correct_credentials_open_the_console(app, stub_credentials):
    client = app.test_client()
    assert post_login(client).status_code == 200
    response = client.get("/admin")
    page = response.get_data(as_text=True)
    assert "API Key" in page and "退出登录" in page and "Key 账本" in page
    assert client.get("/api/admin/overview").status_code == 200
    # The page must say which build it came from and load versioned assets, so an
    # old tab can be spotted instead of silently looking broken.
    build = response.headers.get("X-HSD-Build")
    assert build and "构建 " + build in page
    assert "window.HSD_BUILD = " + repr(build).replace("'", '"') in page
    assert "/static/admin.css?v=" + build in page
    assert "/static/build-check.js?v=" + build in page


def test_healthz_reports_the_running_build(app):
    response = app.test_client().get("/healthz")
    assert response.status_code == 200
    assert response.headers.get("X-HSD-Build")


def test_wrong_password_and_unknown_account_are_rejected_without_echo(app, stub_credentials):
    client = app.test_client()
    for username, password in ((ACCOUNT, "wrong-password"), ("15150000000", "stub-password"),
                               ("", ""), (None, None)):
        response = post_login(client, username, password)
        assert response.status_code in {401, 429}
        body = response.get_data(as_text=True)
        assert "stub-password" not in body and "wrong-password" not in body
    assert client.get("/api/admin/overview").status_code == 401


def test_foreign_origin_is_refused(app):
    response = post_login(app.test_client(), origin="http://evil.example")
    assert response.status_code == 403
    assert app.test_client().get("/api/admin/overview").status_code == 401


def test_session_expiry_closes_the_console(app, stub_credentials):
    client = app.test_client()
    assert post_login(client).status_code == 200
    with client.session_transaction() as stored:
        stored[admin_auth.EXPIRY_KEY] = 1
    assert client.get("/api/admin/overview").status_code == 401


def test_logout_revokes_the_session(app, stub_credentials):
    client = app.test_client()
    assert post_login(client).status_code == 200
    response = client.post("/admin/logout", json={},
                           headers={"X-HSD-Token": "admin-login-token-not-real"})
    assert response.status_code == 200
    assert client.get("/api/admin/overview").status_code == 401


def test_repeated_failures_are_throttled(app, stub_credentials):
    client = app.test_client()
    for _ in range(admin_auth.MAX_ATTEMPTS):
        assert post_login(client, password="wrong-password").status_code == 401
    assert post_login(client).status_code == 429


def test_verifier_rejects_non_credentials_and_never_raises():
    for username, password in ((None, None), ("", ""), (ACCOUNT, ""), ("", "x"),
                               (ACCOUNT, "x" * 300), (ACCOUNT, "有中文")):
        assert admin_auth.verify_credentials(username, password) is False


@pytest.mark.skipif(not LOCAL_SECRET.is_file(), reason="本机没有保存管理员口令的本地副本")
def test_stored_digest_accepts_the_real_password_only():
    password = LOCAL_SECRET.read_text("utf-8").strip()
    assert admin_auth.verify_credentials(ACCOUNT, password) is True
    assert admin_auth.verify_credentials(ACCOUNT, password + " ") is False
    assert admin_auth.verify_credentials(ACCOUNT + " ", password) is False
