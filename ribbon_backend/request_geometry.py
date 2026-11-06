"""Verify measurable request effects, separate from generated-image semantics."""
from __future__ import annotations

import math
import re

from .providers import ClarificationNeeded


def validate_request_image_policy(prompt, prepared):
    """Do not send a known-incompatible alpha instruction to a fixed payload.

    Current editors retain input alpha policy; this does not add background
    removal or claim general detection of every possible transparency request.
    Quoted replacement words are data, not alpha instructions.
    """
    if type(prepared.get('transparent')) is not bool:
        return
    from .request_contract import source_units, _mask_literals, _NEGATION
    to_clear = re.compile(r'(?:改成|变成|变为|设为|转换为).{0,8}透明|(?:去掉|去除|移除).{0,6}背景|remove\s+(?:the\s+)?background|make.{0,15}transparent', re.I)
    to_solid = re.compile(r'(?:改成|变成|变为|设为|转换为).{0,8}不透明|make.{0,15}opaque', re.I)
    for unit in source_units(prompt):
        text = _mask_literals(unit['text'])
        pattern = to_solid if prepared['transparent'] else to_clear
        if any(not _NEGATION.search(text[:match.start()]) for match in pattern.finditer(text)):
            raise ClarificationNeeded('当前精修会保留原图的透明状态，不能完成这次透明背景转换；未调用图片模型、未扣精修次数。')


def _reject():
    raise ClarificationNeeded('当前排版限制使实际大小、间距或方向不能满足这项要求，未保存、未扣精修次数；请调整幅度或排法。')


def validate_request_geometry(before, after, operation, target):
    """Run before paid images and again on the final resolved composition.

    Numeric parameter equality alone cannot prove a requested change survived
    fitting/clamping. Compare complete v2 placements too. Old engines retain
    their own behavior and receive an explicitly unverified receipt instead.
    V3 may repack whole groups after a numeric edit; it retains numeric/source
    validation and an unverified physical-effect receipt until its own exact
    displacement/ratio contract is independently established.
    """
    if before.get('layout_engine') != 'seamless-unit-v2':
        return
    from .loop_layout_v2 import plan

    if (target == 'layout' and before['template_mode'] in ('split', 'panels', 'stacked')
            and 'offset_x' in operation['values']):
        raise ClarificationNeeded('分区排法暂不支持整幅横移，以免改变底纹和图案归属；请选择单个图案调整。')
    left, right = plan(before), plan(after)
    if target in before.get('pattern_slots', []):
        left = [p for p in left if p['slot_id'] == target]
        right = [p for p in right if p['slot_id'] == target]
        old_params = before.get('slot_params', {}).get(target, {})
        new_params = after.get('slot_params', {}).get(target, {})
    else:
        old_params, new_params = before['params'], after['params']
    intents = [item for item in operation.get('intents', []) if item['key'] in operation['values']]
    if not intents:
        return
    if len(left) != len(right) or any(a['slot_id'] != b['slot_id'] for a, b in zip(left, right)):
        _reject()
    for item in intents:
        key, mode = item['key'], item['mode']
        if key == 'background_color':
            continue
        if not left:
            _reject()
        direction = item['direction']
        old_value = float(old_params.get(key, 1. if key in ('scale', 'spacing') else 0.))
        new_value = float(new_params.get(key, 1. if key in ('scale', 'spacing') else 0.))
        if key == 'scale':
            factor = new_value / old_value
            for a, b in zip(left, right):
                for size in ('target_width', 'target_height'):
                    # A rasterized boundary may round by a pixel; no visual
                    # similarity/semantic score is used as proof of geometry.
                    if not math.isclose(b[size], a[size] * factor, abs_tol=1.5, rel_tol=.01):
                        _reject()
        elif key == 'spacing':
            a = before['loop_layout']['metrics']['mean_gap_px']
            b = after['loop_layout']['metrics']['mean_gap_px']
            if not math.isclose(b, a * new_value / old_value, abs_tol=1.5, rel_tol=.01):
                _reject()
        elif key == 'rotation':
            for a, b in zip(left, right):
                expected = (float(item['amount']) if mode == 'absolute'
                            else a['rotation'] + new_value - old_value)
                if abs((b['rotation'] - expected + 180) % 360 - 180) > .5:
                    _reject()
        elif key in ('offset_x', 'offset_y'):
            coordinate = key[-1]
            expected = new_value - old_value
            for a, b in zip(left, right):
                difference = b[coordinate] - a[coordinate]
                if coordinate == 'x' and before['output_profile']['width'] == after['output_profile']['width']:
                    width = before['output_profile']['width']
                    difference = (difference - expected + width / 2) % width - width / 2
                else:
                    difference -= expected
                if abs(difference) > 1.5:
                    _reject()
        # Validate the actual numeric direction as well as the formula. This
        # also covers "a little" requests without an explicit amount.
        if mode == 'direction' and ((direction == 'increase' and new_value <= old_value)
                                    or (direction == 'decrease' and new_value >= old_value)):
            _reject()
