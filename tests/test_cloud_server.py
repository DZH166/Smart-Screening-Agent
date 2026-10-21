"""Synthetic HTTPS/proxy and ownership checks; no provider or real secrets."""
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.test import EnvironBuilder

from hsd_tool import admin_auth
from hsd_tool.cloud_server import CloudAccess, _private_file, create_cloud_app
from hsd_tool.server import EmployeeUploadRequest, create_app
from test_employee_api import captured_jobs as base_captured_jobs, workbook_bytes, zip_bytes


ORIGIN = "https://hsd.example.test"
CODE = "synthetic-cloud-employee-code"
TOKEN = "synthetic-cloud-csrf-token"
CLIENT = "203.0.113.25"


@pytest.fixture
def employee_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("HSD_CREDENTIAL_KEY_FILE", raising=False)
    credentials = SimpleNamespace(verify=lambda username, password: admin_auth.verify_credentials(username, password))
    app = create_app(tmp_path / "data", cloud=CloudAccess(ORIGIN, CODE, admin_credentials=credentials), token=TOKEN,
                     settings_dir=tmp_path / "settings")
    app.config.update(TESTING=True)
    # Route-only fixtures never start the real retention daemon. Production
    # create_cloud_app always installs its authenticated retention manager.
    app.config["HSD_RETENTION"] = SimpleNamespace(register=lambda identifier: None)
    yield app
    app.config["HSD_MANAGER"].close()


@pytest.fixture
def captured_jobs(base_captured_jobs, employee_app, monkeypatch):
    manager = employee_app.config["HSD_MANAGER"]
    capture_create = manager.create
    def create(*args, before_submit=None, **kwargs):
        identifier = capture_create(*args, **kwargs)
        if before_submit:
            before_submit(manager._get(identifier))
        return identifier
    monkeypatch.setattr(manager, "create", create)
    return base_captured_jobs


def cloud_request(client, path, *, method="GET", peer="127.0.0.1", forwarded=CLIENT,
                  origin=ORIGIN, token=TOKEN, payload=None, proxy_headers=None, **kwargs):
    headers = {"X-Forwarded-For": forwarded, "X-Forwarded-Proto": "https"}
    if origin is not None:
        headers["Origin"] = origin
    if token is not None:
        headers["X-HSD-Token"] = token
    headers.update(proxy_headers or {})
    if payload is not None:
        kwargs["json"] = payload
    return client.open(path, method=method, base_url=ORIGIN, headers=headers,
                       environ_overrides={"REMOTE_ADDR": peer}, **kwargs)


def login(client):
    result = cloud_request(client, "/api/lan/login", method="POST", payload={"code": CODE})
    assert result.status_code == 200
    return result


@pytest.mark.parametrize("origin", ["http://hsd.example.test", "https://user:pw@hsd.example.test",
                                    "https://hsd.example.test/path", "https://hsd.example.test?x=1",
                                    "https://hsd.example.test/#x", "https://bad_host.test",
                                    "https://hsd.example.test:0", "https://hsd.example.test:65536"])
def test_public_origin_is_explicit_https_origin_only(origin):
    with pytest.raises(ValueError):
        CloudAccess(origin, CODE)


def test_cloud_never_grants_host_privileges_even_for_loopback():
    access = CloudAccess("https://HSD.example.test:443/", CODE)
    assert access.origin == ORIGIN
    for address in ("127.0.0.1", "::1", CLIENT, "192.168.0.160"):
        assert access.allows(address) and not access.is_host(address)
    assert not access.allows("bad")
    with pytest.raises(ValueError):
        access.validate_paths({})
    with pytest.raises(ValueError):
        CloudAccess(ORIGIN, "HSD")


def test_cloud_code_minimum_remains_sixteen_without_an_explicit_override():
    for code in ("demo", "x" * 15):
        with pytest.raises(ValueError, match="至少需要16位"):
            CloudAccess(ORIGIN, code)
    assert CloudAccess(ORIGIN, "x" * 16).code == "x" * 16
    assert CloudAccess(ORIGIN, "demo", min_code_length=4).code == "demo"
    assert CloudAccess(ORIGIN, "x", min_code_length=1).code == "x"
    assert CloudAccess(ORIGIN, "x" * 64, min_code_length=64).code == "x" * 64


