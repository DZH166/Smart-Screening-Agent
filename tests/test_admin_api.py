"""Host administrator boundaries and metadata-only diagnostics.

All credentials, jobs and events are artificial. These tests make no provider
calls and do not create AI production qualification.
"""
import copy
import json

import pytest

from hsd_tool.ai_admin import AiDebugTrace
from hsd_tool.lan import LanAccess
from hsd_tool.server import create_app


HOST = "192.168.0.160"
REMOTE = "192.168.0.27"
ORIGIN = f"http://{HOST}:8817"
TOKEN = "admin-test-token-not-real"
CODE = "admin-test-access-code"
SECRET = "sk-admin-synthetic-credential-must-never-return"
PRIVATE_PATH = r"C:\private-admin-data\employee\sensitive.ai"
ADMIN_GETS = ["/api/admin/overview", "/api/admin/debug", "/admin",
              "/static/admin.html", "/static/admin.js", "/static/admin.css"]


def call(client, path, *, address=HOST, method="GET", token=TOKEN,
         origin=ORIGIN, payload=None, headers=None):
    headers = dict(headers or {})
    if token is not None:
        headers["X-HSD-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    options = {"json": payload} if payload is not None else {}
    return client.open(path, method=method, base_url=ORIGIN, headers=headers,
                       environ_overrides={"REMOTE_ADDR": address}, **options)


def login(client):
    response = call(client, "/api/lan/login", address=REMOTE,
                    method="POST", payload={"code": CODE})
    assert response.status_code == 200


@pytest.fixture
def admin_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    inputs = tmp_path / "host-inputs"
    inputs.mkdir()
    lan = LanAccess(f"{HOST}/24", inputs, tmp_path / "host-outputs", code=CODE)
    application = create_app(tmp_path / "data", token=TOKEN, lan=lan,
                             settings_dir=tmp_path / "shared-settings")
    application.config.update(TESTING=True, HSD_PORT=8817)
    yield application
    application.config["HSD_MANAGER"].close()


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_unauthenticated_remote_cannot_read_admin(admin_app, path):
    response = call(admin_app.test_client(), path, address=REMOTE)
    assert response.status_code == 401
    assert TOKEN not in response.get_data(as_text=True)


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_authenticated_employee_cannot_read_admin(admin_app, path):
    client = admin_app.test_client()
    login(client)
    response = call(client, path, address=REMOTE)
    assert response.status_code == 403
    assert TOKEN not in response.get_data(as_text=True)


@pytest.mark.parametrize("path", [
    "/static/Admin.js", "/static/ADMIN.HTML", "/static/admin.CSS",
    "/static/./admin.js", "/static/nested/../admin.css",
    "/static/%61dmin.js", "/static/%2e/admin.html",
    "/static/admin.js.", "/static/admin.js%20", "/static/admin.js::$DATA",
])
def test_employee_cannot_read_windows_static_aliases(admin_app, path):
    client = admin_app.test_client()
    login(client)
    response = call(client, path, address=REMOTE)
    assert response.status_code == 403


@pytest.mark.parametrize("headers", [
    {"X-Forwarded-For": HOST}, {"X-Real-IP": "127.0.0.1"},
    {"Forwarded": "for=127.0.0.1;host=localhost"},
])
def test_forwarding_headers_do_not_make_employee_an_admin(admin_app, headers):
    client = admin_app.test_client()
    login(client)
    assert call(client, "/api/admin/overview", address=REMOTE,
                headers=headers).status_code == 403


@pytest.mark.parametrize("logged_in,expected", [(False, 401), (True, 403)])
def test_remote_cannot_write_admin_keys(admin_app, logged_in, expected):
    client = admin_app.test_client()
    if logged_in:
        login(client)
    result = call(client, "/api/admin/keys", address=REMOTE,
                  method="POST", payload={"keys": [SECRET]})
    assert result.status_code == expected
    assert SECRET not in result.get_data(as_text=True)


@pytest.mark.parametrize("token,origin", [
    (None, ORIGIN), ("wrong", ORIGIN), (TOKEN, "https://evil.invalid"),
    (TOKEN, "null"), (TOKEN, f"http://{HOST}:8807"),
])
def test_host_admin_mutations_require_token_and_matching_origin(admin_app, token, origin):
    response = call(admin_app.test_client(), "/api/admin/keys", method="POST",
                    payload={}, token=token, origin=origin)
    assert response.status_code == 403


@pytest.mark.parametrize("status", ["queued", "importing", "matching", "ai_review", "exporting"])
def test_admin_cannot_reconfigure_keys_during_any_employees_busy_task(admin_app, status, monkeypatch):
    manager = admin_app.config["HSD_MANAGER"]
    manager.jobs["another_employee"] = {"status": status, "_owner_id": "other-browser"}
    saves = []
    monkeypatch.setattr(manager.ai_settings, "save_pool", lambda payload: saves.append(payload))
    response = call(admin_app.test_client(), "/api/admin/keys", method="POST", payload={})
    assert response.status_code == 400 and "正在处理" in response.json["error"]
    assert saves == []


@pytest.mark.parametrize("query", [
    "after=-1", "after=one", "after=1.5", "after=0&after=1",
    "limit=0", "limit=201", "limit=-1", "limit=one", "limit=1&limit=2",
    "job_id=private-job", "path=C:/private", "after=1&body=secret",
])
def test_debug_query_rejects_invalid_or_unsupported_parameters(admin_app, query):
    response = call(admin_app.test_client(), "/api/admin/debug?" + query)
    assert response.status_code == 400


def test_debug_paginates_and_resumes_without_repeating_events(admin_app):
    manager = admin_app.config["HSD_MANAGER"]
    trace = manager.ai_debug = AiDebugTrace(capacity=4)
    for index in range(7):
        trace.emit("returned", job_id="privatejob", row_id=f"r{index+2}", verdict="same")
    client = admin_app.test_client()
    first = call(client, "/api/admin/debug?after=0&limit=2").json
    assert [event["seq"] for event in first["events"]] == [4, 5]
    assert first["cursor"] == 5 and first["dropped"] == 3 and first["oldest_seq"] == 4
    second = call(client, "/api/admin/debug?after=5&limit=2").json
    assert [event["seq"] for event in second["events"]] == [6, 7]
    assert second["cursor"] == 7 and second["dropped"] == 0
    third = call(client, "/api/admin/debug?after=7&limit=2").json
    assert third["events"] == [] and third["cursor"] == 7
    reset = call(client, "/api/admin/debug?after=9000&limit=2").json
    assert reset["reset"] is True and reset["instance"] == first["instance"]
    assert [event["seq"] for event in reset["events"]] == [4, 5]


def test_debug_is_read_only_and_cannot_grant_host_ownership(admin_app):
    manager = admin_app.config["HSD_MANAGER"]
    job = {"id": "privatejob", "status": "ready", "_owner_id": "different-employee",
           "rows": [{"id": "r2", "status": "review", "_status": "review"}]}
    manager.jobs["privatejob"] = job
    before = copy.deepcopy(job)
    manager.ai_debug.emit("manual", job_id="privatejob", row_id="r2", verdict="same")
    host = admin_app.test_client()
    response = call(host, "/api/admin/debug")
    assert response.status_code == 200 and response.json["events"][0]["verdict"] == "same"
    for path, method, payload in [
        ("/api/jobs/privatejob", "GET", None),
        ("/api/jobs/privatejob/image/row/r2", "GET", None),
        ("/api/jobs/privatejob/resolve", "POST", {"row_id": "r2", "file_id": "f0001", "expected_revision": 0}),
        ("/api/jobs/privatejob/ai-review", "POST", {}),
    ]:
        assert call(host, path, method=method, payload=payload).status_code == 404
    assert job == before


def test_active_debug_elapsed_time_and_run_cleanup_are_task_scoped():
    clock = [10.0]
    trace = AiDebugTrace(capacity=3, clock=lambda: clock[0])
    trace.emit("requesting", job_id="job_a", row_id="r2", attempt=1)
    trace.emit("requesting", job_id="job_b", row_id="r3", attempt=1)
    clock[0] = 12.25
    first = trace.snapshot()
    assert len(first["active"]) == 2
    assert {event["elapsed_ms"] for event in first["active"]} == {2250}
    trace.emit("manual", job_id="job_a", row_id="r2")
    assert [event["job_id"] for event in trace.snapshot()["active"]] == ["job_b"]
    trace.emit("run_finished", job_id="job_b")
    assert trace.snapshot()["active"] == []
    assert trace.snapshot()["last_seq"] == 4


def test_debug_filters_untrusted_text_paths_images_and_provider_data(admin_app):
    manager = admin_app.config["HSD_MANAGER"]
    manager.ai_debug.emit("returned", job_id="safejob", row_id="r2", key_id="key_001",
        verdict="same", candidate_id="f0001", model="deepseek-flash", attempt=2,
        error_code="untrusted code " + SECRET, reason=SECRET, message=PRIVATE_PATH,
        request_body={"authorization": SECRET}, key_label=SECRET, api_key=SECRET,
        image="data:image/png;base64,private-preview", exception=PRIVATE_PATH,
        usage={"requests": 1, "successes": 1, "unknown_usage_requests": 1,
               "raw_body": SECRET, "path": PRIVATE_PATH})
    response = call(admin_app.test_client(), "/api/admin/debug")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert SECRET not in text and PRIVATE_PATH not in text and "base64" not in text
    assert "authorization" not in text and "raw_body" not in text
    event = response.json["events"][0]
    assert event["error_code"] == "review_unavailable"
    assert event["usage"]["unknown_usage_requests"] == 1
    assert event["usage"]["estimated_usd_upper_bound"] is None
    assert set(event) == {"stage", "message", "time", "seq", "job_id", "row_id", "key_id",
                          "verdict", "candidate_id", "model", "attempt", "error_code", "usage"}


def test_debug_rejects_secret_like_identifiers_and_invalid_field_types():
    trace = AiDebugTrace()
    trace.emit("returned", job_id=SECRET, row_id=PRIVATE_PATH, key_id=SECRET,
               verdict=SECRET, candidate_id=PRIVATE_PATH, model=SECRET,
               attempt=True, elapsed_ms=-1, image_count=3.5)
    event = trace.snapshot()["events"][0]
    assert set(event) == {"stage", "message", "time", "seq"}
    trace.emit(SECRET, job_id="valid")
    assert trace.snapshot()["last_seq"] == 1


def test_trace_snapshot_cannot_mutate_internal_buffer():
    trace = AiDebugTrace()
    trace.emit("requesting", job_id="onejob", row_id="r2", usage={"requests": 1})
    result = trace.snapshot()
    result["events"][0]["usage"]["requests"] = 999
    result["active"][0]["job_id"] = "changed"
    assert trace.snapshot()["events"][0]["usage"]["requests"] == 1
    assert trace.snapshot()["active"][0]["job_id"] == "onejob"


def test_employee_settings_stay_minimal_and_cumulative_usage_stays_forbidden(admin_app):
    manager = admin_app.config["HSD_MANAGER"]
    manager.ai_debug.emit("returned", job_id="not-this-employees-job", verdict="same")
    manager.ai_usage.add({"requests": 2, "failures": 1, "unknown_usage_requests": 1})
    client = admin_app.test_client()
    login(client)
    settings = call(client, "/api/ai/settings", address=REMOTE)
    assert settings.status_code == 200
    assert set(settings.json) == {"enabled", "configured", "model", "mode"}
    assert call(client, "/api/ai/usage", address=REMOTE).status_code == 403
    assert "not-this-employees-job" not in json.dumps(settings.json)


def test_host_can_add_multiple_keys_without_credentials_in_any_admin_response(admin_app):
    client = admin_app.test_client()
    first = call(client, "/api/admin/overview")
    assert first.status_code == 200
    revision = first.json["settings"]["key_revision"]
    other_secret = "sk-another-admin-synthetic-credential-not-real"
    response = call(client, "/api/admin/keys", method="POST", payload={
        "expected_revision": revision,
        "add": [{"label": "测试一", "api_key": SECRET},
                {"label": "测试二", "api_key": other_secret}],
    })
    assert response.status_code == 200
    assert response.json["pool"]["key_count"] == 2
    assert response.json["settings"]["key_revision"] > revision
    assert {row["label"] for row in response.json["pool"]["keys"]} == {"测试一", "测试二"}
    for result in (response, call(client, "/api/admin/overview"), call(client, "/api/ai/settings")):
        text = result.get_data(as_text=True)
        assert SECRET not in text and other_secret not in text
        assert "encrypted_api_key" not in text and '"api_key"' not in text
        assert "fingerprint" not in text
    private_runtime = admin_app.config["HSD_MANAGER"].ai_settings.runtime()
    assert {row["api_key"] for row in private_runtime["keys"]} == {SECRET, other_secret}


def test_stale_admin_write_is_rejected_and_does_not_mutate_key_pool(admin_app):
    first, other = admin_app.test_client(), admin_app.test_client()
    revision = call(first, "/api/admin/overview").json["settings"]["key_revision"]
    accepted = call(first, "/api/admin/keys", method="POST", payload={
        "expected_revision": revision, "add": [{"label": "已保存", "api_key": SECRET}]})
    assert accepted.status_code == 200
    refused = call(other, "/api/admin/keys", method="POST", payload={
        "expected_revision": revision,
        "add": [{"label": "过期页面", "api_key": "sk-stale-key-synthetic-only"}]})
    assert refused.status_code == 409
    assert "sk-stale" not in refused.get_data(as_text=True)
    after = call(other, "/api/admin/overview").json
    assert after["pool"]["key_count"] == 1
    assert after["pool"]["keys"][0]["label"] == "已保存"
    assert after["settings"]["key_revision"] == accepted.json["settings"]["key_revision"]


@pytest.mark.parametrize("payload", [
    {}, {"expected_revision": True}, {"expected_revision": "0"},
    {"expected_revision": 0, "api_key": SECRET},
    {"expected_revision": 0, "model": "different"},
    {"expected_revision": 0, "add": [{"api_key": SECRET + "\n"}]},
    {"expected_revision": 0, "update": [{"id": "not-existing", "api_key": SECRET}]},
])
def test_bad_admin_mutations_fail_without_echoing_or_saving_credentials(admin_app, payload):
    client = admin_app.test_client()
    response = call(client, "/api/admin/keys", method="POST", payload=payload)
    assert response.status_code == 400
    assert SECRET not in response.get_data(as_text=True)
    assert call(client, "/api/admin/overview").json["pool"]["key_count"] == 0


def test_host_can_disable_rename_and_remove_keys_with_current_revision(admin_app):
    client = admin_app.test_client()
    added = call(client, "/api/admin/keys", method="POST", payload={
        "expected_revision": 0, "add": [{"api_key": SECRET, "label": "更名前"}]}).json
    identity = added["pool"]["keys"][0]["id"]
    changed = call(client, "/api/admin/keys", method="POST", payload={
        "expected_revision": added["settings"]["key_revision"],
        "update": [{"id": identity, "label": "更名后", "enabled": False}]})
    assert changed.status_code == 200
    assert changed.json["pool"]["keys"][0]["label"] == "更名后"
    assert changed.json["pool"]["keys"][0]["status"] == "disabled"
    removed = call(client, "/api/admin/keys", method="POST", payload={
        "expected_revision": changed.json["settings"]["key_revision"], "remove": [identity]})
    assert removed.status_code == 200 and removed.json["pool"]["key_count"] == 0


def test_local_gate_explanations_are_whitelisted_instead_of_model_text(admin_app):
    trace = admin_app.config["HSD_MANAGER"].ai_debug
    trace.emit("manual", job_id="onejob", row_id="r2", reason_code="validation_required",
               gate_failures=["local_evidence_conflict", PRIVATE_PATH, SECRET],
               gate_reason=SECRET, reason=PRIVATE_PATH)
    result = call(admin_app.test_client(), "/api/admin/debug").json["events"][0]
    assert result["reason_code"] == "validation_required"
    assert "独立验证资格" in result["gate_reason"] and "本地图案或颜色" in result["gate_reason"]
    assert SECRET not in json.dumps(result) and PRIVATE_PATH not in json.dumps(result)


def test_successful_mock_review_and_debug_cannot_create_production_qualification(tmp_path, monkeypatch):
    """An artificial positive reply still ends as review; no registry activated."""
    from PIL import Image
    from hsd_tool.ai_policy import CHECKS
    from hsd_tool.ai_usage import empty_usage
    import hsd_tool.ai_workflow as workflow
    from test_ai_policy import measured_evidence, competition_for, alignment_for
    from test_service import prepared

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    manager, job = prepared(tmp_path, ["", "KEEP0001"])
    try:
        for index, (file, color) in enumerate(zip(job["files"], ("red", "blue")), 1):
            file["id"] = f"f{index:04}"
            file["page_count"] = 1
            Image.new("RGB", (240, 60), color).save(file["preview_path"])
            job["rows"][index - 1]["_file_id"] = file["id"]
        row = job["rows"][0]
        row.update(_status="review", _file_id=None, _reason="需复核", _reason_code="not_verified",
                   candidates=[{"file_id": "f0001", "score": .92}, {"file_id": "f0002", "score": .65}],
                   evidence=measured_evidence())
        row["evidence"]["competition"] = competition_for(row, job["files"])
        row["evidence"]["alignment"] = alignment_for(row, job["files"])
        job.update(revision=0, timings={})
        manager._plan(job)
        manager.ai_settings.save({"enabled": True})
        manager.ai_settings.save_pool({"expected_revision": 0, "add": [{"api_key": SECRET, "label": "合成测试"}]})
        calls = []

        class ArtificialClient:
            def __init__(self, key):
                assert key == SECRET

            def review(self, content):
                calls.append(len(content))
                return {"model": "deepseek-flash", "request_id": "synthetic-only-not-provider",
                        "usage": {**empty_usage(), "requests": 1, "successes": 1, "prompt_tokens": 25},
                        "decision": {"verdict": "same", "candidate_id": "f0001", "reason": "人工构造响应",
                                     "checks": {key: True for key in CHECKS}, "differences": []}}

        monkeypatch.setattr(workflow, "DeepSeekClient", ArtificialClient)
        workflow.review_job(manager, "sample")
        assert len(calls) == 1
        assert row["status"] == "review" and job["stats"]["ai_auto"] == 0
        assert row["planned_number"] == ""
        assert manager.ai_validation.snapshot()["qualified"] is False
        events = manager.ai_debug.snapshot()["events"]
        assert [event["stage"] for event in events] == [
            "run_started", "preparing", "requesting", "returned", "verifying", "manual", "run_finished"]
        assert events[-2]["verdict"] == "same" and events[-2]["reason_code"] == "validation_required"
        assert manager.ai_debug.snapshot()["active"] == []
        assert manager.ai_usage.snapshot()["requests"] == 1
        assert manager.ai_key_pool.snapshot()["usage"]["requests"] == 1
        assert SECRET not in json.dumps(events) and "人工构造响应" not in json.dumps(events)
    finally:
        manager.close()
