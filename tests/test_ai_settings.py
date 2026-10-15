import json
import os

import pytest

from hsd_tool.ai_settings import AiSettings


KEY = "sk-settings-test-credential-not-real"


class FakeProtector:
    def encrypt(self, value):
        return b"protected:" + bytes(character ^ 129 for character in value)

    def decrypt(self, value):
        if not value.startswith(b"protected:"):
            raise ValueError("cannot decrypt")
        return bytes(character ^ 129 for character in value[10:])


def test_encrypted_storage_and_sanitized_snapshot(tmp_path):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    assert settings.snapshot()["enabled"] is False
    result = settings.save({"api_key": KEY, "enabled": True})
    assert result["configured"] is True and result["key_source"] == "saved"
    assert KEY not in json.dumps(result)
    assert KEY not in settings.path.read_text("utf-8")
    assert "api_key" not in json.loads(settings.path.read_text("utf-8"))
    restored = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    assert restored.runtime()["api_key"] == KEY
    assert restored.runtime()["enabled"] is True
    assert not list(tmp_path.glob("*.tmp"))


def test_blank_key_preserves_saved_key_and_clear_removes_only_saved_key(tmp_path):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    settings.save({"api_key": KEY})
    settings.save({"api_key": "", "enabled": True})
    assert settings.runtime()["api_key"] == KEY
    settings.save({"clear_key": True, "enabled": False})
    assert settings.runtime()["api_key"] == ""
    assert json.loads(settings.path.read_text())["encrypted_api_key"] == ""
    assert AiSettings(tmp_path, protector=FakeProtector(), environ={}).snapshot()["configured"] is False


def test_environment_fallback_and_saved_key_priority(tmp_path):
    environment = {"DEEPSEEK_API_KEY": "sk-environment-credential-not-real"}
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ=environment)
    assert settings.snapshot()["key_source"] == "environment"
    settings.save({"api_key": KEY})
    assert settings.runtime()["api_key"] == KEY
    settings.save({"clear_key": True})
    assert settings.runtime()["api_key"] == environment["DEEPSEEK_API_KEY"]
    assert environment["DEEPSEEK_API_KEY"] not in json.dumps(settings.snapshot())


def test_no_plaintext_fallback_when_platform_cannot_encrypt(tmp_path):
    settings = AiSettings(tmp_path, protector=None, environ={})
    settings.save({"api_key": KEY, "enabled": True})
    assert settings.runtime()["api_key"] == KEY
    assert settings.snapshot()["key_persistence"] == "session_only"
    assert KEY not in settings.path.read_text()
    assert AiSettings(tmp_path, protector=None, environ={}).snapshot()["configured"] is False


@pytest.mark.parametrize("payload", [
    {"api_key": "short"}, {"api_key": KEY + "\n"}, {"api_key": KEY + " "},
    {"api_key": "密钥" * 20}, {"api_key": None}, {"api_key": "k" * 513},
    {"enabled": 1}, {"clear_key": "true"}, {"api_key": KEY, "clear_key": True},
    {"endpoint": "https://example.invalid"}, {"model": "another-model"}, [], None,
])
def test_invalid_settings_do_not_mutate_existing_credentials(tmp_path, payload):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    settings.save({"api_key": KEY, "enabled": True})
    before = settings.path.read_bytes()
    with pytest.raises(ValueError) as error:
        settings.save(payload)
    assert KEY not in str(error.value)
    assert settings.path.read_bytes() == before
    assert settings.runtime()["api_key"] == KEY


@pytest.mark.parametrize("record", ["invalid json", '{"version": 2}',
    '{"version":1,"enabled":true,"encrypted_api_key":"notbase64"}',
    json.dumps({"version": 1, "enabled": True, "encrypted_api_key": "eHh4"})])
def test_corrupt_or_other_user_secret_disables_automatic_calls(tmp_path, record):
    (tmp_path / "ai_settings.json").write_text(record)
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    assert settings.snapshot()["enabled"] is False
    assert settings.snapshot()["configured"] is False
    assert settings.snapshot()["storage_warning"]


def test_failed_encryption_never_writes_plaintext_or_replaces_previous_config(tmp_path):
    class Fails(FakeProtector):
        def encrypt(self, value):
            raise OSError("remote error " + KEY)

    settings = AiSettings(tmp_path, protector=Fails(), environ={})
    with pytest.raises(ValueError) as error:
        settings.save({"api_key": KEY, "enabled": True})
    assert KEY not in str(error.value)
    assert not settings.path.exists()
    assert settings.runtime()["api_key"] == ""


def test_atomic_save_failure_preserves_runtime_and_old_config(tmp_path, monkeypatch):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    settings.save({"api_key": KEY, "enabled": True})
    before = settings.path.read_bytes()
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk unavailable")))
    with pytest.raises(ValueError):
        settings.save({"api_key": "sk-replacement-credential-not-real", "enabled": False})
    assert settings.path.read_bytes() == before
    assert settings.runtime()["api_key"] == KEY
    assert settings.runtime()["enabled"] is True
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="Windows CurrentUser DPAPI integration")
def test_real_windows_current_user_dpapi_round_trip(tmp_path):
    settings = AiSettings(tmp_path, environ={})
    settings.save({"api_key": KEY, "enabled": True})
    assert KEY not in settings.path.read_text()
    assert AiSettings(tmp_path, environ={}).runtime()["api_key"] == KEY
