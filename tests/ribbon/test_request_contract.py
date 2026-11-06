"""Original-source and parameter arithmetic checks, not model image quality."""
from copy import deepcopy
import hashlib

import pytest

from ribbon_backend.providers import ClarificationNeeded, _normalise_plan, _safe_plan_input
from ribbon_backend.request_contract import PROTOCOL, public_request_receipt, request_targets, source_units, validate_request_plan


def view(**changes):
    return dict(output_profile={'width': 1024, 'height': 512}, template_mode='grid',
                layout_engine='seamless-unit-v2', asset_refs=['a', 'b'], pattern_slots=['p1', 'p2'],
                background_ref='bg', params={'scale': 1., 'spacing': 1., 'rotation': 0., 'offset_x': 0., 'offset_y': 0., 'background_color': None}, **changes)


def wire(prompt, effects, operations, targets=None):
    units = source_units(prompt)
    return dict(summary='受控测试计划', clarification=None,
                requirements=[dict(source_id=unit['id'], target_id=target, effect=effect)
                              for unit, target, effect in zip(units, targets or ['layout'] * len(units), effects)],
                operations=operations)


def parameter(key, value, evidence, *, mode='absolute', amount=None, direction='set', sources=None):
    return dict(type='parameters', values={key: value}, source_ids=sources or ['s1'],
                intents=[dict(key=key, mode=mode, amount=value if amount is None and mode != 'direction' else amount,
                              direction=direction, evidence=evidence)])


def content(kind='edit_background', *, sources=None, asset=None):
    result = dict(type=kind, source_ids=sources or ['s1'], prompt='规划器凭空添加的极小极淡蓝色风格')
    if asset:
        result['asset_id'] = asset
    return result


@pytest.mark.parametrize('prompt', [
    '  图案缩小20%，底纹添加叶片。  ', '把文字改成“你好，朋友！”，保留配色。',
    'Replace text with "Love, joy!"; keep colors.', '把文字改成（A，B；C），其余不变',
    "Don't resize it, keep the emoji 👨‍👩‍👧‍👦 unchanged.", '背景添加🌟，\n不要改人物；谢谢。',
    '把文字改成“未结束，后面也不能丢', '比例设为0.8，间距设为1.2',
])
def test_source_units_preserve_every_original_codepoint(prompt):
    units = source_units(prompt)
    assert ''.join(unit['text'] for unit in units) == prompt
    cursor = 0
    for index, unit in enumerate(units):
        assert unit['id'] == f's{index + 1}' and unit['start'] == cursor
        assert prompt[unit['start']:unit['end']] == unit['text']
        cursor = unit['end']
    assert cursor == len(prompt)


def test_quotes_and_brackets_are_not_split_into_partial_replacement_words():
    assert [unit['text'] for unit in source_units('文字改成“你好，朋友！”，背景不变。')] == ['文字改成“你好，朋友！”，', '背景不变。']
    assert len(source_units('文字改成[A,B;C]')) == 1


@pytest.mark.parametrize('current,prompt,mode,amount,direction,value', [
    (1.4, '图案缩小20%', 'percent', 20, 'decrease', 1.12),
    (1.4, '图案放大20%', 'percent', 20, 'increase', 1.68),
    (1.4, '图案缩小到20%', 'percent', 20, 'set', .28),
    (1.4, '缩放比例设为20%', 'absolute_percent', 20, 'set', .2),
    (1.4, '缩放比例设为0.8', 'absolute', .8, 'set', .8),
    (1.4, '图案缩小到0.8倍', 'factor', .8, 'decrease', 1.12),
    (1.4, '图案缩小一点', 'direction', None, 'decrease', 1.2),
])
def test_parameter_math_uses_current_frame_without_rewriting_values(current, prompt, mode, amount, direction, value):
    snapshot = view()
    snapshot['params']['scale'] = current
    op = parameter('scale', value, prompt, mode=mode, amount=amount, direction=direction)
    original = deepcopy(op)
    result = validate_request_plan(prompt, snapshot, wire(prompt, ['parameters'], [op]), 'test')
    assert result['operations'][0] == original
    assert result['request_contract']['coverage'] == 'checked'
    assert result['request_contract']['semantic_verified'] is False


