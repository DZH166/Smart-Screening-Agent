"""Real local files/transactions; all provider responses are explicit substitutes.

No API credentials, paid network requests, business images or live identities.
"""
from dataclasses import replace
from io import BytesIO
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from ribbon_backend.app import create_app
from ribbon_backend.config import Settings
from ribbon_backend.providers import TestProvider as SyntheticProvider
from ribbon_backend.service import Service


@pytest.fixture
def service(tmp_path):
    instance = Service(Settings(data_dir=tmp_path, provider='test', auth_mode='demo'))
    instance.save_profile(dict(name='合成模型工作流规格', width=1080, height=240,
                               dpi=96, format='PNG', is_demo=True))
    yield instance
    instance.stop()


def owner(service):
    with service.db.connect() as db:
        return db.execute("SELECT id FROM users WHERE username='demo'").fetchone()[0]


def selection(service, identity):
    return dict(asset_ids=[item['id'] for item in service.assets(identity, 'pattern')[:2]],
                background_id=service.assets(identity, 'background')[0]['id'], template_id='stagger')


def generate(service):
    identity = owner(service)
    design = service.create_design(identity, '明确的合成模型工作流验收')
    job = service.submit(identity, 'generate', dict(idempotency_key=str(uuid4()),
                         **selection(service, identity)), design['id'])
    assert service.run_once()
    assert service.job(identity, job['id'])['status'] == 'SUCCEEDED'
    return identity, service.design(identity, design['id'])


def refine(service, identity, design, prompt='合成修改请求', choice=None):
    body = dict(idempotency_key=str(uuid4()), base_version_id=design['current_version_id'], prompt=prompt)
    if choice is not None:
        body['selection'] = choice
    job = service.submit(identity, 'refine', body, design['id'])
    assert service.submit(identity, 'refine', body, design['id'])['id'] == job['id']
    assert service.run_once()
    return service.job(identity, job['id']), service.design(identity, design['id'])


def plan(monkeypatch, operations):
    monkeypatch.setattr(SyntheticProvider, 'plan', lambda *args: {
        'summary': '明确的合成计划', 'operations': operations})


def assert_unchanged(service, identity, original, latest, content):
    assert latest['current_version_id'] == original['current_version_id']
    assert latest['successful_refinement_count'] == original['successful_refinement_count']
    assert len(latest['versions']) == len(original['versions'])
    assert service.version_file(identity, original['current_version_id']).read_bytes() == content


def test_config_and_historical_version_project_current_provider_without_rewriting_snapshot(service):
    service.save_profile(dict(name='合成可整幅尺寸', width=1024, height=1024,
                              dpi=96, format='PNG', is_demo=True))
    identity, design = generate(service)
    version = design['versions'][0]
    content = service.version_file(identity, version['id']).read_bytes()
    with service.db.connect() as db:
        stored = db.execute('SELECT snapshot_json FROM versions WHERE id=?', (version['id'],)).fetchone()[0]
    service.save_profile(dict(name='合成正式长条', width=11811, height=520,
                              dpi=300, format='PNG', is_demo=False))
    service.settings = replace(service.settings, provider='deepseek_seedream')
    current = service.config()
    assert current['editing']['composite_edit'] is False
    assert current['editing']['planner_sees_images'] is False
    assert set(current['editing']['allowed_operations']) == {'parameters', 'edit_asset', 'edit_background'}
    projected = service.design(identity, design['id'])['versions'][0]
    # The old square version uses its own profile, not today's active long strip.
    assert projected['editing']['composite_edit'] is True
    assert projected['snapshot'] == json.loads(stored)
    assert service.version_file(identity, version['id']).read_bytes() == content
    with service.db.connect() as db:
        assert db.execute('SELECT snapshot_json FROM versions WHERE id=?', (version['id'],)).fetchone()[0] == stored


def test_formal_deterministic_first_draft_never_acquires_provider_and_stores_truthful_capabilities(service):
    service.save_profile(dict(name='合成正式长条', width=11811, height=520,
                              dpi=300, format='PNG', is_demo=False))
    service.settings = replace(service.settings, provider='deepseek_seedream')
    service.provider_factory = lambda *args: pytest.fail('deterministic first draft acquired a provider')
    identity, design = generate(service)
    version = design['versions'][0]
    assert set(version['snapshot']['capabilities']) == {'parameters', 'asset_edit', 'background_edit'}
    assert version['editing']['composite_edit'] is False
    assert design['successful_refinement_count'] == 0
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM provider_calls').fetchone()[0] == 0


