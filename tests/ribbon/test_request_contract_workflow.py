"""Actual HTTP/worker/native files with v2 request plans and explicit image fakes.

These tests prove request routing, arithmetic and transaction behaviour, never
the visual meaning of a generated picture. No external models are called.
"""

from legacy_jobs import recover_legacy_refinement
from copy import deepcopy
from io import BytesIO
import json
from uuid import uuid4

from PIL import Image, ImageDraw
import pytest

from test_loop_workflow import current, defer_commit, ok, workflow
from ribbon_backend.request_contract import source_units, validate_request_plan


def wire(prompt, effects, operations, *, targets=None):
    units = source_units(prompt)
    assert len(units) == len(effects), units
    targets = targets or ['layout'] * len(units)
    return {
        'summary': 'Explicit synthetic request-contract plan',
        'clarification': None,
        'requirements': [dict(source_id=unit['id'], target_id=target, effect=effect)
                         for unit, effect, target in zip(units, effects, targets)],
        'operations': deepcopy(operations),
    }


def parameter(prompt, key, value, *, index=0, mode='absolute', amount=None,
              direction='set', evidence=None):
    unit = source_units(prompt)[index]
    return dict(type='parameters', values={key: value}, source_ids=[unit['id']],
                intents=[dict(key=key, mode=mode, amount=value if amount is None else amount,
                              direction=direction, evidence=evidence or unit['text'])])


def content(prompt, *, index=0, asset=None):
    result = dict(type='edit_asset' if asset else 'edit_background',
                  prompt='Unrequested tiny pale blue accents invented by the planner',
                  source_ids=[source_units(prompt)[index]['id']])
    if asset:
        result['asset_id'] = asset
    return result


def submit_plan(workflow, design, prompt, plan, *, target='layout', key=None):
    def controlled_plan(text, snapshot, assets):
        workflow.provider.plan_calls.append(dict(prompt=text, snapshot=deepcopy(snapshot)))
        return deepcopy(plan)

    workflow.provider.plan = controlled_plan
    body = dict(idempotency_key=key or str(uuid4()), base_version_id=design['current_version_id'],
                prompt=prompt, edit_target=target)
    response = recover_legacy_refinement(workflow.client, workflow.service, f'/api/designs/{design["id"]}/refinements', json=body)
    job = ok(response)
    return workflow.work(job), workflow.get(design), body


def assert_unchanged(workflow, before, after, job):
    assert job['status'] == 'FAILED', job
    assert after['current_version_id'] == before['current_version_id']
    assert after['successful_refinement_count'] == before['successful_refinement_count']
    assert len(after['versions']) == len(before['versions'])
    assert workflow.download(current(before)) == workflow.download(current(after))


@pytest.mark.parametrize('omission', ['requirement', 'operation'])
def test_each_requested_source_needs_an_actual_execution_not_just_a_coverage_claim(workflow, omission):
    before = workflow.generate()
    prompt = '图案缩小20%，底纹添加树叶装饰'
    plan = wire(prompt, ['parameters', 'content'], [
        parameter(prompt, 'scale', .8, mode='percent', amount=20, direction='decrease'),
    ], targets=['layout', 'background'])
    if omission == 'requirement':
        plan['requirements'].pop()
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)
    assert not workflow.provider.edit_calls


def test_preservation_cannot_be_used_to_authorize_an_extra_operation(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%，底纹保持不变'
    operation = content(prompt, index=1)
    plan = wire(prompt, ['parameters', 'preserve'], [
        parameter(prompt, 'scale', .8, mode='percent', amount=20, direction='decrease'), operation,
    ], targets=['layout', 'background'])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)
    assert not workflow.provider.edit_calls


def test_a_preserve_word_cannot_hide_a_positive_modification_in_the_same_source(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%，底纹铺满叶子并保留底色'
    plan = wire(prompt, ['parameters', 'preserve'], [
        parameter(prompt, 'scale', .8, mode='percent', amount=20, direction='decrease'),
    ], targets=['layout', 'background'])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)
    assert not workflow.provider.edit_calls


