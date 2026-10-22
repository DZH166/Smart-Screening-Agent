"""Synthetic material credentials only: no provider calls or real secrets."""
import base64
import json
import os
from pathlib import Path
import stat

import pytest

from hsd_tool import material_settings as module
from hsd_tool.ai_settings import AiSettings
from hsd_tool.material_settings import MaterialSettings, MaterialSettingsConflict


KEY = "synthetic-fal-id:synthetic-fal-secret-not-real"
SECOND = "synthetic-second-id:synthetic-second-secret-not-real"


class FakeProtector:
    def encrypt(self, value):
        return b"protected:" + bytes(character ^ 129 for character in value)

    def decrypt(self, value):
        if not value.startswith(b"protected:"):
            raise ValueError("synthetic protection failure")
        return bytes(character ^ 129 for character in value[10:])


def settings_at(path):
    return MaterialSettings(path, protector=FakeProtector(), environ={})


def test_encrypted_roundtrip_snapshot_is_closed_and_private_runtime_only(tmp_path):
    settings = settings_at(tmp_path)
    assert settings.snapshot() == {
        "enabled": False, "configured": False, "key_persistence": "windows_dpapi",
        "revision": 0, "warning": ""}
    result = settings.save({"api_key": KEY, "enabled": True, "expected_revision": 0})
    assert result["enabled"] and result["configured"] and result["revision"] == 1
    assert KEY not in json.dumps(result) and KEY[-8:] not in json.dumps(result)
    assert KEY not in settings.path.read_text("utf-8")
    assert set(json.loads(settings.path.read_text("utf-8"))) == {
        "version", "enabled", "revision", "encrypted_fal_key"}
    restored = settings_at(tmp_path)
    assert restored.runtime() == {"enabled": True, "fal_key": KEY, "revision": 1}
    assert restored.snapshot() == result
    assert not list(tmp_path.glob(".material-settings-*.tmp"))


def test_same_settings_are_noop_and_blank_input_preserves_secret(tmp_path):
    settings = settings_at(tmp_path)
    settings.save_fal_key(KEY, expected_revision=0)
    before = settings.path.read_bytes()
    result = settings.save({"api_key": "", "expected_revision": 1})
    assert result["revision"] == 1 and settings.path.read_bytes() == before
    settings.set_enabled(True, expected_revision=1)
    assert settings.runtime() == {"enabled": True, "fal_key": KEY, "revision": 2}


def test_delete_disables_then_new_key_does_not_silently_enable(tmp_path):
    settings = settings_at(tmp_path)
    settings.save({"api_key": KEY, "enabled": True, "expected_revision": 0})
    result = settings.remove_fal_key(expected_revision=1)
    assert not result["enabled"] and not result["configured"] and result["revision"] == 2
    assert settings_at(tmp_path).runtime()["fal_key"] == ""
    assert json.loads(settings.path.read_text("utf-8"))["encrypted_fal_key"] == ""
    settings.save_fal_key(SECOND, expected_revision=2)
    assert settings.runtime()["enabled"] is False


def test_stale_page_cannot_replace_delete_or_toggle_key(tmp_path):
    settings = settings_at(tmp_path)
    settings.save_fal_key(KEY, expected_revision=0)
    before = settings.path.read_bytes()
    for change in ({"api_key": SECOND}, {"clear_key": True}, {"enabled": True}):
        with pytest.raises(MaterialSettingsConflict) as error:
            settings.save(dict(expected_revision=0, **change))
        assert error.value.code == "revision_conflict"
        assert KEY not in str(error.value)
        assert settings.path.read_bytes() == before
    assert settings.runtime()["fal_key"] == KEY


@pytest.mark.parametrize("payload", [
    None, [], {}, {"expected_revision": True}, {"expected_revision": -1},
    {"expected_revision": "1"}, {"expected_revision": 1, "endpoint": "https://example.invalid"},
    {"expected_revision": 1, "api_key": None}, {"expected_revision": 1, "api_key": "short"},
    {"expected_revision": 1, "api_key": KEY + "\n"},
    {"expected_revision": 1, "api_key": KEY + " "},
    {"expected_revision": 1, "api_key": "非ASCII" * 20},
    {"expected_revision": 1, "api_key": "x" * 513},
    {"expected_revision": 1, "enabled": 1},
    {"expected_revision": 1, "clear_key": "yes"},
    {"expected_revision": 1, "api_key": SECOND, "clear_key": True},
])
def test_invalid_save_preserves_existing_runtime_and_file(tmp_path, payload):
    settings = settings_at(tmp_path)
    settings.save({"api_key": KEY, "enabled": True, "expected_revision": 0})
    before = settings.path.read_bytes()
    with pytest.raises(ValueError) as error:
        settings.save(payload)
    assert KEY not in str(error.value) and SECOND not in str(error.value)
    assert settings.path.read_bytes() == before
    assert settings.runtime() == {"enabled": True, "fal_key": KEY, "revision": 1}


