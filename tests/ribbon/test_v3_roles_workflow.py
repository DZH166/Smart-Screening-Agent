"""Role choices cross the real HTTP boundary and bind to immutable versions.

Only synthetic local images/providers are used; these tests do not measure
visual design quality or call paid models.
"""

from legacy_jobs import recover_legacy_refinement
from copy import deepcopy
import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from ribbon_backend import loop_pipeline_v2, loop_pipeline_v3
from ribbon_backend.providers import workflow_editing, _safe_plan_input
from ribbon_backend.ribbon_targets import target_view
from test_loop_workflow import workflow, current, ok, png
from test_v2_targets import edit


def roles(design):
    return current(design)['snapshot']['pattern_roles']


def test_role_choice_saves_slot_ids_and_is_immutable_after_content_edit(workflow):
    a, b, c = workflow.selection['asset_ids']
    initial = workflow.generate({**workflow.selection, 'template_id': 'scene',
        'pattern_roles': {a: 'main', b: 'support', c: 'accent'}})
    first = current(initial)
    snapshot = first['snapshot']
    slots = snapshot['pattern_slots']
    assert snapshot['layout_engine'] == loop_pipeline_v3.ENGINE
    assert roles(initial) == dict(zip(slots, ['main', 'support', 'accent']))
    original_bytes = workflow.download(first)
    workflow.provider.edit_size = (180, 180)
    done, changed = edit(workflow, initial, slots[2],
        {'type': 'edit_asset', 'asset_id': c, 'prompt': 'Synthetic selected accent only'})
    assert done['status'] == 'SUCCEEDED', done
    new = current(changed)['snapshot']
    assert new['asset_refs'][2] != c and new['asset_refs'][:2] == [a, b]
    assert new['pattern_slots'] == slots and new['pattern_roles'] == snapshot['pattern_roles']
    assert workflow.download(first) == original_bytes
    loop_pipeline_v3.validate_binding(new, hashlib.sha256(workflow.download(current(changed))).hexdigest())
    assert changed['successful_refinement_count'] == 1


def test_defaults_do_not_turn_every_uploaded_figure_into_border(workflow):
    initial = workflow.generate({**workflow.selection, 'template_id': 'bordered'})
    assert set(roles(initial).values()) == {'main'}
    transforms = current(initial)['snapshot']['object_transforms']
    assert {p['slot_id'] for p in transforms} == set(roles(initial))
    assert all(p['role'] not in ('top-border', 'bottom-border') for p in transforms)


@pytest.mark.parametrize('mode,mapping', [
    ('single', {'selected': 'main'}),
    ('scene', {'selected': 'border'}),
    ('scatter', {'selected': 'support'}),
    ('bordered', {'selected': 'accent'}),
    ('scene', {'unselected-or-foreign': 'main'}),
    ('scene', None),
    ('scene', {'selected': 'unknown-role'}),
])
def test_invalid_roles_fail_before_a_job_or_model_call(workflow, mode, mapping):
    if isinstance(mapping, dict):
        mapping = {workflow.selection['asset_ids'][0] if k == 'selected' else k: v
                   for k, v in mapping.items()}
    design = workflow.create()
    body = {**workflow.selection, 'template_id': mode, 'pattern_roles': mapping,
            'idempotency_key': str(uuid4())}
    response = workflow.client.post(f'/api/designs/{design["id"]}/generate', json=body)
    assert response.status_code == 422, response.text
    assert not workflow.get(design)['versions']
    assert not workflow.provider.plan_calls and not workflow.provider.edit_calls
    with workflow.service.db.connect() as db:
        assert not db.execute('SELECT 1 FROM jobs WHERE design_id=?', (design['id'],)).fetchone()


@pytest.mark.parametrize('mode,role', [('scene', 'support'), ('scatter', 'accent'), ('bordered', 'border')])
def test_at_least_one_main_is_required(workflow, mode, role):
    design = workflow.create()
    body = {**workflow.selection, 'template_id': mode,
        'pattern_roles': {asset: role for asset in workflow.selection['asset_ids']},
        'idempotency_key': str(uuid4())}
    response = workflow.client.post(f'/api/designs/{design["id"]}/generate', json=body)
    assert response.status_code == 422 and '主图' in response.text


