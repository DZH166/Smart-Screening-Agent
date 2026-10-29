"""Synthetic real WSGI→ASGI integration; never calls an AI endpoint."""
from io import BytesIO
import hashlib
import time

from PIL import Image
import pytest

from hsd_tool import admin_auth
from test_cloud_server import employee_app, cloud_request, login, ORIGIN, TOKEN


def call(client, path, payload=None, **kw):
    kw.setdefault('buffered', True)
    return cloud_request(client, '/api/ribbon' + path,
                         method='POST' if payload is not None else kw.pop('method', 'GET'),
                         payload=payload, **kw)


def read(response):
    try:
        assert response.status_code < 400, response.get_data(as_text=True)
        return response.get_json()
    finally:
        response.close()


def wait_job(client, job):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = read(call(client, '/jobs/' + job['id']))
        if result['status'] not in {'QUEUED', 'RUNNING', 'RECONCILING'}:
            return result
        time.sleep(.05)
    raise AssertionError('worker did not settle')


def selection(client):
    assets = read(call(client, '/assets'))
    return dict(asset_ids=[next(a['id'] for a in assets if a['kind'] == 'pattern')],
                background_id=next(a['id'] for a in assets if a['kind'] == 'background'),
                template_id=read(call(client, '/templates'))[0]['id'])


def test_host_auth_namespace_and_header_spoof(employee_app):
    client = employee_app.test_client()
    denied = call(client, '/auth/me', proxy_headers={'X-HSD-Owner': 'admin', 'X-Ribbon-Role': 'admin'})
    assert denied.status_code == 401
    assert employee_app.config['HSD_RIBBON'].service is None
    login(client)
    me = read(call(client, '/auth/me', proxy_headers={'X-Ribbon-Role': 'admin'}))
    assert me['role'] == 'customer'
    assert call(client, '/admin/overview').status_code in {401, 403}
    assert call(client, '/auth/login', {'username': 'admin', 'password': 'admin12345'}).status_code == 403
    config = read(call(client, '/config'))
    assert config['auth_mode'] == 'hsd' and config['provider'] != 'test'
    assert config['output_profile']['is_demo'] is True


def test_first_draft_parent_versions_quota_and_exact_download(employee_app):
    client = employee_app.test_client()
    login(client)
    design = read(call(client, '/designs', {'name': 'Synthetic ribbon'}))
    selected = selection(client)
    first = read(call(client, f'/designs/{design["id"]}/generate',
                      dict(selected, idempotency_key='first-synthetic-request')))
    first = wait_job(client, first)
    assert first['status'] == 'SUCCEEDED', first
    v0 = first['result_version_id']
    for n in (1, 2):
        job = read(call(client, f'/designs/{design["id"]}/refinements', {
            'base_version_id': v0, 'idempotency_key': f'change-selection-{n}',
            'prompt': '应用所选配置', 'selection': selected}))
        completed = wait_job(client, job)
        assert completed['status'] == 'SUCCEEDED', completed
        current = read(call(client, '/designs/' + design['id']))
        assert current['successful_refinement_count'] == n
        result = read(call(client, f'/designs/{design["id"]}/rollback',
                           {'expected_version_id': completed['result_version_id']}))
        assert result['current_version_id'] == v0
    current = read(call(client, '/designs/' + design['id']))
    assert current['successful_refinement_count'] == 2
    assert all(v['parent_version_id'] == v0 for v in current['versions'] if v['sequence'])
    assert call(client, f'/designs/{design["id"]}/refinements', {
        'base_version_id': v0, 'idempotency_key': 'third-change-selection',
        'prompt': '应用所选配置', 'selection': selected}).status_code == 409
    version = next(v for v in current['versions'] if v['id'] == v0)
    assert version['download_url'].startswith('/api/ribbon/versions/')
    response = cloud_request(client, version['download_url'])
    try:
        assert response.status_code == 200
        service = employee_app.config['HSD_RIBBON'].service
        with service.db.connect() as db:
            digest = db.execute('SELECT master_sha256 FROM versions WHERE id=?', (v0,)).fetchone()[0]
        assert hashlib.sha256(response.data).hexdigest() == digest
    finally:
        response.close()


