"""Gateway settings: endpoint validation, precedence and zero-key clients."""
import json

import pytest

from hsd_tool.ai_client import DeepSeekClient, ReviewError
from hsd_tool.ai_settings import OFFICIAL_ENDPOINT, AiSettings, load_gateway

KEY = "sk-ai-gateway-settings-test-not-real"
TOKEN = "gateway-token-0123456789abcdef"
ENDPOINT = "http://192.168.0.160:8899/v1/chat/completions"


class FakeProtector:
    def encrypt(self, value):
        return b"protected:" + bytes(character ^ 129 for character in value)

    def decrypt(self, value):
        if not value.startswith(b"protected:"):
            raise ValueError("cannot decrypt")
        return bytes(character ^ 129 for character in value[10:])


def settings(tmp_path, **kwargs):
    kwargs.setdefault("environ", {})
    return AiSettings(tmp_path, protector=FakeProtector(), **kwargs)


def test_gateway_file_is_loaded_and_validated(tmp_path):
    path = tmp_path / "gateway.json"
    path.write_text(json.dumps({"endpoint": ENDPOINT, "token": TOKEN}), "utf-8")
    assert load_gateway({}, path) == {"endpoint": ENDPOINT, "token": TOKEN}


def test_gateway_environment_wins_over_file(tmp_path):
    path = tmp_path / "gateway.json"
    path.write_text(json.dumps({"endpoint": "http://10.0.0.9:8899/v1/chat/completions", "token": TOKEN}), "utf-8")
    resolved = load_gateway({"HSD_AI_GATEWAY": ENDPOINT, "HSD_AI_GATEWAY_TOKEN": TOKEN}, path)
    assert resolved["endpoint"] == ENDPOINT


@pytest.mark.parametrize("endpoint", [
    "http://api.deepseek.com/chat/completions",
    "https://user:pass@192.168.0.160/x",
    "ftp://192.168.0.160/x",
    "http://192.168.0.160:8899/x?token=1",
    "",
])
def test_untrusted_gateway_endpoints_are_ignored(tmp_path, endpoint):
    assert load_gateway({"HSD_AI_GATEWAY": endpoint, "HSD_AI_GATEWAY_TOKEN": TOKEN}, tmp_path / "none.json") == {}


def test_incomplete_gateway_configuration_is_ignored(tmp_path):
    assert load_gateway({"HSD_AI_GATEWAY": ENDPOINT}, tmp_path / "none.json") == {}
    assert load_gateway({"HSD_AI_GATEWAY_TOKEN": TOKEN}, tmp_path / "none.json") == {}


def test_gateway_client_needs_no_local_key(tmp_path):
    managed = settings(tmp_path, gateway={"endpoint": ENDPOINT, "token": TOKEN})
    snapshot = managed.snapshot()
    assert snapshot["configured"] is True and snapshot["enabled"] is True
    assert snapshot["key_source"] == "gateway" and snapshot["via_gateway"] is True
    assert snapshot["key_persistence"] == "gateway"
    runtime = managed.runtime()
    assert runtime["api_key"] == TOKEN and runtime["endpoint"] == ENDPOINT
    assert runtime["via_gateway"] is True


def test_saved_local_key_wins_over_gateway(tmp_path):
    managed = settings(tmp_path, gateway={"endpoint": ENDPOINT, "token": TOKEN})
    managed.save({"api_key": KEY, "enabled": True})
    runtime = managed.runtime()
    assert runtime["api_key"] == KEY and runtime["via_gateway"] is False
    assert runtime["endpoint"] == OFFICIAL_ENDPOINT


def test_clearing_the_key_falls_back_to_the_gateway(tmp_path):
    managed = settings(tmp_path, gateway={"endpoint": ENDPOINT, "token": TOKEN})
    managed.save({"api_key": KEY, "enabled": True})
    managed.save({"clear_key": True})
    assert managed.runtime()["api_key"] == TOKEN
    assert managed.runtime()["via_gateway"] is True


def test_existing_settings_file_keeps_its_enabled_choice(tmp_path):
    managed = settings(tmp_path, gateway={"endpoint": ENDPOINT, "token": TOKEN})
    managed.save({"enabled": False})
    reopened = settings(tmp_path, gateway={"endpoint": ENDPOINT, "token": TOKEN})
    assert reopened.snapshot()["enabled"] is False
    assert reopened.snapshot()["configured"] is True


def test_client_uses_the_configured_endpoint():
    client = DeepSeekClient(KEY, endpoint=ENDPOINT)
    assert client.endpoint == ENDPOINT
    assert DeepSeekClient(KEY).endpoint == OFFICIAL_ENDPOINT
    with pytest.raises(ReviewError):
        DeepSeekClient(KEY, endpoint="http://public.example.com/x")
