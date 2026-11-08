"""Explicit persisted, already-accepted pre-retirement jobs for recovery tests.

This is fixture construction, NEVER a replacement HTTP admission implementation.
New requests still receive410. Tests of public admission use generate/background.
No production method, feature flag, model, or client transport is patched here.
"""
from copy import deepcopy
import json
import re

from ribbon_backend.service import ServiceError, digest, dump, now, uid


def seed_accepted_refinement(service, owner, design_id, original_payload):
    """Restore an old queued recipe, then use the unchanged production worker.

    Guards below reject contradictory fixture setup; they are not evidence that
    retired requests are accepted. Existing-key replay uses production hashing.
    """
    body = deepcopy(original_payload)
    key = body['idempotency_key']
    with service.db.transaction() as db:
        previous = db.execute('SELECT 1 FROM jobs WHERE owner_id=? AND idempotency_key=?', (owner, key)).fetchone()
        expired = db.execute('SELECT 1 FROM expired_requests WHERE owner_id=? AND idempotency_key=?', (owner, key)).fetchone()
        if previous or expired:
            replay = True
        else:
            replay = False
            design = service.owned_design(db, owner, design_id)
            if design['active_job_id']:
                raise ServiceError(409, 'Fixture already has an active historical job')
            if body.get('base_version_id') != design['current_version_id']:
                raise ServiceError(409, 'Fixture base version is not current')
            if design['successful_refinement_count'] >= 2:
                raise ServiceError(409, 'Fixture already exhausted historical quota')
            row = db.execute('SELECT snapshot_json FROM versions WHERE id=? AND design_id=?', (body['base_version_id'], design_id)).fetchone()
            assert row, 'Historical fixture requires an owned, saved parent version'
            snapshot = json.loads(row['snapshot_json'])
            if body.get('selection'):
                snapshot = service.selection_snapshot(db, owner, body['selection'], snapshot['output_profile'], snapshot)
            settings = service.current_settings()
            payload = deepcopy(body)
            payload.update(snapshot=snapshot, model_config={name: getattr(settings, name) for name in
                ('language_model', 'image_model', 'image_quality', 'config_revision')})
            job_id, stamp = uid(), now()
            request_hash = digest(dump(dict(kind='refine', design_id=design_id, payload=body)).encode())
            db.execute('INSERT INTO jobs(id,owner_id,design_id,kind,idempotency_key,request_hash,payload_json,base_version_id,status,phase,provider,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (job_id, owner, design_id, 'refine', key, request_hash, dump(payload), body['base_version_id'],
                 'QUEUED', 'Historical accepted fixture', settings.provider, stamp, stamp))
            db.execute('INSERT INTO outbox_events VALUES(?,?,NULL)', (job_id, stamp))
            db.execute('UPDATE designs SET active_job_id=?,revision=revision+1 WHERE id=?', (job_id, design_id))
    if replay:
        return service.submit(owner, 'refine', body, design_id)
    return service.job(owner, job_id)


def recover_legacy_refinement(client, service, path, *, json):
    """Seed an old receipt, then recover it through a REAL read-only HTTP GET.

    Path is only a fixture identifier; this function never POSTs it or fabricates
    an HTTP response. Callers see200 from the existing receipt read route.
    """
    match = re.fullmatch(r'/api/designs/([^/]+)/refinements', path)
    assert match, 'Expected a historical design fixture path'
    owner = client.get('/api/auth/me').json()['id']
    seed_accepted_refinement(service, owner, match[1], json)
    return client.get('/api/jobs/by-request/' + json['idempotency_key'])
