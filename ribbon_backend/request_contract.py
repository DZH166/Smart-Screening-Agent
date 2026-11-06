"""Source-bound refinement plans; this is not image-semantic verification.

The planner must account for every immutable source unit. The service retains
the original text, reconstructs image instructions, checks numeric intent and
rejects an incomplete plan before image calls. It cannot prove that a generated
picture satisfies an aesthetic or content instruction.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import re


PROTOCOL = 'ribbon-request-v2'
_DELIMITERS = set('，,。；;！!？?\n')
_PAIRS = {'“': '”', '‘': '’', '「': '」', '『': '』', '《': '》', '〈': '〉',
          '(': ')', '（': '）', '[': ']', '【': '】', '{': '}'}
_QUOTE_ENDS = set('”’」』》〉\"\'')
_NUMBER = re.compile(r'(?<![A-Za-z0-9_.])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?![0-9.])')
_HEX = re.compile(r'#[0-9a-fA-F]{6}(?![0-9a-fA-F])')
_PRESERVE = re.compile(r'保持|保留|维持|原样|不变|不要|不改|不动|不添加|不改变|不增加|无需|别|勿|preserv|unchanged|keep|do not|don.t', re.I)
_GEOMETRY_KEYS = {'scale', 'spacing', 'rotation', 'offset_x', 'offset_y'}
_ACTION = re.compile(r'铺满|布满|遍布|填满|添加|新增|增加|减少|增大|减小|替换|更换|改成|改为|改变|改|删除|去掉|移除|缩小|放大|旋转|移动|移到|拉开|小一点|大一点|\badd\b|\bremove\b|\breplace\b|\bchange\b|\bincrease\b|\bdecrease\b|\bmove\b|\brotate\b|\bshrink\b|\benlarge\b|\bfill\b', re.I)
_NEGATION = re.compile(r'(?:不要|不许|禁止|别|勿|不(?!相关|同|规则|透明|完整)|do not|don.t)[^，,。；;]*$', re.I)
_PARAMETER_WORDS = {
    'scale': r'大小|缩放|比例|缩小|放大|变小|变大|增大|减小|小一点|大一点|scale|size|smaller|bigger|shrink|enlarge',
    'spacing': r'间距|间隔|距离|疏|密|spacing|gap|closer|apart',
    'rotation': r'旋转|转到|转至|转为|角度|顺时针|逆时针|rotate|rotation|angle|clockwise',
    'offset_x': r'向右|往右|右移|向左|往左|左移|横向|水平|[xX]坐标|\bx\b|right|left|horizontal',
    'offset_y': r'向上|往上|上移|向下|往下|下移|纵向|垂直|[yY]坐标|\by\b|down|up|vertical',
}


def _fail(message):
    from .providers import ClarificationNeeded
    raise ClarificationNeeded(message)


def _action_polarity(text):
    positive, negative = False, False
    for part in re.split(r'但是|不过|而是|(?<!不)但|\bbut\b', _mask_literals(text), flags=re.I):
        for action in _ACTION.finditer(part):
            if _NEGATION.search(part[:action.start()]):
                negative = True
            else:
                positive = True
    return positive, negative


def _mask_literals(text):
    """Quoted replacement text is data, never parameter authority or commands."""
    stack, result = [], []
    for index, char in enumerate(text):
        inside = bool(stack)
        escaped = index > 0 and (len(text[:index]) - len(text[:index].rstrip('\\'))) & 1
        if not escaped:
            if stack and char == stack[-1]:
                stack.pop()
            elif stack and stack[-1] in _QUOTE_ENDS:
                pass
            elif char in ('"', "'"):
                apostrophe = char == "'" and index > 0 and index + 1 < len(text) and text[index - 1].isalnum() and text[index + 1].isalnum()
                if not apostrophe:
                    stack.append(char)
            elif char in _PAIRS:
                stack.append(_PAIRS[char])
        result.append(' ' if inside or stack else char)
    return ''.join(result)


def source_units(prompt: str) -> list[dict]:
    """Partition original Unicode code points, retaining quotes and separators.

    Quoted/bracketed text is indivisible, including commas inside replacement
    wording. An unclosed quote conservatively keeps the remainder together.
    """
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        _fail('请填写具体修改要求（不超过 4000 字）。')
    result, stack, start = [], [], 0
    for index, char in enumerate(prompt):
        escaped = index > 0 and (len(prompt[:index]) - len(prompt[:index].rstrip('\\'))) & 1
        if not escaped:
            if stack and char == stack[-1]:
                stack.pop()
            elif stack and stack[-1] in _QUOTE_ENDS:
                pass
            elif char in ('"', "'"):
                apostrophe = char == "'" and index > 0 and index + 1 < len(prompt) and prompt[index - 1].isalnum() and prompt[index + 1].isalnum()
                if not apostrophe:
                    stack.append(char)
            elif char in _PAIRS:
                stack.append(_PAIRS[char])
        if char in _DELIMITERS and not stack and (index + 1 == len(prompt) or prompt[index + 1] not in _DELIMITERS):
            result.append(dict(id=f's{len(result) + 1}', text=prompt[start:index + 1], start=start, end=index + 1))
            start = index + 1
    if start < len(prompt):
        result.append(dict(id=f's{len(result) + 1}', text=prompt[start:], start=start, end=len(prompt)))
    return result


def request_targets(view: dict) -> dict[str, dict]:
    """Stable identities, without claiming per-operation target capabilities."""
    kind, selected = view.get('target_kind', 'layout'), view.get('target_id', 'layout')
    result = {'layout': dict(kind='layout', preserve_only=kind != 'layout')}
    assets = view.get('asset_refs', [])
    if kind in ('pattern', 'border'):
        if assets:
            result[selected] = dict(kind=kind, asset_id=assets[0], preserve_only=False)
        return result
    if kind == 'background':
        result[selected] = dict(kind='background', asset_id=view.get('background_ref'), preserve_only=False)
        return result
    result['background'] = dict(kind='background', asset_id=view.get('background_ref'), preserve_only=False)
    slots = view.get('pattern_slots', [])
    for index, asset in enumerate(assets):
        target = slots[index] if len(slots) == len(assets) else 'asset:' + asset
        result[target] = dict(kind='pattern', asset_id=asset, preserve_only=False)
    if view.get('border_ref'):
        result['border'] = dict(kind='border', asset_id=view['border_ref'], preserve_only=True)
    for zone, asset in view.get('zone_background_refs', {}).items():
        result['zone:' + zone] = dict(kind='background', asset_id=asset, preserve_only=True)
    return result


def request_effect_targets(view: dict, provider: str) -> dict[str, list[str]]:
    """Targets available for each effect, not just for any kind of editing."""
    from .providers import workflow_editing
    targets, editing = request_targets(view), workflow_editing(provider, view)
    result = dict(parameters=[], content=[], preserve=list(targets), clarify=list(targets))
    kind, selected = view.get('target_kind', 'layout'), view.get('target_id', 'layout')
    if 'parameters' in editing['allowed_operations']:
        if any(key in _GEOMETRY_KEYS for key in editing['allowed_parameters']):
            result['parameters'].append(selected)
        if 'background_color' in editing['allowed_parameters']:
            target = selected if kind == 'background' else 'background'
            if target in targets:
                result['parameters'].append(target)
    if 'edit_asset' in editing['allowed_operations']:
        result['content'].extend(target for target, info in targets.items()
            if info['kind'] in ('pattern', 'border') and not info['preserve_only'] and info.get('asset_id') in view.get('asset_refs', []))
    if 'edit_background' in editing['allowed_operations']:
        target = selected if kind == 'background' else 'background'
        if target in targets:
            result['content'].append(target)
    if 'edit_composite' in editing['allowed_operations'] and not targets['layout']['preserve_only']:
        result['content'].append('layout')
    return {effect: list(dict.fromkeys(ids)) for effect, ids in result.items()}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _close(first, second):
    return math.isclose(first, second, rel_tol=1e-9, abs_tol=1e-9)


def _direction(key, evidence):
    patterns = {
        'scale': (r'放大|变大|增大|increase|enlarge|bigger', r'缩小|变小|减小|decrease|smaller|shrink'),
        'spacing': (r'拉开|加大|增大|扩大|更疏|疏一点|increase|wider', r'缩小|减小|缩短|压缩|更密|密一点|靠近|decrease|closer'),
        'offset_x': (r'向右|往右|右移|right', r'向左|往左|左移|left'),
        'offset_y': (r'向下|往下|下移|down', r'向上|往上|上移|up'),
        'rotation': (r'(?<!逆)顺时针|(?<!counter)clockwise', r'逆时针|counterclockwise'),
    }
    positive, negative = patterns[key]
    up, down = bool(re.search(positive, evidence, re.I)), bool(re.search(negative, evidence, re.I))
    return 'increase' if up and not down else 'decrease' if down and not up else None


def _check_mode(key, mode, direction, evidence):
    """Finite parameter grammar only; unknown wording is not new permission."""
    if not re.search(_PARAMETER_WORDS[key], evidence, re.I):
        _fail('原文没有授权这个参数，不能借用其它要求的数字执行修改。')
    percentage = bool(re.search(r'%|％|百分之|percent', evidence, re.I))
    if percentage:
        if re.search(r'(?:缩放|比例|scale).{0,12}(?:设为|设置为|改为|改成|设成|set\s+to)', evidence, re.I):
            if mode != 'absolute_percent' or direction != 'set':
                _fail('原文要求设置缩放比例，不能当成相对增减百分比。')
        elif re.search(r'(?:到|至|\bto\b)\s*(?:百分之)?\s*\d', evidence, re.I):
            if mode != 'percent' or direction != 'set':
                _fail('原文要求调整到指定百分比，不能当作增加或减少该百分比。')
        elif _direction(key, evidence):
            if mode != 'percent' or direction != _direction(key, evidence):
                _fail('原文要求相对增减百分比，不能换成最终比例。')
    elif key in ('offset_x', 'offset_y', 'rotation') and _NUMBER.search(evidence):
        absolute = bool(re.search(r'到|至|设为|设置为|改为|改成|坐标|coordinate|\bto\b|\bset\b', evidence, re.I))
        if mode != ('absolute' if absolute else 'delta'):
            _fail('原文的移动或旋转增量与目标位置不能混用，未执行修改。')


def _check_intent(intent, value, current, texts, *, layout_rotation=0, pattern_target=False):
    if not isinstance(intent, dict) or set(intent) != {'key', 'mode', 'amount', 'direction', 'evidence'}:
        _fail('参数意图不完整，未执行修改，请重新说明要求。')
    key, mode, amount, direction, evidence = (intent[name] for name in ('key', 'mode', 'amount', 'direction', 'evidence'))
    if not isinstance(evidence, str) or not evidence.strip() or not any(evidence in text for text in texts):
        _fail('参数依据不是本次原文中的完整片段，未执行修改。')
    # Keep original evidence for audit; use same-length masks only for grammar.
    evidence = _mask_literals(evidence)
    texts = [_mask_literals(text) for text in texts]
    if mode not in ('absolute', 'absolute_percent', 'delta', 'percent', 'factor', 'direction') or direction not in ('increase', 'decrease', 'set'):
        _fail('参数意图不在支持范围内，未执行修改。')
    if key == 'background_color':
        if mode != 'absolute' or direction != 'set' or amount is not None or not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            _fail('底色参数不完整，请明确需要的颜色。')
        explicit = _HEX.findall(''.join(texts))
        if explicit and (len({colour.upper() for colour in explicit}) != 1 or explicit[0].upper() != value.upper()):
            _fail('计划底色与原文颜色值不一致，未执行修改。')
        return dict(key=key, mode=mode, verification='hex_parameter_only', semantic_verified=False)
    if key not in _GEOMETRY_KEYS or not _number(value) or not _number(current):
        _fail('参数数值无效，未执行修改。')
    for text in texts:
        for part in re.split(r'但是|不过|而是|(?<!不)但|\bbut\b', text, flags=re.I):
            if any(_NEGATION.search(part[:word.start()]) for word in re.finditer(_PARAMETER_WORDS[key], part, re.I)):
                _fail('原文明确不修改这个参数，不能截掉否定后执行。')
    if key in ('offset_x', 'offset_y') and re.search(r'厘米|毫米|英寸|(?<![A-Za-z])(?:cm|mm|inch|inches)(?![A-Za-z])|(?<=\d)in\b|%|％|百分之', ''.join(texts), re.I):
        _fail('当前位移只支持像素，不能把厘米、英寸或百分比直接当作像素。')
    _check_mode(key, mode, direction, evidence)
    inferred = _direction(key, evidence)
    if inferred and direction != inferred and not (mode == 'percent' and direction == 'set'):
        _fail('参数方向与原文要求不一致，未执行修改。')
    if mode == 'direction':
        if amount is not None or direction == 'set':
            _fail('只指定方向时不能附加模型编造的数值。')
        numeric_text = re.sub(r'第\s*\d+\s*个(?:图案)?|图案\s*\d+', '', ''.join(texts))
        if _NUMBER.search(numeric_text):
            _fail('原文包含明确数值，不能仅检查方向而忽略数值。')
        expected = None
    else:
        if not _number(amount) or not any(_close(abs(amount), abs(float(match.group()))) for match in _NUMBER.finditer(evidence)):
            _fail('参数数值没有原文数字依据，未执行修改。')
        if mode == 'absolute':
            expected = amount - layout_rotation if key == 'rotation' and pattern_target else amount
        elif mode == 'absolute_percent':
            if key not in ('scale', 'spacing') or not re.search(r'%|％|百分之|percent', evidence, re.I):
                _fail('绝对百分比仅用于明确的比例要求。')
            expected = amount / 100
        elif mode == 'delta':
            expected = current + amount
        elif mode == 'factor':
            if amount < 0 or not re.search(r'倍|times|factor|\bx\b|×', evidence, re.I):
                _fail('参数倍数不能为负数。')
            expected = current * amount
        else:
            if amount < 0 or not re.search(r'%|％|百分之|percent', evidence, re.I):
                _fail('百分比必须使用非负原文数值。')
            if direction == 'set':
                expected = current * amount / 100
            elif direction == 'increase':
                expected = current * (1 + amount / 100)
            else:
                expected = current * (1 - amount / 100)
        if not _close(value, expected):
            _fail('计划参数与原文数值不一致，未执行、未扣精修次数。')
    if direction == 'increase' and not value > current or direction == 'decrease' and not value < current:
        _fail('参数没有按要求增大或减小，未执行修改。')
    return dict(key=key, mode=mode, verification='numeric_plan_only', semantic_verified=False)


def validate_request_plan(prompt: str, view: dict, plan: dict, provider: str) -> dict:
    """Validate and rebuild a v2 plan before any requested image is dispatched."""
    from .providers import workflow_editing
    from .imaging import PARAM_DEFAULTS

    units, targets = source_units(prompt), request_targets(view)
    by_id = {unit['id']: unit for unit in units}
    required = {'summary', 'clarification', 'requirements', 'operations'}
    metadata_keys = {'request_contract', 'model', 'request_id', 'usage', 'is_demo', 'description'}
    if not isinstance(plan, dict) or not required <= set(plan) or set(plan) - required - metadata_keys:
        _fail('精修计划缺少原文要求绑定，未执行修改，请重试。')
    if not isinstance(plan['summary'], str) or plan['clarification'] is not None and not isinstance(plan['clarification'], str):
        _fail('精修计划格式不完整，未执行修改。')
    if plan['clarification']:
        _fail(plan['clarification'][:1000])
    requirements, operations = plan['requirements'], deepcopy(plan['operations'])
    if not isinstance(requirements, list) or len(requirements) != len(units) or not isinstance(operations, list) or len(operations) > 8:
        _fail('计划没有覆盖全部原文要求，未执行修改。')
    bound = {}
    for requirement in requirements:
        if not isinstance(requirement, dict) or set(requirement) != {'source_id', 'target_id', 'effect'}:
            _fail('原文要求绑定格式不完整，未执行修改。')
        source, target, effect = (requirement[key] for key in ('source_id', 'target_id', 'effect'))
        if not isinstance(source, str) or source not in by_id or source in bound or not isinstance(target, str) or target not in targets:
            _fail('原文要求的目标或引用无效，未执行修改。')
        if effect not in ('parameters', 'content', 'preserve', 'clarify'):
            _fail('原文要求的处理方式无效，未执行修改。')
        if effect == 'clarify' or targets[target]['preserve_only'] and effect != 'preserve':
            _fail('有一项要求超出当前精修范围，请选择具体目标或分别说明，未执行修改。')
        positive, negative = _action_polarity(by_id[source]['text'])
        if effect != 'preserve' and negative and not positive:
            _fail('否定要求不能变成修改操作，请将需要改变的部分单独写清楚。')
        if effect == 'preserve' and positive:
            _fail('原文含有明确修改动作，不能只当作保留说明而遗漏执行。')
        if effect == 'preserve' and not _PRESERVE.search(_mask_literals(by_id[source]['text'])):
            meaningful = re.sub(r'[\s，,。；;！!？?]+', '', by_id[source]['text'])
            if meaningful and not re.fullmatch(r'谢谢|感谢|麻烦了|thanks|thankyou|please', meaningful, re.I):
                _fail('有一段原文被当作保留说明，无法确认已完整处理，请重新说明。')
        bound[source] = dict(requirement)
    if set(bound) != set(by_id):
        _fail('计划遗漏了原文要求，未执行修改。')

    editing = workflow_editing(provider, view)
    current = {**PARAM_DEFAULTS, **view.get('params', {})}
    used, checks, parameter_keys, image_targets = set(), [], set(), set()
    for operation in operations:
        if not isinstance(operation, dict):
            _fail('精修操作无效，未执行修改。')
        kind = operation.get('type')
        if kind not in editing['allowed_operations']:
            _fail(editing['composite_edit_reason'] or '当前范围不支持这项操作，未执行修改。')
        expected_keys = {'type', 'source_ids', 'values', 'intents'} if kind == 'parameters' else {'type', 'source_ids', 'prompt'} | ({'asset_id'} if kind == 'edit_asset' else set())
        if set(operation) != expected_keys:
            _fail('精修操作缺少原文或数值依据，未执行修改。')
        ids = operation['source_ids']
        if not isinstance(ids, list) or not ids or any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids) or any(value not in bound for value in ids):
            _fail('操作引用的原文要求无效，未执行修改。')
        if used.intersection(ids):
            _fail('同一条原文要求不能分配给多个操作重复执行，请合并为一个操作。')
        rows = [bound[value] for value in ids]
        effect = 'parameters' if kind == 'parameters' else 'content'
        if any(row['effect'] != effect for row in rows):
            _fail('操作与原文要求的类型不一致，未执行修改。')
        if kind == 'parameters':
            values, intents = operation['values'], operation['intents']
            if isinstance(values, dict):
                values = {key: value for key, value in values.items() if value is not None}
                operation['values'] = values
            if not isinstance(values, dict) or not values or not isinstance(intents, list) or len(intents) != len(values):
                _fail('参数没有逐项对应的原文依据，未执行修改。')
            keys = [intent.get('key') if isinstance(intent, dict) else None for intent in intents]
            if any(not isinstance(key, str) for key in keys) or set(keys) != set(values) or len(set(keys)) != len(keys) or set(values) - set(editing['allowed_parameters']):
                _fail('参数依据与可执行参数不一致，未执行修改。')
            matched = set()
            for intent in intents:
                key = intent['key']
                if key in parameter_keys:
                    _fail('同一参数不能在一次计划中反复修改，请说明最终要求。')
                parameter_keys.add(key)
                target = view.get('target_id', 'layout')
                if key == 'background_color' and view.get('target_kind', 'layout') == 'layout':
                    target = 'background'
                sources = [value for value in ids if bound[value]['target_id'] == target]
                if not sources:
                    _fail('参数目标与原文要求不一致，未执行修改。')
                check = _check_intent(intent, values[key], current.get(key), [by_id[value]['text'] for value in sources],
                    layout_rotation=view.get('layout_params', {}).get('rotation', 0), pattern_target=view.get('target_kind') == 'pattern')
                matched.update(value for value in sources if intent['evidence'] in by_id[value]['text'])
                checks.append({**check, 'source_ids': sorted(matched)})
            if matched != set(ids):
                _fail('有一项参数要求没有执行依据，未执行修改。')
            current.update(values)
        else:
            if not isinstance(operation.get('prompt'), str):
                _fail('图片修改计划无效，未执行修改。')
            if kind == 'edit_asset':
                target_ids = [target for target, info in targets.items() if info.get('asset_id') == operation.get('asset_id') and info['kind'] in ('pattern', 'border') and not info['preserve_only']]
            elif kind == 'edit_background':
                selected = view.get('target_id', 'layout')
                target_ids = [selected if view.get('target_kind') == 'background' else 'background']
            else:
                target_ids = ['layout']
            if any(row['target_id'] not in target_ids for row in rows):
                _fail('图片操作目标与原文要求不一致，未执行修改。')
            image_target = (kind, tuple(sorted({row['target_id'] for row in rows})))
            if image_target in image_targets:
                _fail('同一图片目标请合并为一次修改，不重复调用。')
            image_targets.add(image_target)
            forwarded = set(ids) | {source for source, row in bound.items() if row['effect'] == 'preserve'}
            operation['prompt'] = ''.join(unit['text'] for unit in units if unit['id'] in forwarded)
        used.update(ids)
    actionable = {source for source, row in bound.items() if row['effect'] != 'preserve'}
    if used != actionable:
        _fail('有一项修改要求没有对应操作，未执行、未扣精修次数；不能只完成其中一部分。')
    if any(operation['type'] == 'edit_composite' for operation in operations) and len(operations) != 1:
        _fail('整幅重画不能与独立图层操作混用，未执行修改。')
    contract = dict(protocol=PROTOCOL, source_sha256=hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
                    units=units, requirements=[bound[unit['id']] for unit in units],
                    coverage='checked', verification_scope='plan_and_geometry_only',
                    image_effect_verified=False, semantic_verified=False, parameter_checks=checks)
    return {**deepcopy(plan), 'summary': plan['summary'][:1000], 'operations': operations, 'request_contract': contract}


def public_request_receipt(plan: dict, *, geometry_verified=True) -> dict:
    """Call only after service geometry, image and commit checks succeed.

    A forwarded constraint is not a promise of semantic preservation. No source
    words, free-form model prompts or image/credential bytes are returned.
    """
    contract = plan.get('request_contract', {})
    if contract.get('protocol') != PROTOCOL:
        _fail('缺少原文执行记录，无法生成精修回执。')
    units = {unit['id']: unit for unit in contract['units']}
    requirements = []
    for row in contract['requirements']:
        unit, effect = units[row['source_id']], row['effect']
        method = {'parameters': 'parameters', 'content': 'image', 'preserve': 'preserve'}[effect]
        execution = {'parameters': 'geometry_verified' if geometry_verified else 'parameters_applied_unverified', 'content': 'image_generated_unverified', 'preserve': 'constraint_forwarded'}[effect]
        requirements.append(dict(id=row['source_id'], source_id=row['source_id'], start=unit['start'], end=unit['end'],
                                 kind='preserve' if effect == 'preserve' else 'modify', target=row['target_id'],
                                 method=method, execution=execution))
    return {key: contract[key] for key in ('protocol', 'source_sha256', 'coverage', 'verification_scope', 'image_effect_verified')} | {'requirements': requirements}
