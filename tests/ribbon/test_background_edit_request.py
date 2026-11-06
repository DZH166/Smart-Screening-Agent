"""Text/user_request protection only: no real image service or semantic approval."""
import copy

import pytest

from ribbon_backend.background_edit import background_edit_request
from ribbon_backend.providers import ClarificationNeeded


BACKGROUND = dict(target_kind='background', target_id='background')
LAYOUT = {}


def image_edit(prompt='规划器缩写'):
    return dict(type='edit_background', prompt=prompt)


@pytest.mark.parametrize('target', ['background', 'zone:left', 'zone:top'])
def test_explicit_background_preserves_original_words_and_does_not_mutate(target):
    prompt = '请帮我的底纹背景铺满星星装饰，四个角也要有；不要新增人物。'
    operations = [image_edit()]
    original = copy.deepcopy(operations)
    result, meta = background_edit_request(prompt, dict(target_kind='background', target_id=target), operations)
    assert result[0]['prompt'] == prompt
    assert operations == original and result is not operations
    assert meta == dict(protocol='background-request-v1', scope='selected_background_original_request',
                        target=target, explicit_content_request=True, semantic_verified=False)


@pytest.mark.parametrize('user_request', [
    '底纹背景铺满星星装饰', '背景布满几何装饰', '底图遍布抽象纹样',
    '给背景添加花纹', '删除底纹里的装饰', '背景把旧纹样替换为新的图形',
    '把底图换成另一种纹样', '底纹图案间隔拉开一点', '背景图案密度降低',
])
@pytest.mark.parametrize('operations', [[], [{'type': 'parameters', 'values': {'scale': .8}}],
                                         [{'type': 'parameters', 'values': {'background_color': '#446677'}}]])
def test_explicit_content_cannot_be_satisfied_by_only_parameters(user_request, operations):
    with pytest.raises(ClarificationNeeded, match='底纹内容'):
        background_edit_request(user_request, LAYOUT, operations)


@pytest.mark.parametrize('user_request', [
    '背景改成浅蓝色', '背景换成 #ABCDEF', '背景改成柔和的暗红色', '保持底纹不变，把图案缩小',
    '不要给背景添加装饰，只把背景改成蓝色', '背景不要铺满装饰，背景改成红色',
    '不要删除底纹图案', '底纹图案间隔保持不变',
])
def test_negative_preservation_and_colour_only_do_not_force_image_edit(user_request):
    operations = [{'type': 'parameters', 'values': {'background_color': '#ABCDEF'}}]
    result, meta = background_edit_request(user_request, LAYOUT, operations)
    assert result == operations
    assert meta['explicit_content_request'] is False


def test_layout_mixed_scopes_send_only_explicit_background_clauses():
    operations = [dict(type='parameters', values={'scale': .8}),
                  dict(type='edit_asset', asset_id='one', prompt='人物添加小装饰'), image_edit()]
    result, meta = background_edit_request('人物缩小一点，给人物添加小装饰，底纹铺满几何纹样，背景保持原配色', LAYOUT, operations)
    assert result[:2] == operations[:2]
    assert result[2]['prompt'] == '底纹铺满几何纹样；背景保持原配色'
    assert '人物' not in result[2]['prompt']
    assert meta['scope'] == 'explicit_background_clauses'


@pytest.mark.parametrize('user_request', ['人物加装饰同时背景铺满纹样'])
def test_ambiguous_scopes_are_not_guessed(user_request):
    with pytest.raises(ClarificationNeeded):
        background_edit_request(user_request, LAYOUT, [image_edit()])


@pytest.mark.parametrize('kind', ['pattern', 'border'])
def test_explicit_background_content_conflicts_with_selected_foreground(kind):
    with pytest.raises(ClarificationNeeded, match='当前选择的是图案或边饰'):
        background_edit_request('底纹铺满图形装饰', dict(target_kind=kind, target_id='pattern-one'),
                                [dict(type='edit_asset', asset_id='one', prompt='添加装饰')])


def test_preserving_background_does_not_conflict_with_pattern_target():
    operations = [dict(type='edit_asset', asset_id='one', prompt='人物添加小装饰')]
    result, meta = background_edit_request('给人物添加小装饰，背景保持不变', dict(target_kind='pattern'), operations)
    assert result == operations and not meta['explicit_content_request']


