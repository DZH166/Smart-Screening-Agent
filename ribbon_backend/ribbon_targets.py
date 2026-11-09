"""Immutable composition layer identities for new ribbon versions."""
import uuid

ZONES = {'split': ('left', 'right'), 'panels': ('left', 'center', 'right'), 'stacked': ('top', 'bottom')}
MODERN_ENGINES = ('seamless-unit-v2', 'seamless-unit-v3')
ROLE_CHOICES = {'scene': frozenset(('main', 'support', 'accent')),
                'scatter': frozenset(('main', 'accent')),
                'bordered': frozenset(('main', 'border'))}


def configure_roles(selection, mode, snapshot, ids, slots):
    """Turn an employee's selected asset roles into immutable slot roles.

    Unknown IDs fail even if the employee can access those assets: a role is
    only meaningful for a pattern in this specific selection. Roles are not
    inferred from filenames or the image model. Decorations survive a change
    of layout; mode-specific roles reset unless explicitly selected.
    """
    from .service import ServiceError
    supplied = selection.get('pattern_roles')
    if 'pattern_roles' in selection and (not isinstance(supplied, dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in supplied.items())
            or set(supplied) - set(ids)):
        raise ServiceError(422, '图案用途与当前所选素材不一致，请重新选择')
    special = ROLE_CHOICES.get(mode, frozenset())
    choices = special | {'main', 'decoration'}
    if supplied is not None and any(value not in choices for value in supplied.values()):
        raise ServiceError(422, '此排法不支持所选图案用途，请重新选择')
    previous = snapshot.get('pattern_roles', {})
    same_mode = snapshot.get('template_mode') == mode
    result = {}
    has_structural_pattern = False
    for asset, slot in zip(ids, slots):
        saved = previous.get(slot)
        if not same_mode and saved != 'decoration':
            saved = None
        value = supplied.get(asset) if supplied is not None else saved
        if value is None:
            value = 'support' if mode == 'scene' and has_structural_pattern else 'main'
        if value not in choices:
            raise ServiceError(422, '保存的图案用途已不适用，请重新选择')
        result[slot] = value
        has_structural_pattern |= value != 'decoration'
    if 'main' not in result.values():
        raise ServiceError(422, '请至少保留一张主图')
    snapshot['pattern_roles'] = result if special or 'decoration' in result.values() else {}


def loop_inputs(snapshot):
    result = [*snapshot['asset_refs'], snapshot['background_ref']]
    result.extend(value for _, value in sorted(snapshot.get('zone_background_refs', {}).items()))
    if snapshot.get('border_ref'):
        result.append(snapshot['border_ref'])
    return result


def configure_layers(service, db, owner, selection, mode, snapshot, ids):
    from .service import ServiceError
    old = dict(zip(snapshot.get('asset_refs', []), snapshot.get('pattern_slots', [])))
    slots = [old.get(asset) or 'pattern-' + uuid.uuid4().hex[:16] for asset in ids]
    snapshot['pattern_slots'] = slots
    snapshot['slot_params'] = {s: v for s, v in snapshot.get('slot_params', {}).items() if s in slots}
    if snapshot.get('layout_engine') == 'seamless-unit-v3':
        configure_roles(selection, mode, snapshot, ids, slots)
    elif selection.get('pattern_roles'):
        raise ServiceError(422, '此作品保留原排法；图案用途分工可用于新作品')
    allowed = ZONES.get(mode, ())
    refs = selection.get('zone_background_refs', {k: v for k, v in snapshot.get('zone_background_refs', {}).items() if k in allowed})
    if not isinstance(refs, dict) or any(k not in allowed or not isinstance(v, str) for k, v in refs.items()):
        raise ServiceError(422, '底纹分区与当前排法不符，请重新选择')
    for asset in refs.values():
        service.accessible_asset(db, asset, owner, 'background', True)
    previous = snapshot.get('zone_background_refs', {})
    snapshot['zone_colors'] = {k: v for k,v in snapshot.get('zone_colors', {}).items() if k in allowed and refs.get(k) == previous.get(k) and v is not None}
    snapshot['zone_background_refs'] = dict(refs)
    border = selection.get('border_ref', snapshot.get('border_ref') if mode == 'bordered' else None)
    if border is not None:
        if mode != 'bordered' or not isinstance(border, str):
            raise ServiceError(422, '此排法不接受独立边饰')
        service.accessible_asset(db, border, owner, 'pattern', True)
    snapshot['border_ref'] = border

