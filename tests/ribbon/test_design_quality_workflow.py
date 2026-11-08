"""Deterministic quality workflow checks; no business images or model calls."""

from legacy_jobs import seed_accepted_refinement
import json
import sqlite3
from uuid import uuid4

from PIL import Image, PngImagePlugin
import pytest

from ribbon_backend.config import Settings
from ribbon_backend.imaging import PARAM_DEFAULTS
from ribbon_backend.providers import TestProvider as SyntheticProvider, _safe_plan_input
from ribbon_backend.service import LAYOUT_ENGINE, Service, ServiceError, same_rgba_pixels


@pytest.fixture
def env(tmp_path):
    service = Service(Settings(data_dir=tmp_path, provider='test', auth_mode='demo'))
    service.save_profile(dict(name='合成质量工作流', width=1080, height=240,
                              dpi=96, format='PNG', is_demo=True))
    with service.db.connect() as db:
        owner = db.execute("SELECT id FROM users WHERE username='demo'").fetchone()[0]
    choice = dict(asset_ids=[row['id'] for row in service.assets(owner, 'pattern')[:2]],
                  background_id=service.assets(owner, 'background')[0]['id'], template_id='stagger')
    yield service, owner, choice
    service.stop()


def generate(env):
    service, owner, choice = env
    design = service.create_design(owner, '合成设计质量')
    job = service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()), **choice), design['id'])
    assert service.run_once()
    assert service.job(owner, job['id'])['status'] == 'SUCCEEDED'
    return service.design(owner, design['id'])


def refine(env, design, *, choice=None, prompt='合成修改'):
    service, owner, _ = env
    body = dict(idempotency_key=str(uuid4()), base_version_id=design['current_version_id'], prompt=prompt)
    if choice is not None:
        body['selection'] = choice
    submitted = seed_accepted_refinement(service, owner, design['id'], body)
    assert service.submit(owner, 'refine', body, design['id'])['id'] == submitted['id']
    assert service.run_once()
    return service.job(owner, submitted['id']), service.design(owner, design['id'])


def current(design):
    return next(row for row in design['versions'] if row['id'] == design['current_version_id'])


def legacy_generate(env, monkeypatch, engine=None):
    service, _, _ = env
    original = service.selection_snapshot

    def legacy(*args, **kwargs):
        snapshot = original(*args, **kwargs)
        snapshot['output_profile'] = snapshot.pop('output_profile_source', snapshot['output_profile'])
        snapshot.pop('loop', None)
        snapshot.pop('loop_layout', None)
        if engine is None:
            snapshot.pop('layout_engine', None)
            snapshot.pop('background_tone', None)
            snapshot.pop('design_density', None)
        else:
            snapshot['layout_engine'] = engine
        return snapshot

    with monkeypatch.context() as patch:
        patch.setattr(service, 'selection_snapshot', legacy)
        return generate(env)


def test_new_snapshots_record_engine_and_default_tone_but_legacy_selection_keeps_engine(env):
    service, owner, choice = env
    with service.db.connect() as db:
        first = service.selection_snapshot(db, owner, choice)
        assert first['layout_engine'] == LAYOUT_ENGINE
        assert first['background_tone'] == 'soft'
        assert first['design_density'] == 'balanced'
        first['background_tone'] = 'original'
        retained = service.selection_snapshot(db, owner, choice, base=first)
        assert retained['background_tone'] == 'original'
        legacy = {key: value for key, value in first.items() if key not in ('layout_engine', 'background_tone', 'design_density')}
        old = service.selection_snapshot(db, owner, choice, base=legacy)
        assert 'layout_engine' not in old and old['background_tone'] == 'original'
        assert 'design_density' not in old
        explicit = service.selection_snapshot(db, owner, dict(choice, background_tone='soft'), base=legacy)
        assert 'layout_engine' not in explicit and explicit['background_tone'] == 'soft'
        assert 'background_tone' not in legacy


def test_density_is_version_bound_and_legacy_never_silently_acquires_new_layout(env):
    service, owner, choice = env
    with service.db.connect() as db:
        first = service.selection_snapshot(db, owner, dict(choice, design_density='rich'))
        assert first['design_density'] == 'rich'
        retained = service.selection_snapshot(db, owner, choice, base=first)
        assert retained['design_density'] == 'rich'
        changed = service.selection_snapshot(db, owner, dict(choice, design_density='airy'), base=first)
        assert changed['design_density'] == 'airy' and first['design_density'] == 'rich'
        legacy = {key: value for key, value in first.items() if key not in ('layout_engine', 'design_density')}
        assert 'design_density' not in service.selection_snapshot(db, owner, choice, base=legacy)
        assert 'design_density' not in service.selection_snapshot(db, owner, dict(choice, design_density='balanced'), base=legacy)
        with pytest.raises(ServiceError) as error:
            service.selection_snapshot(db, owner, dict(choice, design_density='rich'), base=legacy)
        assert error.value.status == 422 and '新建作品' in error.value.message