def test_content_and_preservation_in_one_source_are_forwarded_together(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%，底纹铺满叶子并保留底色'
    plan = wire(prompt, ['parameters', 'content'], [
        parameter(prompt, 'scale', .8, mode='percent', amount=20, direction='decrease'),
        content(prompt, index=1),
    ], targets=['layout', 'background'])
    workflow.provider.edit_size = (320, 320)
    seen = []
    editor = workflow.provider.edit_image

    def record(text, source, output, kind):
        seen.append(text)
        return editor(text, source, output, kind)

    workflow.provider.edit_image = record
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert job['status'] == 'SUCCEEDED', job
    assert len(seen) == 1 and '底纹铺满叶子并保留底色' in seen[0]
    assert '图案缩小' not in seen[0]
    assert current(after)['snapshot']['params']['scale'] == pytest.approx(.8)


def test_percent_is_relative_to_current_value_not_the_template_default(workflow):
    # Keep headroom: a balanced layout at 1.4 is already height-capped and a
    # 20% parameter reduction would not mean a 20% visible reduction there.
    before = workflow.generate({**workflow.selection, 'design_density': 'airy'})
    workflow.provider.operations = [dict(type='parameters', values={'scale': 1.4})]
    prior, before = workflow.refine(before)
    assert prior['status'] == 'SUCCEEDED', prior
    assert current(before)['snapshot']['params']['scale'] == 1.4
    prompt = '图案缩小20%'
    wrong = wire(prompt, ['parameters'], [parameter(
        prompt, 'scale', .8, mode='percent', amount=20, direction='decrease')])
    job, same, _ = submit_plan(workflow, before, prompt, wrong)
    assert_unchanged(workflow, before, same, job)
    correct = wire(prompt, ['parameters'], [parameter(
        prompt, 'scale', 1.12, mode='percent', amount=20, direction='decrease')])
    job, after, _ = submit_plan(workflow, before, prompt, correct)
    assert job['status'] == 'SUCCEEDED', job
    assert current(after)['snapshot']['params']['scale'] == pytest.approx(1.12)
    assert after['successful_refinement_count'] == 2


@pytest.mark.parametrize('failure', ['wrong_amount', 'invented_evidence', 'negated_evidence'])
def test_wrong_number_or_negation_cannot_become_a_valid_directional_edit(workflow, failure):
    before = workflow.generate()
    prompt = '不要放大图案' if failure == 'negated_evidence' else '图案缩小20%'
    operation = parameter(prompt, 'scale', .8 if failure != 'negated_evidence' else 1.2,
                          mode='direction' if failure == 'negated_evidence' else 'percent',
                          amount=10 if failure == 'wrong_amount' else 20,
                          direction='increase' if failure == 'negated_evidence' else 'decrease',
                          evidence='图案缩小10%' if failure == 'invented_evidence' else
                          '放大图案' if failure == 'negated_evidence' else None)
    if failure == 'negated_evidence':
        # Evidence is a genuine substring, but cherry-picks away its negation.
        operation['intents'][0]['amount'] = None
    plan = wire(prompt, ['parameters'], [operation])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)
    assert not workflow.provider.edit_calls


def test_parameter_direction_must_match_the_requested_visible_change(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%'
    plan = wire(prompt, ['parameters'], [parameter(
        prompt, 'scale', 1.2, mode='percent', amount=20, direction='increase')])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)


def test_one_requirement_cannot_be_executed_twice_by_two_consistent_parameter_operations(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%'
    plan = wire(prompt, ['parameters'], [
        parameter(prompt, 'scale', .8, mode='percent', amount=20, direction='decrease'),
        parameter(prompt, 'scale', .64, mode='percent', amount=20, direction='decrease'),
    ])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)


def test_layer_name_before_negation_cannot_be_cherry_picked_out_of_evidence(workflow):
    before = workflow.generate()
    prompt = '图案不要放大'
    operation = parameter(prompt, 'scale', 1.2, mode='direction', direction='increase', evidence='放大')
    operation['intents'][0]['amount'] = None
    plan = wire(prompt, ['parameters'], [operation])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)