def target_view(snapshot, target):
    """A planning view scoped to an immutable base; never becomes the saved snapshot."""
    from .providers import ClarificationNeeded
    from .imaging import PARAM_DEFAULTS
    view = dict(snapshot)
    target = target or 'layout'
    if target == 'layout':
        return view
    if snapshot.get('layout_engine') not in MODERN_ENGINES:
        raise ClarificationNeeded('此版本不支持选择局部目标，请使用原有精修方式')
    slots = snapshot['pattern_slots']
    if target in slots:
        asset = snapshot['asset_refs'][slots.index(target)]
        view.update(asset_refs=[asset], params={**PARAM_DEFAULTS, **snapshot['slot_params'].get(target, {})},
                    target_kind='pattern', target_id=target, target_ordinal=slots.index(target)+1,
                    layout_params=dict(snapshot['params']))
    elif target == 'border' and snapshot.get('border_ref'):
        view.update(asset_refs=[snapshot['border_ref']], target_kind='border', target_id=target)
    elif target == 'background' or target.startswith('zone:') and target[5:] in ZONES.get(snapshot['template_mode'], ()):
        zone = target[5:] if target.startswith('zone:') else None
        if zone is None and ZONES.get(snapshot['template_mode']) and all(
                k in snapshot.get('zone_background_refs', {}) or k in snapshot.get('zone_colors', {})
                for k in ZONES[snapshot['template_mode']]):
            raise ClarificationNeeded('各分区都使用独立底纹，请选择实际要修改的分区')
        refs = snapshot.get('zone_background_refs', {})
        colour = snapshot.get('zone_colors', {}).get(zone, None if zone in refs else snapshot['params'].get('background_color'))
        view.update(asset_refs=[], background_ref=refs.get(zone,snapshot['background_ref']),
                    params={**PARAM_DEFAULTS, 'background_color':colour}, target_kind='background', target_id=target)
    else:
        raise ClarificationNeeded('选择的修改目标已变化，请重新选择')
    return view


def apply_values(snapshot, target, values):
    if target in snapshot.get('pattern_slots', []):
        snapshot.setdefault('slot_params', {}).setdefault(target, {}).update(values)
    elif target.startswith('zone:'):
        colors = snapshot.setdefault('zone_colors', {})
        if values['background_color'] is None:
            colors.pop(target[5:], None)
        else:
            colors[target[5:]] = values['background_color']
    else:
        snapshot['params'].update(values)


def check_parameter_effect(before, after, target, values):
    """Compare actual placement dimensions and spacing, not requested numbers or RGB noise."""
    from .providers import ClarificationNeeded
    if before.get('layout_engine') not in MODERN_ENGINES:
        return
    if before.get('layout_engine') == 'seamless-unit-v3':
        from .loop_layout_v3 import plan
    else:
        from .loop_layout_v2 import plan
    geom = set(values) - {'background_color'}
    if not geom:
        return
    left, right = plan(before), plan(after)
    if target in before.get('pattern_slots', []):
        left = [p for p in left if p['slot_id'] == target]
        right = [p for p in right if p['slot_id'] == target]
    def difference(key):
        return max((abs(a[key]-b[key]) for a,b in zip(left,right)), default=0)
    threshold = 1.5
    for key in geom:
        if key == 'scale':
            effect = max(difference('target_width'), difference('target_height'))
        elif key == 'spacing':
            effect = abs(before['loop_layout']['metrics']['mean_gap_px']-after['loop_layout']['metrics']['mean_gap_px'])
        elif key in ('offset_x','offset_y'):
            if key == 'offset_x' and before['output_profile']['width'] == after['output_profile']['width']:
                width = before['output_profile']['width']
                effect = max((abs((a['x'] - b['x'] + width / 2) % width - width / 2) for a,b in zip(left,right)), default=0)
            else:
                effect = difference(key[-1])
        elif key == 'rotation':
            effect = max((abs((a['rotation']-b['rotation']+180)%360-180) for a,b in zip(left,right)),default=0)
        else:
            continue
        if effect < (0.5 if key=='rotation' else threshold):
            raise ClarificationNeeded('这项调整已达到布局边界或实际变化太小，未保存、未扣次；请增大幅度或换一个方向')
