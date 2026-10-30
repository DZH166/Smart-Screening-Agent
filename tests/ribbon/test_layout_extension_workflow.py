"""Real local transactions and files for the added layout families.

Providers here are explicitly synthetic. No company preview is production input
and no paid API, cloud identity or real administrator credential is used.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ribbon_backend.app import create_app
from ribbon_backend.config import Settings
from ribbon_backend import service as service_module
from ribbon_backend.service import Service, ServiceError, file_digest


LEGACY_MODES = ('grid', 'stagger', 'scatter', 'single', 'ends', 'panels')
EXTRA_MODES = ('bordered', 'scene', 'fullwidth', 'alternating', 'ends_open', 'split', 'stacked', 'opposed')


def actor(service, name='demo'):
    with service.db.connect() as db:
        return dict(db.execute('SELECT id,username,role FROM users WHERE username=?', (name,)).fetchone())


def choices(service, owner, mode, count=None):
    if count is None:
        count = 1 if mode == 'fullwidth' else (2 if mode == 'ends_open' else 3)
    return dict(asset_ids=[item['id'] for item in service.assets(owner, 'pattern')[:count]],
                background_id=service.assets(owner, 'background')[0]['id'], template_id=mode)


def generate(service, owner, mode):
    design = service.create_design(owner, '合成排版扩展验收')
    job = service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()),
                         **choices(service, owner, mode)), design['id'])
    assert service.run_once()
    assert service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    return service.design(owner, design['id'])


def refine(service, owner, design, prompt='图案缩小一些', selection=None):
    payload = dict(idempotency_key=str(uuid4()), base_version_id=design['current_version_id'], prompt=prompt)
    if selection is not None:
        payload['selection'] = selection
    job = service.submit(owner, 'refine', payload, design['id'])
    assert service.submit(owner, 'refine', payload, design['id'])['id'] == job['id']
    assert service.run_once()
    return service.job(owner, job['id']), service.design(owner, design['id'])


@pytest.fixture
def service(tmp_path):
    instance = Service(Settings(data_dir=tmp_path, provider='test', auth_mode='demo'))
    instance.save_profile(dict(name='合成验收规格', width=1080, height=240,
                               dpi=96, format='PNG', is_demo=True))
    yield instance
    instance.stop()


@pytest.mark.parametrize('mode', EXTRA_MODES)
def test_added_mode_real_generate_branch_refine_and_pinned_download(service, mode):
    owner = actor(service)['id']
    original = generate(service, owner, mode)
    v0 = original['current_version_id']
    bytes0 = service.version_file(owner, v0).read_bytes()
    assert original['successful_refinement_count'] == 0
    assert original['versions'][0]['snapshot']['asset_refs'] == choices(service, owner, mode)['asset_ids']
    assert original['versions'][0]['snapshot']['template_mode'] == mode
    job, one = refine(service, owner, original)
    assert job['status'] == 'SUCCEEDED'
    v1 = one['current_version_id']
    bytes1 = service.version_file(owner, v1).read_bytes()
    assert bytes0 != bytes1
    assert one['successful_refinement_count'] == 1
    back = service.rollback(owner, original['id'], v1)
    assert back['current_version_id'] == v0 and back['successful_refinement_count'] == 1
    job, two = refine(service, owner, back, '图案放大一些')
    assert job['status'] == 'SUCCEEDED' and two['successful_refinement_count'] == 2
    versions = {item['id']: item for item in two['versions']}
    assert versions[v1]['parent_version_id'] == versions[two['current_version_id']]['parent_version_id'] == v0
    assert service.version_file(owner, v0).read_bytes() == bytes0
    assert service.version_file(owner, v1).read_bytes() == bytes1
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM quota_events WHERE design_id=?', (original['id'],)).fetchone()[0] == 2
    with pytest.raises(ServiceError, match='两次精修已用完'):
        refine(service, owner, two)


@pytest.mark.parametrize('mode,count,message', [
    ('bordered', 1, '至少选择2个'),
    ('fullwidth', 2, '请选择1张完整设计'),
    ('ends_open', 3, '请选择1或2个'),
    ('split', 1, '至少选择2个'),
    ('stacked', 1, '至少选择2个'),
])
def test_invalid_pattern_count_rejects_generate_without_job_or_charge(service, mode, count, message):
    owner = actor(service)['id']
    design = service.create_design(owner, '不合法选择')
    with pytest.raises(ServiceError, match=message):
        service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()),
                       **choices(service, owner, mode, count)), design['id'])
    assert service.design(owner, design['id'])['active_job'] is None
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs WHERE design_id=?', (design['id'],)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM quota_events WHERE design_id=?', (design['id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('mode,count', [('ends_open', 1), ('split', 2), ('alternating', 1),
                                       ('stacked', 2), ('opposed', 1)])
def test_new_mode_minimum_pattern_selection_is_rendered_without_dropping_inputs(service, mode, count):
    owner = actor(service)['id']
    design = service.create_design(owner, '最小图案选择')
    selection = choices(service, owner, mode, count)
    job = service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()), **selection), design['id'])
    assert service.run_once()
    assert service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    saved = service.design(owner, design['id'])['versions'][0]['snapshot']
    assert saved['asset_refs'] == selection['asset_ids']
    assert {item['asset_ref'] for item in saved['object_transforms']} == set(selection['asset_ids'])


@pytest.mark.parametrize('mode,count', [('bordered', 1), ('fullwidth', 2), ('ends_open', 3), ('split', 1),
                                       ('stacked', 1)])
def test_selection_refinement_revalidates_added_mode_counts(service, mode, count):
    owner = actor(service)['id']
    design = generate(service, owner, 'grid')
    current = design['current_version_id']
    with pytest.raises(ServiceError) as error:
        refine(service, owner, design, '应用所选配置', choices(service, owner, mode, count))
    assert error.value.status == 422
    unchanged = service.design(owner, design['id'])
    assert unchanged['current_version_id'] == current
    assert unchanged['active_job'] is None and unchanged['successful_refinement_count'] == 0


@pytest.mark.parametrize('mode', EXTRA_MODES)
def test_switching_from_legacy_layout_binds_new_selection_without_rewriting_old_version(service, mode):
    owner = actor(service)['id']
    original = generate(service, owner, 'grid')
    old_id = original['current_version_id']
    old_bytes = service.version_file(owner, old_id).read_bytes()
    selection = choices(service, owner, mode)
    job, changed = refine(service, owner, original, '应用所选配置', selection)
    assert job['status'] == 'SUCCEEDED'
    snapshot = changed['versions'][-1]['snapshot']
    assert snapshot['template_mode'] == mode and snapshot['asset_refs'] == selection['asset_ids']
    assert changed['versions'][-1]['parent_version_id'] == old_id
    assert changed['successful_refinement_count'] == 1
    assert service.version_file(owner, old_id).read_bytes() == old_bytes
    back = service.rollback(owner, original['id'], changed['current_version_id'])
    assert back['current_version_id'] == old_id and back['successful_refinement_count'] == 1


@pytest.mark.parametrize('mode', ('fullwidth', 'ends_open'))
def test_non_repeating_spacing_request_does_not_fake_a_success_or_charge(service, mode):
    owner = actor(service)['id']
    original = generate(service, owner, mode)
    content = service.version_file(owner, original['current_version_id']).read_bytes()
    job, latest = refine(service, owner, original, '图案间距拉大一点')
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '不使用重复间距' in job['error']
    assert latest['current_version_id'] == original['current_version_id']
    assert latest['successful_refinement_count'] == 0
    assert service.version_file(owner, original['current_version_id']).read_bytes() == content


@pytest.mark.parametrize('mode', ('fullwidth', 'ends_open'))
@pytest.mark.parametrize('same_selection', (False, True))
def test_synthetic_unchanged_spacing_only_never_creates_a_version_or_charge(service, monkeypatch, mode, same_selection):
    from ribbon_backend.providers import TestProvider
    owner = actor(service)['id']
    original = generate(service, owner, mode)
    old_id = original['current_version_id']
    old_bytes = service.version_file(owner, old_id).read_bytes()
    # Explicit synthetic planner, not a real model accuracy/usage assertion.
    monkeypatch.setattr(TestProvider, 'plan', lambda self, prompt, snapshot, assets: {
        'summary': 'synthetic unchanged spacing only',
        'operations': [{'type': 'parameters', 'values': {'spacing': snapshot['params']['spacing']}}]})
    selection = choices(service, owner, mode) if same_selection else None
    job, latest = refine(service, owner, original, '合成检查：保留间距', selection)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '没有可执行的修改' in job['error']
    assert latest['current_version_id'] == old_id and len(latest['versions']) == 1
    assert latest['successful_refinement_count'] == 0
    assert service.version_file(owner, old_id).read_bytes() == old_bytes
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM quota_events WHERE design_id=?', (original['id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('mode', ('fullwidth', 'ends_open'))
def test_synthetic_unchanged_spacing_with_real_scale_keeps_the_real_edit(service, monkeypatch, mode):
    from ribbon_backend.providers import TestProvider
    owner = actor(service)['id']
    original = generate(service, owner, mode)
    old_id = original['current_version_id']
    old_bytes = service.version_file(owner, old_id).read_bytes()
    monkeypatch.setattr(TestProvider, 'plan', lambda self, prompt, snapshot, assets: {
        'summary': 'synthetic real scale with an unchanged spacing default',
        'operations': [{'type': 'parameters', 'values': {'spacing': snapshot['params']['spacing'], 'scale': 0.8}}]})
    job, latest = refine(service, owner, original, '合成检查：缩小并保留间距')
    assert job['status'] == 'SUCCEEDED' and latest['successful_refinement_count'] == 1
    assert latest['current_version_id'] != old_id
    assert service.version_file(owner, latest['current_version_id']).read_bytes() != old_bytes
    assert service.version_file(owner, old_id).read_bytes() == old_bytes
    assert latest['versions'][-1]['snapshot']['edit_plan']['operations'] == [
        {'type': 'parameters', 'values': {'scale': 0.8}}]


@pytest.mark.parametrize('mode', ('fullwidth', 'ends_open'))
def test_synthetic_unchanged_spacing_does_not_hide_a_real_selection_change(service, monkeypatch, mode):
    from ribbon_backend.providers import TestProvider
    owner = actor(service)['id']
    original = generate(service, owner, mode)
    old_id = original['current_version_id']
    old_bytes = service.version_file(owner, old_id).read_bytes()
    selected = choices(service, owner, mode)
    if mode == 'fullwidth':
        selected['asset_ids'] = [service.assets(owner, 'pattern')[1]['id']]
    else:
        selected['asset_ids'] = list(reversed(selected['asset_ids']))
    monkeypatch.setattr(TestProvider, 'plan', lambda self, prompt, snapshot, assets: {
        'summary': 'synthetic unchanged spacing with changed input selection',
        'operations': [{'type': 'parameters', 'values': {'spacing': snapshot['params']['spacing']}}]})
    job, latest = refine(service, owner, original, '合成检查：应用新选择并保留间距', selected)
    assert job['status'] == 'SUCCEEDED' and latest['successful_refinement_count'] == 1
    assert latest['versions'][-1]['snapshot']['asset_refs'] == selected['asset_ids']
    assert latest['versions'][-1]['snapshot']['edit_plan']['operations'] == []
    assert service.version_file(owner, latest['current_version_id']).read_bytes() != old_bytes
    assert service.version_file(owner, old_id).read_bytes() == old_bytes


def test_initialization_only_appends_missing_modes_and_preserves_legacy_records(tmp_path, monkeypatch):
    current_modes = service_module.MODES.copy()
    monkeypatch.setattr(service_module, 'MODES', {key: current_modes[key] for key in LEGACY_MODES})
    settings = Settings(data_dir=tmp_path, provider='test', auth_mode='demo')
    old = Service(settings)
    try:
        owner = actor(old)['id']
        old.save_profile(dict(name='合成正式配置', width=1080, height=240, dpi=300, format='PNG', is_demo=False))
        work = generate(old, owner, 'grid')
        old.save_template(dict(id='grid', name='管理员停用旧网格', mode='grid', enabled=False,
                               rules=dict(rows=3, is_demo=False)))
        # A pre-existing custom ID must not be overwritten just because it
        # happens to equal the short name of a newly introduced mode.
        old.save_template(dict(id='bordered', name='旧自定义模板', mode='single', enabled=False, rules={}))
        with old.db.connect() as db:
            templates = [dict(row) for row in db.execute('SELECT * FROM templates ORDER BY id,version')]
            profiles = [tuple(row) for row in db.execute('SELECT * FROM output_profiles ORDER BY version')]
            versions = [tuple(row) for row in db.execute('SELECT * FROM versions ORDER BY id')]
            designs = [tuple(row) for row in db.execute('SELECT * FROM designs ORDER BY id')]
        protected = {row['thumbnail_path']: file_digest(row['thumbnail_path']) for row in templates}
        protected[str(old.version_file(owner, work['current_version_id']))] = file_digest(old.version_file(owner, work['current_version_id']))
        monkeypatch.setattr(service_module, 'MODES', current_modes)
        old.initialize()
        with old.db.connect() as db:
            added = [dict(row) for row in db.execute('SELECT * FROM templates ORDER BY id,version')]
            assert [tuple(row) for row in db.execute('SELECT * FROM output_profiles ORDER BY version')] == profiles
            assert [tuple(row) for row in db.execute('SELECT * FROM versions ORDER BY id')] == versions
            assert [tuple(row) for row in db.execute('SELECT * FROM designs ORDER BY id')] == designs
        lookup = {(row['id'], row['version']): row for row in added}
        assert all(lookup[row['id'], row['version']] == row for row in templates)
        assert len(added) == len(templates) + len(EXTRA_MODES)
        fallback = next(row for row in added if row['mode'] == 'bordered')
        assert fallback['id'] == 'builtin-bordered'
        assert all(file_digest(path) == sha for path, sha in protected.items())
        old.save_template(dict(id=fallback['id'], name='停用新边饰', mode='bordered', enabled=False, rules={}))
        before = old.templates()
        old.initialize()
        old.initialize()
        assert old.templates() == before
        assert not next(row for row in old.templates() if row['id'] == fallback['id'])['enabled']
    finally:
        old.stop()


def test_admin_http_schema_accepts_real_added_modes(service):
    with TestClient(create_app(service.settings, service=service), base_url='http://localhost') as client:
        assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin12345'}).status_code == 200
        for mode in EXTRA_MODES:
            response = client.post('/api/admin/templates', json={'name': '合成自定义排版', 'mode': mode,
                                                               'rules': {'is_demo': True}})
            assert response.status_code == 201, response.text
            assert response.json()['mode'] == mode
        assert client.post('/api/admin/templates', json={'name': '未知', 'mode': 'imaginary'}).status_code == 422


@pytest.mark.parametrize('mode,rules', [('bordered', {'rows': 3}), ('scene', {'rows': 2}),
                                       ('fullwidth', {'rows': 2}), ('fullwidth', {'step_ratio': 0.5}),
                                       ('alternating', {'rows': 2}), ('ends_open', {'rows': 2}),
                                       ('ends_open', {'step_ratio': 0.5}), ('split', {'rows': 2}),
                                       ('stacked', {'rows': 2}), ('opposed', {'rows': 2})])
def test_inapplicable_template_rules_cannot_be_saved_as_fake_configuration(service, mode, rules):
    before = service.templates()
    with pytest.raises(ServiceError, match='移除不适用的规则') as error:
        service.save_template(dict(id=mode, name='不适用配置', mode=mode, rules=rules))
    assert error.value.status == 422
    assert service.templates() == before
