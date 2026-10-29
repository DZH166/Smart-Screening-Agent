"""Legacy demo stays read-only; the employee shell hosts real material work."""
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest

from hsd_tool import admin_auth, material_demo
from hsd_tool.cloud_server import CloudAccess
from hsd_tool.lan import LanAccess
from hsd_tool.server import create_app


CODE = "synthetic-material-employee-code"
TOKEN = "synthetic-material-token-not-real"
ADMIN = "synthetic-demo-admin"
PASSWORD = "synthetic-demo-password-not-real"


@pytest.fixture(params=("desktop", "lan", "cloud"))
def demo(request, tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("HSD_CREDENTIAL_KEY_FILE", raising=False)
    mode = request.param
    options = {}
    origin, address = "http://127.0.0.1:8874", "127.0.0.1"
    if mode == "lan":
        source = tmp_path / "source"
        source.mkdir()
        options["lan"] = LanAccess("192.168.0.160/24", source, tmp_path / "output", code=CODE)
        origin, address = "http://192.168.0.160:8874", "192.168.0.25"
    elif mode == "cloud":
        origin = "https://material.example.test"
        credentials = SimpleNamespace(verify=lambda username, password: (username, password) == (ADMIN, PASSWORD))
        options["cloud"] = CloudAccess(origin, CODE, admin_credentials=credentials)
    monkeypatch.setattr(admin_auth, "verify_credentials", lambda username, password: (username, password) == (ADMIN, PASSWORD))
    app = create_app(tmp_path / "state", token=TOKEN, settings_dir=tmp_path / "settings", **options)
    app.config.update(TESTING=True)
    client = app.test_client()

    def call(path, *, method="GET", payload=None, peer=None, headers=None):
        outgoing = {"Origin": origin, "X-HSD-Token": TOKEN}
        if mode == "cloud":
            outgoing.update({"X-Forwarded-For": "203.0.113.25", "X-Forwarded-Proto": "https"})
        outgoing.update(headers or {})
        return client.open(path, method=method, base_url=origin, headers=outgoing,
                           environ_overrides={"REMOTE_ADDR": peer or address},
                           **({"json": payload} if payload is not None else {}))

    def login():
        if mode != "desktop":
            assert call("/api/lan/login", method="POST", payload={"code": CODE}).status_code == 200

    yield SimpleNamespace(mode=mode, app=app, call=call, login=login, client=client, origin=origin)
    app.config["HSD_MANAGER"].close()


@pytest.mark.parametrize("path", ("/material-demo", "/material-demo/", "/material-demo/index.html"))
def test_direct_demo_link_uses_existing_employee_login_and_keeps_url(demo, path):
    response = demo.call(path)
    if demo.mode == "desktop":
        assert response.status_code in {200, 308}
    else:
        html = response.get_data(as_text=True)
        assert response.status_code == 200 and '<form id="login"' in html
        assert "素材提取（demo内测）" in html and "不调用 AI，也不上传文件" in html
        assert "location.reload()" in html
        assert 'data-hosted="true"' not in html and TOKEN not in html
        assert "connect-src 'self'" in response.headers["Content-Security-Policy"]
    demo.login()
    result = demo.call(path)
    if path == "/material-demo":
        assert result.status_code == 308 and result.headers["Location"] == "/material-demo/"
        result = demo.call(result.headers["Location"])
    assert result.status_code == 200
    assert 'data-hosted="true"' in result.get_data(as_text=True)


def test_assets_do_not_bypass_login_even_if_the_path_is_known(demo):
    if demo.mode == "desktop":
        pytest.skip("desktop is already restricted to its local host")
    for filename in material_demo.FILES:
        if filename == "index.html":
            continue
        response = demo.call("/material-demo/" + filename)
        assert response.status_code == 401
        assert not response.content_type.startswith(("image/", "text/css", "text/javascript"))
    assert demo.call("/material-demo/", method="HEAD").status_code == 401


def test_admin_login_alone_does_not_grant_employee_or_demo_access(demo):
    if demo.mode == "desktop":
        pytest.skip("host does not need an employee access code")
    assert demo.call("/admin/login", method="POST", payload={"username": ADMIN, "password": PASSWORD}).status_code == 200
    assert demo.call("/material-demo/demo.js").status_code == 401
    assert '<form id="login"' in demo.call("/material-demo/").get_data(as_text=True)
    assert demo.call("/api/config").status_code == 401


def test_allowlisted_files_have_correct_types_and_separate_browser_policy(demo):
    demo.login()
    for filename, expected_type in material_demo.FILES.items():
        response = demo.call("/material-demo/" + filename)
        assert response.status_code == 200 and response.mimetype == expected_type
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Content-Security-Policy"] == material_demo.CSP
        assert TOKEN.encode() not in response.data and CODE.encode() not in response.data
        if filename != "index.html":
            assert response.data == (material_demo.ROOT / filename).read_bytes()
        head = demo.call("/material-demo/" + filename, method="HEAD")
        assert head.status_code == 200 and not head.data
    original = demo.call("/")
    policy = original.headers["Content-Security-Policy"]
    assert "img-src 'self' data: blob:;" in policy
    assert "default-src 'self';" in policy
    assert "connect-src 'self';" in policy
    assert "frame-ancestors 'none';" in policy
    assert "blob:" not in policy.split("script-src ", 1)[1].split(";", 1)[0]


def test_employee_navigation_enters_real_material_workspace_on_the_same_page(demo):
    demo.login()
    response = demo.call("/")
    assert response.status_code == 200

    class EmployeeMarkup(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links, self.ids, self.scripts = {}, set(), []

        def handle_starttag(self, tag, attributes):
            attributes = dict(attributes)
            if attributes.get("id"):
                self.ids.add(attributes["id"])
            if tag == "a" and attributes.get("data-workspace"):
                self.links[attributes["data-workspace"]] = attributes
            if tag == "script" and attributes.get("src"):
                self.scripts.append(attributes["src"])

    markup = EmployeeMarkup()
    markup.feed(response.get_data(as_text=True))
    assert set(markup.links) == {"numbering", "material", "ribbon"}
    assert markup.links["numbering"]["href"] == "#numbering"
    assert markup.links["material"]["href"] == "#material"
    assert markup.links["ribbon"]["href"] == "#ribbon"
    assert all(link.get("target") != "_blank" for link in markup.links.values())
    assert {"numbering-workspace", "material-workspace", "import-form",
            "material-upload-form", "material-files", "material-stop",
            "material-results", "ribbon-workspace", "ribbon-mount"} <= markup.ids
    assert markup.scripts.count("/static/app.js") == 1
    assert markup.scripts.count("/static/material.js") == 1
    assert markup.scripts.count("/static/ribbon-loader.js") == 1
    assert "/static/ribbon/ribbon.js" not in markup.scripts, "ribbon bundle loads only when its workspace opens"
    # Keep the old synthetic demo available only through its separate,
    # authenticated read-only route; it is no longer the normal feature link.
    legacy = demo.call("/material-demo/")
    assert legacy.status_code == 200
    assert 'data-hosted="true"' in legacy.get_data(as_text=True)
    assert legacy.headers["Content-Security-Policy"] == material_demo.CSP


def test_selected_file_blob_policy_does_not_expand_admin_or_api_permissions(demo):
    demo.login()
    assert demo.call("/admin/login", method="POST",
                     payload={"username": ADMIN, "password": PASSWORD}).status_code == 200
    for path in ("/admin", "/admin/material", "/api/config", "/api/material/config",
                 "/api/admin/material-settings"):
        response = demo.call(path)
        assert response.status_code == 200
        policy = response.headers["Content-Security-Policy"]
        assert "blob:" not in policy
        assert "connect-src 'self';" in policy
        assert "frame-ancestors 'none';" in policy
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("suffix", (
    "README.md", "../README.md", "%2e%2e/README.md", "assets/../../AGENTS.md",
    "assets/%2e%2e/%2e%2e/AGENTS.md", "assets\\source-sheet.svg", "demo.js:README.md",
    "assets", "assets/", "assets/source-sheet.svg/extra", "assets/unknown.svg", ".git/config",
))
def test_extra_files_and_traversal_are_not_served(demo, suffix):
    demo.login()
    result = demo.call("/material-demo/" + suffix)
    assert result.status_code == 404
    assert str(material_demo.ROOT) not in result.get_data(as_text=True)


@pytest.mark.parametrize("method", ("POST", "PUT", "PATCH", "DELETE"))
@pytest.mark.parametrize("path", ("/material-demo/", "/material-demo/demo.js", "/material-demo/assets/cherry.svg"))
def test_demo_methods_never_mutate_jobs_or_configuration(demo, monkeypatch, method, path):
    demo.login()
    manager = demo.app.config["HSD_MANAGER"]

    def forbidden(*args, **kwargs):
        pytest.fail("read-only material demo touched a job, AI settings, or a provider")

    for name in ("create", "snapshot", "ai_config", "cancel"):
        if hasattr(manager, name):
            monkeypatch.setattr(manager, name, forbidden)
    monkeypatch.setattr(manager.ai_settings, "save", forbidden)
    assert demo.call(path, method=method, payload={"pretend_upload": "ignored"}).status_code == 405
    assert manager.jobs == {}
    # A failed write cannot prevent a subsequent read of the demo.
    assert demo.call("/material-demo/").status_code == 200


def test_demo_does_not_change_host_or_admin_boundaries(demo):
    demo.login()
    assert demo.call("/api/admin/keys").status_code == 401
    if demo.mode == "desktop":
        assert demo.call("/material-demo/", peer="192.168.0.25").status_code == 403
    else:
        assert demo.call("/api/pick", method="POST", payload={}).status_code == 403
        assert demo.call("/api/shutdown", method="POST", payload={}).status_code == 403
    assert demo.call("/material-demo/", headers={"Host": "untrusted.example.test"}).status_code == 403


def test_missing_asset_and_linked_asset_fail_closed(demo, tmp_path, monkeypatch):
    demo.login()
    root = tmp_path / "demo-root"
    root.mkdir()
    monkeypatch.setattr(material_demo, "ROOT", root)
    assert demo.call("/material-demo/demo.js").status_code == 404
    target = tmp_path / "private.txt"
    target.write_text("synthetic-private-content", encoding="utf-8")
    try:
        (root / "demo.js").symlink_to(target)
    except OSError:
        pytest.skip("OS does not permit creating synthetic symlinks")
    result = demo.call("/material-demo/demo.js")
    assert result.status_code == 404 and "synthetic-private-content" not in result.get_data(as_text=True)


def test_demo_assets_directory_cannot_link_into_other_project(demo, tmp_path, monkeypatch):
    demo.login()
    root = tmp_path / "demo-root"
    root.mkdir()
    outside = tmp_path / "other-project"
    outside.mkdir()
    (outside / "cherry.svg").write_text("synthetic-private-content", encoding="utf-8")
    try:
        (root / "assets").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not permit creating synthetic directory links")
    monkeypatch.setattr(material_demo, "ROOT", root)
    result = demo.call("/material-demo/assets/cherry.svg")
    assert result.status_code == 404 and "synthetic-private-content" not in result.get_data(as_text=True)
