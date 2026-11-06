from copy import deepcopy

import pytest

from ribbon_backend.loop_layout_v2 import resolve
from ribbon_backend.providers import ClarificationNeeded
from ribbon_backend.request_geometry import validate_request_geometry
from ribbon_backend.request_geometry import validate_request_image_policy
from ribbon_backend.ribbon_targets import apply_values
from test_loop_workflow import current, workflow


def moved(before, target, values):
    after = deepcopy(before)
    apply_values(after, target, values)
    return resolve(after, specs=before['loop_layout']['specs'])


def operation(key, value, *, mode='direction', amount=None, direction='increase'):
    return {'type': 'parameters', 'values': {key: value},
            'intents': [{'key': key, 'mode': mode, 'amount': amount, 'direction': direction,
                         'evidence': 'Explicit synthetic request'}]}


def test_measured_scale_ratio_and_translation(workflow):
    before = current(workflow.generate())['snapshot']
    after = moved(before, 'layout', {'scale': .8})
    validate_request_geometry(before, after, operation('scale', .8, mode='percent', amount=20,
                                                      direction='decrease'), 'layout')
    after = moved(before, 'layout', {'offset_x': 10})
    validate_request_geometry(before, after, operation('offset_x', 10, mode='delta', amount=10), 'layout')


def test_numeric_scale_cannot_hide_clamping(workflow):
    before = current(workflow.generate())['snapshot']
    before = moved(before, 'layout', {'scale': 2.4})
    after = moved(before, 'layout', {'scale': 2.5})
    with pytest.raises(ClarificationNeeded):
        validate_request_geometry(before, after, operation('scale', 2.5), 'layout')


@pytest.mark.parametrize('mode', ['grid', 'scatter'])
def test_absolute_pattern_orientation_accounts_for_global_and_intrinsic_angles(workflow, mode):
    before = current(workflow.generate({**workflow.selection, 'template_id': mode}))['snapshot']
    before = moved(before, 'layout', {'rotation': 20})
    slot = before['pattern_slots'][0]
    after = moved(before, slot, {'rotation': 70})
    call = lambda: validate_request_geometry(before, after,
        operation('rotation', 70, mode='absolute', amount=90, direction='set'), slot)
    if mode == 'grid':
        call()
    else:
        with pytest.raises(ClarificationNeeded):
            call()


@pytest.mark.parametrize('mode', ['split', 'panels', 'stacked'])
def test_partition_global_shift_cannot_reassign_background_or_pattern(workflow, mode):
    before = current(workflow.generate({**workflow.selection, 'template_id': mode}))['snapshot']
    after = moved(before, 'layout', {'offset_x': 10})
    with pytest.raises(ClarificationNeeded, match='分区排法'):
        validate_request_geometry(before, after, operation('offset_x', 10, mode='delta', amount=10), 'layout')


@pytest.mark.parametrize('text,alpha', [('把背景改成透明', False), ('去掉背景', False),
                                      ('把背景变成不透明', True)])
def test_incompatible_alpha_conversion_fails_before_image_request(text, alpha):
    with pytest.raises(ClarificationNeeded, match='透明状态'):
        validate_request_image_policy(text, {'transparent': alpha})


@pytest.mark.parametrize('text', ['不要去掉背景', '把文字改成“去掉背景”',
                                '把文字改成“透明背景”', '保留配色，添加月亮'])
def test_literal_text_and_preservation_are_not_alpha_conversion_requests(text):
    validate_request_image_policy(text, {'transparent': False})


@pytest.mark.parametrize('image_first', [False, True])
def test_full_plan_rejects_a_later_colour_hiding_the_paid_image(workflow, image_first):
    from test_request_contract_workflow import wire, content, submit_plan, assert_unchanged
    from ribbon_backend.request_contract import source_units
    before = workflow.generate()
    prompt = '背景改为#224488，底纹添加树叶装饰'
    unit = source_units(prompt)[0]
    colour = dict(type='parameters', source_ids=[unit['id']], values={'background_color': '#224488'},
                  intents=[dict(key='background_color', mode='absolute', amount=None,
                                direction='set', evidence=unit['text'])])
    image = content(prompt, index=1)
    operations = [image, colour] if image_first else [colour, image]
    plan = wire(prompt, ['parameters', 'content'], operations, targets=['background', 'background'])
    workflow.provider.edit_size = (320, 320)
    job, after, _ = submit_plan(workflow, before, prompt, plan, target='background')
    if image_first:
        assert_unchanged(workflow, before, after, job)
        assert not workflow.provider.edit_calls
        assert '盖住' in job['error']
    else:
        assert job['status'] == 'SUCCEEDED', job
        assert len(workflow.provider.edit_calls) == 1
        assert current(after)['snapshot']['params']['background_color'] is None