def test_role_change_is_real_refinement_and_same_choice_is_noop(workflow):
    selection = {**workflow.selection, 'template_id': 'bordered'}
    initial = workflow.generate(selection)
    a, b, c = selection['asset_ids']
    choice = {**selection, 'pattern_roles': {a: 'main', b: 'main', c: 'border'}}
    done, changed = workflow.refine(initial, selection=choice, prompt='应用所选配置')
    assert done['status'] == 'SUCCEEDED', done
    assert workflow.download(current(changed)) != workflow.download(current(initial))
    assert changed['successful_refinement_count'] == 1
    failed, same = workflow.refine(changed, selection=choice, prompt='应用所选配置')
    assert failed['status'] == 'FAILED', failed
    assert same['current_version_id'] == changed['current_version_id']
    assert same['successful_refinement_count'] == 1
    assert not workflow.provider.plan_calls and not workflow.provider.edit_calls


def test_omitted_roles_survive_same_mode_and_clear_on_mode_change(workflow):
    a, b, c = workflow.selection['asset_ids']
    initial = workflow.generate({**workflow.selection, 'template_id': 'scene',
        'pattern_roles': {a: 'main', b: 'support', c: 'accent'}})
    done, next_version = workflow.refine(initial,
        selection={**workflow.selection, 'template_id': 'scene', 'design_density': 'airy'},
        prompt='应用所选配置')
    assert done['status'] == 'SUCCEEDED', done
    assert roles(next_version) == roles(initial)
    done, plain = workflow.refine(next_version, selection=workflow.selection, prompt='应用所选配置')
    assert done['status'] == 'SUCCEEDED', done
    assert roles(plain) == {}


def test_saved_v2_generation_refinement_download_remain_on_v2(workflow, monkeypatch):
    original = workflow.service.selection_snapshot
    def historical(db, owner, selection, profile=None, base=None):
        value = original(db, owner, selection, profile, base)
        if base is None:
            value['layout_engine'] = loop_pipeline_v2.ENGINE
            value.pop('pattern_roles', None)
        return value
    with monkeypatch.context() as patch:
        patch.setattr(workflow.service, 'selection_snapshot', historical)
        initial = workflow.generate({**workflow.selection, 'template_id': 'stagger'})
    first = current(initial)
    saved = workflow.download(first)
    loop_pipeline_v2.validate_binding(first['snapshot'], hashlib.sha256(saved).hexdigest())
    target = first['snapshot']['pattern_slots'][0]
    done, changed = edit(workflow, initial, target, {'type': 'parameters', 'values': {'offset_x': -4}})
    assert done['status'] == 'SUCCEEDED', done
    assert current(changed)['snapshot']['layout_engine'] == loop_pipeline_v2.ENGINE
    assert workflow.download(first) == saved
    body = {**workflow.selection, 'template_id': 'scene',
            'pattern_roles': {workflow.selection['asset_ids'][0]: 'main'}}
    from ribbon_backend.service import ServiceError
    # The retained v2 recipe validator cannot be granted v3 role capabilities.
    with workflow.service.db.connect() as db, pytest.raises(ServiceError) as invalid:
        workflow.service.selection_snapshot(db, workflow.owner, body,
            current(changed)['snapshot']['output_profile'], current(changed)['snapshot'])
    assert invalid.value.status == 422
    assert workflow.client.post(f'/api/designs/{changed["id"]}/refinements', json={}).status_code == 410
    assert workflow.get(changed)['successful_refinement_count'] == 1


def test_v3_geometry_signature_rejects_role_relabel(workflow):
    initial = workflow.generate({**workflow.selection, 'template_id': 'scene'})
    first = current(initial)
    tampered = deepcopy(first['snapshot'])
    tampered['pattern_roles'][tampered['pattern_slots'][1]] = 'accent'
    with pytest.raises(ValueError):
        loop_pipeline_v3.validate_binding(tampered, hashlib.sha256(workflow.download(first)).hexdigest())


def test_loop_v3_does_not_expose_composite_redraw_or_drop_spacing():
    capabilities = workflow_editing('test', {'layout_engine': 'seamless-unit-v3',
        'template_mode': 'fullwidth', 'output_profile': {'width': 512, 'height': 256}})
    assert 'edit_composite' not in capabilities['allowed_operations']
    assert 'spacing' in capabilities['allowed_parameters']


def test_planner_receives_the_selected_slots_role_not_the_first_patterns_role():
    snapshot = dict(layout_engine='seamless-unit-v3', template_mode='scene',
        asset_refs=['first', 'second', 'third'], pattern_slots=['slot-a', 'slot-b', 'slot-c'],
        pattern_roles={'slot-a': 'main', 'slot-b': 'support', 'slot-c': 'accent'},
        slot_params={}, params={}, output_profile={'width': 1000, 'height': 240})
    view = target_view(snapshot, 'slot-c')
    safe = _safe_plan_input('Make selected accent smaller', view,
        [{'id': 'third', 'name': 'Synthetic accent', 'kind': 'pattern'}], provider='test')
    assert safe['assets'] == [{'position': 3, 'id': 'third', 'name': 'Synthetic accent',
                              'kind': 'pattern', 'layout_role': 'accent'}]
    assert safe['snapshot']['editing']['allowed_operations'] == ['parameters', 'edit_asset']