def test_editing_is_exposed_by_authenticated_api_beside_immutable_snapshot(service):
    app = create_app(service.settings, service=service)
    with TestClient(app, base_url='http://localhost') as client:
        assert client.get('/api/config').status_code == 401
        assert client.post('/api/auth/login', json={'username': 'demo', 'password': 'demo12345'}).status_code == 200
        config = client.get('/api/config').json()
        assert config['editing']['planner_sees_images'] is False
        identity, design = generate(service)
        result = client.get('/api/designs/' + design['id'])
        assert result.status_code == 200
        version = result.json()['versions'][0]
        assert version['editing']['allowed_operations']
        assert 'editing' not in version['snapshot']
        assert not any(key in repr(config) for key in ('api_key', 'credential', 'password'))


@pytest.mark.parametrize('values', [
    {'scale': 1.0}, {'spacing': 1.0}, {'rotation': 0}, {'offset_x': 0, 'offset_y': 0},
    {'background_color': None},
    {'scale': 1.0, 'spacing': 1.0, 'rotation': 0, 'offset_x': 0, 'offset_y': 0, 'background_color': None},
])
def test_echoed_parameter_defaults_do_not_create_versions_or_charge(service, monkeypatch, values):
    identity, original = generate(service)
    content = service.version_file(identity, original['current_version_id']).read_bytes()
    plan(monkeypatch, [{'type': 'parameters', 'values': values}])
    monkeypatch.setattr(SyntheticProvider, 'edit_image', lambda *args: pytest.fail('no-op called image model'))
    job, latest = refine(service, identity, original)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '没有可执行的修改' in job['error']
    assert_unchanged(service, identity, original, latest, content)


def test_echoed_defaults_are_filtered_but_mixed_real_changes_succeed(service, monkeypatch):
    identity, original = generate(service)
    content = service.version_file(identity, original['current_version_id']).read_bytes()
    # Complete repeat groups quantise spacing; use a change that crosses a
    # visible group boundary. The dedicated quality test covers no-op spacing.
    plan(monkeypatch, [{'type': 'parameters', 'values': {'scale': 1.0, 'spacing': 2.0, 'rotation': 0}}])
    job, latest = refine(service, identity, original)
    assert job['status'] == 'SUCCEEDED' and latest['successful_refinement_count'] == 1
    version = next(v for v in latest['versions'] if v['id'] == latest['current_version_id'])
    assert version['snapshot']['edit_plan']['operations'] == [
        {'type': 'parameters', 'values': {'spacing': 2.0}}]
    assert service.version_file(identity, latest['current_version_id']).read_bytes() != content
    assert service.version_file(identity, original['current_version_id']).read_bytes() == content


def test_parameter_changes_that_cancel_are_not_a_chargeable_edit(service, monkeypatch):
    identity, original = generate(service)
    content = service.version_file(identity, original['current_version_id']).read_bytes()
    plan(monkeypatch, [{'type': 'parameters', 'values': {'scale': 1.2}},
                       {'type': 'parameters', 'values': {'scale': 1.0}}])
    job, latest = refine(service, identity, original)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert_unchanged(service, identity, original, latest, content)


def test_noop_plan_still_allows_a_real_selection_change(service, monkeypatch):
    identity, original = generate(service)
    changed = selection(service, identity)
    changed['template_id'] = 'single'
    plan(monkeypatch, [{'type': 'parameters', 'values': {'scale': 1.0}}])
    job, latest = refine(service, identity, original, choice=changed)
    assert job['status'] == 'SUCCEEDED' and latest['successful_refinement_count'] == 1
    version = next(v for v in latest['versions'] if v['id'] == latest['current_version_id'])
    assert version['snapshot']['template_mode'] == 'single'
    assert version['snapshot']['edit_plan']['operations'] == []


def test_identical_selection_and_noop_plan_are_not_an_edit(service, monkeypatch):
    identity, original = generate(service)
    content = service.version_file(identity, original['current_version_id']).read_bytes()
    plan(monkeypatch, [])
    job, latest = refine(service, identity, original, choice=selection(service, identity))
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert_unchanged(service, identity, original, latest, content)


def test_formal_composite_is_rejected_before_flatten_or_image_request(service, monkeypatch):
    service.save_profile(dict(name='合成正式长条', width=11811, height=520,
                              dpi=300, format='PNG', is_demo=False))
    service.settings = replace(service.settings, provider='deepseek_seedream')
    service.provider_factory = lambda *args: SyntheticProvider()
    identity, original = generate(service)
    content = service.version_file(identity, original['current_version_id']).read_bytes()
    plan(monkeypatch, [{'type': 'edit_composite', 'prompt': '合成整幅修改'}])
    monkeypatch.setattr('ribbon_backend.imaging.render', lambda *args: pytest.fail('unsupported composite flattened'))
    monkeypatch.setattr(SyntheticProvider, 'edit_image', lambda *args: pytest.fail('unsupported composite called model'))
    job, latest = refine(service, identity, original)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '长条' in job['error']
    assert_unchanged(service, identity, original, latest, content)


