"""Host-session regressions for asynchronous ribbon refinements; no AI calls."""
import threading
import hashlib
from types import SimpleNamespace

import pytest

from hsd_tool import cloud_sessions, server
from hsd_tool.cloud_server import CloudAccess
from ribbon_backend.providers import ProviderError
from test_cloud_server import CODE, ORIGIN, TOKEN, cloud_request, employee_app, login
from test_ribbon_gateway import call, read, selection, wait_job


def _draft(client):
    design = read(call(client, '/designs', {'name': 'Session regression'}))
    selected = selection(client)
    job = read(call(client, f'/designs/{design["id"]}/generate', {
        **selected, 'idempotency_key': 'session-regression-draft'}))
    settled = wait_job(client, job)
    assert settled['status'] == 'SUCCEEDED', settled
    return design['id'], selected, settled['result_version_id']


def test_refinement_wait_and_reads_preserve_employee_session(employee_app, monkeypatch):
    client = employee_app.test_client()
    login(client)
    owner = read(call(client, '/auth/me'))['id']
    design_id, selected, version_id = _draft(client)
    service = employee_app.config['HSD_RIBBON'].service
    entered, release = threading.Event(), threading.Event()
    original = service.build_artifact

    def wait_for_result(job, directory):
        if job['kind'] == 'refine':
            entered.set()
            assert release.wait(15), 'test did not release refinement'
        return original(job, directory)

    monkeypatch.setattr(service, 'build_artifact', wait_for_result)
    modified = {**selected, 'template_id': next(
        row['id'] for row in read(call(client, '/templates'))
        if row['mode'] in ('grid', 'single') and row['id'] != selected['template_id'])}
    job = read(call(client, f'/designs/{design_id}/refinements', {
        'base_version_id': version_id, 'idempotency_key': 'session-wait-refine',
        'prompt': '应用所选配置', 'selection': modified}))
    try:
        assert entered.wait(10)
        for _ in range(3):
            response = call(client, '/jobs/' + job['id'])
            assert not response.headers.getlist('Set-Cookie')
            assert read(response)['status'] == 'RUNNING'
            assert read(call(client, '/auth/me'))['id'] == owner
            current = read(call(client, '/designs/' + design_id))
            assert current['current_version_id'] == version_id
            assert current['successful_refinement_count'] == 0
        anonymous = employee_app.test_client()
        assert call(anonymous, '/jobs/' + job['id']).status_code == 401
        other = employee_app.test_client()
        login(other)
        assert call(other, '/jobs/' + job['id']).status_code == 404
    finally:
        release.set()
    settled = wait_job(client, job)
    assert settled['status'] == 'SUCCEEDED', settled
    assert read(call(client, '/auth/me'))['id'] == owner
    assert read(call(client, '/designs/' + design_id))['successful_refinement_count'] == 1


def test_provider_auth_failure_does_not_expire_employee_login(employee_app, monkeypatch):
    client = employee_app.test_client()
    login(client)
    owner = read(call(client, '/auth/me'))['id']
    design_id, selected, version_id = _draft(client)
    service = employee_app.config['HSD_RIBBON'].service

    def provider_denied(job, directory):
        raise ProviderError('图片服务认证失败，请联系管理员检查配置',
                            details={'category': 'authentication', 'stage': 'response',
                                     'http_status': 401})

    monkeypatch.setattr(service, 'build_artifact', provider_denied)
    job = read(call(client, f'/designs/{design_id}/refinements', {
        'base_version_id': version_id, 'idempotency_key': 'provider-denied-refine',
        'prompt': '改善图案细节', 'selection': selected}))
    settled = wait_job(client, job)
    assert settled['status'] == 'FAILED'
    assert '认证失败' in settled['error']
    assert read(call(client, '/auth/me'))['id'] == owner
    current = read(call(client, '/designs/' + design_id))
    assert current['current_version_id'] == version_id
    assert current['successful_refinement_count'] == 0


