"""Retired ribbon edits: HTTP tombstone and immutable historical recovery.

Synthetic local PNGs and persisted legacy jobs only; no external model calls.
"""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from ribbon_backend.service import ServiceError, digest, dump, now, uid
from test_workflow import env, key, ok


def counts(service):
    with service.db.connect() as db:
        return {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                for table in ('jobs', 'versions', 'quota_events', 'provider_calls', 'outbox_events')}


def seed_accepted_legacy_job(env, design):
    """Represent a job already accepted before the feature was retired.

    The production submit boundary is never relaxed for tests. Copy its stored
    immutable recipe, pinned settings and request hash into a historical fixture.
    """
    owner = env.login()['id']
    body = dict(idempotency_key=key(), base_version_id=design['current_version_id'],
                prompt='应用所选配置', selection={**env.selection(), 'design_density': 'airy'})
    original = next(v['snapshot'] for v in design['versions'] if v['id'] == design['current_version_id'])
    with env.service.db.transaction() as db:
        snapshot = env.service.selection_snapshot(db, owner, body['selection'], original['output_profile'], original)
        settings = env.service.current_settings()
        payload = deepcopy(body)
        payload['snapshot'] = snapshot
        payload['model_config'] = dict(language_model=settings.language_model, image_model=settings.image_model,
            image_quality=settings.image_quality, config_revision=getattr(settings, 'config_revision', ''))
        job_id, stamp = uid(), now()
        request_hash = digest(dump(dict(kind='refine', design_id=design['id'], payload=body)).encode())
        db.execute('INSERT INTO jobs(id,owner_id,design_id,kind,idempotency_key,request_hash,payload_json,base_version_id,status,phase,provider,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (job_id, owner, design['id'], 'refine', body['idempotency_key'], request_hash, dump(payload),
             design['current_version_id'], 'QUEUED', '等待处理', 'test', stamp, stamp))
        db.execute('INSERT INTO outbox_events VALUES(?,?,NULL)', (job_id, stamp))
        db.execute('UPDATE designs SET active_job_id=?,revision=revision+1 WHERE id=?', (job_id, design['id']))
    return owner, body, env.service.job(owner, job_id)


def test_public_config_and_version_never_advertise_new_refinements(env):
    design = env.generate()
    config = ok(env.client.get('/api/config'))
    assert config['max_refinements'] == 0 and config['refinement_enabled'] is False
    for editing in [config['editing'], design['versions'][0]['editing']]:
        assert editing['enabled'] is False
        assert editing['allowed_operations'] == editing['allowed_parameters'] == []
        assert editing['composite_edit'] is False
    assert design['versions'][0]['snapshot']['capabilities']  # Saved history is not rewritten.


@pytest.mark.parametrize('body', [{}, {'prompt': '添加星星'}, {'prompt': '', 'selection': None}])
def test_old_refine_post_is_410_without_submission_or_model_activity(env, monkeypatch, body):
    design = env.generate()
    before, original = counts(env.service), env.download(design['current_version_id'])
    def forbidden(*args, **kwargs):
        pytest.fail('Retired HTTP route must not submit or initialize a model')
    monkeypatch.setattr(env.service, 'submit', forbidden)
    monkeypatch.setattr(env.service, 'provider_factory', forbidden)
    result = env.client.post(f'/api/designs/{design["id"]}/refinements', json=body)
    assert result.status_code == 410 and '新建作品' in result.json()['detail']
    assert counts(env.service) == before
    assert env.get(design)['successful_refinement_count'] == 0
    assert env.download(design['current_version_id']) == original


def test_retirement_preserves_auth_and_ownership(env):
    design = env.generate()
    with TestClient(env.app, base_url='http://localhost') as other:
        assert other.post(f'/api/designs/{design["id"]}/refinements', json={}).status_code == 401
        env.login('client', client=other)
        assert other.post(f'/api/designs/{design["id"]}/refinements', json={}).status_code == 404
    assert env.client.post('/api/designs/missing/refinements', json={}).status_code == 404


def test_new_refinement_cannot_enter_service_and_generate_cannot_overwrite(env):
    design = env.generate()
    owner = env.login()['id']
    before, original = counts(env.service), env.download(design['current_version_id'])
    with pytest.raises(ServiceError) as denied:
        env.service.submit(owner, 'refine', dict(idempotency_key=key(), prompt='应用所选配置',
            base_version_id=design['current_version_id']), design['id'])
    assert denied.value.status == 410
    response = env.client.post(f'/api/designs/{design["id"]}/generate', json=dict(env.selection(), idempotency_key=key()))
    assert response.status_code == 409 and '新建作品' in response.json()['detail']
    assert counts(env.service) == before and env.download(design['current_version_id']) == original
    another = env.generate()
    assert another['id'] != design['id'] and len(another['versions']) == 1
    assert another['successful_refinement_count'] == 0


def test_previously_accepted_job_can_settle_replay_and_rollback_without_new_submission(env, monkeypatch):
    first = env.generate()
    original = env.download(first['current_version_id'])
    owner, body, accepted = seed_accepted_legacy_job(env, first)
    before = counts(env.service)
    assert env.service.submit(owner, 'refine', body, first['id'])['id'] == accepted['id']
    assert counts(env.service) == before
    assert env.client.post(f'/api/designs/{first["id"]}/refinements', json=body).status_code == 410
    assert ok(env.client.get('/api/jobs/' + accepted['id']))['status'] == 'QUEUED'
    def forbidden(*args, **kwargs):
        pytest.fail('Historical local selection replay must not call models')
    monkeypatch.setattr(env.service, 'provider_factory', forbidden)
    settled = env.work(accepted)
    assert settled['status'] == 'SUCCEEDED', settled
    current = env.get(first)
    assert current['successful_refinement_count'] == 1 and len(current['versions']) == 2
    assert env.download(first['current_version_id']) == original
    derived = current['current_version_id']
    assert env.download(derived) != original
    rolled = env.rollback(current)
    assert rolled['current_version_id'] == first['current_version_id']
    assert rolled['successful_refinement_count'] == 1 and env.download(derived)


def test_unknown_request_recovery_is_read_only_private_and_distinguishes_expiry(env):
    first = env.generate()
    owner, body, accepted = seed_accepted_legacy_job(env, first)
    before = counts(env.service)
    url = '/api/jobs/by-request/' + body['idempotency_key']
    response = env.client.get(url)
    assert response.status_code == 200 and response.headers['cache-control'] == 'private, no-store'
    assert response.json()['id'] == accepted['id']
    assert not {'prompt', 'payload_json', 'model_config', 'idempotency_key', 'request_hash'} & response.json().keys()
    with TestClient(env.app, base_url='http://localhost') as other:
        assert other.get(url).status_code == 401
        env.login('client', client=other)
        assert other.get(url).status_code == 404
    assert env.client.get('/api/jobs/by-request/never-accepted-request').status_code == 404
    expired_key = key()
    with env.service.db.transaction() as db:
        db.execute('INSERT INTO expired_requests VALUES(?,?,?)', (owner, expired_key, 'synthetic-prior-request-hash'))
    assert env.client.get('/api/jobs/by-request/' + expired_key).status_code == 410
    assert counts(env.service) == before
    assert ok(env.client.get('/api/jobs/' + accepted['id']))['status'] == 'QUEUED'