def test_service_revalidates_real_adapter_normalized_shape_with_safe_call_metadata(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%'
    raw = wire(prompt, ['parameters'], [parameter(
        prompt, 'scale', .8, mode='percent', amount=20, direction='decrease')])
    normalized = validate_request_plan(prompt, current(before)['snapshot'], raw, 'test')
    normalized.update(model='explicit-synthetic-normalized-plan', request_id='synthetic-plan-id',
                      usage={'prompt_tokens': 24})
    job, after, _ = submit_plan(workflow, before, prompt, normalized)
    assert job['status'] == 'SUCCEEDED', job
    assert current(after)['snapshot']['params']['scale'] == pytest.approx(.8)
    assert after['successful_refinement_count'] == 1


def test_relative_percent_cannot_be_reinterpreted_as_target_percent(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%'
    # The amount exists in the source and arithmetic is internally consistent,
    # but "shrink by 20%" is not "shrink to 20%".
    plan = wire(prompt, ['parameters'], [parameter(
        prompt, 'scale', .2, mode='percent', amount=20, direction='set')])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)


def test_original_number_does_not_authorize_a_different_parameter(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%'
    plan = wire(prompt, ['parameters'], [parameter(
        prompt, 'rotation', 20, mode='absolute', amount=20, direction='set')])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)


def test_move_twenty_pixels_is_a_delta_not_an_absolute_position(workflow):
    before = workflow.generate()
    workflow.provider.operations = [dict(type='parameters', values={'offset_x': 10})]
    prior, before = workflow.refine(before)
    assert prior['status'] == 'SUCCEEDED', prior
    prompt = '图案向右移动20像素'
    wrong = wire(prompt, ['parameters'], [parameter(
        prompt, 'offset_x', 20, mode='absolute', amount=20, direction='increase')])
    job, same, _ = submit_plan(workflow, before, prompt, wrong)
    assert_unchanged(workflow, before, same, job)
    correct = wire(prompt, ['parameters'], [parameter(
        prompt, 'offset_x', 30, mode='delta', amount=20, direction='increase')])
    job, after, _ = submit_plan(workflow, before, prompt, correct)
    assert job['status'] == 'SUCCEEDED', job
    assert current(after)['snapshot']['params']['offset_x'] == 30


def test_selected_pattern_absolute_angle_compensates_for_global_rotation(workflow):
    before = workflow.generate()
    workflow.provider.operations = [dict(type='parameters', values={'rotation': 20})]
    prior, before = workflow.refine(before)
    assert prior['status'] == 'SUCCEEDED', prior
    slot = current(before)['snapshot']['pattern_slots'][1]
    prompt = '图案旋转到90度'
    wrong = wire(prompt, ['parameters'], [parameter(
        prompt, 'rotation', 90, mode='absolute', amount=90, direction='set')], targets=[slot])
    job, same, _ = submit_plan(workflow, before, prompt, wrong, target=slot)
    assert_unchanged(workflow, before, same, job)
    correct = wire(prompt, ['parameters'], [parameter(
        prompt, 'rotation', 70, mode='absolute', amount=90, direction='set')], targets=[slot])
    job, after, _ = submit_plan(workflow, before, prompt, correct, target=slot)
    assert job['status'] == 'SUCCEEDED', job
    snapshot = current(after)['snapshot']
    assert snapshot['slot_params'][slot]['rotation'] == 70
    assert {copy['rotation'] for copy in snapshot['object_transforms'] if copy['slot_id'] == slot} == {90}
    assert {copy['rotation'] for copy in snapshot['object_transforms'] if copy['slot_id'] != slot} == {20}


def test_selected_target_cannot_be_redirected_by_a_valid_but_wrong_owned_asset(workflow):
    before = workflow.generate()
    snapshot = current(before)['snapshot']
    target = snapshot['pattern_slots'][1]
    prompt = '给这个图案添加金色圆点'
    plan = wire(prompt, ['content'], [content(prompt, asset=snapshot['asset_refs'][0])], targets=[target])
    job, after, _ = submit_plan(workflow, before, prompt, plan, target=target)
    assert_unchanged(workflow, before, after, job)
    assert not workflow.provider.edit_calls


def test_original_asset_content_and_preservation_reach_editor_without_planner_style(workflow):
    before = workflow.generate()
    snapshot = current(before)['snapshot']
    slot, asset = snapshot['pattern_slots'][1], snapshot['asset_refs'][1]
    prompt = '给这个图案添加金色圆点，保留原有文字和配色'
    plan = wire(prompt, ['content', 'preserve'], [content(prompt, asset=asset)], targets=[slot, slot])
    seen = []

    def edit_image(text, source, output, kind):
        seen.append(dict(prompt=text, kind=kind, source=source.read_bytes()))
        with Image.open(source) as image:
            draw = ImageDraw.Draw(image)
            draw.rectangle((45, 35, 65, 55), fill='#f1c343')
            image.save(output, format='PNG')
        return dict(model='explicit-synthetic-image-edit', is_demo=True, usage={'generated_images': 1})

    workflow.provider.edit_image = edit_image
    key = str(uuid4())
    job, after, body = submit_plan(workflow, before, prompt, plan, target=slot, key=key)
    assert job['status'] == 'SUCCEEDED', job
    assert len(seen) == 1 and seen[0]['kind'] == 'asset'
    assert '给这个图案添加金色圆点' in seen[0]['prompt']
    assert '保留原有文字和配色' in seen[0]['prompt']
    assert 'Unrequested tiny pale' not in seen[0]['prompt']
    newer = current(after)['snapshot']
    assert newer['pattern_slots'] == snapshot['pattern_slots']
    assert newer['asset_refs'][0] == snapshot['asset_refs'][0]
    assert newer['asset_refs'][2] == snapshot['asset_refs'][2]
    assert newer['background_ref'] == snapshot['background_ref']
    assert newer['asset_refs'][1] != asset
    assert after['successful_refinement_count'] == 1
    assert workflow.download(current(before)) != workflow.download(current(after))
    duplicate = ok(recover_legacy_refinement(workflow.client, workflow.service, f'/api/designs/{before["id"]}/refinements', json=body))
    assert duplicate['id'] == job['id'] and duplicate['status'] == 'SUCCEEDED'
    assert len(seen) == 1
    assert workflow.get(after)['successful_refinement_count'] == 1


def test_image_copy_cannot_hide_behind_a_successful_parameter_change(workflow):
    before = workflow.generate()
    prompt = '图案缩小20%，底纹添加树叶装饰'
    plan = wire(prompt, ['parameters', 'content'], [
        parameter(prompt, 'scale', .8, mode='percent', amount=20, direction='decrease'),
        content(prompt, index=1),
    ], targets=['layout', 'background'])
    calls = []

    def copy_image(text, source, output, kind):
        calls.append(kind)
        output.write_bytes(source.read_bytes())
        return dict(model='explicit-synthetic-copy', is_demo=True,
                    request_id='synthetic-copy-with-geometry', usage={'generated_images': 1})

    workflow.provider.edit_image = copy_image
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)
    assert calls == ['background']
    with workflow.service.db.connect() as db:
        call = db.execute("SELECT * FROM provider_calls WHERE operation='edit_background'").fetchone()
    assert call['status'] == 'FAILED'
    assert call['request_id'] == 'synthetic-copy-with-geometry'
    assert json.loads(call['usage_json']) == {'generated_images': 1}


