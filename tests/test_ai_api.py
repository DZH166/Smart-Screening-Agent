"""Local-only settings, usage and workflow eligibility HTTP contracts."""
import json
from pathlib import Path

import pytest

from hsd_tool.server import create_app
from hsd_tool.ai_usage import UsageLedger
from test_service import prepared, wait_export


@pytest.fixture
def application(tmp_path):
    app = create_app(tmp_path / "application", token="local-test-token")
    yield app
    app.config["HSD_MANAGER"].close()


def test_settings_never_echo_key_and_blank_save_preserves_it(application):
    client = application.test_client()
    headers = {"X-HSD-Token": "local-test-token"}
    key = "synthetic-not-a-real-deepseek-key"
    response = client.post("/api/ai/settings", json={"api_key": key, "enabled": True}, headers=headers)
    assert response.status_code == 200 and response.json["configured"]
    assert key not in response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "no-store"
    blank = client.post("/api/ai/settings", json={"api_key": "", "enabled": True}, headers=headers)
    assert blank.json["configured"]
    assert application.config["HSD_MANAGER"].ai_settings.runtime()["api_key"] == key
    assert key not in client.get("/api/config").get_data(as_text=True)
    assert key not in client.get("/api/ai/settings").get_data(as_text=True)
    cleared = client.post("/api/ai/settings", json={"clear_key": True}, headers=headers)
    assert not cleared.json["configured"]


def test_settings_do_not_accept_browser_activation_or_untrusted_destination(application):
    client = application.test_client()
    for payload in ({"mode": "validated"}, {"trusted": True}, {"base_url": "https://example.invalid"},
                    {"model": "unverified-model"}, {"api_key": "secret\nheader"}):
        assert client.post("/api/ai/settings", json=payload, headers={"X-HSD-Token": "local-test-token"}).status_code == 400
    assert client.get("/api/ai/settings").json["mode"] == "evaluation"
    assert client.post("/api/ai/settings", json={"enabled": True}).status_code == 403


@pytest.mark.parametrize("payload", [[], ["bad"], "bad", None])
def test_post_payload_requires_object(application, payload):
    response = application.test_client().post("/api/ai/settings", data=json.dumps(payload),
        headers={"X-HSD-Token": "local-test-token", "Content-Type": "application/json"})
    assert response.status_code == 400


def test_settings_and_shutdown_refuse_while_ai_is_in_flight(application):
    manager = application.config["HSD_MANAGER"]
    manager.jobs["busy"] = {"status": "ai_review"}
    client = application.test_client()
    headers = {"X-HSD-Token": "local-test-token"}
    assert client.post("/api/ai/settings", json={"enabled": True}, headers=headers).status_code == 400
    assert client.post("/api/shutdown", json={}, headers=headers).status_code == 400
    manager.jobs.clear()


def test_usage_reads_external_validator_updates_and_marks_unknown_charges(application):
    manager = application.config["HSD_MANAGER"]
    other = UsageLedger(manager.data_dir)
    other.add({"requests": 2, "successes": 1, "failures": 1, "unknown_usage_requests": 1,
               "estimated_usd": .001})
    value = application.test_client().get("/api/ai/usage").json
    assert value["requests"] == 2 and value["estimated_usd"] == .001
    assert value["cost_incomplete"] and value["estimated_usd_upper_bound"] is None


def test_review_requires_config_and_cannot_run_during_export(tmp_path):
    manager, job = prepared(tmp_path, [""])
    try:
        with pytest.raises(ValueError, match="密钥"):
            manager.review_ai("sample")
        job["status"] = "exporting"
        with pytest.raises(ValueError, match="当前任务"):
            manager.review_ai("sample")
    finally:
        manager.close()


def test_export_uses_server_status_not_an_ai_suggestion(tmp_path):
    manager, job = prepared(tmp_path, ["KEEP", ""])
    try:
        row = job["rows"][1]
        row.update(_status="review", _file_id=None, status="auto", file_id="f3",
                   ai_review={"outcome": "auto_passed", "verdict": "same", "candidate_id": "f3"})
        manager.export("sample")
        result = wait_export(manager)
        assert result["status"] == "done" and result["report"]["exported"] == 1
        assert result["report"]["new_numbers"] == 0
        report = json.loads((Path(result["output_dir"]) / "处理记录.json").read_text("utf-8"))
        assert report["pending_rows"][0]["status"] == "review"
    finally:
        manager.close()


def test_export_rejects_stale_summary_revision(tmp_path):
    manager, job = prepared(tmp_path, ["A", "B"])
    try:
        revision = manager.snapshot("sample")["revision"]
        manager.resolve("sample", "r2", None)
        with pytest.raises(ValueError, match="其他页面"):
            manager.export("sample", expected_revision=revision)
        assert job["status"] == "ready"
    finally:
        manager.close()