@pytest.mark.parametrize('prompt,key,current,mode,amount,direction,value', [
    ('图案缩小20%', 'scale', 1., 'percent', 20, 'set', .2),
    ('图案放大到120%', 'scale', 1., 'percent', 120, 'increase', 2.2),
    ('向右移动20px', 'offset_x', 10., 'absolute', 20, 'increase', 20.),
    ('旋转15度', 'rotation', 10., 'absolute', 15, 'increase', 15.),
    ('旋转到15度', 'rotation', 10., 'delta', 15, 'increase', 25.),
    ('图案缩小20%', 'scale', 1., 'percent', 20, 'increase', 1.2),
    ('图案缩小20%', 'scale', 1., 'direction', None, 'decrease', .8),
    ('图案缩小20%', 'rotation', 0., 'absolute', 20, 'set', 20.),
])
def test_model_cannot_choose_a_different_numeric_interpretation(prompt, key, current, mode, amount, direction, value):
    snapshot = view()
    snapshot['params'][key] = current
    op = parameter(key, value, prompt, mode=mode, amount=amount, direction=direction)
    with pytest.raises(ClarificationNeeded):
        validate_request_plan(prompt, snapshot, wire(prompt, ['parameters'], [op]), 'test')


def test_explicit_movement_is_a_delta_and_target_rotation_uses_global_frame():
    prompt = '向右移动20px'
    snapshot = view()
    snapshot['params']['offset_x'] = 10
    op = parameter('offset_x', 30, prompt, mode='delta', amount=20, direction='increase')
    validate_request_plan(prompt, snapshot, wire(prompt, ['parameters'], [op]), 'test')
    prompt = '旋转到90度'
    snapshot.update(target_kind='pattern', target_id='p1', asset_refs=['a'], layout_params={'rotation': 30})
    op = parameter('rotation', 60, prompt, mode='absolute', amount=90)
    result = validate_request_plan(prompt, snapshot, wire(prompt, ['parameters'], [op], ['p1']), 'test')
    assert result['operations'][0]['values']['rotation'] == 60


@pytest.mark.parametrize('evidence', ['20', '20%', '图案缩小10%'])
def test_isolated_number_or_invented_quote_is_not_parameter_authorization(evidence):
    prompt = '图案缩小20%'
    op = parameter('scale', .8, evidence, mode='percent', amount=20, direction='decrease')
    with pytest.raises(ClarificationNeeded):
        validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [op]), 'test')


@pytest.mark.parametrize('change', ['drop_requirement', 'duplicate_requirement', 'drop_operation', 'unknown_source', 'unknown_target', 'preserve_as_action', 'clarify'])
def test_every_requirement_and_operation_needs_both_valid_bindings(change):
    prompt = '图案缩小20%，底纹添加叶片'
    plan = wire(prompt, ['parameters', 'content'], [parameter('scale', .8, '图案缩小20%', mode='percent', amount=20, direction='decrease'), content(sources=['s2'])], ['layout', 'background'])
    if change == 'drop_requirement': plan['requirements'].pop()
    elif change == 'duplicate_requirement': plan['requirements'][1] = deepcopy(plan['requirements'][0])
    elif change == 'drop_operation': plan['operations'].pop()
    elif change == 'unknown_source': plan['operations'][0]['source_ids'] = ['invented']
    elif change == 'unknown_target': plan['requirements'][0]['target_id'] = 'other-employee-pattern'
    elif change == 'preserve_as_action': plan['requirements'][1]['effect'] = 'preserve'
    else: plan['requirements'][1]['effect'] = 'clarify'
    with pytest.raises(ClarificationNeeded):
        validate_request_plan(prompt, view(), plan, 'test')