def test_private_upload_owner_and_delete_csrf(employee_app):
    a, b = employee_app.test_client(), employee_app.test_client()
    login(a); login(b)
    image = BytesIO()
    Image.new('RGBA', (64, 32), 'red').save(image, 'PNG')
    image.seek(0)
    uploaded = read(call(a, '/assets', method='POST', data={
        'file': (image, 'synthetic.png'), 'kind': 'pattern'}, content_type='multipart/form-data'))
    assert uploaded['url'].startswith('/api/ribbon/')
    assert cloud_request(b, uploaded['url'], buffered=True).status_code == 404
    assert call(a, '/assets/' + uploaded['id'], method='DELETE', token=None).status_code == 403
    assert call(a, '/assets/' + uploaded['id'], method='DELETE', origin='https://evil.test').status_code == 403
    assert read(call(a, '/assets/' + uploaded['id'], method='DELETE'))['ok']


def test_admin_settings_and_maintenance_are_server_guarded(employee_app):
    client = employee_app.test_client()
    login(client)
    assert cloud_request(client, '/api/admin/ribbon-settings').status_code == 401
    with client.session_transaction(base_url=ORIGIN) as state:
        admin_auth.grant_session(state)
    settings = read(cloud_request(client, '/api/admin/ribbon-settings'))
    assert 'api_key' not in settings and 'openai_api_key' not in settings
    assert read(call(client, '/auth/me'))['role'] == 'admin'
    overview = read(call(client, '/admin/overview'))
    assert overview['output_profiles']
    with client.session_transaction(base_url=ORIGIN) as state:
        admin_auth.revoke_session(state)
    assert call(client, '/admin/overview').status_code in {401, 403}


def test_missing_provider_fails_without_quota_or_demo_output(employee_app):
    client = employee_app.test_client()
    login(client)
    response = call(client, '/background-jobs', {'prompt': '蓝色花纹', 'idempotency_key': 'missing-ai-config'})
    if response.status_code < 400:
        failed = wait_job(client, read(response))
        assert failed['status'] == 'FAILED' and not failed['result_asset_id']
    else:
        assert response.status_code in {409, 422, 503}


def test_stopping_blocks_changes_and_gateway_drains(employee_app):
    client = employee_app.test_client()
    login(client)
    read(call(client, '/auth/me'))
    employee_app.config['HSD_STOPPING'] = True
    assert call(client, '/designs', {'name': 'no'}).status_code == 409
    gateway = employee_app.config['HSD_RIBBON']
    gateway.close()
    assert gateway.closing and not gateway.service.thread.is_alive()


def test_same_browser_reauth_preserves_private_identity(employee_app):
    client = employee_app.test_client()
    login(client)
    first = read(call(client, '/auth/me'))
    design = read(call(client, '/designs', {'name': 'private recovered'}))
    # Same recovery cookie, new authenticated session: owner remains stable.
    login(client)
    assert read(call(client, '/auth/me'))['id'] == first['id']
    assert read(call(client, '/designs/' + design['id']))['id'] == design['id']
    other = employee_app.test_client()
    login(other)
    assert call(other, '/designs/' + design['id']).status_code == 404


def test_identity_initialization_failure_releases_gateway_request(employee_app, monkeypatch):
    client = employee_app.test_client()
    login(client)
    read(call(client, '/auth/me'))
    gateway = employee_app.config['HSD_RIBBON']
    def unavailable(*args, **kwargs):
        raise OSError('synthetic database unavailable')
    monkeypatch.setattr(gateway.service, 'ensure_external_user', unavailable)
    response = call(client, '/auth/me')
    assert response.status_code >= 400
    assert gateway.active_requests == 0