def test_selected_background_does_not_accept_positive_foreground_content_request():
    with pytest.raises(ClarificationNeeded, match='人物或图案'):
        background_edit_request('人物添加图形装饰，底纹保持不变', BACKGROUND, [image_edit()])


@pytest.mark.parametrize('user_request', ['删除底纹上的装饰', '将背景旧装饰替换成花纹', '背景不要添加新内容，只删除旧纹样'])
def test_removal_and_replacement_are_not_rewritten_as_addition(user_request):
    result, _ = background_edit_request(user_request, BACKGROUND, [image_edit('添加装饰')])
    assert result[0]['prompt'] == user_request


def test_long_valid_original_is_not_concatenated_with_planner_prompt_or_truncated():
    user_request = '底纹铺满装饰。' + '保持原有配色。' * 500
    assert len(user_request) < 4000
    result, _ = background_edit_request(user_request, BACKGROUND, [image_edit('规划器输出' * 700)])
    assert result[0]['prompt'] == user_request
    assert len(result[0]['prompt']) <= 4000


@pytest.mark.parametrize('user_request', ['', ' ', None, '底纹' + 'x' * 4000])
def test_invalid_request_is_rejected_before_dispatch(user_request):
    with pytest.raises(ClarificationNeeded):
        background_edit_request(user_request, BACKGROUND, [image_edit()])


def test_module_does_not_invent_image_operations():
    result, meta = background_edit_request('图案缩小一点', LAYOUT, [{'type': 'parameters', 'values': {'scale': .8}}])
    assert result == [{'type': 'parameters', 'values': {'scale': .8}}]
    assert meta['scope'] == 'not_applied' and not meta['semantic_verified']


@pytest.mark.parametrize('user_request', ['背景改成蓝色装饰', '背景换成图形和蓝色', '底纹换成有装饰的红色'])
def test_colour_word_inside_content_description_is_not_pure_colour(user_request):
    with pytest.raises(ClarificationNeeded, match='底纹内容'):
        background_edit_request(user_request, LAYOUT, [{'type': 'parameters', 'values': {'background_color': '#ABCDEF'}}])


def test_unscoped_contrastive_continuation_leaves_controlled_plan_unchanged():
    operations = [image_edit('只在底纹添加小装饰')]
    result, meta = background_edit_request('背景不要删除原有花纹，但增加一些装饰', LAYOUT, operations)
    assert result == operations and meta['scope'] == 'not_applied'


def test_nonrelated_content_is_not_mistaken_for_negated_removal():
    with pytest.raises(ClarificationNeeded, match='底纹内容'):
        background_edit_request('把底纹中不相关的部分删除', LAYOUT, [])


def test_selected_background_rejects_foreground_geometry_request_too():
    with pytest.raises(ClarificationNeeded, match='人物或图案'):
        background_edit_request('人物缩小一点，底纹铺满装饰', BACKGROUND, [image_edit()])


def test_selected_background_can_preserve_foreground_without_editing_it():
    user_request = '人物保持不变，底纹铺满装饰'
    result, _ = background_edit_request(user_request, BACKGROUND, [image_edit()])
    assert result[0]['prompt'] == user_request


@pytest.mark.parametrize('user_request', [
    'Add stars all over the background', 'Give the background a floral pattern',
    'Fill the background with stars, do not resize the motifs', '多加一点装饰',
    '换一种温柔的感觉',
])
def test_unrecognized_language_or_unscoped_request_does_not_create_new_mandatory_rules(user_request):
    operations = [image_edit('受控规划器给出的背景要求')]
    result, meta = background_edit_request(user_request, LAYOUT, operations)
    assert result == operations
    assert meta['scope'] == 'not_applied'
    assert not meta['explicit_content_request']


@pytest.mark.parametrize('user_request', [
    '背景改成天蓝色', '底纹换成奶油色', '背景改成暖白色', '背景更换成藏蓝色',
    '背景改成浅灰蓝色', '背景改成蓝色就可以', '将底图改为一种没有名字的颜色',
])
def test_unknown_and_compound_colours_leave_existing_controlled_plan(user_request):
    operations = [dict(type='parameters', values={'background_color': '#ABCDEF'})]
    result, meta = background_edit_request(user_request, LAYOUT, operations)
    assert result == operations and not meta['explicit_content_request']