def test_one_parameter_cannot_be_repeated_to_claim_intermediate_steps():
    prompt = '图案缩小20%，图案再放大20%'
    plan = wire(prompt, ['parameters', 'parameters'], [
        parameter('scale', .8, '图案缩小20%', mode='percent', amount=20, direction='decrease'),
        parameter('scale', .96, '图案再放大20%', mode='percent', amount=20, direction='increase', sources=['s2'])])
    with pytest.raises(ClarificationNeeded, match='反复修改'):
        validate_request_plan(prompt, view(), plan, 'test')


def test_negative_source_cannot_be_cherry_picked_into_positive_evidence():
    prompt = '不要放大图案'
    op = parameter('scale', 1.2, '放大图案', mode='direction', direction='increase')
    with pytest.raises(ClarificationNeeded, match='否定'):
        validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [op]), 'test')


@pytest.mark.parametrize('kind,target,asset', [('pattern', 'p1', 'a'), ('border', 'border', 'strip'), ('background', 'zone:left', 'left-bg')])
def test_selected_target_preserves_original_content_and_all_constraints(kind, target, asset):
    prompt = '添加深色几何装饰，保留文字和配色'
    snapshot = view()
    snapshot.update(target_kind=kind, target_id=target, asset_refs=[asset])
    if kind == 'background': snapshot['background_ref'] = asset
    op = content('edit_background' if kind == 'background' else 'edit_asset', asset=None if kind == 'background' else asset)
    result = validate_request_plan(prompt, snapshot, wire(prompt, ['content', 'preserve'], [op], [target, target]), 'test')
    assert result['operations'][0]['prompt'] == prompt
    assert '极小极淡' not in result['operations'][0]['prompt']


def test_mixed_targets_never_receive_other_targets_modify_source():
    prompt = '给图案添加红色装饰，底纹添加叶片，保持原有文字'
    operations = [content('edit_asset', asset='a'), content(sources=['s2'])]
    result = validate_request_plan(prompt, view(), wire(prompt, ['content', 'content', 'preserve'], operations, ['p1', 'background', 'layout']), 'test')
    assert result['operations'][0]['prompt'] == '给图案添加红色装饰，保持原有文字'
    assert result['operations'][1]['prompt'] == '底纹添加叶片，保持原有文字'


def test_colour_uses_hex_channel_without_a_colour_name_dictionary():
    prompt = '底色设成奶油色'
    op = parameter('background_color', '#EEE4C5', prompt, amount=None)
    op['intents'][0]['amount'] = None
    result = validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [op], ['background']), 'test')
    assert result['operations'][0]['values']['background_color'] == '#EEE4C5'
    prompt = '底色设为#ABCDEF'
    op['intents'][0]['evidence'] = prompt
    with pytest.raises(ClarificationNeeded, match='颜色值不一致'):
        validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [op], ['background']), 'test')


def test_normalized_metadata_does_not_bypass_second_validation():
    prompt = '图案缩小20%'
    op = parameter('scale', .8, prompt, mode='percent', amount=20, direction='decrease')
    result = validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [op]), 'test')
    result.update(model='actual-model', request_id='request-1', usage={'total_tokens': 12})
    result['request_contract']['source_sha256'] = 'forged'
    checked = validate_request_plan(prompt, view(), result, 'test')
    assert checked['request_contract']['source_sha256'] == hashlib.sha256(prompt.encode()).hexdigest()
    assert checked['request_id'] == 'request-1'
    result['operations'][0]['values']['scale'] = .7
    with pytest.raises(ClarificationNeeded):
        validate_request_plan(prompt, view(), result, 'test')


def test_receipt_has_codepoint_spans_no_private_text_and_honest_effect_status():
    prompt = '底纹添加🌟，保留文字'
    result = validate_request_plan(prompt, view(), wire(prompt, ['content', 'preserve'], [content()], ['background', 'layout']), 'test')
    receipt = public_request_receipt(result)
    assert receipt['protocol'] == PROTOCOL and receipt['coverage'] == 'checked'
    assert receipt['image_effect_verified'] is False
    assert receipt['requirements'][0]['execution'] == 'image_generated_unverified'
    assert receipt['requirements'][1]['execution'] == 'constraint_forwarded'
    assert '底纹' not in str(receipt) and '原文' not in str(receipt)
    row = receipt['requirements'][0]
    assert prompt[row['start']:row['end']] == '底纹添加🌟，'


