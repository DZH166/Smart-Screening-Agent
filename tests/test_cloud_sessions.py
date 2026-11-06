"""Synthetic credentials only; stable signing never weakens expiry or origin."""
import json
import os
from types import SimpleNamespace

from flask import Flask
from itsdangerous import BadSignature
import pytest

from hsd_tool import cloud_admin, cloud_sessions


@pytest.fixture
def session_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud_sessions, '_read_signing_seed', lambda _: b'a' * 32)
    return dict(key_file=tmp_path / 'master', origin='https://hsd.example.test:8443',
                data_dir=tmp_path / 'data', settings_dir=tmp_path / 'settings',
                employee_code='synthetic-employee-code',
                admin_credentials=SimpleNamespace(session_fingerprint=lambda: b'b' * 32))


def serializer(configuration):
    app = Flask('synthetic-cloud-session')
    app.config.update(configuration)
    return app.session_interface.get_signing_serializer(app)


def test_normal_restart_keeps_instance_signing_and_cookie_name(session_arguments):
    first = cloud_sessions.cloud_session_config(**session_arguments)
    second = cloud_sessions.cloud_session_config(**session_arguments)
    assert first == second
    assert first['SECRET_KEY'] != b'a' * 32
    assert len(first['SECRET_KEY']) == 32
    assert first['SESSION_COOKIE_NAME'].startswith('hsd_cloud_')
    payload = {'employee_id': 'synthetic-owner', 'lan_authenticated': True,
               'employee_authenticated_until': 1234567890}
    cookie = serializer(first).dumps(payload)
    assert serializer(second).loads(cookie) == payload


@pytest.mark.parametrize('change', ['key', 'origin', 'data', 'settings', 'employee', 'admin'])
def test_other_authority_cannot_accept_old_session(session_arguments, monkeypatch, change, tmp_path):
    first = cloud_sessions.cloud_session_config(**session_arguments)
    cookie = serializer(first).dumps({'employee_id': 'synthetic-owner', 'lan_authenticated': True})
    if change == 'key':
        monkeypatch.setattr(cloud_sessions, '_read_signing_seed', lambda _: b'c' * 32)
    elif change == 'origin':
        session_arguments['origin'] = 'https://hsd.example.test:9443'
    elif change == 'data':
        session_arguments['data_dir'] = tmp_path / 'other-data'
    elif change == 'settings':
        session_arguments['settings_dir'] = tmp_path / 'other-settings'
    elif change == 'employee':
        session_arguments['employee_code'] = 'different-synthetic-code'
    else:
        session_arguments['admin_credentials'] = SimpleNamespace(session_fingerprint=lambda: b'd' * 32)
    changed = cloud_sessions.cloud_session_config(**session_arguments)
    assert changed['SECRET_KEY'] != first['SECRET_KEY']
    with pytest.raises(BadSignature):
        serializer(changed).loads(cookie)
    # Credential rotation replaces the existing cookie rather than collecting a
    # new cookie name every restart; a different deployment gets its own name.
    assert (changed['SESSION_COOKIE_NAME'] == first['SESSION_COOKIE_NAME']) == (change in {'key', 'employee', 'admin'})


@pytest.mark.parametrize('value', [b'', b'a' * 31, b'a' * 33, 'a' * 32, None])
def test_invalid_machine_key_has_no_random_fallback(session_arguments, monkeypatch, value):
    monkeypatch.setattr(cloud_sessions, '_read_signing_seed', lambda _: value)
    with pytest.raises(ValueError) as error:
        cloud_sessions.cloud_session_config(**session_arguments)
    assert str(session_arguments['key_file']) not in str(error.value)
    assert session_arguments['employee_code'] not in str(error.value)


def test_unreadable_machine_key_has_no_random_fallback(session_arguments, monkeypatch):
    def unavailable(_):
        raise OSError('synthetic-private-path-key-content')
    monkeypatch.setattr(cloud_sessions, '_read_signing_seed', unavailable)
    with pytest.raises(ValueError) as error:
        cloud_sessions.cloud_session_config(**session_arguments)
    assert 'synthetic-private-path-key-content' not in str(error.value)


def test_cloud_admin_generation_is_stable_and_changes_with_credentials(monkeypatch):
    record = {'username': 'synthetic-admin', 'salt_hex': 'ab' * 32,
              'digest_hex': 'cd' * 32, 'iterations': cloud_admin.MIN_ITERATIONS}
    monkeypatch.setattr(cloud_admin, '_read_admin_file', lambda _: json.dumps(record).encode())
    first = cloud_admin.CloudAdminCredentials('unused')
    monkeypatch.setattr(cloud_admin, '_read_admin_file', lambda _: json.dumps(record, indent=3).encode())
    second = cloud_admin.CloudAdminCredentials('unused')
    assert first.session_fingerprint() == second.session_fingerprint()
    record['digest_hex'] = 'ef' * 32
    changed = cloud_admin.CloudAdminCredentials('unused')
    assert changed.session_fingerprint() != first.session_fingerprint()


@pytest.mark.skipif(os.name != 'posix', reason='requires actual Linux openat and private-file semantics')
@pytest.mark.parametrize('problem', [None, 'short', 'mode', 'parent_mode', 'symlink', 'ancestor_link', 'hardlink'])
def test_actual_private_signing_seed_file(tmp_path, problem):
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    path = directory / 'master'
    path.write_bytes(b'a' * (31 if problem == 'short' else 32))
    path.chmod(0o600)
    if problem == 'mode':
        path.chmod(0o644)
    elif problem == 'parent_mode':
        directory.chmod(0o755)
    elif problem == 'symlink':
        actual = directory / 'actual'
        path.rename(actual)
        path.symlink_to(actual)
    elif problem == 'ancestor_link':
        alias = tmp_path / 'alias'
        alias.symlink_to(directory, target_is_directory=True)
        path = alias / path.name
    elif problem == 'hardlink':
        os.link(path, directory / 'other')
    if problem is None:
        assert cloud_sessions._read_signing_seed(path) == b'a' * 32
    else:
        with pytest.raises(ValueError) as error:
            cloud_sessions._read_signing_seed(path)
        assert str(path) not in str(error.value)