@pytest.mark.parametrize('extra', [
    dict(type='parameters', values={'scale': .8}),
    dict(type='parameters', values={'spacing': 1.2}),
    dict(type='parameters', values={'rotation': 5}),
    dict(type='parameters', values={'offset_x': 10}),
    dict(type='edit_asset', asset_id='one', prompt='人物添加装饰'),
    dict(type='edit_composite', prompt='重画整个图'),
])
@pytest.mark.parametrize('user_request', [
    '背景铺满星星，不要改图案大小', '底纹铺满几何装饰，不改变人物', '背景添加花纹',
])
def test_high_confidence_background_only_does_not_authorize_extra_foreground_operations(user_request, extra):
    with pytest.raises(ClarificationNeeded, match='要求只修改底纹'):
        background_edit_request(user_request, LAYOUT, [image_edit(), extra])


@pytest.mark.parametrize('user_request', [
    '把背景里的花纹缩小', '背景星星变小一点', '背景图案缩小一点', '底图里面的图案间隔拉开',
])
def test_texture_geometry_is_not_satisfied_by_foreground_geometry(user_request):
    with pytest.raises(ClarificationNeeded, match='底纹内容'):
        background_edit_request(user_request, LAYOUT, [dict(type='parameters', values={'scale': .8})])


def test_background_with_foreground_preservation_keeps_original_without_clarification():
    user_request = '底纹铺满星星，不改变人物'
    result, meta = background_edit_request(user_request, LAYOUT, [image_edit()])
    assert result[0]['prompt'] == user_request
    assert meta['explicit_content_request']


@pytest.mark.parametrize('user_request', [
    '底纹铺满装饰，不要改图案并把人物缩小',
    '底纹铺满装饰，不要将人物缩小以及把图案旋转',
    '底纹铺满装饰，人物大小保持不变',
    '底纹铺满装饰，不缩小人物',
])
def test_negation_and_preservation_never_authorize_foreground_geometry(user_request):
    with pytest.raises(ClarificationNeeded, match='要求只修改底纹'):
        background_edit_request(user_request, LAYOUT, [image_edit(), dict(type='parameters', values={'scale': .8})])


def test_explicit_positive_foreground_geometry_in_mixed_request_is_allowed():
    user_request = '图案缩小一点，底纹铺满装饰，不修改图案的内部内容'
    operations = [image_edit(), dict(type='parameters', values={'scale': .8})]
    result, _ = background_edit_request(user_request, LAYOUT, operations)
    assert result[1] == operations[1]
    assert result[0]['prompt'] == '底纹铺满装饰'


def test_negation_is_not_limited_to_a_short_character_window():
    user_request = '底纹铺满装饰，不要把我上传的所有这些人物图案和完整设计尤其是这里这个小朋友放大'
    with pytest.raises(ClarificationNeeded, match='要求只修改底纹'):
        background_edit_request(user_request, LAYOUT, [image_edit(), dict(type='parameters', values={'scale': 1.2})])


def test_background_only_keeps_an_unscoped_followup_in_original_request():
    user_request = '底纹铺满装饰，四个角也要有，不改变人物'
    result, _ = background_edit_request(user_request, LAYOUT, [image_edit()])
    assert result[0]['prompt'] == user_request


@pytest.mark.parametrize('user_request', ['背景换成奶油色', '背景更换为暖白色', '背景改成天蓝色就可以'])
def test_unknown_colour_does_not_rewrite_a_controlled_image_plan_either(user_request):
    operations = [image_edit('规划器的底色要求')]
    result, meta = background_edit_request(user_request, LAYOUT, operations)
    assert result == operations and meta['scope'] == 'not_applied'


def test_new_content_is_still_content_without_recognizing_its_shape():
    with pytest.raises(ClarificationNeeded, match='底纹内容'):
        background_edit_request('背景新增一些抽象设计', LAYOUT, [])


def test_foreground_colour_change_conflicts_with_selected_background():
    with pytest.raises(ClarificationNeeded, match='人物或图案'):
        background_edit_request('人物改成红色，底纹铺满星星', BACKGROUND, [image_edit()])


def test_foreground_colour_change_is_real_content_in_mixed_layout_request():
    operations = [dict(type='edit_asset', asset_id='one', prompt='人物改成红色'), image_edit()]
    result, _ = background_edit_request('人物改成红色，底纹铺满星星', LAYOUT, operations)
    assert result[0] == operations[0]
    assert result[1]['prompt'] == '底纹铺满星星'