@pytest.mark.parametrize('later', [
    {'type': 'edit_asset', 'asset_id': 'not-owned-by-this-design', 'prompt': '合成修改'},
    {'type': 'parameters', 'values': {'scale': 999}},
    {'type': 'edit_background', 'prompt': ''},
    {'type': 'edit_background', 'prompt': '   '},
    {'type': 'unknown_operation'},
])
def test_invalid_later_operation_blocks_all_image_calls(service, monkeypatch, later):
    identity, original = generate(service)
    content = service.version_file(identity, original['current_version_id']).read_bytes()
    target = original['versions'][0]['snapshot']['asset_refs'][0]
    plan(monkeypatch, [{'type': 'edit_asset', 'asset_id': target, 'prompt': '添加星光'}, later])
    monkeypatch.setattr(SyntheticProvider, 'edit_image', lambda *args: pytest.fail('partially valid plan spent an image call'))
    job, latest = refine(service, identity, original)
    assert job['status'] == 'FAILED'
    assert_unchanged(service, identity, original, latest, content)


def test_duplicate_target_is_rejected_before_first_image_generation(service, monkeypatch):
    identity, original = generate(service)
    content = service.version_file(identity, original['current_version_id']).read_bytes()
    target = original['versions'][0]['snapshot']['asset_refs'][0]
    plan(monkeypatch, [{'type': 'edit_asset', 'asset_id': target, 'prompt': '添加星光'},
                       {'type': 'edit_asset', 'asset_id': target, 'prompt': '添加另一种装饰'}])
    monkeypatch.setattr(SyntheticProvider, 'edit_image', lambda *args: pytest.fail('duplicate edits spent an image call'))
    job, latest = refine(service, identity, original)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '合并成一条' in job['error']
    assert_unchanged(service, identity, original, latest, content)


def test_fresh_claim_and_recovery_use_distinct_truthful_phases(service):
    identity = owner(service)
    design = service.create_design(identity, '合成阶段检查')
    submitted = service.submit(identity, 'generate', dict(idempotency_key=str(uuid4()),
                               **selection(service, identity)), design['id'])
    first = service.claim_job()
    assert not first['recovered'] and service.job(identity, submitted['id'])['phase'] == '正在准备处理'
    with service.db.transaction() as db:
        db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (submitted['id'],))
    recovered = service.claim_job()
    assert recovered['recovered'] and service.job(identity, submitted['id'])['phase'] == '正在恢复任务'


@pytest.mark.parametrize('operation,expected_phase', [
    ('edit_asset', '正在修改图案'), ('edit_background', '正在修改底图'),
    ('edit_composite', '正在修改整幅画面'),
])
def test_image_target_phase_is_visible_before_synthetic_editor(service, monkeypatch, operation, expected_phase):
    identity, original = generate(service)
    op = dict(type=operation, prompt='添加星光' if operation != 'edit_background' else '添加波点')
    if operation == 'edit_asset':
        op['asset_id'] = original['versions'][0]['snapshot']['asset_refs'][0]
    plan(monkeypatch, [op])
    phases = []
    actual = SyntheticProvider.edit_image
    def observe(provider, prompt, source, output, target):
        with service.db.connect() as db:
            phases.append(db.execute("SELECT phase FROM jobs WHERE kind='refine' ORDER BY created_at DESC LIMIT 1").fetchone()[0])
        return actual(provider, prompt, source, output, target)
    monkeypatch.setattr(SyntheticProvider, 'edit_image', observe)
    job, latest = refine(service, identity, original)
    assert job['status'] == 'SUCCEEDED'
    assert phases == [expected_phase]


def upload(service, identity, size, color, kind):
    stream = BytesIO()
    Image.new('RGBA', size, color).save(stream, 'PNG')
    return service.upload(dict(id=identity, role='customer'), stream.getvalue(),
                          '明确的合成输入资格验收图', kind)['id']


def real_input_guard_synthetic_editor(service, events):
    from ribbon_backend.providers import DeepSeekSeedreamProvider
    # Construct only its stateless local input validator; no credentials/client
    # or network transport is initialized. Editing remains a visible substitute.
    checker = object.__new__(DeepSeekSeedreamProvider)
    class GuardedSyntheticProvider(SyntheticProvider):
        def validate_edit_input(self, source_path, target):
            events.append(('validate', str(source_path), target))
            return checker.validate_edit_input(source_path, target)

        def edit_image(self, prompt, source_path, output_path, target):
            events.append(('edit', str(source_path), target))
            return super().edit_image(prompt, source_path, output_path, target)
    service.provider_factory = lambda *args: GuardedSyntheticProvider()


