"""Protect explicit background requests before any image call.

This is deliberately a high-confidence text guard, not general language or
image-semantic verification. It preserves the employee's words rather than
trying to recognize a particular decoration or invent a new image operation.
Ambiguous mixed scopes require clarification; target eligibility, ownership,
image validation and quota remain the service's responsibility.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .providers import ClarificationNeeded


_BACKGROUND = re.compile(r'背景|底纹|底图', re.I)
_CLAUSES = re.compile(r'[，,。；;！!？?\n]+')
# Contrastive words end a negation scope. Do not split "并/以及": in
# "不要改人物并缩小图案" the negation still covers the second action.
_PARTS = re.compile(r'但是|不过|而是|(?<!不)但')
_NEGATIVE = re.compile(r'(?:不要|别|不用|无需|不需要|禁止|不必|不再|不(?!相关|同|规则|透明|必要|确定|完整|自然|均匀))[^，,。；;]*$')
_CONTENT = re.compile(
    r'铺满|布满|遍布|撒满|填满|满是|添加|新增|增加|增添|加上|加点|加一些|'
    r'加(?!大|宽|高|长|粗|深|亮)|去掉|去除|删除|移除|清除|抹掉'
)
_REPLACE = re.compile(r'替换|更换|换成|改成|改为')
_TEXTURE = re.compile(r'图案|图形|纹样|花纹|装饰|纹理')
_GEOMETRY = re.compile(r'间距|间隔|疏密|密度|排列|缩小|放大|旋转|移动|移到|挪动|变小|变大|拉开|挤紧')
_OBJECT = re.compile(r'背景|底纹|底图|人物|角色|主体|前景|边饰|文字|图案|素材')
_PRESERVE = re.compile(r'保持|保留|维持|不变|不动|不要动|不修改|不改|无需改')


def _entities(text: str) -> list[tuple[int, int, str]]:
    result = []
    for match in _OBJECT.finditer(text):
        kind = 'background' if _BACKGROUND.fullmatch(match.group()) else 'foreground'
        # "背景里的图案" means the texture's motifs, not an uploaded layer.
        if match.group() in ('图案', '文字') and result and result[-1][2] == 'background':
            if re.fullmatch(r'(?:里面|里|内部|内|上面|上|中间|中|本身)?的?', text[result[-1][1]:match.start()]):
                kind = 'background'
        result.append((match.start(), match.end(), kind))
    return result


def _intents(clause: str) -> set[tuple[str, str]]:
    """Only recognize positive actions with an explicit nearby layer noun."""
    result = set()
    for part in _PARTS.split(clause):
        entities = _entities(part)
        for action_kind, pattern in (('content', _CONTENT), ('replace', _REPLACE), ('geometry', _GEOMETRY)):
            for match in pattern.finditer(part):
                if _NEGATIVE.search(part[:match.start()]):
                    continue
                before = [entity for entity in entities if entity[0] < match.start()]
                entity = before[-1] if before else next(iter(entities), None)
                if not entity:
                    continue
                if action_kind == 'replace' and entity[2] == 'background' and not _TEXTURE.search(part[match.end():]):
                    # Unknown colours ("奶油色", "天蓝色") need no colour-name
                    # list. Leave replacements without texture evidence to the
                    # existing controlled planner; do not force an image call.
                    continue
                if action_kind == 'geometry' and _PRESERVE.search(part):
                    continue
                result.add((entity[2], 'content' if action_kind == 'replace' else action_kind))
    return result


def _foreground_modification(clause: str) -> bool:
    return any(scope == 'foreground' for scope, _ in _intents(clause))


def _layout_background_text(clauses: list[str]) -> str:
    selected = []
    for clause in clauses:
        if _BACKGROUND.search(clause):
            if _foreground_modification(clause):
                raise ClarificationNeeded('同一句话包含图案和底纹的修改，请分别写清楚，或选择具体精修范围。')
            selected.append(clause)
        elif not _entities(clause) and not _PRESERVE.search(clause):
            # Do not silently drop an unscoped continuation such as "四角也
            # 要有" or send it to the wrong layer.
            raise ClarificationNeeded('有一部分要求没有说明修改图案还是底纹，请选择底纹范围或分别写清楚。')
    return '；'.join(selected)


def background_edit_request(prompt: str, view: dict, operations: list[dict]) -> tuple[list[dict], dict]:
    """Return copied operations plus bounded, non-semantic protection metadata.

    An explicit background/zone selection uses the original prompt verbatim.
    A clearly background-only layout request also keeps its preservation
    constraints. Mixed requests pass only explicit background clauses. Unknown
    wording/languages leave the existing controlled plan unchanged. This
    function never adds an operation, changes its target, performs a model call
    or authorizes a version/quota change.
    """
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ClarificationNeeded('请填写具体修改要求（不超过 4000 字）。')
    copied = deepcopy(operations)
    if not isinstance(copied, list) or any(not isinstance(op, dict) for op in copied):
        raise ClarificationNeeded('修改计划无效，请重新说明需要调整的内容。')
    clauses = [value.strip() for value in _CLAUSES.split(prompt) if value.strip()]
    kind = view.get('target_kind', 'layout')
    target = view.get('target_id', 'layout')
    explicit = kind == 'background'
    intents = set().union(*(_intents(value) for value in clauses))
    requested = any(scope == 'background' for scope, _ in intents)
    # A selected background supplies the scope for a noun-less instruction.
    if explicit and not requested:
        requested = any(_intents('背景' + value) for value in clauses if not _entities(value))
    has_image_edit = any(op.get('type') == 'edit_background' for op in copied)

    metadata = dict(protocol='background-request-v1', scope='not_applied', target=target,
                    explicit_content_request=requested, semantic_verified=False)
    if not explicit and not requested:
        return copied, metadata

    if requested and kind in ('pattern', 'border'):
        raise ClarificationNeeded('要求中包含底纹内容修改，但当前选择的是图案或边饰，请先选择底纹范围。')
    if requested and not has_image_edit:
        raise ClarificationNeeded('这次要求需要修改底纹内容，当前计划只有排版或颜色调整，未执行、未扣精修次数；请明确底纹要求后重试。')

    if kind == 'layout' and requested:
        for op in copied:
            if op.get('type') == 'parameters' and set(op.get('values', {})) - {'background_color'}:
                if ('foreground', 'geometry') not in intents:
                    raise ClarificationNeeded('要求只修改底纹，计划却包含图案大小或位置调整；未执行、未扣精修次数，请分别写清楚。')
            elif op.get('type') in ('edit_asset', 'edit_composite') and ('foreground', 'content') not in intents:
                raise ClarificationNeeded('要求只修改底纹，计划却包含人物或图案内容修改；未执行、未扣精修次数，请分别写清楚。')

    scope = 'not_applied'
    if has_image_edit:
        if kind not in ('layout', 'background'):
            raise ClarificationNeeded('当前精修范围不支持修改底纹，请先选择底纹范围。')
        if explicit:
            if any(_foreground_modification(value) for value in clauses):
                raise ClarificationNeeded('当前只修改底纹，请将人物或图案的要求分开提交。')
            image_prompt = prompt
            scope = 'selected_background_original_request'
        else:
            image_prompt = prompt if not any(scope == 'foreground' for scope, _ in intents) else _layout_background_text(clauses)
            scope = 'explicit_background_clauses'
        for op in copied:
            if op.get('type') == 'edit_background':
                op['prompt'] = image_prompt

    return copied, {**metadata, 'scope': scope}