def test_enabling_without_key_rejected_without_creating_file(tmp_path):
    settings = settings_at(tmp_path)
    with pytest.raises(ValueError, match="请先保存"):
        settings.set_enabled(True, expected_revision=0)
    assert not settings.path.exists() and settings.snapshot()["revision"] == 0


def test_no_session_or_environment_fallback_without_protection(tmp_path):
    settings = MaterialSettings(tmp_path, protector=None, environ={
        "FAL_KEY": KEY, "FAL_API_KEY": KEY, "DEEPSEEK_API_KEY": KEY})
    assert settings.snapshot()["key_persistence"] == "unavailable"
    assert settings.runtime()["fal_key"] == ""
    with pytest.raises(ValueError) as error:
        settings.save_fal_key(KEY, expected_revision=0)
    assert KEY not in str(error.value) and not settings.path.exists()
    assert settings.runtime()["fal_key"] == ""


def test_encryption_failure_keeps_old_key_and_hides_protector_exception(tmp_path):
    settings = settings_at(tmp_path)
    settings.save_fal_key(KEY, expected_revision=0)
    before = settings.path.read_bytes()

    class Broken(FakeProtector):
        def encrypt(self, value):
            raise RuntimeError(SECOND)

    settings._protector = Broken()
    with pytest.raises(ValueError) as error:
        settings.save_fal_key(SECOND, expected_revision=1)
    assert SECOND not in str(error.value)
    assert settings.path.read_bytes() == before and settings.runtime()["fal_key"] == KEY


def test_replace_failure_keeps_file_runtime_and_cleans_temporary(tmp_path, monkeypatch):
    settings = settings_at(tmp_path)
    settings.save({"api_key": KEY, "enabled": True, "expected_revision": 0})
    before = settings.path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError(SECOND)

    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(ValueError) as error:
        settings.save({"api_key": SECOND, "enabled": False, "expected_revision": 1})
    assert SECOND not in str(error.value)
    assert settings.path.read_bytes() == before
    assert settings.runtime() == {"enabled": True, "fal_key": KEY, "revision": 1}
    assert not list(tmp_path.glob(".material-settings-*.tmp"))


def test_local_hardlinked_settings_are_not_read_or_replaced(tmp_path):
    settings = settings_at(tmp_path)
    settings.save_fal_key(KEY, expected_revision=0)
    linked = tmp_path / "other.json"
    try:
        os.link(settings.path, linked)
    except OSError:
        pytest.skip("filesystem does not support hardlinks")
    before = linked.read_bytes()
    restored = settings_at(tmp_path)
    assert not restored.snapshot()["configured"] and restored.snapshot()["warning"]
    with pytest.raises(ValueError):
        settings.save_fal_key(SECOND, expected_revision=1)
    assert settings.path.read_bytes() == before and linked.read_bytes() == before
    assert settings.runtime()["fal_key"] == KEY


@pytest.mark.parametrize("failure", ["json", "oversized", "fields", "version_bool", "revision_bool",
                                     "ciphertext", "domain", "enabled_empty"])
def test_corrupt_storage_fails_closed_without_echoing_content(tmp_path, failure):
    settings = settings_at(tmp_path)
    settings.save_fal_key(KEY, expected_revision=0)
    record = json.loads(settings.path.read_text("utf-8"))
    if failure == "json":
        content = KEY
    elif failure == "oversized":
        content = "x" * (module.MAX_SETTINGS_BYTES + 1)
    else:
        if failure == "fields":
            record["api_key"] = KEY
        elif failure == "version_bool":
            record["version"] = True
        elif failure == "revision_bool":
            record["revision"] = True
        elif failure == "ciphertext":
            record["encrypted_fal_key"] = "!!!not-base64!!!"
        elif failure == "domain":
            record["encrypted_fal_key"] = base64.b64encode(
                FakeProtector().encrypt(KEY.encode())).decode()
        else:
            record.update(enabled=True, encrypted_fal_key="")
        content = json.dumps(record)
    settings.path.write_text(content, encoding="utf-8")
    restored = settings_at(tmp_path)
    assert restored.runtime() == {"enabled": False, "fal_key": "", "revision": 0}
    assert restored.snapshot()["warning"] and KEY not in json.dumps(restored.snapshot())
    assert settings.path.read_text("utf-8") == content


def test_fal_and_deepseek_ciphertext_are_not_interchangeable(tmp_path):
    deepseek = AiSettings(tmp_path, protector=FakeProtector(), environ={})
    deepseek.save({"api_key": KEY, "enabled": True})
    original = deepseek.path.read_bytes()
    material = settings_at(tmp_path)
    material.save_fal_key(SECOND, expected_revision=0)
    assert deepseek.path.read_bytes() == original
    assert deepseek.runtime()["api_key"] == KEY
    record = json.loads(material.path.read_text("utf-8"))
    record["encrypted_fal_key"] = json.loads(original)["keys"][0]["encrypted_api_key"]
    material.path.write_text(json.dumps(record), encoding="utf-8")
    assert settings_at(tmp_path).snapshot()["configured"] is False