@pytest.mark.parametrize('density', [None, 'automatic', True, []])
def test_unknown_density_cannot_enter_a_snapshot(env, density):
    service, owner, choice = env
    with service.db.connect() as db, pytest.raises(ServiceError) as error:
        service.selection_snapshot(db, owner, dict(choice, design_density=density))
    assert error.value.status == 422


@pytest.mark.parametrize('tone', [None, True, 1, '', 'automatic', ['soft'], {'soft': True}])
def test_unknown_or_untyped_background_tone_cannot_enter_a_job(env, tone):
    service, owner, choice = env
    design = service.create_design(owner, '非法底纹选择')
    with pytest.raises(ServiceError) as error:
        service.submit(owner, 'generate', dict(idempotency_key=str(uuid4()),
                       **dict(choice, background_tone=tone)), design['id'])
    assert error.value.status == 422
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0


def test_legacy_tiny_spacing_quantisation_does_not_charge_or_create_a_version(env, monkeypatch):
    service, owner, _ = env
    initial = legacy_generate(env, monkeypatch)
    original = service.version_file(owner, initial['current_version_id']).read_bytes()
    monkeypatch.setattr(SyntheticProvider, 'plan', lambda *args: {
        'summary': '合成量化间距', 'operations': [{'type': 'parameters', 'values': {'spacing': 1.001}}]})
    job, latest = refine(env, initial)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '像素相同' in job['error']
    assert latest['successful_refinement_count'] == 0
    assert latest['current_version_id'] == initial['current_version_id']
    assert len(latest['versions']) == 1
    assert service.version_file(owner, initial['current_version_id']).read_bytes() == original
    with service.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM provider_calls WHERE operation='plan'").fetchone()[0] == 1


def test_v2_repeat_spacing_quantisation_does_not_charge_or_create_a_version(env, monkeypatch):
    # This regression belongs to v2's fixed-width repeat quantisation. New loop
    # versions calculate their own period and have independent geometry checks.
    initial = legacy_generate(env, monkeypatch, engine='design-rhythm-v2')
    assert current(initial)['snapshot']['layout_engine'] == 'design-rhythm-v2'
    assert current(initial)['snapshot']['output_profile']['width'] == 1080
    monkeypatch.setattr(SyntheticProvider, 'plan', lambda *args: {
        'summary': '合成整周期量化', 'operations': [{'type': 'parameters', 'values': {'spacing': 1.01}}]})
    job, latest = refine(env, initial)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '像素相同' in job['error']
    assert latest['successful_refinement_count'] == 0
    assert latest['current_version_id'] == initial['current_version_id']
    assert len(latest['versions']) == 1
    assert current(latest)['snapshot'] == current(initial)['snapshot']


def test_explicit_legacy_tone_change_is_real_versioned_and_rollback_keeps_original(env, monkeypatch):
    service, owner, choice = env
    initial = legacy_generate(env, monkeypatch)
    previous = service.version_file(owner, initial['current_version_id']).read_bytes()
    job, latest = refine(env, initial, choice=dict(choice, background_tone='soft'), prompt='应用所选配置')
    assert job['status'] == 'SUCCEEDED' and latest['successful_refinement_count'] == 1
    assert current(latest)['snapshot']['background_tone'] == 'soft'
    assert 'layout_engine' not in current(latest)['snapshot']
    assert service.version_file(owner, latest['current_version_id']).read_bytes() != previous
    assert service.version_file(owner, initial['current_version_id']).read_bytes() == previous
    rolled = service.rollback(owner, latest['id'], latest['current_version_id'])
    assert rolled['current_version_id'] == initial['current_version_id']
    assert rolled['successful_refinement_count'] == 1
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM provider_calls').fetchone()[0] == 0


def test_legacy_selection_normalisation_is_not_an_edit_and_does_not_upgrade_layout(env, monkeypatch):
    _, _, choice = env
    initial = legacy_generate(env, monkeypatch)
    job, latest = refine(env, initial, choice=dict(choice, background_tone='original'), prompt='应用所选配置')
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert latest['current_version_id'] == initial['current_version_id']
    assert 'layout_engine' not in current(latest)['snapshot']
    assert latest['successful_refinement_count'] == 0


def test_decoded_comparison_ignores_png_metadata_and_compression_but_detects_pixel_changes(tmp_path):
    first, second = tmp_path / 'first.png', tmp_path / 'second.png'
    image = Image.new('RGBA', (71, 137), (20, 140, 80, 200))
    image.save(first, dpi=(96, 96), compress_level=1)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('synthetic', 'different container metadata')
    image.save(second, pnginfo=metadata, dpi=(300, 300), compress_level=9)
    assert first.read_bytes() != second.read_bytes()
    assert same_rgba_pixels(first, second)
    image.putpixel((70, 136), (21, 140, 80, 200))
    image.save(second)
    assert not same_rgba_pixels(first, second)
    image.close()


