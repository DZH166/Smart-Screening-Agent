"""Actual HTTP/Pydantic quality controls with synthetic local images/providers."""
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from ribbon_backend.app import create_app
from ribbon_backend.config import Settings
from ribbon_backend.service import Service, LAYOUT_ENGINE


@pytest.fixture
def api(tmp_path):
    service = Service(Settings(data_dir=tmp_path, provider='test', auth_mode='demo'))
    service.save_profile(dict(name='合成HTTP质量合同', width=1080, height=240,
                              dpi=96, format='PNG', is_demo=True))
    with TestClient(create_app(service.settings, service=service), base_url='http://localhost') as client:
        response = client.post('/api/auth/login', json={'username': 'demo', 'password': 'demo12345'})
        assert response.status_code == 200
        patterns = client.get('/api/assets?kind=pattern').json()
        backgrounds = client.get('/api/assets?kind=background').json()
        choice = dict(asset_ids=[row['id'] for row in patterns[:2]],
                      background_id=backgrounds[0]['id'], template_id='stagger')
        yield service, client, choice


def new_design(client):
    response = client.post('/api/designs', json={'name': '合成HTTP设计'})
    assert response.status_code == 201
    return response.json()


def run(service, client, response):
    assert response.status_code == 202, response.text
    job = response.json()
    assert service.run_once()
    state = client.get('/api/jobs/' + job['id']).json()
    assert state['status'] == 'SUCCEEDED', state
    return state


def generate(api, choice=None):
    service, client, defaults = api
    work = new_design(client)
    body = dict(idempotency_key=str(uuid4()), **(choice or defaults))
    response = client.post('/api/designs/' + work['id'] + '/generate', json=body)
    state = run(service, client, response)
    return client.get('/api/designs/' + work['id']).json(), state['id']


def current(work):
    return next(row for row in work['versions'] if row['id'] == work['current_version_id'])


def test_new_controls_pass_actual_http_schema_and_persist_through_refinement(api):
    service, client, choice = api
    work, _ = generate(api, dict(choice, background_tone='original', design_density='rich'))
    original = current(work)
    assert original['snapshot']['layout_engine'] == LAYOUT_ENGINE
    assert original['snapshot']['output_profile_source']['width'] == 1080
    assert original['snapshot']['loop']['width'] == original['snapshot']['output_profile']['width']
    assert original['snapshot']['background_tone'] == 'original'
    assert original['snapshot']['design_density'] == 'rich'
    response = client.post('/api/designs/' + work['id'] + '/refinements', json={
        'idempotency_key': str(uuid4()), 'base_version_id': work['current_version_id'], 'prompt': '应用所选配置',
        'selection': dict(choice, background_tone='soft', design_density='airy')})
    run(service, client, response)
    changed = client.get('/api/designs/' + work['id']).json()
    assert changed['successful_refinement_count'] == 1
    assert current(changed)['snapshot']['background_tone'] == 'soft'
    assert current(changed)['snapshot']['design_density'] == 'airy'
    assert current(changed)['parent_version_id'] == original['id']
    assert client.get('/api/versions/' + original['id'] + '/download').status_code == 200


def test_old_http_payload_omits_unset_nested_fields_and_keeps_saved_defaults(api):
    service, client, choice = api
    work, generate_id = generate(api)
    assert current(work)['snapshot']['background_tone'] == 'soft'
    assert current(work)['snapshot']['design_density'] == 'balanced'
    with service.db.connect() as db:
        original_payload = json.loads(db.execute('SELECT payload_json FROM jobs WHERE id=?', (generate_id,)).fetchone()[0])
    assert 'background_tone' not in original_payload and 'design_density' not in original_payload
    response = client.post('/api/designs/' + work['id'] + '/refinements', json={
        'idempotency_key': str(uuid4()), 'base_version_id': work['current_version_id'], 'prompt': '应用所选配置',
        'selection': dict(choice, template_id='single')})
    job = run(service, client, response)
    changed = client.get('/api/designs/' + work['id']).json()
    assert current(changed)['snapshot']['background_tone'] == 'soft'
    assert current(changed)['snapshot']['design_density'] == 'balanced'
    with service.db.connect() as db:
        payload = json.loads(db.execute('SELECT payload_json FROM jobs WHERE id=?', (job['id'],)).fetchone()[0])
    assert 'background_tone' not in payload['selection'] and 'design_density' not in payload['selection']


def test_old_http_client_can_refine_legacy_work_without_softening_or_upgrading_it(api, monkeypatch):
    service, client, choice = api
    original_selection = service.selection_snapshot

    def legacy(*args, **kwargs):
        snapshot = original_selection(*args, **kwargs)
        for field in ('layout_engine', 'background_tone', 'design_density'):
            snapshot.pop(field, None)
        return snapshot

    with monkeypatch.context() as patch:
        patch.setattr(service, 'selection_snapshot', legacy)
        work, _ = generate(api)
    before = client.get('/api/versions/' + work['current_version_id'] + '/download').content
    response = client.post('/api/designs/' + work['id'] + '/refinements', json={
        'idempotency_key': str(uuid4()), 'base_version_id': work['current_version_id'], 'prompt': '应用所选配置',
        'selection': dict(choice, template_id='single')})
    run(service, client, response)
    changed = client.get('/api/designs/' + work['id']).json()
    saved = current(changed)['snapshot']
    assert saved['background_tone'] == 'original'
    assert 'design_density' not in saved and 'layout_engine' not in saved
    assert client.get('/api/versions/' + work['current_version_id'] + '/download').content == before


@pytest.mark.parametrize('field,value', [
    ('background_tone', 'automatic'), ('design_density', 'automatic'),
    ('background_tone', None), ('design_density', None),
])
def test_invalid_enums_and_explicit_null_are_rejected_for_generate_and_nested_refine(api, field, value):
    service, client, choice = api
    invalid = dict(choice, **{field: value})
    empty = new_design(client)
    response = client.post('/api/designs/' + empty['id'] + '/generate', json={
        'idempotency_key': str(uuid4()), **invalid})
    assert response.status_code == 422
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
    work, _ = generate(api)
    response = client.post('/api/designs/' + work['id'] + '/refinements', json={
        'idempotency_key': str(uuid4()), 'base_version_id': work['current_version_id'], 'prompt': '应用所选配置',
        'selection': invalid})
    assert response.status_code == 422
    latest = client.get('/api/designs/' + work['id']).json()
    assert latest['current_version_id'] == work['current_version_id']
    assert latest['successful_refinement_count'] == 0
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 1


def test_quality_controls_do_not_bypass_another_employee_or_admin_boundaries(api):
    service, client, choice = api
    work, _ = generate(api)
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/designs/' + work['id']).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'client', 'password': 'client12345'}).status_code == 200
    assert client.get('/api/designs/' + work['id']).status_code == 404
    response = client.post('/api/designs/' + work['id'] + '/refinements', json={
        'idempotency_key': str(uuid4()), 'base_version_id': work['current_version_id'], 'prompt': '应用所选配置',
        'selection': dict(choice, background_tone='original', design_density='rich')})
    assert response.status_code in (403, 404)
    assert client.get('/api/admin/overview').status_code == 403
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM quota_events').fetchone()[0] == 0