def test_legacy_plan_parsing_is_explicit_not_a_real_provider_fallback():
    legacy = dict(summary='legacy', clarification=None, operations=[dict(type='parameters', values={'scale': .8})])
    assert _normalise_plan(legacy, 'test', view())['operations'][0]['values']['scale'] == .8
    with pytest.raises(ClarificationNeeded):
        _normalise_plan(legacy, 'test', view(), original_request='图案缩小20%')
    safe = _safe_plan_input('图案缩小20%', view(), [], provider='test')
    assert safe['source_units'][0]['text'] == '图案缩小20%'
    assert set(safe['request_targets']) == {'layout', 'background', 'p1', 'p2'}


def test_old_assets_have_stable_aliases_and_unselected_zones_do_not_gain_capability():
    snapshot = view()
    snapshot.pop('pattern_slots')
    snapshot['zone_background_refs'] = {'left': 'zone-a'}
    targets = request_targets(snapshot)
    assert targets['asset:a']['asset_id'] == 'a'
    assert targets['zone:left']['preserve_only'] is True


def test_content_source_can_mix_positive_edit_with_negative_constraints():
    prompt = '衣服改蓝但不要添加装饰'
    result = validate_request_plan(prompt, view(), wire(prompt, ['content'], [content('edit_asset', asset='a')], ['p1']), 'test')
    assert result['operations'][0]['prompt'] == prompt


def test_parameter_source_can_preserve_a_different_parameter():
    prompt = '图案缩小20%但不要旋转'
    op = parameter('scale', .8, prompt, mode='percent', amount=20, direction='decrease')
    validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [op]), 'test')
    bad = parameter('rotation', 20, prompt, mode='absolute', amount=20)
    with pytest.raises(ClarificationNeeded):
        validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [bad]), 'test')


def test_preservation_cannot_hide_same_source_positive_content():
    prompt = '底纹铺满装饰并保留底色，图案缩小20%'
    op = parameter('scale', .8, '图案缩小20%', mode='percent', amount=20, direction='decrease', sources=['s2'])
    with pytest.raises(ClarificationNeeded, match='明确修改动作'):
        validate_request_plan(prompt, view(), wire(prompt, ['preserve', 'parameters'], [op], ['background', 'layout']), 'test')


@pytest.mark.parametrize('unit', ['厘米', '毫米', '英寸', 'cm', 'mm', 'inch', '%'])
def test_movement_does_not_treat_non_pixel_units_as_pixels(unit):
    prompt = f'向右移动1{unit}'
    op = parameter('offset_x', 1, prompt, mode='delta', amount=1, direction='increase')
    with pytest.raises(ClarificationNeeded, match='只支持像素'):
        validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [op]), 'test')


def test_quoted_replacement_text_is_not_a_negation_command():
    prompt = '把文字改成“不要放大”'
    result = validate_request_plan(prompt, view(), wire(prompt, ['content'], [content('edit_asset', asset='a')], ['p1']), 'test')
    assert result['operations'][0]['prompt'] == prompt


def test_quoted_percentage_does_not_authorize_a_parameter():
    prompt = '把文字改成“缩小20%”'
    op = parameter('scale', .8, prompt, mode='percent', amount=20, direction='decrease')
    with pytest.raises(ClarificationNeeded):
        validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [op]), 'test')


def test_source_cannot_be_consumed_by_two_operations():
    prompt = '图案缩小20%'
    first = parameter('scale', .8, prompt, mode='percent', amount=20, direction='decrease')
    second = parameter('rotation', 20, prompt, amount=20)
    with pytest.raises(ClarificationNeeded, match='多个操作重复执行'):
        validate_request_plan(prompt, view(), wire(prompt, ['parameters'], [first, second]), 'test')