def test_normal_restart_preserves_owner_versions_and_safe_stale_token_recovery(employee_app, monkeypatch, tmp_path):
    manager = employee_app.config['HSD_MANAGER']
    settings_dir = manager.ai_settings.path.parent
    monkeypatch.setattr(cloud_sessions, '_read_signing_seed', lambda _: b's' * 32)
    configuration = cloud_sessions.cloud_session_config(
        key_file=tmp_path / 'synthetic-key', origin=ORIGIN, data_dir=manager.data_dir,
        settings_dir=settings_dir, employee_code=CODE,
        admin_credentials=SimpleNamespace(session_fingerprint=lambda: b'a' * 32))
    employee_app.config.update(configuration)
    client = employee_app.test_client()
    login(client)
    owner = read(call(client, '/auth/me'))['id']
    design_id, selected, version_id = _draft(client)
    path = '/versions/' + version_id + '/download'
    previous_download = call(client, path)
    try:
        assert previous_download.status_code == 200
        old_sha = hashlib.sha256(previous_download.data).hexdigest()
    finally:
        previous_download.close()
    cookie_name = configuration['SESSION_COOKIE_NAME']
    cookie = client.get_cookie(cookie_name, domain='hsd.example.test')
    assert cookie is not None
    employee_app.config['HSD_MATERIAL_MANAGER'].close()
    manager.close()
    access = CloudAccess(ORIGIN, CODE)
    access.session_config = configuration
    restarted = server.create_app(manager.data_dir, cloud=access, token=TOKEN + '-after-restart',
                                  settings_dir=settings_dir)
    restarted.config.update(TESTING=True)
    restarted.config['HSD_RETENTION'] = SimpleNamespace(register=lambda _: None)
    try:
        resumed = restarted.test_client()
        resumed.set_cookie(cookie_name, cookie.value, domain='hsd.example.test')
        assert read(call(resumed, '/auth/me'))['id'] == owner
        current = read(call(resumed, '/designs/' + design_id))
        assert current['current_version_id'] == version_id
        assert current['successful_refinement_count'] == 0
        download = call(resumed, path)
        try:
            assert download.status_code == 200
            assert hashlib.sha256(download.data).hexdigest() == old_sha
        finally:
            download.close()
        modified = {**selected, 'template_id': next(
            row['id'] for row in read(call(resumed, '/templates'))
            if row['mode'] in ('grid', 'single') and row['id'] != selected['template_id'])}
        payload = {'base_version_id': version_id, 'idempotency_key': 'post-restart-same-request',
                   'prompt': '应用所选配置', 'selection': modified}
        rejected = call(resumed, f'/designs/{design_id}/refinements', payload)
        try:
            assert rejected.status_code == 403
            assert rejected.get_json()['code'] == 'page_token_expired'
        finally:
            rejected.close()
        assert read(call(resumed, '/designs/' + design_id))['active_job_id'] is None
        token = read(call(resumed, '/session'))['token']
        assert token == TOKEN + '-after-restart'
        job = read(call(resumed, f'/designs/{design_id}/refinements', payload, token=token))
        repeated = read(call(resumed, f'/designs/{design_id}/refinements', payload, token=token))
        assert repeated['id'] == job['id']
        settled = wait_job(resumed, job)
        assert settled['status'] == 'SUCCEEDED', settled
        assert read(call(resumed, '/auth/me'))['id'] == owner
        assert read(call(resumed, '/designs/' + design_id))['successful_refinement_count'] == 1
        with restarted.config['HSD_RIBBON'].service.db.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM provider_calls').fetchone()[0] == 0
        anonymous = restarted.test_client()
        assert call(anonymous, '/auth/me').status_code == 401
        other = restarted.test_client()
        login(other)
        assert call(other, '/designs/' + design_id).status_code == 404
    finally:
        restarted.config['HSD_MATERIAL_MANAGER'].close()
        restarted.config['HSD_MANAGER'].close()


def test_employee_absolute_expiry_survives_admin_cookie_resigning(employee_app, monkeypatch):
    client = employee_app.test_client()
    login(client)
    with client.session_transaction(base_url=ORIGIN) as state:
        until = state['employee_authenticated_until']
    initial = until - 8 * 60 * 60
    # The administrator login re-signs the same browser cookie seven hours
    # later; its own expiry must not extend the employee's initial eight hours.
    employee_app.wsgi_app.access.admin_credentials = SimpleNamespace(verify=lambda *_: True)
    with monkeypatch.context() as clock:
        clock.setattr(server.time, 'time', lambda: initial + 7 * 60 * 60)
        logged_in = cloud_request(client, '/admin/login', method='POST',
                                  payload={'username': 'synthetic', 'password': 'synthetic'})
        assert logged_in.status_code == 200
        assert logged_in.headers.getlist('Set-Cookie')
        assert call(client, '/session').status_code == 200
    with monkeypatch.context() as clock:
        clock.setattr(server.time, 'time', lambda: until + 1)
        assert call(client, '/session').status_code == 401
        assert call(client, '/auth/me').status_code == 401
        assert call(client, '/designs', {'name': 'expired employee'}).status_code == 401
        # The independently granted administrator session remains valid.
        assert cloud_request(client, '/api/admin/overview').status_code == 200


@pytest.mark.parametrize('until', [None, True, False, 'future', 0, -1, float('nan')])
def test_missing_or_invalid_employee_expiry_is_not_a_cloud_login(employee_app, until):
    client = employee_app.test_client()
    login(client)
    with client.session_transaction(base_url=ORIGIN) as state:
        state['employee_authenticated_until'] = until
    assert call(client, '/session').status_code == 401


def test_page_token_bootstrap_is_authenticated_same_origin_and_side_effect_free(employee_app):
    anonymous = employee_app.test_client()
    assert call(anonymous, '/session').status_code == 401
    assert employee_app.config['HSD_RIBBON'].service is None
    client = employee_app.test_client()
    login(client)
    cookie_name = employee_app.config['SESSION_COOKIE_NAME']
    before = client.get_cookie(cookie_name, domain='hsd.example.test').value
    with client.session_transaction(base_url=ORIGIN) as state:
        expiry = state['employee_authenticated_until']
    response = call(client, '/session')
    try:
        assert response.status_code == 200
        assert response.get_json() == {'token': TOKEN}
        assert response.headers['Cache-Control'] == 'no-store'
        assert not response.headers.getlist('Set-Cookie')
    finally:
        response.close()
    assert client.get_cookie(cookie_name, domain='hsd.example.test').value == before
    with client.session_transaction(base_url=ORIGIN) as state:
        assert state['employee_authenticated_until'] == expiry
    assert call(client, '/session', origin='https://other.example.test').status_code == 403
    assert call(client, '/session', origin=None,
                proxy_headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert employee_app.config['HSD_RIBBON'].service is None