def test_text_planning_context_describes_measured_program_responsibility_without_image_data():
    snapshot = dict(template_mode='scene', template_rules={}, output_profile={'width': 11811, 'height': 520},
                    asset_refs=['asset-a'], params=dict(PARAM_DEFAULTS), layout_engine=LAYOUT_ENGINE,
                    background_tone='soft', private_path='never-send-this')
    result = _safe_plan_input('主体放大一点', snapshot,
                              [dict(id='asset-a', name='完整文字装饰', kind='pattern', path='never-send-this')],
                              provider='deepseek_seedream')
    assert result['snapshot']['layout_engine'] == LAYOUT_ENGINE
    assert result['snapshot']['background_tone'] == 'soft'
    assert result['snapshot']['editing']['planner_sees_images'] is False
    assert 'never-send-this' not in json.dumps(result)


def test_meaningful_legacy_refinement_and_parent_rollback_preserve_pixel_bound_downloads(env, monkeypatch):
    service, owner, _ = env
    initial = legacy_generate(env, monkeypatch)
    old = service.version_file(owner, initial['current_version_id']).read_bytes()
    monkeypatch.setattr(SyntheticProvider, 'plan', lambda *args: {
        'summary': '合成真实放大', 'operations': [{'type': 'parameters', 'values': {'scale': .7}}]})
    job, changed = refine(env, initial)
    assert job['status'] == 'SUCCEEDED' and changed['successful_refinement_count'] == 1
    assert 'layout_engine' not in current(changed)['snapshot']
    assert current(changed)['parent_version_id'] == initial['current_version_id']
    assert service.version_file(owner, initial['current_version_id']).read_bytes() == old
    rolled = service.rollback(owner, changed['id'], changed['current_version_id'])
    assert rolled['current_version_id'] == initial['current_version_id']
    assert rolled['successful_refinement_count'] == 1
    assert service.version_file(owner, rolled['current_version_id']).read_bytes() == old


def test_model_copy_is_recorded_as_an_attempt_but_not_a_successful_refinement(env, monkeypatch):
    service, owner, _ = env
    initial = legacy_generate(env, monkeypatch)
    target = current(initial)['snapshot']['asset_refs'][0]
    monkeypatch.setattr(SyntheticProvider, 'plan', lambda *args: {
        'summary': '合成原样返回', 'operations': [{'type': 'edit_asset', 'asset_id': target, 'prompt': '进一步细腻'}]})

    def unchanged_copy(self, prompt, source, output, kind):
        output.write_bytes(source.read_bytes())
        return {'model': 'explicit-synthetic-copy', 'usage': {'generated_images': 1}}

    monkeypatch.setattr(SyntheticProvider, 'edit_image', unchanged_copy)
    with service.db.connect() as db:
        count = db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
    job, latest = refine(env, initial)
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '像素相同' in job['error']
    assert latest['current_version_id'] == initial['current_version_id']
    assert latest['successful_refinement_count'] == 0 and len(latest['versions']) == 1
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == count
        calls = list(db.execute('SELECT operation,status,usage_json FROM provider_calls WHERE job_id=? ORDER BY created_at', (job['id'],)))
        assert [row['operation'] for row in calls] == ['plan', 'edit_asset']
        assert all(row['status'] == 'SUCCEEDED' for row in calls)
        assert json.loads(calls[-1]['usage_json']) == {'generated_images': 1}


def test_recovered_checkpoint_rechecks_pixel_noop_without_repeating_the_planner(env, monkeypatch):
    service, owner, _ = env
    initial = legacy_generate(env, monkeypatch)
    monkeypatch.setattr(SyntheticProvider, 'plan', lambda *args: {
        'summary': '合成待恢复间距', 'operations': [{'type': 'parameters', 'values': {'spacing': 1.001}}]})
    original_complete = service.complete_job

    def unavailable_commit(*args):
        raise sqlite3.OperationalError('synthetic temporary commit failure')

    monkeypatch.setattr(service, 'complete_job', unavailable_commit)
    submitted = seed_accepted_refinement(service, owner, initial['id'], dict(idempotency_key=str(uuid4()),
                               base_version_id=initial['current_version_id'], prompt='合成量化'))
    assert service.run_once()
    assert service.job(owner, submitted['id'])['status'] == 'RECONCILING'
    monkeypatch.setattr(service, 'complete_job', original_complete)
    monkeypatch.setattr(SyntheticProvider, 'plan', lambda *args: pytest.fail('checkpoint recovery repeated planner'))
    assert service.run_once()
    job, latest = service.job(owner, submitted['id']), service.design(owner, initial['id'])
    assert job['status'] == 'FAILED' and job['needs_clarification']
    assert '像素相同' in job['error']
    assert latest['current_version_id'] == initial['current_version_id']
    assert latest['successful_refinement_count'] == 0 and len(latest['versions']) == 1
    assert latest['active_job_id'] is None
    with service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM provider_calls WHERE job_id=?', (job['id'],)).fetchone()[0] == 1
