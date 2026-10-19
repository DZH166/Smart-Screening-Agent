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
    assert json.loads(settings.path.read_text("utf-8"))["keys"] == []
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
    assert KEY not in settings.path.read_text("utf-8")
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
    assert KEY not in settings.path.read_text("utf-8")
    assert AiSettings(tmp_path, environ={}).runtime()["api_key"] == KEY


def test_v1_migration_preserves_key_without_touching_original_before_save(tmp_path):
    import base64
    original = json.dumps({"version": 1, "enabled": True, "encrypted_api_key":
                           base64.b64encode(FakeProtector().encrypt(KEY.encode())).decode()})
    path = tmp_path / "ai_settings.json"
    path.write_text(original, "utf-8")
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    assert settings.runtime()["api_key"] == KEY
    assert path.read_text("utf-8") == original
    assert settings.snapshot()["keys"][0]["id"] == "legacy"
    settings.save_pool({"expected_revision": 0, "add": [{"api_key": "sk-second-not-real-credential"}]})
    assert json.loads(path.read_text("utf-8"))["version"] == 2
    restored = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    assert [row["api_key"] for row in restored.runtime()["keys"]] == [KEY, "sk-second-not-real-credential"]
    assert restored.snapshot()["key_count"] == 2
    assert restored.runtime()["enabled"] is True


def test_pool_add_dedup_update_disable_delete_and_revision(tmp_path):
    from hsd_tool.ai_settings import AiSettingsConflict
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    state = settings.save_pool({"expected_revision": 0, "add": [
        {"api_key": KEY, "label": "账户 A"}, {"api_key": KEY},
        {"api_key": "sk-another-test-credential", "label": "账户 B"}]})
    assert state["key_count"] == 2 and state["key_revision"] == 1
    assert KEY not in json.dumps(state) and KEY not in settings.path.read_text("utf-8")
    first, second = [row["id"] for row in state["keys"]]
    state = settings.save_pool({"expected_revision": 1, "update": [{"id": first, "enabled": False, "label": "主账户"}]})
    assert state["keys"][0]["enabled"] is False
    assert settings.runtime()["api_key"] == "sk-another-test-credential"
    before = settings.path.read_bytes()
    with pytest.raises(AiSettingsConflict):
        settings.save_pool({"expected_revision": 1, "remove": [second]})
    assert settings.path.read_bytes() == before
    state = settings.save_pool({"expected_revision": 2, "remove": [first]})
    assert state["key_count"] == 1
    assert state["keys"][0]["id"] == second
    restored = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    assert restored.snapshot() == state


def test_pool_atomic_failure_does_not_disable_rename_or_remove(tmp_path, monkeypatch):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    initial = settings.save_pool({"expected_revision": 0, "add": [{"api_key": KEY}]})
    before = settings.path.read_bytes()
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk unavailable")))
    with pytest.raises(ValueError):
        settings.save_pool({"expected_revision": 1, "update": [{"id": initial["keys"][0]["id"], "enabled": False}]})
    assert settings.snapshot() == initial
    assert settings.path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("change", [
    {"expected_revision": True}, {"expected_revision": -1}, {"expected_revision": 0, "enabled": True},
    {"expected_revision": 0, "add": None}, {"expected_revision": 0, "remove": [None]},
    {"expected_revision": 0, "add": [{"api_key": KEY, "enabled": False}]},
    {"expected_revision": 0, "add": [{"api_key": KEY, "label": "a\nb"}]},
    {"expected_revision": 0, "add": [{"api_key": KEY, "label": KEY}]},
    {"expected_revision": 0, "add": [{"api_key": KEY, "label": "a" * 65}]},
    {"expected_revision": 0, "update": [{"id": "legacy", "enabled": "false"}]},
])
def test_invalid_pool_operations_never_persist_or_echo_secrets(tmp_path, change):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    with pytest.raises(ValueError) as error:
        settings.save_pool(change)
    assert KEY not in str(error.value)
    assert settings.snapshot()["key_count"] == 0
    assert not settings.path.exists()


def test_pool_accepts_100_keys_and_rejects_overflow_without_partial_save(tmp_path):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    initial = settings.save_pool({"expected_revision": 0, "add": [
        {"api_key": "sk-unit-test-%03d-not-real" % i} for i in range(100)]})
    assert initial["key_count"] == 100
    with pytest.raises(ValueError):
        settings.save_pool({"expected_revision": 1, "add": [{"api_key": KEY}]})
    assert settings.snapshot() == initial
    restored = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    assert restored.snapshot() == initial


def test_pool_session_only_never_writes_keys_and_environment_can_be_disabled(tmp_path):
    settings = AiSettings(tmp_path / "session", protector=None, environ={})
    settings.save_pool({"expected_revision": 0, "add": [{"api_key": KEY}]})
    assert settings.runtime()["api_key"] == KEY
    assert KEY not in settings.path.read_text("utf-8")
    assert AiSettings(tmp_path / "session", protector=None, environ={}).snapshot()["key_count"] == 0
    environment = AiSettings(tmp_path / "env", protector=None, environ={"DEEPSEEK_API_KEY": KEY})
    state = environment.save_pool({"expected_revision": 0, "update": [{"id": "environment", "enabled": False}]})
    assert state["key_count"] == 1 and state["configured"] is True
    assert environment.runtime()["api_key"] == ""
    with pytest.raises(ValueError):
        environment.save_pool({"expected_revision": 1, "remove": ["environment"]})


def test_pool_thread_revision_conflict_allows_only_one_winner(tmp_path):
    import concurrent.futures
    from hsd_tool.ai_settings import AiSettingsConflict
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    def save(index):
        try:
            settings.save_pool({"expected_revision": 0, "add": [{"api_key": "sk-thread-%02d-not-real" % index}]})
            return "saved"
        except AiSettingsConflict:
            return "conflict"
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(save, range(8)))
    assert results.count("saved") == 1 and results.count("conflict") == 7
    assert settings.snapshot()["key_count"] == 1


def test_legacy_save_preserves_other_keys_and_replacement_has_new_identity(tmp_path):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    first = settings.save_pool({"expected_revision": 0, "add": [
        {"api_key": KEY}, {"api_key": "sk-another-legacy-test-key"}]})
    settings.save({"api_key": "sk-replaced-legacy-test-key", "enabled": True})
    current = settings.snapshot()
    assert current["key_count"] == 2
    assert current["keys"][0]["id"] != first["keys"][0]["id"]
    settings.save({"clear_key": True})
    assert settings.snapshot()["key_count"] == 1
    assert settings.runtime()["api_key"] == "sk-another-legacy-test-key"


def test_removed_key_cannot_be_leaked_as_label_in_same_transaction(tmp_path):
    settings = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    first = settings.save_pool({"expected_revision": 0, "add": [{"api_key": KEY}]})
    with pytest.raises(ValueError) as error:
        settings.save_pool({"expected_revision": 1, "remove": [first["keys"][0]["id"]],
                            "add": [{"api_key": "sk-new-credential-not-real", "label": KEY}]})
    assert KEY not in str(error.value)
    assert settings.snapshot() == first
