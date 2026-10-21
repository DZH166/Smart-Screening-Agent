"""Synthetic credential tests; no production Keys or Linux claims on Windows."""
import base64
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from hsd_tool.ai_settings import AiSettings
from hsd_tool import credential_store as store


KEY = "sk-linux-synthetic-test-key-not-real"
SECOND = "sk-linux-second-synthetic-not-real"
REAL_STORE = store.LinuxCredentialStore


def synthetic_cipher(key=None):
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    protector = REAL_STORE.__new__(REAL_STORE)
    protector._key = key or os.urandom(32)
    protector._read_key = lambda: protector._key
    protector._cipher_class = AESGCM
    return protector


def test_cipher_is_authenticated_nondeterministic_and_never_contains_plaintext():
    protector = synthetic_cipher()
    one, two = (protector.encrypt(KEY.encode()) for _ in range(2))
    assert one != two and KEY.encode() not in one
    assert protector.decrypt(one) == KEY.encode()
    assert protector.decrypt(two) == KEY.encode()


@pytest.mark.parametrize("change", ["header", "nonce", "body", "tag", "truncate", "wrong_key"])
def test_cipher_rejects_corruption_and_wrong_master_without_echo(change):
    protector = synthetic_cipher()
    encrypted = bytearray(protector.encrypt(KEY.encode()))
    indexes = {"header": 0, "nonce": len(store._MAGIC), "body": len(store._MAGIC) + 12, "tag": -1}
    if change == "truncate":
        encrypted = encrypted[:12]
    elif change == "wrong_key":
        protector = synthetic_cipher()
    else:
        encrypted[indexes[change]] ^= 1
    with pytest.raises(ValueError) as error:
        protector.decrypt(bytes(encrypted))
    assert KEY not in str(error.value)


def test_cipher_detects_master_key_replacement_during_process_lifetime():
    protector = synthetic_cipher()
    protector._read_key = lambda: os.urandom(32)
    with pytest.raises(ValueError):
        protector.encrypt(KEY.encode())


@pytest.mark.parametrize("directory,mode,owner,links,valid", [
    (True, stat.S_IFDIR | 0o700, 1001, 1, True),
    (False, stat.S_IFREG | 0o600, 1001, 1, True),
    (False, stat.S_IFREG | 0o400, 1001, 1, True),
    (True, stat.S_IFDIR | 0o750, 1001, 1, False),
    (True, stat.S_IFDIR | 0o700, 1002, 1, False),
    (True, stat.S_IFDIR | 0o600, 1001, 1, False),
    (False, stat.S_IFREG | 0o644, 1001, 1, False),
    (False, stat.S_IFREG | 0o600, 1002, 1, False),
    (False, stat.S_IFREG | 0o600, 1001, 2, False),
    (False, stat.S_IFLNK | 0o600, 1001, 1, False),
    (False, stat.S_IFIFO | 0o600, 1001, 1, False),
    (False, stat.S_IFREG | 0o700, 1001, 1, False),
    (False, stat.S_IFREG | 0o4600, 1001, 1, False),
    (True, stat.S_IFDIR | 0o1700, 1001, 1, False),
])
def test_posix_permission_policy(directory, mode, owner, links, valid, monkeypatch):
    monkeypatch.setattr(store.os, "geteuid", lambda: 1001, raising=False)
    info = SimpleNamespace(st_mode=mode, st_uid=owner, st_nlink=links)
    if valid:
        store._private_stat(info, directory=directory)
    else:
        with pytest.raises(ValueError):
            store._private_stat(info, directory=directory)


def test_aes_settings_pool_roundtrip_with_synthetic_file_io(tmp_path, monkeypatch):
    """Exercise actual AES/pool integration, not POSIX filesystem enforcement."""
    master = os.urandom(32)

    class SyntheticFileStore:
        def __init__(self, key_file, settings_file):
            self.path = Path(settings_file)
            self.cipher = synthetic_cipher(master)

        def encrypt(self, value):
            return self.cipher.encrypt(value)

        def decrypt(self, value):
            return self.cipher.decrypt(value)

        def read_settings(self, limit):
            return self.path.read_bytes() if self.path.exists() else None

        def write_settings(self, record):
            self.path.write_text(json.dumps(record), encoding="utf-8")

    monkeypatch.setattr(store, "LinuxCredentialStore", SyntheticFileStore)
    settings = AiSettings(tmp_path, credential_key_file="synthetic", environ={})
    first = settings.save_pool({"expected_revision": 0, "add": [{"api_key": KEY}, {"api_key": SECOND}]})
    settings.save({"enabled": True})
    assert first["key_persistence"] == "linux_aesgcm"
    assert KEY not in json.dumps(first) and SECOND not in settings.path.read_text()
    assert KEY not in settings.path.read_text()
    restored = AiSettings(tmp_path, environ={"HSD_CREDENTIAL_KEY_FILE": "synthetic"})
    assert [row["api_key"] for row in restored.runtime()["keys"]] == [KEY, SECOND]
    assert restored.runtime()["enabled"] is True
    restored.save_pool({"expected_revision": 2, "update": [{"id": first["keys"][0]["id"], "enabled": False}]})
    assert restored.runtime()["api_key"] == SECOND
    assert KEY not in json.dumps(restored.snapshot())


def test_explicit_server_protection_cannot_be_silently_overridden(tmp_path):
    with pytest.raises(ValueError):
        AiSettings(tmp_path, protector=None, credential_key_file="synthetic", environ={})


POSIX = pytest.mark.skipif(os.name != "posix", reason="requires actual POSIX openat/owner/mode semantics")