def test_one_source_cannot_claim_two_independent_targets_as_fully_executed(workflow):
    before = workflow.generate()
    prompt = '把图案缩小并给底纹添加树叶装饰'
    operation = parameter(prompt, 'scale', .8, mode='direction', amount=None, direction='decrease')
    operation['intents'][0]['amount'] = None
    plan = wire(prompt, ['parameters'], [operation, content(prompt)])
    job, after, _ = submit_plan(workflow, before, prompt, plan)
    assert_unchanged(workflow, before, after, job)
    assert not workflow.provider.edit_calls


@pytest.mark.parametrize('provider_name', ['deepseek_seedream', 'openai'])
def test_real_provider_local_selection_path_never_constructs_or_calls_a_model(workflow, monkeypatch, provider_name):
    before = workflow.generate()
    workflow.service.settings.provider = provider_name

    def no_provider(*args):
        pytest.fail('Applying selected configuration must not instantiate an AI provider')

    monkeypatch.setattr(workflow.service, 'provider_factory', no_provider)
    prompt = '应用所选配置'
    accepted = ok(workflow.submit_refine(before, prompt=prompt,
        selection={**workflow.selection, 'design_density': 'airy'}))
    assert accepted['provider'] == provider_name
    job = workflow.work(accepted)
    assert job['status'] == 'SUCCEEDED', job
    after = workflow.get(before)
    assert after['successful_refinement_count'] == 1
    snapshot = current(after)['snapshot']
    assert snapshot['design_density'] == 'airy'
    assert snapshot['edit_plan']['local_selection_only'] is True
    assert 'request_contract' not in snapshot['edit_plan']
    assert 'request_receipt' not in snapshot['edit_plan']
    with workflow.service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM provider_calls WHERE job_id=?', (job['id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('corruption', ['contract', 'receipt'])
def test_recovery_rechecks_request_binding_and_receipt_without_repeating_models(workflow, monkeypatch, corruption):
    before = workflow.generate()
    prompt = '图案缩小20%'
    plan = wire(prompt, ['parameters'], [parameter(
        prompt, 'scale', .8, mode='percent', amount=20, direction='decrease')])
    complete = workflow.service.complete_job
    monkeypatch.setattr(workflow.service, 'complete_job', defer_commit)
    submitted, same, _ = submit_plan(workflow, before, prompt, plan)
    assert submitted['status'] == 'RECONCILING', submitted
    assert same['current_version_id'] == before['current_version_id']
    with workflow.service.db.transaction() as db:
        saved = json.loads(db.execute('SELECT artifact_json FROM jobs WHERE id=?', (submitted['id'],)).fetchone()[0])
        record = saved['snapshot']['edit_plan']
        if corruption == 'contract':
            record['request_contract']['units'][0]['text'] = 'A forged source without the employee requirement'
        else:
            record['request_receipt']['requirements'][0]['execution'] = 'image_generated_unverified'
        db.execute('UPDATE jobs SET artifact_json=? WHERE id=?', (json.dumps(saved), submitted['id']))
    monkeypatch.setattr(workflow.service, 'complete_job', complete)
    monkeypatch.setattr(workflow.provider, 'plan', lambda *args: pytest.fail('Recovery must not rerun the planner'))
    monkeypatch.setattr(workflow.provider, 'edit_image', lambda *args: pytest.fail('Recovery must not submit an image'))
    failed = workflow.work(submitted)
    after = workflow.get(before)
    assert_unchanged(workflow, before, after, failed)
    with workflow.service.db.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM quota_events WHERE design_id=?', (before['id'],)).fetchone()[0] == 0