@pytest.mark.parametrize("minimum", [True, False, None, "4", 4.0, 0, -1, 65])
def test_cloud_rejects_invalid_constructor_code_minimum(minimum):
    with pytest.raises(ValueError, match="最短长度"):
        CloudAccess(ORIGIN, CODE, min_code_length=minimum)


@pytest.mark.parametrize("code", ["", " ", "has space", "line\nbreak", "\x00bad", "非ASCII", "x" * 65])
def test_short_code_override_does_not_relax_visible_ascii_or_maximum_length(code):
    with pytest.raises(ValueError):
        CloudAccess(ORIGIN, code, min_code_length=1)


def test_short_code_override_preserves_rate_limit_and_host_boundaries(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("HSD_CREDENTIAL_KEY_FILE", raising=False)
    access = CloudAccess(ORIGIN, "demo", min_code_length=4)
    app = create_app(tmp_path / "data", cloud=access, token=TOKEN, settings_dir=tmp_path / "settings")
    try:
        client = app.test_client()
        for _ in range(10):
            assert cloud_request(client, "/api/lan/login", method="POST", payload={"code": "wrong"}).status_code == 403
        assert cloud_request(client, "/api/lan/login", method="POST", payload={"code": "demo"}).status_code == 429
        logged_in = cloud_request(client, "/api/lan/login", method="POST", payload={"code": "demo"}, forwarded="203.0.113.26")
        assert logged_in.status_code == 200 and "Secure" in logged_in.headers["Set-Cookie"]
        config = cloud_request(client, "/api/config", forwarded="127.0.0.1").json
        assert config["access"]["remote"] and "code" not in config["access"]
        for address in ("127.0.0.1", "::1", CLIENT):
            assert not access.is_host(address)
        for path in ("/api/pick", "/api/jobs", "/api/shutdown", "/api/ai/settings"):
            assert cloud_request(client, path, method="POST", payload={}, forwarded="127.0.0.1").status_code == 403
        assert cloud_request(client, "/api/admin/keys").status_code == 401
    finally:
        app.config["HSD_MANAGER"].close()


@pytest.mark.parametrize("peer,forwarded,headers", [
    (CLIENT, CLIENT, {}), ("127.0.0.1", "", {}),
    ("127.0.0.1", "127.0.0.1, 203.0.113.25", {}),
    ("127.0.0.1", "not-an-ip", {}), ("127.0.0.1", " 203.0.113.25", {}),
    ("127.0.0.1", CLIENT, {"X-Forwarded-Proto": "http"}),
    ("127.0.0.1", CLIENT, {"X-Forwarded-Proto": "https,http"}),
    ("127.0.0.1", CLIENT, {"Host": "evil.test"}),
])
def test_proxy_boundary_rejects_untrusted_peers_chains_and_host(employee_app, peer, forwarded, headers):
    result = cloud_request(employee_app.test_client(), "/", peer=peer, forwarded=forwarded,
                           proxy_headers=headers)
    assert result.status_code == 403 and TOKEN not in result.get_data(as_text=True)


def test_loopback_forwarded_client_still_needs_employee_login(employee_app):
    client = employee_app.test_client()
    result = cloud_request(client, "/", forwarded="127.0.0.1")
    assert result.status_code == 200 and "访问码" in result.get_data(as_text=True)
    assert "服务器暂存 3 天" in result.get_data(as_text=True) and "请连接公司局域网" not in result.get_data(as_text=True)
    assert TOKEN not in result.get_data(as_text=True)
    assert cloud_request(client, "/api/config", forwarded="127.0.0.1").status_code == 401
    logged_in = login(client)
    assert "Secure" in logged_in.headers["Set-Cookie"]
    assert "HttpOnly" in logged_in.headers["Set-Cookie"]
    config = cloud_request(client, "/api/config").json
    assert config["access"]["remote"] and config["access"]["upload"]
    assert "code" not in config["access"]
    assert config["access"]["upload_limits"] == {"workbook_bytes": None, "source_bytes": None, "total_bytes": None}


@pytest.mark.parametrize("path", ["/api/pick", "/api/jobs", "/api/shutdown", "/api/ai/settings"])
def test_cloud_blocks_host_machine_mutations_even_after_employee_login(employee_app, path):
    client = employee_app.test_client()
    login(client)
    result = cloud_request(client, path, method="POST", payload={})
    assert result.status_code == 403


@pytest.mark.parametrize("origin", [None, "http://hsd.example.test", "https://evil.test", "null"])
def test_https_mutations_require_exact_origin(employee_app, origin):
    result = cloud_request(employee_app.test_client(), "/api/lan/login", method="POST",
                           payload={"code": CODE}, origin=origin)
    assert result.status_code == 403


def test_forwarded_addresses_are_used_for_throttling_and_extra_proxy_fields_ignored(employee_app):
    client = employee_app.test_client()
    for _ in range(10):
        assert cloud_request(client, "/api/lan/login", method="POST", payload={"code": "wrong"}).status_code == 403
    assert cloud_request(client, "/api/lan/login", method="POST", payload={"code": CODE}).status_code == 429
    result = cloud_request(client, "/api/lan/login", method="POST", payload={"code": CODE},
                           forwarded="203.0.113.26", proxy_headers={"Forwarded": "for=127.0.0.1;proto=http",
                                                                  "X-Forwarded-Host": "evil.test"})
    assert result.status_code == 200


def test_cloud_admin_login_does_not_log_in_employee_or_grant_host_operations(employee_app, monkeypatch):
    monkeypatch.setattr(admin_auth, "verify_credentials", lambda name, secret: (name, secret) == ("synthetic-admin", "synthetic-password"))
    client = employee_app.test_client()
    for path in ("/api/admin/keys", "/api/admin/ledger", "/static/admin.js", "/static/admin.html"):
        assert cloud_request(client, path).status_code == 401
    assert cloud_request(client, "/admin/login", method="POST", payload={"username": "synthetic-admin", "password": "synthetic-password"}).status_code == 200
    assert cloud_request(client, "/api/admin/keys").status_code == 200
    assert cloud_request(client, "/api/admin/ledger").status_code == 200
    assert cloud_request(client, "/api/config").status_code == 401
    assert cloud_request(client, "/api/jobs/upload", method="POST", data={}, content_type="multipart/form-data").status_code == 401
    login(client)
    assert cloud_request(client, "/api/shutdown", method="POST", payload={}).status_code == 403


def test_cloud_has_no_builtin_admin_password_fallback(employee_app, monkeypatch):
    employee_app.wsgi_app.access.admin_credentials = None
    monkeypatch.setattr(admin_auth, "verify_credentials", lambda *args: True)
    result = cloud_request(employee_app.test_client(), "/admin/login", method="POST",
                           payload={"username": "any", "password": "any"})
    assert result.status_code == 401


def test_upload_streaming_ownership_and_request_leases(employee_app, captured_jobs, monkeypatch):
    client, other = employee_app.test_client(), employee_app.test_client()
    login(client)
    login(other)
    registered = []
    class Retention:
        register = staticmethod(registered.append)
    employee_app.config["HSD_RETENTION"] = Retention()
    original = EmployeeUploadRequest._get_file_stream
    observed = []
    def stream(self, *args, **kwargs):
        assert self.max_content_length is None
        result = original(self, *args, **kwargs)
        observed.append(result)
        return result
    monkeypatch.setattr(EmployeeUploadRequest, "_get_file_stream", stream)
    data = {"start_number": "12", "workbook": (BytesIO(workbook_bytes()), "synthetic.xlsx"),
            "source": (BytesIO(zip_bytes({"pattern.ai": b"synthetic" * 65536})), "synthetic.zip")}
    result = cloud_request(client, "/api/jobs/upload", method="POST", data=data, content_type="multipart/form-data")
    assert result.status_code == 200 and len(observed) == 2
    identifier = result.json["id"]
    assert registered == [identifier]
    assert captured_jobs[0]["owner_id"] and captured_jobs[0]["downloadable"]
    response = cloud_request(client, f"/api/jobs/{identifier}")
    assert response.status_code == 200
    assert employee_app.config["HSD_JOB_LEASES"] == {identifier: 1}
    response.close()
    response.close()
    assert employee_app.config["HSD_JOB_LEASES"] == {}
    for path in (f"/api/jobs/{identifier}", f"/api/jobs/{identifier}/image/row/r1",
                 f"/api/jobs/{identifier}/download", f"/api/jobs/{identifier}/open-output"):
        result = cloud_request(other, path, method="POST" if path.endswith("open-output") else "GET", payload={} if path.endswith("open-output") else None)
        assert result.status_code in {403, 404}
        result.close()
    assert employee_app.config["HSD_JOB_LEASES"] == {}


@pytest.mark.parametrize("failure", [OSError("synthetic-private-detail"), ValueError("暂存记录无法写入")])
def test_retention_registration_failure_cleans_upload_and_never_submits_background_work(employee_app, monkeypatch, failure):
    manager = employee_app.config["HSD_MANAGER"]
    submitted = []
    monkeypatch.setattr(manager, "_submit", lambda *args: submitted.append(args))
    def fail(identifier):
        job = manager._get(identifier)
        assert job["_upload_managed"] and Path(job["_upload_dir"]).is_dir()
        raise failure
    employee_app.config["HSD_RETENTION"] = SimpleNamespace(register=fail)
    client = employee_app.test_client()
    login(client)
    result = cloud_request(client, "/api/jobs/upload", method="POST", content_type="multipart/form-data", data={
        "start_number": "1", "workbook": (BytesIO(workbook_bytes()), "synthetic.xlsx"),
        "source": (BytesIO(zip_bytes({"pattern.ai": b"synthetic"})), "synthetic.zip")})
    assert result.status_code == 400 and "synthetic-private-detail" not in result.get_data(as_text=True)
    assert submitted == [] and manager.jobs == {} and manager._job_locks == {}
    assert not list((manager.data_dir / "jobs").iterdir())
    assert not list(employee_app.config["HSD_UPLOADS"].input_root.iterdir())
    assert employee_app.config["HSD_ACTIVE_UPLOADS"] == 0


def test_retention_registration_is_complete_before_background_submission(employee_app, monkeypatch):
    manager = employee_app.config["HSD_MANAGER"]
    order = []
    def registered(identifier):
        job = manager._get(identifier)
        assert job["_upload_managed"]
        assert Path(job["_upload_dir"]).is_dir()
        order.append(("registered", identifier))
    def submitted(job, operation):
        assert order == [("registered", job["id"])]
        order.append(("submitted", job["id"]))
    monkeypatch.setattr(manager, "_submit", submitted)
    employee_app.config["HSD_RETENTION"] = SimpleNamespace(register=registered)
    client = employee_app.test_client()
    login(client)
    result = cloud_request(client, "/api/jobs/upload", method="POST", content_type="multipart/form-data", data={
        "start_number": "1", "workbook": (BytesIO(workbook_bytes()), "synthetic.xlsx"),
        "source": (BytesIO(zip_bytes({"pattern.ai": b"synthetic"})), "synthetic.zip")})
    assert result.status_code == 200
    identifier = result.json["id"]
    assert order == [("registered", identifier), ("submitted", identifier)]
    assert Path(manager._get(identifier)["_upload_dir"]).is_dir()


def test_cloud_and_lan_cannot_be_enabled_together(tmp_path):
    with pytest.raises(ValueError):
        create_app(tmp_path, lan=object(), cloud=CloudAccess(ORIGIN, CODE))


@pytest.mark.parametrize("method,conditional,status", [("GET", False, "200"), ("HEAD", False, "200"), ("GET", True, "304")])
def test_preview_lease_follows_real_wsgi_iterator_close(employee_app, captured_jobs, monkeypatch, method, conditional, status):
    client = employee_app.test_client()
    login(client)
    result = cloud_request(client, "/api/jobs/upload", method="POST", content_type="multipart/form-data", data={
        "start_number": "1", "workbook": (BytesIO(workbook_bytes()), "synthetic.xlsx"),
        "source": (BytesIO(zip_bytes({"pattern.ai": b"synthetic"})), "synthetic.zip")})
    identifier = result.json["id"]
    preview = employee_app.config["HSD_MANAGER"].data_dir / "synthetic-preview.png"
    preview.write_bytes(b"synthetic-preview-body")
    monkeypatch.setattr(employee_app.config["HSD_MANAGER"], "image_asset", lambda *args, **kwargs: (preview, "synthetic-etag"))
    cookie_name = employee_app.config["SESSION_COOKIE_NAME"]
    cookie = client.get_cookie(cookie_name, domain="hsd.example.test")
    headers = {"X-Forwarded-For": CLIENT, "X-Forwarded-Proto": "https", "Cookie": f"{cookie_name}={cookie.value}"}
    if conditional:
        headers["If-None-Match"] = '"synthetic-etag"'
    builder = EnvironBuilder(path=f"/api/jobs/{identifier}/image/row/r1", method=method,
                             base_url=ORIGIN, headers=headers, environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    statuses = []
    iterator = employee_app.wsgi_app(builder.get_environ(), lambda code, headers, exc_info=None: statuses.append(code))
    assert statuses[0].startswith(status)
    assert employee_app.config["HSD_JOB_LEASES"] == {identifier: 1}
    payload = b"".join(iterator)
    assert payload == (b"synthetic-preview-body" if method == "GET" and not conditional else b"")
    iterator.close()
    assert employee_app.config["HSD_JOB_LEASES"] == {}


def test_explicit_https_port_is_part_of_origin_and_host_boundary():
    access = CloudAccess("https://39.106.45.116:8443/", CODE)
    assert access.origin == "https://39.106.45.116:8443"
    captured = []
    def app(environ, start_response):
        captured.append((environ["REMOTE_ADDR"], environ["wsgi.url_scheme"], environ["HTTP_HOST"], environ["SERVER_PORT"]))
        start_response("200 OK", [])
        return [b"ok"]
    environment = EnvironBuilder(base_url=access.origin, headers={"X-Forwarded-For": CLIENT,
        "X-Forwarded-Proto": "https"}, environ_overrides={"REMOTE_ADDR": "127.0.0.1"}).get_environ()
    assert list(access.middleware(app)(environment, lambda *args: None)) == [b"ok"]
    assert captured == [(CLIENT, "https", "39.106.45.116:8443", "8443")]


def test_cloud_factory_requires_all_private_configuration():
    with pytest.raises(ValueError):
        create_cloud_app({})


@pytest.fixture
def cloud_factory_stubs(tmp_path, monkeypatch):
    from hsd_tool import cloud_admin, cloud_retention, cloud_server, server
    created = []
    closed = []
    manager = SimpleNamespace(ai_settings=SimpleNamespace(snapshot=lambda: {"key_persistence": "linux_aesgcm"}),
                              close=lambda: closed.append(True))
    app = SimpleNamespace(config={"HSD_MANAGER": manager, "HSD_JOB_LEASES": {}})
    def create(*args, **kwargs):
        created.append(kwargs["cloud"])
        return app
    retention = SimpleNamespace(start=lambda: retention)
    monkeypatch.setattr(server, "create_app", create)
    monkeypatch.setattr(cloud_admin, "CloudAdminCredentials", lambda path: object())
    monkeypatch.setattr(cloud_retention, "CloudRetention", lambda *args: retention)
    environment = {"HSD_PUBLIC_ORIGIN": ORIGIN, "HSD_DATA_DIR": str(tmp_path / "data"),
                   "HSD_SETTINGS_DIR": str(tmp_path / "settings"),
                   "HSD_EMPLOYEE_CODE_FILE": str(tmp_path / "synthetic-employee-code"),
                   "HSD_CREDENTIAL_KEY_FILE": str(tmp_path / "synthetic-encryption-key"),
                   "HSD_ADMIN_CREDENTIAL_FILE": str(tmp_path / "synthetic-admin-digest")}
    return cloud_server, environment, app, created, closed


def test_factory_default_code_minimum_remains_sixteen(cloud_factory_stubs, monkeypatch):
    module, environment, app, created, closed = cloud_factory_stubs
    monkeypatch.setattr(module, "_private_file", lambda path: b"demo")
    with pytest.raises(ValueError, match="至少需要16位"):
        create_cloud_app(environment)
    assert created == [] and closed == []
    monkeypatch.setattr(module, "_private_file", lambda path: b"x" * 16)
    assert create_cloud_app(environment) is app
    assert created[0].code == "x" * 16


@pytest.mark.parametrize("minimum,code", [("1", "x"), ("4", "demo"), ("16", CODE), ("64", "x" * 64)])
def test_factory_explicit_code_minimum_is_instance_configuration(cloud_factory_stubs, monkeypatch, minimum, code):
    module, environment, app, created, closed = cloud_factory_stubs
    monkeypatch.setattr(module, "_private_file", lambda path: code.encode("ascii"))
    environment["HSD_EMPLOYEE_CODE_MIN_LENGTH"] = minimum
    assert create_cloud_app(environment) is app
    assert created[0].code == code and closed == []


@pytest.mark.parametrize("minimum", ["", "0", "65", "-1", "+4", " 4", "4 ", "04", "4.0", "true", "４", None, 4, True])
def test_factory_invalid_code_minimum_fails_before_reading_credentials(cloud_factory_stubs, monkeypatch, minimum):
    module, environment, app, created, closed = cloud_factory_stubs
    environment["HSD_EMPLOYEE_CODE_MIN_LENGTH"] = minimum
    read = []
    monkeypatch.setattr(module, "_private_file", lambda path: read.append(path))
    with pytest.raises(ValueError, match="最短长度配置"):
        create_cloud_app(environment)
    assert read == [] and created == [] and closed == []


def test_cloud_factory_closes_manager_instead_of_accepting_plaintext_fallback(tmp_path, monkeypatch):
    from hsd_tool import cloud_admin, server
    tmp_path.chmod(0o700)
    code_file = tmp_path / "employee-code"
    code_file.write_text(CODE, "ascii")
    code_file.chmod(0o600)
    closed = []
    manager = SimpleNamespace(ai_settings=SimpleNamespace(snapshot=lambda: {"key_persistence": "session_only"}),
                              close=lambda: closed.append(True))
    app = SimpleNamespace(config={"HSD_MANAGER": manager, "HSD_JOB_LEASES": {}})
    monkeypatch.setattr(server, "create_app", lambda *args, **kwargs: app)
    monkeypatch.setattr(cloud_admin, "CloudAdminCredentials", lambda path: object())
    environment = {"HSD_PUBLIC_ORIGIN": ORIGIN, "HSD_DATA_DIR": str(tmp_path / "data"),
                   "HSD_SETTINGS_DIR": str(tmp_path / "settings"),
                   "HSD_EMPLOYEE_CODE_FILE": str(code_file),
                   "HSD_CREDENTIAL_KEY_FILE": str(tmp_path / "encryption-key"),
                   "HSD_ADMIN_CREDENTIAL_FILE": str(tmp_path / "admin-digest")}
    with pytest.raises(ValueError, match="加密"):
        create_cloud_app(environment)
    assert closed == [True]


def test_private_employee_code_file_requires_absolute_ordinary_file(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "code"
    path.write_bytes(CODE.encode())
    path.chmod(0o600)
    assert _private_file(path) == CODE.encode()
    with pytest.raises(ValueError):
        _private_file(Path("relative"))
    with pytest.raises(ValueError):
        _private_file(tmp_path)


def test_cloud_service_options_are_fixed_single_worker_streaming():
    import ast
    # Gunicorn requires POSIX imports. Inspect only the portable option builder
    # on Windows; Linux additionally imports the real production module below.
    source = (Path(__file__).parents[1] / "hsd_tool" / "cloud_gunicorn.py").read_text("utf-8")
    parsed = ast.parse(source)
    function = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == "server_options")
    namespace = {"os": __import__("os")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "cloud-options", "exec"), namespace)
    options = namespace["server_options"]({"HSD_BIND_PORT": "8835", "WEB_CONCURRENCY": "20", "GUNICORN_CMD_ARGS": "--workers 20"})
    assert options["bind"] == "127.0.0.1:8835" and options["workers"] == 1
    assert not options["preload_app"] and not options["reload"] and options["max_requests"] == 0
    assert options["timeout"] == 0 and options["forwarded_allow_ips"] == "" and options["secure_scheme_headers"] == {}
    assert options["accesslog"] is None
    with pytest.raises(ValueError):
        namespace["server_options"]({"HSD_BIND_PORT": "80"})
