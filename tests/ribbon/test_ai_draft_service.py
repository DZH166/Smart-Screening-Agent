"""AI first-draft contracts using explicit synthetic providers and local images.

No company image, credential or paid endpoint is read or sent by this suite.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from hsd_tool import ribbon_examples
from ribbon_backend.app import create_app
from ribbon_backend.config import Settings
from ribbon_backend.providers import ProviderError
from ribbon_backend.service import Service, ServiceError


class SyntheticDraftProvider:
    name = 'test'

    def __init__(self):
        self.calls = []
        self.failure = None
        self.output_size = (2048, 2048)
        self.after_input = None

    def generate_draft_background(self, patterns, background, reference, output, **options):
        self.calls.append(dict(patterns=[Path(p).read_bytes() for p in patterns],
                               background=Path(background).read_bytes(), reference=reference, options=options))
        if self.failure:
            raise self.failure
        if self.after_input:
            self.after_input(Path(background))
        with Image.new('RGBA', self.output_size, '#dae8f4') as image:
            image.save(output, format='PNG', dpi=(144, 144))
        return dict(model='synthetic-draft-provider', is_demo=True, request_id='synthetic-draft-request')


@pytest.fixture
def api(tmp_path):
    provider = SyntheticDraftProvider()
    service = Service(Settings(data_dir=tmp_path, provider='test', auth_mode='demo'),
                      provider_factory=lambda *args: provider)
    service.save_profile(dict(name='Synthetic first draft', width=1080, height=240, dpi=96, format='PNG', is_demo=True))
    with TestClient(create_app(service.settings, service=service)) as client:
        owner = client.post('/api/auth/login', json=dict(username='demo', password='demo12345')).json()['id']
        choice = dict(asset_ids=[a['id'] for a in service.assets(owner, 'pattern')[:2]],
                      background_id=service.assets(owner, 'background')[0]['id'], template_id='grid')
        yield service, client, provider, owner, choice


def submit(api, **options):
    service, client, provider, owner, choice = api
    work = client.post('/api/designs', json={'name': 'Synthetic AI first draft'}).json()
    body = dict(choice, idempotency_key=str(uuid4()), **options)
    return work, body, client.post(f'/api/designs/{work["id"]}/generate', json=body)


def state(api, work, response):
    service, client, provider, owner, choice = api
    assert response.status_code == 202, response.text
    assert service.run_once()
    return service.job(owner, response.json()['id']), service.design(owner, work['id'])


def install_synthetic_reference(api, monkeypatch):
    output = BytesIO()
    with Image.new('RGB', (48, 24), '#ccbb99') as image:
        image.save(output, format='PNG')
    value = output.getvalue()
    code = 'HSD68145'  # Only the catalog ID is reused; bytes are self-made.
    monkeypatch.setitem(ribbon_examples.IMAGE_SPECS, code, (48, 24, len(value), hashlib.sha256(value).hexdigest()))
    seen = []
    api[0].example_resolver = lambda selected: seen.append(selected) or value
    return code, value, seen


@pytest.mark.parametrize('options', [
    {'ai_assisted': 1}, {'ai_assisted': 'true'}, {'ai_assisted': None},
    {'ai_assisted': True, 'reference_code': 123}, {'ai_assisted': True, 'reference_code': False},
    {'ai_assisted': True, 'reference_code': ''}, {'ai_assisted': False, 'reference_code': 'HSD68145'},
    {'ai_assisted': True, 'reference_code': '../../private'},
    {'ai_assisted': True, 'reference_code': 'HSD51441'},  # Single-mode case cannot authorize grid.
    {'ai_assisted': True, 'reference_code': 'HSD68145'},  # No installed reference resolver.
])
def test_http_rejects_invalid_ai_options_before_queue_or_provider(api, options):
    service, client, provider, owner, choice = api
    work, body, response = submit(api, **options)
    assert response.status_code == 422, response.text
    assert provider.calls == []
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0


def test_config_advertises_only_ready_supported_real_provider_and_submit_obeys_it(api):
    service, client, provider, owner, choice = api
    assert client.get('/api/config').json()['ai_draft_available'] is False
    for settings, available in [
        (replace(service.settings, provider='deepseek_seedream'), False),
        (replace(service.settings, provider='openai', language_model='synthetic-language', image_model='synthetic-image', openai_api_key='synthetic-only'), False),
        (replace(service.settings, provider='deepseek_seedream', language_model='synthetic-language', image_model='synthetic-image', deepseek_pool=object(), ark_key='synthetic-only'), True),
    ]:
        service.settings = settings
        assert client.get('/api/config').json()['ai_draft_available'] is available
        work, body, response = submit(api, ai_assisted=True)
        assert response.status_code == (202 if available else 503), response.text
    assert provider.calls == []


def test_old_client_payload_never_reads_reference_or_acquires_provider(api):
    service, client, provider, owner, choice = api
    service.example_resolver = lambda *args: pytest.fail('No reference was selected')
    service.provider_factory = lambda *args: pytest.fail('Old payload must remain deterministic')
    work, body, response = submit(api)
    job, final = state(api, work, response)
    saved = final['versions'][0]['snapshot']
    assert job['status'] == 'SUCCEEDED' and final['successful_refinement_count'] == 0
    assert saved['layout_engine'] == 'design-rhythm-v2' and 'ai_draft' not in saved
    assert saved['background_ref'] == choice['background_id']


@pytest.mark.parametrize('with_reference', [False, True])
def test_ai_draft_calls_once_keeps_original_patterns_and_binds_download_provenance(api, monkeypatch, with_reference):
    service, client, provider, owner, choice = api
    if with_reference:
        code, value, seen = install_synthetic_reference(api, monkeypatch)
    else:
        code, value, seen = None, None, []
        service.example_resolver = lambda *args: pytest.fail('No reference was selected')
    source = {a: service.verified_asset_path(owner, a).read_bytes() for a in [*choice['asset_ids'], choice['background_id']]}
    work, body, response = submit(api, ai_assisted=True, reference_code=code)
    assert response.status_code == 202
    with ThreadPoolExecutor(max_workers=2) as pool:
        replay = list(pool.map(lambda _: service.submit(owner, 'generate', body, work['id']), range(2)))
    assert {r['id'] for r in replay} == {response.json()['id']}
    job, final = state(api, work, response)
    assert job['status'] == 'SUCCEEDED' and len(provider.calls) == 1
    call = provider.calls[0]
    assert call['patterns'] == [source[a] for a in choice['asset_ids']]
    assert call['background'] == source[choice['background_id']] and call['reference'] == value
    assert call['options'] == dict(mode='grid', density='balanced', prompt='')
    version = final['versions'][0]; snapshot = version['snapshot']
    assert snapshot['asset_refs'] == choice['asset_ids'] and snapshot['background_ref'] != choice['background_id']
    assert snapshot['ai_draft']['original_background_ref'] == choice['background_id']
    assert snapshot['ai_draft']['reference_code'] == code
    assert snapshot['ai_draft']['reference_sha256'] == (hashlib.sha256(value).hexdigest() if value else None)
    assert snapshot['ai_draft']['full_canvas_redraw'] is False and snapshot['ai_draft']['redraws_original_patterns'] is False
    assert {row['id']: row['sha256'] for row in snapshot['ai_draft']['input_assets']} == {a: hashlib.sha256(raw).hexdigest() for a, raw in source.items()}
    assert len(seen) == (2 if with_reference else 0)
    assert all(service.verified_asset_path(owner, a).read_bytes() == raw for a, raw in source.items())
    with service.db.connect() as db:
        derived = db.execute('SELECT * FROM assets WHERE id=?', (snapshot['background_ref'],)).fetchone()
        assert derived['derived_from'] == choice['background_id'] and derived['is_demo'] == 1
        assert db.execute('SELECT COUNT(*) FROM quota_events').fetchone()[0] == 0
        assert [r['operation'] for r in db.execute('SELECT * FROM provider_calls')] == ['design_background']
        payload = db.execute('SELECT payload_json FROM jobs WHERE id=?', (job['id'],)).fetchone()[0]
    assert str(service.root) not in json.dumps(snapshot) and str(service.root) not in payload
    assert final['successful_refinement_count'] == 0
    downloaded = client.get(version['download_url'])
    assert downloaded.status_code == 200 and downloaded.content == service.version_file(owner, version['id']).read_bytes()


@pytest.mark.parametrize('corruption', ['reference_bytes', 'reference_spec', 'last_pattern', 'background_identity'])
def test_changed_reference_or_any_input_fails_before_the_first_provider_call(api, monkeypatch, corruption):
    service, client, provider, owner, choice = api
    code, value, seen = install_synthetic_reference(api, monkeypatch)
    work, body, response = submit(api, ai_assisted=True, reference_code=code)
    assert response.status_code == 202
    if corruption == 'reference_bytes':
        service.example_resolver = lambda *args: value + b'changed'
    elif corruption == 'reference_spec':
        monkeypatch.setitem(ribbon_examples.IMAGE_SPECS, code, (48, 24, len(value), 'a' * 64))
    elif corruption == 'last_pattern':
        service.verified_asset_path(owner, choice['asset_ids'][-1]).write_bytes(b'changed')
    else:
        with service.db.transaction() as db:
            db.execute('UPDATE assets SET sha256=? WHERE id=?', ('a' * 64, choice['background_id']))
    job, final = state(api, work, response)
    assert job['status'] == 'FAILED' and provider.calls == [] and final['versions'] == []
    assert final['successful_refinement_count'] == 0
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM provider_calls').fetchone()[0] == 0


@pytest.mark.parametrize('uncertain', [False, True])
def test_failed_or_unknown_ai_draft_never_falls_back_or_spends_refinement_quota(api, uncertain):
    service, client, provider, owner, choice = api
    provider.failure = ProviderError('Synthetic unknown result' if uncertain else 'Synthetic settled failure', uncertain_result=uncertain)
    work, body, response = submit(api, ai_assisted=True)
    job, final = state(api, work, response)
    assert job['status'] == 'FAILED' and len(provider.calls) == 1
    assert final['versions'] == [] and final['current_version_id'] is None and final['successful_refinement_count'] == 0
    assert service.submit(owner, 'generate', body, work['id'])['id'] == job['id']
    assert service.run_once() is False
    with service.db.connect() as db:
        call = db.execute('SELECT * FROM provider_calls').fetchone()
        assert call['status'] == ('UNKNOWN' if uncertain else 'FAILED')
        assert db.execute('SELECT COUNT(*) FROM quota_events').fetchone()[0] == 0


def test_interrupted_ai_generate_without_artifact_is_not_reissued(api):
    service, client, provider, owner, choice = api
    work, body, response = submit(api, ai_assisted=True)
    job = service.claim_job()
    directory = service.root / 'jobs' / job['id'] / str(job['attempt']); directory.mkdir(parents=True)
    service.build_artifact(job, directory)  # Simulate termination after the model returned, before checkpoint.
    with service.db.transaction() as db:
        db.execute('UPDATE jobs SET lease_until=? WHERE id=?', (time.time() - 1, job['id']))
    assert service.run_once()
    failed = service.job(owner, job['id'])
    assert failed['status'] == 'FAILED' and '未知' in failed['error'] and len(provider.calls) == 1
    assert service.design(owner, work['id'])['versions'] == []


def test_artifact_recovery_commits_exact_result_without_provider_or_reference_reread(api, monkeypatch):
    service, client, provider, owner, choice = api
    code, value, seen = install_synthetic_reference(api, monkeypatch)
    work, body, response = submit(api, ai_assisted=True, reference_code=code)
    job = service.claim_job()
    directory = service.root / 'jobs' / job['id'] / str(job['attempt']); directory.mkdir(parents=True)
    artifact = service.build_artifact(job, directory)
    service.checkpoint(job, artifact, directory)
    master = Path(artifact['master_path']).read_bytes()
    with service.db.transaction() as db:
        db.execute("UPDATE jobs SET status='RECONCILING',lease_until=? WHERE id=?", (time.time() - 1, job['id']))
    reopened = Service(service.settings, provider_factory=lambda *args: pytest.fail('Recovery repeated the image request'),
                       example_resolver=lambda *args: pytest.fail('Saved artifact must retain its bound reference digest'))
    assert reopened.run_once()
    result = reopened.design(owner, work['id'])
    assert len(provider.calls) == 1 and len(seen) == 2
    assert result['successful_refinement_count'] == 0 and len(result['versions']) == 1
    assert reopened.version_file(owner, result['current_version_id']).read_bytes() == master


@pytest.mark.parametrize('invalid', ['undersize', 'changed_original_background'])
def test_invalid_result_or_mutated_original_background_cannot_commit_fake_success(api, invalid):
    service, client, provider, owner, choice = api
    if invalid == 'undersize':
        provider.output_size = (128, 128)
    else:
        provider.after_input = lambda path: path.write_bytes(b'changed during synthetic provider')
    work, body, response = submit(api, ai_assisted=True)
    job, final = state(api, work, response)
    assert job['status'] == 'FAILED' and len(provider.calls) == 1
    assert final['versions'] == [] and final['successful_refinement_count'] == 0


def test_hsd_mode_cannot_use_the_explicit_demo_provider_fallback(tmp_path):
    service = Service(Settings(data_dir=tmp_path, auth_mode='hsd', provider='test'))
    owner = service.ensure_external_user('hsd:synthetic-owner')['id']
    work = service.create_design(owner, 'synthetic isolated hsd work')
    choices = dict(asset_ids=[service.assets(owner, 'pattern')[0]['id']],
                   background_id=service.assets(owner, 'background')[0]['id'], template_id='grid')
    with pytest.raises(ServiceError) as denied:
        service.submit(owner, 'generate', dict(choices, idempotency_key=str(uuid4()), ai_assisted=True), work['id'])
    assert denied.value.status == 503
    assert service.config()['ai_draft_available'] is False


def test_historical_v1_defaults_and_density_edit_keep_the_saved_engine_and_download(api, monkeypatch):
    service, client, provider, owner, choice = api
    original = service.selection_snapshot
    def historical(*args, **kwargs):
        snapshot = original(*args, **kwargs)
        snapshot['layout_engine'] = 'design-rhythm-v1'
        snapshot.pop('background_tone', None)
        snapshot.pop('design_density', None)
        return snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service, 'selection_snapshot', historical)
        work, body, response = submit(api)
        job, first = state(api, work, response)
    assert job['status'] == 'SUCCEEDED'
    previous = first['versions'][0]
    content = service.version_file(owner, previous['id']).read_bytes()
    submitted = client.post(f'/api/designs/{work["id"]}/refinements', json=dict(
        idempotency_key=str(uuid4()), base_version_id=previous['id'], prompt='应用所选配置',
        selection={**choice, 'design_density': 'airy', 'background_tone': 'soft'}))
    job, final = state(api, work, submitted)
    assert job['status'] == 'SUCCEEDED'
    latest = final['versions'][-1]['snapshot']
    assert latest['layout_engine'] == 'design-rhythm-v1' and latest['design_density'] == 'airy'
    assert latest['background_tone'] == 'soft' and final['successful_refinement_count'] == 1
    assert final['versions'][0] == previous and service.version_file(owner, previous['id']).read_bytes() == content
    assert provider.calls == []
