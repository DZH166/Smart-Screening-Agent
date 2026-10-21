"""Cloud account tests use generated synthetic passwords only."""
import hashlib
import json
import os

import pytest

from hsd_tool import cloud_admin


USERNAME = "synthetic-cloud-admin"
PASSWORD = "synthetic-cloud-password-not-production"
SALT = b"synthetic-salt-32-bytes-1234567890"
ITERATIONS = cloud_admin.MIN_ITERATIONS


@pytest.fixture(scope="module")
def record():
    return {"username": USERNAME, "salt_hex": SALT.hex(), "iterations": ITERATIONS,
            "digest_hex": hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), SALT, ITERATIONS).hex()}


@pytest.fixture
def credentials(record, monkeypatch):
    monkeypatch.setattr(cloud_admin, "_read_admin_file", lambda _: json.dumps(record).encode())
    return cloud_admin.CloudAdminCredentials("synthetic-private-file")


def test_cloud_credentials_accept_only_the_private_account(credentials):
    assert credentials.verify(USERNAME, PASSWORD)
    assert not credentials.verify(USERNAME, PASSWORD + "wrong")
    assert not credentials.verify(USERNAME + "wrong", PASSWORD)
    assert not credentials.verify("15159156156", PASSWORD)
    assert PASSWORD not in repr(credentials)


@pytest.mark.parametrize("username,password", [
    (None, None), (True, PASSWORD), (USERNAME, None), ("", PASSWORD), (USERNAME, ""),
    (USERNAME, "x" * 257), ("x" * 129, PASSWORD), (USERNAME, "\ud800"), ("\ud800", PASSWORD),
])
def test_malformed_login_values_never_raise_or_authenticate(credentials, username, password):
    assert credentials.verify(username, password) is False


def test_unknown_username_still_computes_password_digest(credentials, monkeypatch):
    original = cloud_admin.hashlib.pbkdf2_hmac
    calls = []

    def record_call(*args):
        calls.append((args[0], args[3]))
        return original(*args)

    monkeypatch.setattr(cloud_admin.hashlib, "pbkdf2_hmac", record_call)
    assert credentials.verify("unknown-account", PASSWORD) is False
    assert calls == [("sha256", ITERATIONS)]


@pytest.mark.parametrize("field,value", [
    ("username", ""), ("username", "bad user"), ("username", "x" * 65), ("username", "管理员"),
    ("salt_hex", "00" * 15), ("salt_hex", "00" * 65), ("salt_hex", "a" * 33),
    ("salt_hex", "z" * 32), ("digest_hex", "a" * 63), ("digest_hex", "z" * 64),
    ("iterations", True), ("iterations", ITERATIONS - 1),
    ("iterations", cloud_admin.MAX_ITERATIONS + 1), ("iterations", str(ITERATIONS)),
])
def test_invalid_stored_credentials_fail_closed_without_echo(record, monkeypatch, field, value):
    invalid = {**record, field: value}
    monkeypatch.setattr(cloud_admin, "_read_admin_file", lambda _: json.dumps(invalid).encode())
    with pytest.raises(ValueError) as error:
        cloud_admin.CloudAdminCredentials("synthetic-private-file")
    assert PASSWORD not in str(error.value) and USERNAME not in str(error.value)


@pytest.mark.parametrize("payload", [b"not json", b"[]", b"null", b"{}", b"\xff"])
def test_invalid_json_never_enables_a_default_admin(monkeypatch, payload):
    monkeypatch.setattr(cloud_admin, "_read_admin_file", lambda _: payload)
    with pytest.raises(ValueError):
        cloud_admin.CloudAdminCredentials("synthetic-private-file")


def test_file_must_not_contain_plaintext_password_or_unknown_fields(record, monkeypatch):
    payload = {**record, "password": PASSWORD}
    monkeypatch.setattr(cloud_admin, "_read_admin_file", lambda _: json.dumps(payload).encode())
    with pytest.raises(ValueError) as error:
        cloud_admin.CloudAdminCredentials("synthetic-private-file")
    assert PASSWORD not in str(error.value)


def test_missing_file_is_a_sanitized_startup_error(tmp_path):
    with pytest.raises(ValueError) as error:
        cloud_admin.CloudAdminCredentials(tmp_path / "nonexistent")
    assert str(tmp_path) not in str(error.value)


POSIX = pytest.mark.skipif(os.name != "posix", reason="requires actual POSIX openat/owner/mode semantics")


@POSIX
@pytest.mark.parametrize("failure", [None, "mode", "parent_mode", "symlink", "ancestor_link", "hardlink"])
def test_actual_linux_private_credential_file(tmp_path, record, failure):
    directory = tmp_path / "private-admin"
    directory.mkdir(mode=0o700)
    path = directory / "admin.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    path.chmod(0o600)
    if failure == "mode":
        path.chmod(0o644)
    elif failure == "parent_mode":
        directory.chmod(0o755)
    elif failure == "symlink":
        actual = directory / "actual.json"
        path.rename(actual)
        path.symlink_to(actual)
    elif failure == "ancestor_link":
        alias = tmp_path / "private-admin-link"
        alias.symlink_to(directory, target_is_directory=True)
        path = alias / path.name
    elif failure == "hardlink":
        os.link(path, directory / "other.json")
    if failure is None:
        assert cloud_admin.CloudAdminCredentials(path).verify(USERNAME, PASSWORD)
    else:
        with pytest.raises(ValueError) as error:
            cloud_admin.CloudAdminCredentials(path)
        assert str(path) not in str(error.value)
