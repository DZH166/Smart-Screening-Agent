"""Isolated LAN access contracts; no business samples or external API calls."""
import json
import time

import pytest

from hsd_tool.lan import LanAccess
from hsd_tool.server import create_app


HOST = "192.168.0.160"
REMOTE = "192.168.0.25"
ORIGIN = f"http://{HOST}:8805"
ACCESS_CODE = "synthetic-access-code"
TOKEN = "synthetic-session-token"


@pytest.fixture
def lan(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    return LanAccess(f"{HOST}/24", inputs, tmp_path / "outputs", code=ACCESS_CODE)


@pytest.fixture
def app(tmp_path, lan):
    application = create_app(tmp_path / "state", token=TOKEN, lan=lan)
    application.config["TESTING"] = True
    application.config["HSD_PORT"] = 8805
    yield application
    application.config["HSD_MANAGER"].close()


def remote_request(client, path, *, method="GET", address=REMOTE, origin=ORIGIN,
                   token=None, payload=None, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    if origin is not None:
        headers["Origin"] = origin
    if token is not None:
        headers["X-HSD-Token"] = token
    if payload is not None:
        kwargs["json"] = payload
    return client.open(path, method=method, base_url=ORIGIN,
                       environ_overrides={"REMOTE_ADDR": address}, headers=headers, **kwargs)


def login(client):
    response = remote_request(client, "/api/lan/login", method="POST", payload={"code": ACCESS_CODE})
    assert response.status_code == 200
    return response


def input_payload(lan):
    workbook = lan.input_root / "batch.xlsx"
    workbook.write_bytes(b"synthetic-only")
    source = lan.input_root / "originals"
    source.mkdir(exist_ok=True)
    return {"workbook_path": str(workbook), "source_path": str(source),
            "output_root": str(lan.output_root), "start_number": 1}


@pytest.mark.parametrize("interface", [
    "192.168.0.160", "8.8.8.8/24", "0.0.0.0/0", "127.0.0.1/8",
    "169.254.10.1/16", "100.64.1.1/24", "192.168.0.160/8", "::1/128",
    "192.168.0.0/24", "192.168.0.255/24",
])
def test_lan_requires_explicit_rfc1918_host_and_subnet(tmp_path, interface):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    with pytest.raises(ValueError):
        LanAccess(interface, inputs, tmp_path / "outputs")


def test_lan_limits_addresses_to_selected_subnet(lan):
    assert lan.host == HOST and str(lan.network) == "192.168.0.0/24"
    for address in (HOST, REMOTE, "127.0.0.1", "::1"):
        assert lan.allows(address)
    for address in ("192.168.1.25", "10.0.0.25", "8.8.8.8", "bad-address", None):
        assert not lan.allows(address)
    assert lan.is_host(HOST) and lan.is_host("127.0.0.1") and lan.is_host("::1")
    assert not lan.is_host(REMOTE)


def test_lan_requires_existing_input_and_separate_output(tmp_path):
    with pytest.raises(ValueError):
        LanAccess(f"{HOST}/24", tmp_path / "missing", tmp_path / "outputs")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for output in (inputs, inputs / "results"):
        with pytest.raises(ValueError):
            LanAccess(f"{HOST}/24", inputs, output)


def test_unauthenticated_root_has_login_form_without_application_token(app):
    response = remote_request(app.test_client(), "/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and "访问码" in html
    assert TOKEN not in html and ACCESS_CODE not in html and "__HSD_TOKEN__" not in html
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/api/config", "/api/health", "/api/ai/settings",
                                 "/api/jobs/missing", "/api/jobs/missing/image/row/r1",
                                 "/static/app.js"])
def test_all_data_images_and_scripts_require_remote_login(app, path):
    response = remote_request(app.test_client(), path)
    assert response.status_code == 401
    assert TOKEN not in response.get_data(as_text=True)


def test_login_requires_correct_code_and_sets_limited_http_only_session(app):
    client = app.test_client()
    denied = remote_request(client, "/api/lan/login", method="POST", payload={"code": "wrong"})
    assert denied.status_code == 403
    assert remote_request(client, "/api/config").status_code == 401
    response = login(client)
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Expires=" in cookie
    assert ACCESS_CODE not in cookie and TOKEN not in cookie
    assert app.permanent_session_lifetime.total_seconds() == 8 * 60 * 60
    config = remote_request(client, "/api/config")
    assert config.status_code == 200 and config.json["access"]["remote"]
    assert config.json["access"]["upload"] is True
    assert config.json["access"]["upload_limits"] == {
        "workbook_bytes": 100 * 1024**2, "source_bytes": 1900 * 1024**2,
        "total_bytes": 2 * 1024**3,
    }
    assert "input_root" not in config.json["access"] and "output_root" not in config.json["access"]
    assert config.json["last_workbook"] == config.json["last_source"] == config.json["last_output"] == ""
    for private in (str(app.config["HSD_MANAGER"].data_dir.parent / "inputs"),
                    str(app.config["HSD_MANAGER"].data_dir.parent / "outputs")):
        assert private not in config.get_data(as_text=True)
        assert private.replace("\\", "\\\\") not in config.get_data(as_text=True)
    html = remote_request(client, "/").get_data(as_text=True)
    assert TOKEN in html and ACCESS_CODE not in html and "__HSD_TOKEN__" not in html


@pytest.mark.parametrize("origin", [None, "https://evil.invalid", f"http://{HOST}:8806", "null"])
def test_login_rejects_missing_or_different_origin(app, origin):
    response = remote_request(app.test_client(), "/api/lan/login", method="POST", origin=origin,
                              payload={"code": ACCESS_CODE})
    assert response.status_code == 403


@pytest.mark.parametrize("payload", [[], None, "bad", 123])
def test_login_requires_json_object(app, payload):
    response = remote_request(app.test_client(), "/api/lan/login", method="POST",
                              data=json.dumps(payload), headers={"Content-Type": "application/json"})
    assert response.status_code == 400


def test_login_rejects_form_and_malformed_json(app):
    client = app.test_client()
    form = remote_request(client, "/api/lan/login", method="POST", data={"code": ACCESS_CODE})
    malformed = remote_request(client, "/api/lan/login", method="POST", data="{",
                               headers={"Content-Type": "application/json"})
    assert form.status_code == 400 and malformed.status_code == 400


def test_bad_code_attempts_are_throttled_per_remote_address(app):
    client = app.test_client()
    for _ in range(10):
        assert remote_request(client, "/api/lan/login", method="POST", payload={"code": "wrong"}).status_code == 403
    assert remote_request(client, "/api/lan/login", method="POST", payload={"code": ACCESS_CODE}).status_code == 429
    other = remote_request(client, "/api/lan/login", method="POST", address="192.168.0.26",
                           payload={"code": ACCESS_CODE})
    assert other.status_code == 200


def test_logged_in_mutations_still_require_csrf_token_and_same_origin(app):
    client = app.test_client()
    login(client)
    for supplied in (None, "wrong"):
        assert remote_request(client, "/api/jobs", method="POST", payload={}, token=supplied).status_code == 403
    for origin in (None, "https://evil.invalid"):
        assert remote_request(client, "/api/jobs", method="POST", payload={}, token=TOKEN, origin=origin).status_code == 403


def test_logout_requires_csrf_and_ends_remote_access(app):
    client = app.test_client()
    login(client)
    assert remote_request(client, "/api/lan/logout", method="POST", payload={}).status_code == 403
    assert remote_request(client, "/api/config").status_code == 200
    assert remote_request(client, "/api/lan/logout", method="POST", payload={}, token=TOKEN).status_code == 200
    assert remote_request(client, "/api/config").status_code == 401
    assert TOKEN not in remote_request(client, "/").get_data(as_text=True)


def test_expired_session_and_cookie_from_other_instance_are_rejected(app, tmp_path, lan, monkeypatch):
    client = app.test_client()
    serializer = app.session_interface.get_signing_serializer(app)
    old_timestamp = int(time.time()) - 8 * 60 * 60 - 10
    with monkeypatch.context() as patch:
        patch.setattr("itsdangerous.timed.TimestampSigner.get_timestamp", lambda self: old_timestamp)
        expired_cookie = serializer.dumps({"_permanent": True, "lan_authenticated": True})
    name = app.config["SESSION_COOKIE_NAME"]
    client.set_cookie(name, expired_cookie, domain=HOST)
    assert remote_request(client, "/api/config").status_code == 401
    other = create_app(tmp_path / "other-instance", token=TOKEN, lan=lan)
    try:
        other_serializer = other.session_interface.get_signing_serializer(other)
        cookie = other_serializer.dumps({"_permanent": True, "lan_authenticated": True})
        client.set_cookie(name, cookie, domain=HOST)
        assert remote_request(client, "/api/config").status_code == 401
    finally:
        other.config["HSD_MANAGER"].close()


@pytest.mark.parametrize("path", ["/api/pick", "/api/ai/settings", "/api/shutdown",
                                 "/api/jobs/missing/open-output"])
def test_remote_cannot_invoke_host_administration_even_with_token(app, path):
    client = app.test_client()
    login(client)
    response = remote_request(client, path, method="POST", payload={}, token=TOKEN)
    assert response.status_code == 403 and "主机" in response.json["error"]


@pytest.mark.parametrize("address", [HOST, "127.0.0.1"])
def test_host_admin_keeps_local_access_without_lan_login(app, address):
    client = app.test_client()
    assert remote_request(client, "/api/config", address=address).status_code == 200
    html = remote_request(client, "/", address=address).get_data(as_text=True)
    assert TOKEN in html and ACCESS_CODE not in html
    response = remote_request(client, "/api/ai/settings", method="POST", address=address,
                              token=TOKEN, payload={"enabled": False})
    assert response.status_code == 200
    assert remote_request(client, "/api/shutdown", method="POST", address=address,
                          token=TOKEN, payload={}).status_code == 200


@pytest.mark.parametrize("address", ["192.168.1.25", "10.1.1.25", "8.8.8.8"])
def test_outside_subnet_cannot_spoof_a_loopback_forwarded_address(app, address):
    response = remote_request(app.test_client(), "/", address=address,
                              headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": HOST})
    assert response.status_code == 403


@pytest.mark.parametrize("host", ["evil.invalid", "192.168.0.160.evil.invalid", "127.0.0.1.evil.invalid",
                                 "192.168.0.26:8805", "192.168.0.160@evil.invalid",
                                 "192.168.0.160:8806", "192.168.0.160"])
def test_untrusted_host_headers_are_rejected_before_login(app, host):
    response = remote_request(app.test_client(), "/", headers={"Host": host})
    assert response.status_code == 403


def test_default_server_remains_loopback_only(tmp_path):
    app = create_app(tmp_path / "local", token=TOKEN)
    try:
        client = app.test_client()
        assert client.get("/api/config").status_code == 200
        response = client.get("/api/config", environ_overrides={"REMOTE_ADDR": REMOTE},
                              headers={"Host": "127.0.0.1", "X-Forwarded-For": "127.0.0.1"})
        assert response.status_code == 403
        login_response = client.post("/api/lan/login", json={"code": ACCESS_CODE},
                                     headers={"Origin": "http://localhost", "X-HSD-Token": TOKEN})
        assert login_response.status_code == 404
    finally:
        app.config["HSD_MANAGER"].close()


def test_path_validation_returns_canonical_paths_and_default_output(lan):
    payload = input_payload(lan)
    payload["workbook_path"] = str(lan.input_root / "originals" / ".." / "batch.xlsx")
    payload["output_root"] = ""
    resolved = lan.validate_paths(payload)
    assert resolved["workbook_path"] == str(lan.input_root / "batch.xlsx")
    assert resolved["output_root"] == str(lan.output_root)
    assert resolved["start_number"] == 1 and payload["output_root"] == ""


@pytest.mark.parametrize("key", ["workbook_path", "source_path", "output_root"])
@pytest.mark.parametrize("raw", ["relative/path", r"\\server\share\file", "//server/share/file"])
def test_path_validation_rejects_relative_and_unc(lan, key, raw):
    payload = input_payload(lan)
    payload[key] = raw
    with pytest.raises(ValueError):
        lan.validate_paths(payload)


@pytest.mark.parametrize("key", ["workbook_path", "source_path", "output_root"])
def test_path_validation_rejects_outside_and_prefix_lookalike(lan, key):
    payload = input_payload(lan)
    root = lan.output_root if key == "output_root" else lan.input_root
    for path in (root / ".." / "outside", root.with_name(root.name + "-other") / "file"):
        payload[key] = str(path)
        with pytest.raises(ValueError):
            lan.validate_paths(payload)


@pytest.mark.parametrize("key", ["workbook_path", "source_path", "output_root"])
def test_resolved_link_cannot_escape_test_directories(lan, tmp_path, key):
    payload = input_payload(lan)
    outside = tmp_path / "outside"
    outside.mkdir()
    root = lan.output_root if key == "output_root" else lan.input_root
    link = root / "escaped"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Directory symlink creation unavailable: {exc}")
    payload[key] = str(link / "file.xlsx") if key == "workbook_path" else str(link)
    with pytest.raises(ValueError):
        lan.validate_paths(payload)


def test_remote_path_job_creation_is_disabled_before_manager(app, lan, monkeypatch):
    client = app.test_client()
    login(client)
    calls = []
    monkeypatch.setattr(app.config["HSD_MANAGER"], "create", lambda payload: calls.append(payload) or "synthetic-job")
    payload = input_payload(lan)
    outside = dict(payload, source_path=str(lan.input_root.parent / "private-originals"))
    denied = remote_request(client, "/api/jobs", method="POST", payload=outside, token=TOKEN)
    assert denied.status_code == 403 and not calls
    inside = remote_request(client, "/api/jobs", method="POST", payload=payload, token=TOKEN)
    assert inside.status_code == 403 and not calls


def test_remote_ai_settings_response_is_only_sanitized_configuration(app):
    client = app.test_client()
    login(client)
    response = remote_request(client, "/api/ai/settings")
    assert response.status_code == 200
    assert set(response.json) == {"enabled", "configured", "model", "mode"}
    assert ACCESS_CODE not in response.get_data(as_text=True)


def test_access_code_is_only_visible_in_host_config(app):
    client = app.test_client()
    login(client)
    remote = remote_request(client, "/api/config")
    host = remote_request(app.test_client(), "/api/config", address=HOST)
    assert "code" not in remote.json["access"]
    assert ACCESS_CODE not in remote.get_data(as_text=True)
    assert host.json["access"]["code"] == ACCESS_CODE


def install_synthetic_job(app, lan, client):
    from test_service import prepared

    batch = lan.input_root / "synthetic-batch"
    batch.mkdir()
    owner, job = prepared(batch, [""])
    try:
        job["_output_root"] = str(lan.output_root)
        with client.session_transaction(base_url=ORIGIN) as state:
            job["_owner_id"] = state["employee_id"]
        app.config["HSD_MANAGER"].jobs[job["id"]] = job
    finally:
        owner.close()
    return job


@pytest.mark.parametrize("action", ["resolve", "undo", "export"])
@pytest.mark.parametrize("revision", [None, True, 0.0, "0", -1])
def test_lan_mutations_require_current_integer_revision(app, lan, action, revision):
    client = app.test_client()
    login(client)
    job = install_synthetic_job(app, lan, client)
    payload = {"row_id": "r2", "file_id": None}
    if revision is not None:
        payload["expected_revision"] = revision
    response = remote_request(client, f"/api/jobs/sample/{action}", method="POST", payload=payload, token=TOKEN)
    assert response.status_code == 409
    assert job.get("revision", 0) == 0 and job["rows"][0]["_status"] == "auto"


def test_two_pages_cannot_overwrite_newer_resolution_or_export_stale_summary(app, lan):
    first, second = app.test_client(), app.test_client()
    login(first)
    install_synthetic_job(app, lan, first)
    # Tabs in one employee browser share a session; different employees do not.
    cookie_name = app.config["SESSION_COOKIE_NAME"]
    cookie = first.get_cookie(cookie_name, domain=HOST)
    assert cookie is not None
    second.set_cookie(cookie_name, cookie.value, domain=HOST)
    initial = remote_request(first, "/api/jobs/sample").json
    assert initial["revision"] == remote_request(second, "/api/jobs/sample").json["revision"] == 0
    accepted = remote_request(first, "/api/jobs/sample/resolve", method="POST", token=TOKEN,
                              payload={"row_id": "r2", "file_id": None, "expected_revision": 0})
    assert accepted.status_code == 200 and accepted.json["revision"] == 1
    stale = remote_request(second, "/api/jobs/sample/resolve", method="POST", token=TOKEN,
                           payload={"row_id": "r2", "file_id": "f2", "expected_revision": 0})
    assert stale.status_code == 409
    refreshed = remote_request(second, "/api/jobs/sample").json
    assert refreshed["revision"] == 1 and refreshed["rows"][0]["status"] == "skipped"
    undone = remote_request(second, "/api/jobs/sample/undo", method="POST", token=TOKEN,
                            payload={"expected_revision": 1})
    assert undone.status_code == 200 and undone.json["revision"] == 2
    stale_export = remote_request(first, "/api/jobs/sample/export", method="POST", token=TOKEN,
                                  payload={"expected_revision": 1})
    assert stale_export.status_code == 409
    assert remote_request(first, "/api/jobs/sample").json["status"] == "ready"


@pytest.mark.parametrize("path", ["/api/jobs/sample", "/api/jobs/sample/image/row/r2"])
def test_existing_job_outside_test_root_cannot_be_exposed(app, lan, tmp_path, path):
    client = app.test_client()
    login(client)
    job = install_synthetic_job(app, lan, client)
    job["_source_path"] = str(tmp_path / "private-originals")
    assert remote_request(client, path).status_code == 400


def test_host_job_creation_also_preserves_shared_directory_boundary(app, lan, monkeypatch):
    calls = []
    monkeypatch.setattr(app.config["HSD_MANAGER"], "create", lambda payload: calls.append(payload) or "synthetic-job")
    payload = input_payload(lan)
    payload["source_path"] = str(lan.input_root.parent / "private-originals")
    denied = remote_request(app.test_client(), "/api/jobs", method="POST", address=HOST,
                            payload=payload, token=TOKEN)
    assert denied.status_code == 400 and not calls
