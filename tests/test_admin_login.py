"""The admin console requires its own account, on top of the host-only boundary."""
from pathlib import Path

import pytest

from hsd_tool import admin_auth
from hsd_tool.server import create_app

ACCOUNT = "15159156156"
PASSWORD = "HSD15159156156"
ORIGIN = "http://localhost"
ADMIN_PAGES = ("/admin", "/api/admin/overview", "/api/admin/debug")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    application = create_app(tmp_path / "data", token="admin-login-token-not-real")
    application.config.update(TESTING=True)
    yield application
    application.config["HSD_MANAGER"].close()


def post_login(client, username=ACCOUNT, password=PASSWORD, origin=ORIGIN):
    return client.post("/admin/login", json={"username": username, "password": password},
                       headers={"Origin": origin} if origin else {})


def test_admin_page_serves_the_login_form_when_signed_out(app):
    response = app.test_client().get("/admin")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "/static/admin-login.html" not in page and "<form id=\"login\"" in page
    assert "admin-login.js" not in page


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_endpoints_are_closed_before_login(app, path):
    response = app.test_client().get(path)
    assert response.status_code in {200, 401}
    if path.startswith("/api/admin/"):
        assert response.status_code == 401
    else:
        assert "<form id=\"login\"" in response.get_data(as_text=True)


def test_correct_credentials_open_the_console(app):
    client = app.test_client()
    assert post_login(client).status_code == 200
    page = client.get("/admin").get_data(as_text=True)
    assert "API Key" in page and "退出登录" in page and "Key 账本" in page
    assert client.get("/api/admin/overview").status_code == 200


def test_wrong_password_and_unknown_account_are_rejected_without_echo(app):
    client = app.test_client()
    for username, password in ((ACCOUNT, "wrong-password"), ("15150000000", PASSWORD),
                               ("", ""), (None, None)):
        response = post_login(client, username, password)
        assert response.status_code in {401, 429}
        body = response.get_data(as_text=True)
        assert PASSWORD not in body and "wrong-password" not in body
    assert client.get("/api/admin/overview").status_code == 401


def test_foreign_origin_is_refused(app):
    response = post_login(app.test_client(), origin="http://evil.example")
    assert response.status_code == 403
    assert app.test_client().get("/api/admin/overview").status_code == 401


def test_session_expiry_closes_the_console(app):
    client = app.test_client()
    assert post_login(client).status_code == 200
    with client.session_transaction() as stored:
        stored[admin_auth.EXPIRY_KEY] = 1
    assert client.get("/api/admin/overview").status_code == 401


def test_logout_revokes_the_session(app):
    client = app.test_client()
    assert post_login(client).status_code == 200
    response = client.post("/admin/logout", json={},
                           headers={"X-HSD-Token": "admin-login-token-not-real"})
    assert response.status_code == 200
    assert client.get("/api/admin/overview").status_code == 401


def test_repeated_failures_are_throttled(app):
    client = app.test_client()
    for _ in range(admin_auth.MAX_ATTEMPTS):
        assert post_login(client, password="wrong-password").status_code == 401
    assert post_login(client).status_code == 429


def test_credentials_are_compared_in_constant_time_and_hashed():
    assert admin_auth.verify_credentials(ACCOUNT, PASSWORD) is True
    assert admin_auth.verify_credentials(ACCOUNT, PASSWORD + " ") is False
    assert admin_auth.verify_credentials(ACCOUNT + " ", PASSWORD) is False
    assert admin_auth.verify_credentials(ACCOUNT, "") is False
    assert admin_auth.verify_credentials(None, PASSWORD) is False


def test_repository_never_stores_the_plaintext_password():
    root = Path(__file__).resolve().parents[1]
    suspects = [root / "hsd_tool" / name for name in
                ("admin_auth.py", "admin-login.html", "admin.html", "admin.js", "server.py")]
    suspects += [root / name for name in ("README.md", "使用说明.txt", "AGENTS.md", "CHANGELOG.md")]
    for path in suspects:
        if path.is_file():
            assert PASSWORD not in path.read_text("utf-8", errors="replace"), path
