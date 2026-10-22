"""Administrator-managed employee admission; generated secrets, no provider calls.

Access codes grant admission only. Browser sessions and recovery cookies remain
the authority for task ownership, including when people share an access code.
"""
from types import SimpleNamespace

import pytest

from hsd_tool import server
from hsd_tool.cloud_server import CloudAccess
from test_admin_settings_api import (
    CODE, PASSWORD, TOKEN, USERNAME, call, login_admin, settings_app,
)


API = "/api/admin/access-codes"
NEW_CODE = "synthetic-new-employee-admission"
OTHER_CODE = "synthetic-other-employee-admission"
PUBLIC_FIELDS = {"supported", "revision", "min_length", "max_length", "codes"}


def get(context, browser, path=API):
    return call(context, browser, path, method="GET")


def save(context, browser, payload, **options):
    return call(context, browser, API, payload=payload, **options)


def employee_login(context, browser, code=CODE):
    return call(context, browser, "/api/lan/login", payload={"code": code})


def require_employee_mode(context):
    if context.mode == "local":
        pytest.skip("desktop has no employee admission boundary")


def add(context, browser, code=NEW_CODE, label="临时员工"):
    current = get(context, browser).json
    response = save(context, browser, {
        "expected_revision": current["revision"], "add": [{"code": code, "label": label}],
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    assert code.encode() not in response.data
    rows = [row for row in response.json["codes"] if row["source"] != "configured" and row["label"] == label]
    assert len(rows) == 1
    return response.json, rows[0]["id"]


def owner(context, browser):
    with browser.session_transaction(base_url=context.origin) as stored:
        return stored["employee_id"]


def test_admin_page_and_assets_require_independent_admin_login(settings_app):
    context = settings_app
    browser = context.app.test_client()
    paths = (API, "/static/access-codes.html", "/static/access-codes.js", "/static/access-codes.css",
             "/static/ACCESS-CODES.JS", "/static/access-codes.html.", "/static/access-codes.js:extra")
    for path in paths:
        response = get(context, browser, path)
        assert response.status_code == 401
        assert "no-store" in response.headers["Cache-Control"]
        assert TOKEN.encode() not in response.data and NEW_CODE.encode() not in response.data
    page = get(context, browser, "/admin/access-codes")
    assert page.status_code == 200 and '<form id="login"' in page.get_data(as_text=True)
    if context.mode != "local":
        assert employee_login(context, browser).status_code == 200
        assert get(context, browser).status_code == 401
        assert save(context, browser, {"expected_revision": 0, "add": [{"code": NEW_CODE}]}).status_code == 401
    login_admin(context, browser)
    page = get(context, browser, "/admin/access-codes")
    assert page.status_code == 200 and b"window.HSD_TOKEN" in page.data
    for path in paths[1:4]:
        assert get(context, browser, path).status_code == 200


def test_snapshot_has_only_public_metadata_and_desktop_does_not_enable_codes(settings_app):
    context = settings_app
    browser = context.app.test_client()
    login_admin(context, browser)
    response = get(context, browser)
    assert response.status_code == 200 and set(response.json) == PUBLIC_FIELDS
    value = response.json
    assert value["supported"] is (context.mode != "local")
    assert type(value["revision"]) is int and value["revision"] >= 0
    assert value["max_length"] == 64
    assert response.headers["Cache-Control"] == "no-store"
    assert CODE.encode() not in response.data
    for row in value["codes"]:
        assert set(row) == {"id", "label", "enabled", "source"}
    if context.mode == "local":
        assert value["codes"] == [] and context.app.config["HSD_ACCESS_CODES"] is None
        assert save(context, browser, {"expected_revision": 0, "add": [{"code": NEW_CODE}]}).status_code == 400
    else:
        assert value["min_length"] == (16 if context.mode == "cloud" else 1)
        assert len(value["codes"]) == 1
        assert value["codes"][0]["source"] == "configured" and value["codes"][0]["enabled"] is True
        # An administrator session is not an employee session.
        assert get(context, browser, "/api/config").status_code == 401


def test_add_enable_disable_delete_and_old_sessions_remain_valid(settings_app):
    context = settings_app
    require_employee_mode(context)
    admin = context.app.test_client()
    login_admin(context, admin)
    initial_ai = context.app.config["HSD_MANAGER"].ai_settings.runtime()
    initial_material = context.app.config["HSD_MATERIAL_SETTINGS"].snapshot()
    snapshot, identifier = add(context, admin)
    employee = context.app.test_client()
    assert employee_login(context, employee, NEW_CODE).status_code == 200
    assert get(context, employee, "/api/config").status_code == 200
    assert get(context, employee).status_code == 401
    disabled = save(context, admin, {
        "expected_revision": snapshot["revision"], "update": [{"id": identifier, "enabled": False}],
    })
    assert disabled.status_code == 200
    assert employee_login(context, context.app.test_client(), NEW_CODE).status_code == 403
    assert get(context, employee, "/api/config").status_code == 200
    assert employee_login(context, context.app.test_client(), CODE).status_code == 200
    enabled = save(context, admin, {
        "expected_revision": disabled.json["revision"], "update": [{"id": identifier, "enabled": True}],
    })
    assert enabled.status_code == 200
    assert employee_login(context, context.app.test_client(), NEW_CODE).status_code == 200
    removed = save(context, admin, {"expected_revision": enabled.json["revision"], "remove": [identifier]})
    assert removed.status_code == 200
    assert employee_login(context, context.app.test_client(), NEW_CODE).status_code == 403
    assert get(context, employee, "/api/config").status_code == 200
    assert employee_login(context, context.app.test_client(), CODE).status_code == 200
    assert all(row["source"] == "configured" for row in removed.json["codes"])
    assert context.app.config["HSD_MANAGER"].ai_settings.runtime() == initial_ai
    assert context.app.config["HSD_MATERIAL_SETTINGS"].snapshot() == initial_material


@pytest.mark.parametrize("token,origin", [(None, True), ("wrong", True), (TOKEN, None),
    (TOKEN, "https://evil.example.test"), (TOKEN, "null")])
def test_mutation_requires_origin_and_token_even_for_admin(settings_app, token, origin):
    context = settings_app
    browser = context.app.test_client()
    login_admin(context, browser)
    initial = get(context, browser).json
    response = save(context, browser, {"expected_revision": initial["revision"], "add": [{"code": NEW_CODE}]},
                    token=token, origin=origin)
    assert response.status_code == 403
    assert get(context, browser).json == initial
    assert NEW_CODE.encode() not in response.data and response.headers["Cache-Control"] == "no-store"


def test_stale_pages_and_readonly_configured_code_cannot_change_settings(settings_app):
    context = settings_app
    require_employee_mode(context)
    browser = context.app.test_client()
    login_admin(context, browser)
    initial = get(context, browser).json
    snapshot, _ = add(context, browser)
    assert save(context, browser, {"expected_revision": initial["revision"], "add": [{"code": OTHER_CODE}]}).status_code == 409
    configured = next(row["id"] for row in snapshot["codes"] if row["source"] == "configured")
    for change in ({"remove": [configured]}, {"update": [{"id": configured, "enabled": False}]}):
        response = save(context, browser, {"expected_revision": snapshot["revision"], **change})
        assert response.status_code == 400
        assert CODE.encode() not in response.data
    assert get(context, browser).json == snapshot
    assert employee_login(context, context.app.test_client()).status_code == 200
    assert call(context, browser, "/admin/logout", payload={}).status_code == 200
    assert get(context, browser).status_code == 401


@pytest.mark.parametrize("bad", [
    {}, {"expected_revision": True, "add": [{"code": NEW_CODE}]},
    {"expected_revision": -1, "add": [{"code": NEW_CODE}]},
    {"expected_revision": "0", "add": [{"code": NEW_CODE}]},
    {"expected_revision": 0, "add": [{"code": NEW_CODE}], "min_length": 1},
    {"expected_revision": 0, "add": [{"code": NEW_CODE, "enabled": False}]},
    {"expected_revision": 0, "add": [{"code": ""}]},
    {"expected_revision": 0, "add": [{"code": "a b"}]},
    {"expected_revision": 0, "add": [{"code": "\u4e2d\u6587"}]},
    {"expected_revision": 0, "add": [{"code": "\ud800"}]},
    {"expected_revision": 0, "add": [{"code": "x" * 65}]},
    {"expected_revision": 0, "add": [{"code": NEW_CODE, "label": {"unexpected": "object"}}]},
    {"expected_revision": 0, "add": [NEW_CODE]},
    {"expected_revision": 0, "update": [{"id": "not-present", "enabled": True}]},
    {"expected_revision": 0, "update": [{"id": "not-present", "enabled": "yes"}]},
    {"expected_revision": 0, "remove": ["../outside"]},
])
def test_invalid_input_is_rejected_without_mutation_or_echo(settings_app, bad):
    context = settings_app
    browser = context.app.test_client()
    login_admin(context, browser)
    initial = get(context, browser).json
    response = save(context, browser, bad)
    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "no-store" and NEW_CODE.encode() not in response.data
    assert get(context, browser).json == initial


def test_duplicate_codes_do_not_create_an_alternate_enabled_entry(settings_app):
    context = settings_app
    require_employee_mode(context)
    browser = context.app.test_client()
    login_admin(context, browser)
    snapshot, identifier = add(context, browser)
    for code in (CODE, NEW_CODE):
        assert save(context, browser, {"expected_revision": snapshot["revision"], "add": [{"code": code}]}).status_code == 400
    disabled = save(context, browser, {"expected_revision": snapshot["revision"], "update": [{"id": identifier, "enabled": False}]})
    assert disabled.status_code == 200
    duplicate = save(context, browser, {"expected_revision": disabled.json["revision"], "add": [{"code": NEW_CODE}]})
    assert duplicate.status_code == 400
    assert get(context, browser).json == disabled.json
    assert employee_login(context, context.app.test_client(), NEW_CODE).status_code == 403


def test_minimum_length_is_instance_policy_and_64_character_code_is_supported(settings_app):
    context = settings_app
    require_employee_mode(context)
    browser = context.app.test_client()
    login_admin(context, browser)
    current = get(context, browser).json
    if context.mode == "cloud":
        assert save(context, browser, {"expected_revision": current["revision"], "add": [{"code": "short"}]}).status_code == 400
    maximum = "z" * 64
    add(context, browser, maximum, "64位测试")
    assert employee_login(context, context.app.test_client(), maximum).status_code == 200


def test_all_codes_share_the_existing_per_client_login_budget(settings_app):
    context = settings_app
    require_employee_mode(context)
    browser = context.app.test_client()
    login_admin(context, browser)
    add(context, browser)
    employee = context.app.test_client()
    for value in ("wrong-one", "wrong-two") * 5:
        assert employee_login(context, employee, value).status_code == 403
    assert employee_login(context, employee, NEW_CODE).status_code == 429
    assert employee_login(context, employee, CODE).status_code == 429
    assert get(context, employee, "/api/config").status_code == 401


@pytest.mark.parametrize("bad_code", [None, [], {}, 123, True, "\ud800", "a b", "x" * 65])
def test_malformed_login_does_not_raise_or_create_a_session(settings_app, bad_code):
    context = settings_app
    require_employee_mode(context)
    browser = context.app.test_client()
    assert employee_login(context, browser, bad_code).status_code == 403
    assert get(context, browser, "/api/config").status_code == 401


@pytest.mark.parametrize("same_code", [True, False])
def test_shared_or_different_codes_never_grant_another_browsers_tasks(settings_app, monkeypatch, same_code):
    context = settings_app
    require_employee_mode(context)
    admin = context.app.test_client()
    login_admin(context, admin)
    add(context, admin)
    if not same_code:
        add(context, admin, OTHER_CODE, "另一组")
    first, other = context.app.test_client(), context.app.test_client()
    assert employee_login(context, first, NEW_CODE).status_code == 200
    assert employee_login(context, other, NEW_CODE if same_code else OTHER_CODE).status_code == 200
    first_owner, other_owner = owner(context, first), owner(context, other)
    assert first_owner != other_owner and NEW_CODE not in first_owner and NEW_CODE not in other_owner
    manager = context.app.config["HSD_MANAGER"]
    identifier = "9" * 32
    manager.jobs[identifier] = {"id": identifier, "status": "ready", "start_number": 1,
                                "_owner_id": first_owner, "_upload_managed": True}
    monkeypatch.setattr(context.app.config["HSD_UPLOADS"], "validate_job", lambda job: None)
    monkeypatch.setattr(manager, "snapshot", lambda identifier: {"id": identifier, "status": "ready"})
    try:
        response = get(context, first, f"/api/jobs/{identifier}")
        assert response.status_code == 200
        response.close()
        for path in (f"/api/jobs/{identifier}", f"/api/jobs/{identifier}/image/row/row1",
                     f"/api/jobs/{identifier}/download"):
            response = get(context, other, path)
            assert response.status_code == 404
            response.close()
        assert get(context, other, "/api/config").json["active_job_id"] is None
        assert get(context, first, "/api/config").json["active_job_id"] == identifier
        assert not context.app.config["HSD_JOB_LEASES"]
    finally:
        # This admission-only fixture deliberately did not create real upload
        # files. It must not enter the separate cloud checkpoint lifecycle.
        manager.jobs.pop(identifier, None)


def test_cloud_relogin_uses_original_browser_cookie_instead_of_access_code(settings_app):
    context = settings_app
    if context.mode != "cloud":
        pytest.skip("persistent browser recovery is cloud-only")
    admin = context.app.test_client()
    login_admin(context, admin)
    add(context, admin)
    first, other = context.app.test_client(), context.app.test_client()
    assert employee_login(context, first, CODE).status_code == 200
    original_owner = owner(context, first)
    assert call(context, first, "/api/lan/logout", payload={}).status_code == 200
    assert employee_login(context, first, NEW_CODE).status_code == 200
    assert owner(context, first) == original_owner
    assert employee_login(context, other, NEW_CODE).status_code == 200
    assert owner(context, other) != original_owner


def test_cloud_explicit_minimum_override_is_respected_for_added_codes(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("HSD_CREDENTIAL_KEY_FILE", raising=False)
    origin = "https://short-code.example.test"
    access = CloudAccess(origin, "orig", min_code_length=4,
                         admin_credentials=SimpleNamespace(verify=lambda name, secret: (name, secret) == (USERNAME, PASSWORD)))
    app = server.create_app(tmp_path / "data", token=TOKEN, settings_dir=tmp_path / "settings", cloud=access)
    app.config["TESTING"] = True
    context = SimpleNamespace(app=app, mode="cloud", peer="127.0.0.1", origin=origin)
    try:
        admin = app.test_client()
        login_admin(context, admin)
        assert get(context, admin).json["min_length"] == 4
        add(context, admin, "new1")
        assert employee_login(context, app.test_client(), "new1").status_code == 200
        assert employee_login(context, app.test_client(), "orig").status_code == 200
    finally:
        app.config["HSD_MANAGER"].close()


def test_query_parameters_and_failed_disk_write_do_not_report_success(settings_app, monkeypatch):
    context = settings_app
    browser = context.app.test_client()
    login_admin(context, browser)
    initial = get(context, browser).json
    response = get(context, browser, API + "?include_secrets=true")
    assert response.status_code == 400
    if context.mode == "local":
        return
    store = context.app.config["HSD_ACCESS_CODES"]

    def fail_write(payload):
        raise ValueError("访问码未保存，请检查可用空间。")

    monkeypatch.setattr(store, "save", fail_write)
    response = save(context, browser, {"expected_revision": initial["revision"], "add": [{"code": NEW_CODE}]})
    assert response.status_code == 400 and NEW_CODE.encode() not in response.data
    assert get(context, browser).json == initial
    assert employee_login(context, context.app.test_client(), NEW_CODE).status_code == 403