@pytest.fixture
def linux_paths(tmp_path):
    private = tmp_path / "secrets"
    settings = tmp_path / "settings"
    private.mkdir(mode=0o700)
    settings.mkdir(mode=0o700)
    key_file = private / "credential.key"
    key_file.write_bytes(os.urandom(32))
    key_file.chmod(0o600)
    return key_file, settings


@POSIX
def test_linux_actual_encrypted_pool_restart_and_permissions(linux_paths):
    key_file, directory = linux_paths
    settings = AiSettings(directory, credential_key_file=key_file, environ={})
    settings.save_pool({"expected_revision": 0, "add": [{"api_key": KEY}, {"api_key": SECOND}]})
    settings.save({"enabled": True})
    assert stat.S_IMODE(settings.path.stat().st_mode) == 0o600
    assert KEY not in settings.path.read_text()
    restored = AiSettings(directory, credential_key_file=key_file, environ={})
    assert restored.snapshot()["key_persistence"] == "linux_aesgcm"
    assert restored.runtime()["enabled"] is True
    assert [row["api_key"] for row in restored.runtime()["keys"]] == [KEY, SECOND]
    assert not list(directory.glob(".ai-settings-*.tmp"))


@POSIX
@pytest.mark.parametrize("failure", ["missing", "short", "master_mode", "parent_mode", "master_link", "ancestor_link", "hardlink", "master_in_data"])
def test_linux_unsafe_master_never_falls_back(linux_paths, failure):
    key_file, directory = linux_paths
    if failure == "missing":
        key_file.unlink()
    elif failure == "short":
        key_file.write_bytes(b"bad-size")
    elif failure == "master_mode":
        key_file.chmod(0o644)
    elif failure == "parent_mode":
        key_file.parent.chmod(0o755)
    elif failure == "master_link":
        target = key_file.with_name("original")
        key_file.rename(target)
        key_file.symlink_to(target)
    elif failure == "ancestor_link":
        target = key_file.parent.with_name("linked-secrets")
        target.symlink_to(key_file.parent, target_is_directory=True)
        key_file = target / key_file.name
    elif failure == "hardlink":
        os.link(key_file, key_file.with_name("copy"))
    else:
        key_file = directory / "credential.key"
        key_file.write_bytes(os.urandom(32))
        key_file.chmod(0o600)
    with pytest.raises(ValueError) as error:
        AiSettings(directory, credential_key_file=key_file, environ={})
    assert str(key_file) not in str(error.value)
    assert not (directory / "ai_settings.json").exists()


@POSIX
@pytest.mark.parametrize("failure", ["symlink", "permissions", "corruption", "new_master"])
def test_linux_unsafe_or_corrupt_settings_disable_ai_without_plaintext(linux_paths, failure):
    key_file, directory = linux_paths
    settings = AiSettings(directory, credential_key_file=key_file, environ={})
    settings.save({"api_key": KEY, "enabled": True})
    if failure == "symlink":
        actual = settings.path.with_name("actual.json")
        settings.path.rename(actual)
        settings.path.symlink_to(actual)
    elif failure == "permissions":
        settings.path.chmod(0o644)
    elif failure == "corruption":
        record = json.loads(settings.path.read_text())
        encrypted = bytearray(base64.b64decode(record["keys"][0]["encrypted_api_key"]))
        encrypted[-1] ^= 1
        record["keys"][0]["encrypted_api_key"] = base64.b64encode(encrypted).decode()
        settings.path.write_text(json.dumps(record))
    else:
        key_file.write_bytes(os.urandom(32))
    restored = AiSettings(directory, credential_key_file=key_file, environ={})
    assert not restored.snapshot()["enabled"] and not restored.snapshot()["configured"]
    assert restored.snapshot()["storage_warning"]
    assert KEY not in settings.path.read_text()


@POSIX
def test_linux_master_changed_during_save_preserves_previous_runtime_and_settings(linux_paths):
    key_file, directory = linux_paths
    settings = AiSettings(directory, credential_key_file=key_file, environ={})
    settings.save({"api_key": KEY, "enabled": True})
    before = settings.path.read_bytes()
    key_file.write_bytes(os.urandom(32))
    with pytest.raises(ValueError):
        settings.save({"enabled": False})
    assert settings.path.read_bytes() == before
    assert settings.runtime()["api_key"] == KEY and settings.runtime()["enabled"] is True


@POSIX
@pytest.mark.skipif(not hasattr(os, "O_PATH"), reason="Linux O_PATH traversal")
def test_linux_private_credentials_under_search_only_ancestor(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses directory read permission; run as the service user")
    ancestor = tmp_path / "search-only-ancestor"
    ancestor.mkdir(mode=0o700)
    secrets_directory = ancestor / "secrets"
    settings_directory = ancestor / "settings"
    secrets_directory.mkdir(mode=0o700)
    settings_directory.mkdir(mode=0o700)
    key_file = secrets_directory / "credential.key"
    key_file.write_bytes(os.urandom(32))
    key_file.chmod(0o600)
    # Non-root tests cannot chown this directory to root and simulate the
    # deployed root-owned 0711 parent. 0111 removes read permission for the
    # current owner too, while preserving the same traversal-only constraint.
    ancestor.chmod(0o111)
    try:
        with pytest.raises(PermissionError):
            list(ancestor.iterdir())
        settings = AiSettings(settings_directory, credential_key_file=key_file, environ={})
        settings.save({"api_key": KEY, "enabled": True})
        restored = AiSettings(settings_directory, credential_key_file=key_file, environ={})
        assert restored.runtime()["api_key"] == KEY
        assert restored.snapshot()["enabled"] is True
        # Successful write_settings includes fsync(directory), so this also
        # rejects an implementation that accidentally yields the O_PATH fd.
        assert settings.path.stat().st_mode & 0o777 == 0o600
    finally:
        ancestor.chmod(0o700)
