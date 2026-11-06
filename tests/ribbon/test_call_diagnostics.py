"""Provider call records survive a crash and disclose only classified diagnostics."""
import json

import pytest

from hsd_tool.material_ark import ENDPOINT, HttpReply
from ribbon_backend.config import Settings
from ribbon_backend.providers import ProviderError, get_provider
from ribbon_backend.service import Service


@pytest.fixture
def work(tmp_path):
    settings = Settings(data_dir=tmp_path, auth_mode='hsd', provider='deepseek_seedream',
                        deepseek_pool=object(), ark_key='private-test-key', language_model='deepseek-flash',
                        image_model='doubao-seedream-5-0-flash-test')
    service = Service(settings)
    owner = service.ensure_external_user('hsd:test-user')['id']
    queued = service.submit(owner, 'background', {'prompt': 'sample', 'idempotency_key': 'test-private-call'})
    job = service.claim_job()
    assert job['id'] == queued['id']
    return service, owner, job, get_provider(settings)


@pytest.mark.parametrize('status,error_code,category,settlement', [
    (400, 'InputImageSensitiveContentDetected', 'input_policy', 'FAILED'),
    (400, 'OutputImageSensitiveContentDetected', 'output_policy', 'FAILED'),
    (400, 'InvalidParameter', 'parameters', 'FAILED'),
    (403, 'Forbidden', 'permission', 'FAILED'),
    (429, 'RateLimitExceeded.EndpointRPMExceeded', 'rate_limit', 'FAILED'),
    (500, 'InternalServiceError', 'service', 'UNKNOWN'),
    (400, 'sensitive-user-value', 'unclassified', 'FAILED'),
])
def test_request_recorded_before_transport_and_settled_without_private_response(
        work, tmp_path, status, error_code, category, settlement):
    service, _, job, provider = work
    seen = []
    def transport(request, **kwargs):
        with service.db.connect() as db:
            seen.extend(dict(r) for r in db.execute("SELECT id,status FROM provider_calls WHERE job_id=? AND status='STARTED'", (job['id'],)))
        return HttpReply(status, json.dumps({'error': {'code': error_code, 'message': 'sensitive-user-value'}}).encode(),
                         {'x-request-id': 'safe-request-123'}, ENDPOINT)
    provider.ark._transport = transport
    with pytest.raises(ProviderError) as exc:
        service.call_provider(job, 'generate_background', lambda: provider.generate_background(
            'sensitive-user-value', tmp_path/'never-created.png'), retry_provider=provider)
    assert 'sensitive-user-value' not in str(exc.value)
    rows = service.admin_overview()['provider_calls']
    assert len(rows) == (2 if category == 'output_policy' else 1)
    call = rows[0]
    # Output-review blocks get one automatic retry, so that category records
    # two dispatched calls; every other failure is dispatched once.
    assert seen and all(row['status'] == 'STARTED' for row in seen)
    assert len(seen) == (1 if category != 'output_policy' else 2)
    assert call['status'] == settlement
    assert call['diagnostic']['category'] == category
    assert call['diagnostic']['http_status'] == status
    assert call['request_id'] == 'safe-request-123'
    assert 'sensitive-user-value' not in json.dumps(call)
    with service.db.connect() as db:
        saved = dict(db.execute('SELECT * FROM provider_calls WHERE job_id=?', (job['id'],)).fetchone())
    assert 'sensitive-user-value' not in json.dumps(saved)
    assert 'private-test-key' not in json.dumps(saved)


def test_orphaned_call_is_marked_unknown_on_lease_recovery_and_never_redispatched(work):
    service, owner, job, _ = work
    with service.db.transaction() as db:
        db.execute('INSERT INTO provider_calls VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('crashed-call', job['id'], job['attempt'], 'generate_background', job['provider'],
                    'configured-test-model', None, '{}', 0, 'STARTED', None, job['created_at']))
        db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (job['id'],))
    assert service.run_once()
    assert service.job(owner, job['id'])['status'] == 'FAILED'
    calls = service.admin_overview()['provider_calls']
    assert len(calls) == 1 and calls[0]['id'] == 'crashed-call'
    assert calls[0]['status'] == 'UNKNOWN'
    assert calls[0]['diagnostic']['category'] == 'interrupted'


def test_bad_return_after_generation_keeps_observed_usage_and_no_new_submit(work, tmp_path):
    service, _, job, provider = work
    count = []
    def transport(request, **opts):
        count.append(1)
        return HttpReply(200, b'{"data":[],"usage":{"generated_images":1}}', {'request-id':'safe-return'}, ENDPOINT)
    provider.ark._transport = transport
    with pytest.raises(ProviderError):
        service.call_provider(job, 'generate_background', lambda: provider.generate_background('test', tmp_path/'out.png'))
    call = service.admin_overview()['provider_calls'][0]
    assert len(count) == 1 and call['status'] == 'FAILED'
    assert call['diagnostic']['category'] == 'invalid_result'
    assert json.loads(call['usage_json'])['generated_images'] == 1


def test_item_rejection_in_2xx_reply_keeps_official_code(work, tmp_path):
    service, _, job, provider = work
    body = {'data': [{'error': {'code': 'OutputImageSensitiveContentDetected.PolicyViolation',
                                'message': 'sensitive-user-value'}}]}
    provider.ark._transport = lambda *args, **kwargs: HttpReply(
        200, json.dumps(body).encode(), {'request-id':'item-return'}, ENDPOINT)
    with pytest.raises(ProviderError):
        service.call_provider(job, 'generate_background', lambda: provider.generate_background('test', tmp_path/'out.png'))
    call = service.admin_overview()['provider_calls'][0]
    assert call['diagnostic']['category'] == 'output_policy'
    assert call['diagnostic']['upstream_code'] == 'OutputImageSensitiveContentDetected.PolicyViolation'
    assert call['status'] == 'FAILED' and 'sensitive-user-value' not in json.dumps(call)


def test_legacy_error_reports_missing_diagnostics(work):
    service, _, job, _ = work
    with service.db.transaction() as db:
        db.execute('INSERT INTO provider_calls VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('old-call', job['id'], 1, 'design_background', job['provider'], 'image',
                    None, '{}', 1234, 'FAILED', '提供商调用失败', job['created_at']))
    call = service.admin_overview()['provider_calls'][0]
    assert call['diagnostic']['category'] == 'not_recorded'
    assert call['diagnostic']['http_status'] is None


def test_persistence_boundary_filters_custom_adapter_error_fields(work):
    service, _, job, _ = work
    error = RuntimeError('private-user-data')
    error.diagnostic = {'category':'parameters','stage':'provider','http_status':422,
                        'upstream_code':'private-user-data','raw':'private-user-data'}
    error.request_id = 'sk-' + 'x' * 30
    error.usage = {'input_tokens':12, 'raw':'private-user-data'}
    def fail():
        raise error
    with pytest.raises(RuntimeError):
        service.call_provider(job,'plan',fail)
    with service.db.connect() as db:
        saved = dict(db.execute('SELECT * FROM provider_calls WHERE job_id=?',(job['id'],)).fetchone())
    assert 'private-user-data' not in json.dumps(saved) and error.request_id not in json.dumps(saved)
    assert json.loads(saved['usage_json']) == {'input_tokens':12}
    assert json.loads(saved['error'])['upstream_code'] is None