@pytest.mark.parametrize('invalid_kind', ('pattern', 'background'))
def test_later_ineligible_image_blocks_every_image_call_and_keeps_quota(service, monkeypatch, invalid_kind):
    identity = owner(service)
    bad = upload(service, identity, (1700, 64), '#e89050', invalid_kind)
    choice = selection(service, identity)
    if invalid_kind == 'pattern':
        choice['asset_ids'][1] = bad
    else:
        choice['background_id'] = bad
    work = service.create_design(identity, '合成输入成本防护')
    first = service.submit(identity, 'generate', dict(idempotency_key=str(uuid4()), **choice), work['id'])
    assert service.run_once() and service.job(identity, first['id'])['status'] == 'SUCCEEDED'
    original = service.design(identity, work['id'])
    content = service.version_file(identity, original['current_version_id']).read_bytes()
    good = choice['asset_ids'][0]
    later = dict(type='edit_asset', asset_id=bad, prompt='添加星光') if invalid_kind == 'pattern' else dict(type='edit_background', prompt='添加波点')
    plan(monkeypatch, [dict(type='edit_asset', asset_id=good, prompt='添加星光'), later])
    events = []
    real_input_guard_synthetic_editor(service, events)
    job, latest = refine(service, identity, original)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert len(events) == 2 and all(item[0] == 'validate' for item in events)
    assert_unchanged(service, identity, original, latest, content)
    with service.db.connect() as db:
        calls = [row[0] for row in db.execute('SELECT operation FROM provider_calls WHERE job_id=?', (job['id'],))]
    assert calls == ['plan']


def test_all_eligible_sources_are_checked_before_a_valid_two_pattern_edit(service, monkeypatch):
    identity, original = generate(service)
    refs = original['versions'][0]['snapshot']['asset_refs']
    plan(monkeypatch, [dict(type='edit_asset', asset_id=ref, prompt='添加星光') for ref in refs])
    events = []
    real_input_guard_synthetic_editor(service, events)
    job, latest = refine(service, identity, original)
    assert job['status'] == 'SUCCEEDED' and latest['successful_refinement_count'] == 1
    assert [item[0] for item in events[:3]] == ['validate', 'validate', 'edit']
    assert sum(item[0] == 'edit' for item in events) == 2
    version = next(v for v in latest['versions'] if v['id'] == latest['current_version_id'])
    assert set(version['snapshot']['asset_refs']).isdisjoint(refs)


def test_input_precheck_uses_visible_opaque_override_of_transparent_background(service, monkeypatch):
    identity = owner(service)
    transparent = upload(service, identity, (96, 96), (0, 0, 0, 0), 'background')
    choice = selection(service, identity)
    choice['background_id'] = transparent
    work = service.create_design(identity, '合成可见底色资格验收')
    first = service.submit(identity, 'generate', dict(idempotency_key=str(uuid4()), **choice), work['id'])
    assert service.run_once() and service.job(identity, first['id'])['status'] == 'SUCCEEDED'
    original = service.design(identity, work['id'])
    plan(monkeypatch, [dict(type='parameters', values={'background_color': '#345678'}),
                       dict(type='edit_background', prompt='添加波点')])
    events = []
    real_input_guard_synthetic_editor(service, events)
    job, latest = refine(service, identity, original)
    assert job['status'] == 'SUCCEEDED' and latest['successful_refinement_count'] == 1
    assert events[0][0] == 'validate' and events[1][0] == 'edit'
    assert events[0][1] == events[1][1] and 'before-background-' in events[0][1]
    with Image.open(events[0][1]) as visible:
        assert visible.size == (96, 96) and visible.getchannel('A').getextrema() == (255, 255)
        assert visible.getpixel((0, 0)) == (0x34, 0x56, 0x78, 255)
    version = next(v for v in latest['versions'] if v['id'] == latest['current_version_id'])
    assert version['snapshot']['params']['background_color'] is None


def test_repeated_background_edits_are_merged_by_clarification_before_any_image_call(service, monkeypatch):
    identity, original = generate(service)
    plan(monkeypatch, [dict(type='edit_background', prompt='添加波点'),
                       dict(type='edit_background', prompt='添加星光')])
    monkeypatch.setattr(SyntheticProvider, 'edit_image', lambda *args: pytest.fail('repeated background edits called images'))
    job, latest = refine(service, identity, original)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '合并成一条' in job['error'] and latest['successful_refinement_count'] == 0