def test_linux_store_integration_with_real_aes_and_synthetic_file_io(tmp_path, monkeypatch):
    from hsd_tool import credential_store
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    cipher = credential_store.LinuxCredentialStore.__new__(credential_store.LinuxCredentialStore)
    cipher._key = os.urandom(32)
    cipher._read_key = lambda: cipher._key
    cipher._cipher_class = AESGCM

    class SyntheticStore:
        def __init__(self, key_file, settings_file):
            self.path = Path(settings_file)

        def encrypt(self, value):
            return cipher.encrypt(value)

        def decrypt(self, value):
            return cipher.decrypt(value)

        def read_settings(self, limit):
            return self.path.read_bytes() if self.path.exists() else None

        def write_settings(self, record):
            self.path.write_text(json.dumps(record), encoding="utf-8")

    monkeypatch.setattr(credential_store, "LinuxCredentialStore", SyntheticStore)
    settings = MaterialSettings(tmp_path, credential_key_file="synthetic", environ={})
    result = settings.save({"api_key": KEY, "enabled": True, "expected_revision": 0})
    assert result["key_persistence"] == "linux_aesgcm"
    assert KEY not in settings.path.read_text("utf-8")
    restored = MaterialSettings(tmp_path, environ={"HSD_CREDENTIAL_KEY_FILE": "synthetic"})
    assert restored.runtime() == {"enabled": True, "fal_key": KEY, "revision": 1}


def test_explicit_linux_store_cannot_be_overridden_by_session_or_test_protector(tmp_path):
    with pytest.raises(ValueError, match="不能"):
        MaterialSettings(tmp_path, protector=None, credential_key_file="synthetic", environ={})


@pytest.mark.skipif(os.name != "nt", reason="actual Windows CurrentUser DPAPI")
def test_windows_dpapi_actual_roundtrip(tmp_path):
    settings = MaterialSettings(tmp_path, environ={})
    settings.save({"api_key": KEY, "enabled": True, "expected_revision": 0})
    assert KEY not in settings.path.read_text("utf-8")
    assert MaterialSettings(tmp_path, environ={}).runtime()["fal_key"] == KEY


@pytest.mark.skipif(os.name != "posix", reason="actual Linux openat/private file permissions")
def test_linux_actual_roundtrip_permissions_and_master_rotation(tmp_path):
    private = tmp_path / "private"
    data = tmp_path / "settings"
    private.mkdir(mode=0o700)
    data.mkdir(mode=0o700)
    key_file = private / "key"
    key_file.write_bytes(os.urandom(32))
    key_file.chmod(0o600)
    settings = MaterialSettings(data, credential_key_file=key_file, environ={})
    settings.save({"api_key": KEY, "enabled": True, "expected_revision": 0})
    assert stat.S_IMODE(settings.path.stat().st_mode) == 0o600
    restored = MaterialSettings(data, credential_key_file=key_file, environ={})
    assert restored.runtime()["fal_key"] == KEY
    before = settings.path.read_bytes()
    key_file.write_bytes(os.urandom(32))
    with pytest.raises(ValueError):
        settings.set_enabled(False, expected_revision=1)
    assert settings.path.read_bytes() == before and settings.runtime()["enabled"]


@pytest.mark.skipif(os.name != "posix", reason="actual Linux link and permission semantics")
@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "file_mode", "parent_mode"])
def test_linux_unsafe_settings_never_overwritten_or_enabled(tmp_path, unsafe):
    private = tmp_path / "private"
    data = tmp_path / "settings"
    private.mkdir(mode=0o700)
    data.mkdir(mode=0o700)
    key_file = private / "key"
    key_file.write_bytes(os.urandom(32))
    key_file.chmod(0o600)
    settings = MaterialSettings(data, credential_key_file=key_file, environ={})
    settings.save_fal_key(KEY, expected_revision=0)
    if unsafe == "symlink":
        target = data / "original.json"
        settings.path.rename(target)
        settings.path.symlink_to(target)
    elif unsafe == "hardlink":
        os.link(settings.path, data / "linked.json")
    elif unsafe == "file_mode":
        settings.path.chmod(0o644)
    else:
        data.chmod(0o755)
    if unsafe == "parent_mode":
        with pytest.raises(ValueError):
            MaterialSettings(data, credential_key_file=key_file, environ={})
    else:
        restored = MaterialSettings(data, credential_key_file=key_file, environ={})
        assert not restored.snapshot()["configured"] and restored.snapshot()["warning"]
    with pytest.raises(ValueError):
        settings.save_fal_key(SECOND, expected_revision=1)
    assert settings.runtime()["fal_key"] == KEY