def test_v3_does_not_rewrite_existing_template_versions_or_seed_thumbnails(workflow):
    old = next(t for t in workflow.service.templates() if t['mode'] == 'scene')
    original = workflow.client.get(old['thumbnail_url']).content
    updated = workflow.service.save_template(dict(id=old['id'], name='Existing customized scene',
        mode=old['mode'], rules=dict(old['rules'], motif_ratio=.22), enabled=True))
    def stored():
        with workflow.service.db.connect() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM templates ORDER BY id, version')]
        return rows, {row['thumbnail_path']: hashlib.sha256(Path(row['thumbnail_path']).read_bytes()).hexdigest()
                      for row in rows}
    before = stored()
    workflow.service.initialize()
    assert stored() == before
    design = workflow.generate({**workflow.selection, 'template_id': old['id']})
    snapshot = current(design)['snapshot']
    assert snapshot['layout_engine'] == 'seamless-unit-v3'
    assert snapshot['template_version'] == updated['version']
    assert snapshot['template_rules'] == updated['rules']
    assert workflow.client.get(old['thumbnail_url']).content == original
    assert stored() == before


def test_twelve_mixed_patterns_keep_complete_coverage_and_thirteenth_is_rejected(workflow):
    selected = list(workflow.selection['asset_ids'])
    for i in range(9):
        size = ((72, 200), (300, 70), (160, 160))[i % 3]
        selected.append(workflow.upload(png(size, f'#{20+i*7:02x}4f90', marker=i+10),
                                        f'Mixed synthetic {i}')['id'])
    selection = {**workflow.selection, 'asset_ids': selected, 'template_id': 'scatter',
                 'pattern_roles': {selected[-1]: 'accent'}}
    initial = workflow.generate(selection)
    snapshot = current(initial)['snapshot']
    assert len(snapshot['asset_refs']) == 12
    assert {p['asset_ref'] for p in snapshot['object_transforms']} == set(selected)
    assert len(snapshot['pattern_slots']) == len(set(snapshot['pattern_slots'])) == 12
    extra = workflow.upload(png((110, 140), '#ad1234'), 'Thirteenth synthetic')['id']
    empty = workflow.create()
    failed = workflow.client.post(f'/api/designs/{empty["id"]}/generate', json={
        **selection, 'asset_ids': selected + [extra], 'idempotency_key': str(uuid4())})
    assert failed.status_code == 422 and not workflow.get(empty)['versions']


@pytest.mark.parametrize('mode', ['scatter', 'scene', 'bordered'])
def test_v3_ineffective_or_outside_target_does_not_charge_or_call_editor(workflow, mode):
    initial = workflow.generate({**workflow.selection, 'template_id': mode})
    base = current(initial)
    snapshot = base['snapshot']
    target = snapshot['pattern_slots'][0]
    original = workflow.download(base)
    for values in ({'scale': .999}, {'offset_y': snapshot['output_profile']['height']}):
        workflow.provider.operations = [
            {'type': 'parameters', 'values': values},
            {'type': 'edit_asset', 'asset_id': snapshot['asset_refs'][0], 'prompt': 'Must not run'},
        ]
        job = ok(recover_legacy_refinement(workflow.client, workflow.service, f'/api/designs/{initial["id"]}/refinements', json={
            'base_version_id': base['id'], 'idempotency_key': str(uuid4()),
            'prompt': 'Synthetic invalid geometry before image edit', 'edit_target': target}))
        failed = workflow.work(job)
        unchanged = workflow.get(initial)
        assert failed['status'] == 'FAILED', failed
        assert unchanged['current_version_id'] == base['id']
        assert unchanged['successful_refinement_count'] == 0
        assert len(unchanged['versions']) == 1 and not workflow.provider.edit_calls
        assert workflow.download(base) == original
    succeeded, refined = edit(workflow, initial, target,
        {'type': 'parameters', 'values': {'scale': .8}})
    assert succeeded['status'] == 'SUCCEEDED', succeeded
    assert refined['successful_refinement_count'] == 1
    before = snapshot['object_transforms']
    after = current(refined)['snapshot']['object_transforms']
    for a, b in zip(before, after):
        if a['slot_id'] == target:
            assert b['height'] < a['height']
        else:
            assert (a['x'], a['y'], a['width'], a['height'], a['rotation']) == (
                b['x'], b['y'], b['width'], b['height'], b['rotation'])
