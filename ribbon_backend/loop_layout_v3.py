"""Versioned free scatter, explicit composition roles and equal zone layouts.

Unchanged modes delegate to v2; historical versions keep their original engine.
The scatter packer places complete rotated bounding boxes on a horizontal
cylinder, rather than jittering a number of predetermined horizontal lanes.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import random

from . import loop_layout_v2 as previous
from .imaging import _profile, png_space
from .loop_decorations import place_decorations

ENGINE = 'seamless-unit-v3'
MODES = previous.MODES
ZONE_IDS = previous.ZONE_IDS
original = previous.original

# Visual occupancy targets concern actual complete rotated bounding boxes.
# Spacing adds horizontal breathing room after a collision-free free-field pack.
_SCATTER_FILL = {'airy': .25, 'balanced': .36, 'rich': .47}
ROLE_MODES = {'scene': {'main', 'support', 'accent'},
              'scatter': {'main', 'accent'}, 'bordered': {'main', 'border'}}


def pattern_roles(snapshot, slots):
    mode = snapshot['template_mode']
    supplied = snapshot.get('pattern_roles', {})
    if not isinstance(supplied, dict) or set(supplied) - set(slots):
        raise ValueError('图案角色与所选素材不一致')
    allowed = ROLE_MODES.get(mode)
    if 'decoration' in supplied.values():
        choices = (allowed or {'main'}) | {'decoration'}
        if any(not isinstance(role, str) or role not in choices for role in supplied.values()):
            raise ValueError('图案角色不适用于当前排法')
        structural = [slot for slot in slots if supplied.get(slot) != 'decoration']
        if not structural:
            raise ValueError('请至少保留一个主体图案')
        defaults = {slot: ('support' if mode == 'scene' and i else 'main')
                    for i, slot in enumerate(structural)}
        result = {slot: supplied[slot] if slot in supplied else defaults[slot] for slot in slots}
        if 'main' not in result.values():
            raise ValueError('请至少保留一个主体图案')
        return result
    if allowed is None:
        if supplied:
            raise ValueError('此排法不使用主辅图案角色')
        return {}
    result = {slot: ('support' if mode == 'scene' and i else 'main')
              for i, slot in enumerate(slots)}
    if any(not isinstance(role, str) or role not in allowed for role in supplied.values()):
        raise ValueError('图案角色不适用于当前排法')
    result.update(supplied)
    if 'main' not in result.values():
        raise ValueError('请至少保留一个主体图案')
    return result


def _distance(a, b, width):
    dx = abs(a['x'] - b['x'])
    dx = min(dx, width - dx)
    return dx, abs(a['y'] - b['y'])


def _clear(a, b, width, gap=2.):
    dx, dy = _distance(a, b, width)
    return (dx >= (a['planned_width'] + b['planned_width']) / 2 + gap or
            dy >= (a['planned_height'] + b['planned_height']) / 2 + gap)


def _validate_positions(placements, width, top, bottom, *, gap=1.):
    for i, current in enumerate(placements):
        if current['planned_width'] + gap > width:
            raise ValueError('图案宽于完整循环，无法安全放置')
        if (current['y'] - current['planned_height'] / 2 < top - 1e-7 or
                current['y'] + current['planned_height'] / 2 > bottom + 1e-7):
            raise ValueError('目标位置会超出丝带上下边界，请减小偏移或图案')
        if any(not _clear(current, other, width, gap) for other in placements[:i]):
            raise ValueError('目标调整会与相邻图案重叠，请缩小图案、减小偏移或增大间距')


def _pack(items, width, top, bottom, seed, *, fixed=(), decorate_group=False):
    """Seeded best-candidate packing, without rows or a hidden snap grid.

    The largest boxes are placed first. Candidates come from the full available
    two-dimensional area. Circular distance tests include both seam neighbours.
    Different candidate streams per item avoid implicit common Y coordinates.
    """
    rng = random.Random(seed)
    placed = list(fixed)
    generated = []
    for item in sorted(items, key=lambda q: (-q['planned_width'] * q['planned_height'], q['serial'])):
        hw, hh = item['planned_width'] / 2, item['planned_height'] / 2
        if 2 * hw + 4 > width or top + hh > bottom - hh:
            return None
        best, score = None, -math.inf
        # Bounded candidates for the selected complete motifs; no infinite
        # rejection loop at the density or width limit.
        # A small randomized preference prevents symmetric corner solutions.
        for _ in range(384):
            candidate = {**item, 'x': rng.uniform(hw + 2, width - hw - 2),
                         'y': rng.uniform(top + hh, bottom - hh)}
            if any(not _clear(candidate, other, width) for other in placed):
                continue
            if not placed:
                best = candidate
                break
            clearance = min(
                math.hypot(max(0., _distance(candidate, other, width)[0] -
                               (candidate['planned_width'] + other['planned_width']) / 2),
                           max(0., abs(candidate['y'] - other['y']) -
                               (candidate['planned_height'] + other['planned_height']) / 2))
                for other in placed)
            # Do not always select a geometric extreme; favour balanced empty
            # regions while retaining a continuous, reproducible distribution.
            candidate_score = clearance * rng.uniform(.82, 1.18)
            if decorate_group and fixed:
                # Scene ornaments should accompany the group, not flee to the
                # farthest empty corner. Prefer a small clear distance above
                # the nearest body while still requiring full-box separation.
                distances = []
                for body in fixed:
                    dx, dy = _distance(candidate, body, width)
                    distance = math.hypot(max(0., dx-(candidate['planned_width']+body['planned_width'])/2),
                                          max(0., dy-(candidate['planned_height']+body['planned_height'])/2))
                    distances.append((distance, body))
                nearest, body = min(distances,key=lambda pair:pair[0])
                candidate_score = (-abs(nearest-item['planned_height']*.35)/max(1.,item['planned_height'])
                                   - (1. if candidate['y'] > body['y'] else 0.) + rng.uniform(0.,.12))
            if candidate_score > score:
                best, score = candidate, candidate_score
        if best is None:
            return None
        placed.append(best)
        generated.append(best)
    return sorted(generated, key=lambda q: q['serial'])


def _scatter(snapshot, specs):
    c = original._configuration({**snapshot, 'design_density': 'balanced'}, specs,
                                 independent_border=True)
    density = snapshot.get('design_density', 'balanced')
    if density not in previous.DENSITY:
        raise ValueError('请选择有效的画面密度')
    occupancy, gap_ratio = previous.DENSITY[density]
    slots, edits = previous._slots(snapshot)
    roles = pattern_roles(snapshot, slots)
    h, n = c['height'], c['n']
    row_hint = c['rules'].get('rows', 3 if density == 'rich' else 2)
    if type(row_hint) is not int or not 1 <= row_hint <= 4:
        raise ValueError('模板密度层数必须在一至四之间')
    top, bottom = .06 * h, .94 * h
    room = bottom - top
    # The count is a density budget, not a requirement to align into rows.
    copies = max(row_hint, math.ceil(8 / n))
    count = n * copies
    if count > original.MAX_PLACEMENTS:
        raise ValueError('完整循环单元包含过多图案')
    base = room / row_hint * occupancy
    scale = min(c['scale'], (room - 4) / base)
    if base <= 0 or scale <= 0:
        raise ValueError('当前高度容不下完整图案')
    seed = int(snapshot.get('seed', 0))
    rng = random.Random(seed)
    angles = [-18., -9., 9., 18.]
    rng.shuffle(angles)
    order = list(range(n)) * copies
    rng.shuffle(order)
    factors = [.78, .88, 1.]
    items = []
    for serial, index in enumerate(order):
        angle = c['angle'] + angles[serial % len(angles)]
        factor = factors[serial % len(factors)] * (.35 if roles[slots[index]] == 'accent' else 1.)
        nominal = base * scale * factor
        tw, th, bw, bh = original._size(specs[index], nominal, room, angle)
        items.append(dict(serial=serial, asset_index=index, slot_id=slots[index],
                          target_width=tw, target_height=th, planned_width=bw,
                          planned_height=bh, rotation=angle, nominal_height=nominal,
                          role=roles[slots[index]], group=serial // n, row=0))
    width = max(16, math.ceil(max(q['planned_width'] + 6 for q in items)),
                math.ceil(sum(q['planned_width'] * q['planned_height'] for q in items) /
                          (room * _SCATTER_FILL[density])))
    placements = None
    attempts = 0
    for attempts in range(10):
        _profile({**snapshot['output_profile'], 'width': width})
        placements = _pack(items, width, top, bottom, seed)
        if placements is not None:
            break
        width = math.ceil(width * 1.12)
    if placements is None:
        raise ValueError('当前散点图案无法在安全间距内完整放置，请换用更小图案或减少素材')
    packed_width = width
    # Stretch only the empty horizontal distribution, leaving motif pixels
    # unchanged. Increasing spacing cannot tighten any pair or change Y.
    nominal_gap = max(2., room / row_hint * gap_ratio * .48)
    weighted_count = sum(.35 if q['role'] == 'accent' else 1. for q in items)
    extra = nominal_gap * c['spacing'] * weighted_count / row_hint
    width = math.ceil(width + extra)
    _profile({**snapshot['output_profile'], 'width': width})
    stretch = width / packed_width
    for p in placements:
        p['x'] *= stretch
    # Local transforms are applied AFTER placement. Unselected slots never move
    # simply because one pattern was translated/resized/rotated.
    slot_caps = {i: min(2.5, (room - 4) / max(q['nominal_height'] for q in items
                                            if q['asset_index'] == i)) for i in range(n)}
    slot_scales = {i: min(float(edits.get(slots[i], {}).get('scale', 1.)), slot_caps[i])
                   for i in range(n)}
    for p in placements:
        edit = edits.get(p['slot_id'], {})
        angle = p['rotation'] + float(edit.get('rotation', 0.))
        tw, th, bw, bh = original._size(specs[p['asset_index']],
            p['nominal_height'] * slot_scales[p['asset_index']], room, angle)
        p.update(target_width=tw, target_height=th, planned_width=bw,
                 planned_height=bh, rotation=angle)
        p['x'] = (p['x'] + c['ox'] + float(edit.get('offset_x', 0.))) % width
        p['y'] += c['oy'] + float(edit.get('offset_y', 0.))
        p['region'] = (0., top, float(width), bottom)
        p['wrap'] = True
        p.pop('nominal_height')
        p.pop('serial')
    _validate_positions(placements, width, top, bottom)
    gap_values, horizontal_gaps = [], []
    for i, p in enumerate(placements):
        neighbours, alongside = [], []
        for j, other in enumerate(placements):
            if i == j:
                continue
            dx, dy = _distance(p, other, width)
            neighbours.append(math.hypot(max(0., dx - (p['planned_width'] + other['planned_width']) / 2),
                                         max(0., dy - (p['planned_height'] + other['planned_height']) / 2)))
            if dy < (p['planned_height'] + other['planned_height']) / 2 + 1:
                alongside.append(dx - (p['planned_width'] + other['planned_width']) / 2)
        gap_values.append(min(neighbours) if neighbours else width - p['planned_width'])
        horizontal_gaps.append(min(alongside) if alongside else width - p['planned_width'])
    # The spacing control opens horizontal intervals. A vertically adjacent
    # neighbour may keep the same Euclidean clearance while X genuinely moves;
    # report both, so the no-op gate observes the actual controlled interval.
    mean_gap = sum(horizontal_gaps) / len(horizontal_gaps)
    cycle = dict(period=width, unit_period=width, groups=copies, sequence_length=n,
                 gap=mean_gap, boundary_gap=mean_gap, desired_gap=nominal_gap * c['spacing'],
                 desired_boundary_gap=nominal_gap * c['spacing'], row=0,
                 region=[0., top, float(width), bottom], sequence=order,
                 natural_period=packed_width, arrangement='free_2d')
    for p in placements:
        p['repetition'] = cycle
    slot_metrics = {}
    for index, slot in enumerate(slots):
        rows = [q for q in placements if q['slot_id'] == slot]
        slot_metrics[slot] = dict(copies=len(rows), scale_ceiling=round(slot_caps[index], 4),
            effective_scale=round(slot_scales[index], 4),
            target_width_px=[min(q['target_width'] for q in rows), max(q['target_width'] for q in rows)],
            target_height_px=[min(q['target_height'] for q in rows), max(q['target_height'] for q in rows)],
            rotations_deg=sorted({q['rotation'] for q in rows}),
            free_up_px=round(min(q['y'] - q['planned_height']/2 - top for q in rows),2),
            free_down_px=round(min(bottom - q['y'] - q['planned_height']/2 for q in rows),2))
    metrics = dict(slots=slot_metrics, row_count=0, arrangement='free_2d',
                   placements=count, per_1000px=round(count*1000/width,4),
                   footprint_ratio=round(sum(q['target_width']*q['target_height'] for q in placements)/(width*h),5),
                   mean_gap_px=round(mean_gap,2), gap_axis='horizontal',
                   mean_nearest_clearance_px=round(sum(gap_values)/len(gap_values),2),
                   packing_attempts=attempts+1, pattern_roles=roles)
    payload = dict(engine=ENGINE, placements=placements, assets=snapshot['asset_refs'], pattern_roles=roles,
                   zone_background_refs=snapshot.get('zone_background_refs', {}),
                   zone_colors=snapshot.get('zone_colors', {}),
                   background_tone=snapshot.get('background_tone', 'original'),
                   background_color=snapshot.get('params', {}).get('background_color'),
                   border_ref=snapshot.get('border_ref'), background_ref=snapshot.get('background_ref'))
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    verified = dict(passed=True, errors=[], source_coverage_complete=True, selected_asset_count=n,
                    placement_count=count, row_count=0, complete_group_count=copies,
                    arrangement='free_2d', complete_rotated_bounds=True, pairwise_circular_clearance=True)
    meta = dict(engine=ENGINE, kind=original.MODE_MATRIX['scatter'][0],
                loop_kind=original.MODE_MATRIX['scatter'][0], mode_notice=original.MODE_MATRIX['scatter'][1],
                period_px=width, natural_width=packed_width, height_px=h, dpi=c['dpi'],
                groups=[cycle], specs=specs, metrics=metrics, input_signature=signature, verification=verified)
    return placements, meta



def _structured(snapshot, specs):
    """Complete composition groups with explicit roles and equal zone geometry."""
    c = original._configuration({**snapshot, 'design_density': 'balanced'}, specs,
                                 independent_border=True)
    mode, h, n = c['mode'], c['height'], c['n']
    density = snapshot.get('design_density', 'balanced')
    if density not in previous.DENSITY:
        raise ValueError('请选择有效的画面密度')
    occupancy, gap_ratio = previous.DENSITY[density]
    slots, edits = previous._slots(snapshot)
    roles = pattern_roles(snapshot, slots)
    prepared, groups = [], []
    top, bottom = h * .06, h * .94

    def item(index, nominal, room, role, row=0, group=0):
        angle = c['angle']
        tw, th, bw, bh = original._size(specs[index], nominal, room, angle)
        return dict(asset_index=index, slot_id=slots[index], target_width=tw,
                    target_height=th, planned_width=bw, planned_height=bh,
                    nominal_height=nominal, rotation=angle, role=role, row=row, group=group)

    if mode == 'scene':
        room = bottom - top
        # Space above the grounded group is reserved for declared small accents.
        base = min(room * .82 * occupancy * c['scale'], room - 4)
        primary = [i for i, slot in enumerate(slots) if roles[slot] != 'accent']
        accents = [i for i, slot in enumerate(slots) if roles[slot] == 'accent']
        body = [item(i, base * (.65 if roles[slots[i]] == 'support' else 1.), room,
                     roles[slots[i]]) for i in primary]
        ornaments = [item(i, base * .25, room, 'accent', row=1) for i in accents]
        desired_gap = max(2., room * gap_ratio * .16) * c['spacing']
        # Find the decoration arrangement independently of the editable gap.
        # Otherwise a larger gap can happen to require fewer packing retries,
        # producing a narrower final group and reversing the user's request.
        gap = 2.
        boundary = max(2., base * .18) + gap * 2
        natural = sum(q['planned_width'] for q in body) + gap * (len(body)-1) + boundary
        width = max(16, math.ceil(natural),
                    math.ceil(max((q['planned_width']+6 for q in ornaments),default=0)))
        # Accents belong to THIS complete group and are fitted into actual open
        # space. They are not squeezed into a false decorative horizontal row.
        for attempt in range(10):
            _profile({**snapshot['output_profile'], 'width': width})
            actual_gap = gap + (width - natural) / max(1, len(body)-1)
            cursor = boundary / 2
            placed = []
            for q in body:
                part = {**q, 'x': cursor + q['planned_width']/2,
                        'y': bottom - q['planned_height']/2,
                        'region': (0., top, float(width), bottom), 'wrap': True}
                placed.append(part)
                cursor += q['planned_width'] + actual_gap
            # A single body still needs its centre, not all extra room on one side.
            if len(placed) == 1:
                placed[0]['x'] = width/2
            trial = [dict(q, serial=i) for i,q in enumerate(ornaments)]
            decorated = _pack(trial, width, top, bottom, int(snapshot.get('seed',0)), fixed=placed, decorate_group=True)
            if decorated is not None:
                for q in decorated:
                    q.pop('serial')
                    q.update(region=(0.,top,float(width),bottom),wrap=True)
                prepared = placed + decorated
                break
            width = math.ceil(width * 1.12)
        else:
            raise ValueError('组合中的辅助装饰无法完整放入空隙，请减少辅饰或缩小图案')
        packed_width = width
        width = math.ceil(packed_width + desired_gap * (len(body)+1))
        _profile({**snapshot['output_profile'], 'width': width})
        stretch = width / packed_width
        for q in prepared:
            q['x'] *= stretch
            q['region'] = (0.,top,float(width),bottom)
        primary_positions = prepared[:len(body)]
        actual_boundary = (width + primary_positions[0]['x'] - primary_positions[-1]['x'] -
                           (primary_positions[0]['planned_width']+primary_positions[-1]['planned_width'])/2)
        actual_gaps = [b['x']-a['x']-(a['planned_width']+b['planned_width'])/2
                       for a,b in zip(primary_positions,primary_positions[1:])]
        actual_gap = sum(actual_gaps)/len(actual_gaps) if actual_gaps else actual_boundary
        groups.append(dict(period=width, unit_period=width, groups=1, sequence_length=n,
                           gap=actual_gap, boundary_gap=actual_boundary, desired_gap=desired_gap,
                           desired_boundary_gap=desired_gap*2, row=0,
                           region=[0.,top,float(width),bottom], sequence=list(range(n)),
                           natural_period=packed_width, arrangement='grounded_group_with_accents'))
    else:
        # All partition regions use the same row count and the same height
        # budget. No left region silently gets extra rows and tiny characters.
        count = c['rules'].get('rows',1)
        if type(count) is not int or not 1 <= count <= 4:
            raise ValueError('模板行数必须在一至四行之间')
        all_ids = list(range(n))
        horizontal_zones = 1
        rows = []
        if mode == 'bordered':
            main_ids = [i for i,slot in enumerate(slots) if roles[slot]=='main']
            border_ids = [i for i,slot in enumerate(slots) if roles[slot]=='border']
            rows.append((0, main_ids, .23*h, .77*h, 'main'))
            if border_ids:
                rows.extend([(0,border_ids,.06*h,.195*h,'top-border'),
                             (0,border_ids,.805*h,.94*h,'bottom-border')])
        elif mode == 'stacked':
            halves = [all_ids[:(n+1)//2], all_ids[(n+1)//2:]]
            for zone, ids in enumerate(halves):
                for j in range(count):
                    a = (zone/2 + (.06+.88*j/count)/2)*h
                    b = (zone/2 + (.06+.88*(j+1)/count)/2)*h
                    rows.append((0,ids,a,b,('top-zone','bottom-zone')[zone]))
        else:
            horizontal_zones = 2 if mode=='split' else 3
            parts = [all_ids[i*n//horizontal_zones:(i+1)*n//horizontal_zones]
                     or [all_ids[min(i,n-1)]] for i in range(horizontal_zones)]
            # Split follows its historical ceil-half selection order.
            if mode=='split':
                parts=[all_ids[:(n+1)//2],all_ids[(n+1)//2:]]
            zone_names = ('left-zone','right-zone') if mode=='split' else ('left-panel','middle-panel','right-panel')
            for zone, ids in enumerate(parts):
                for j in range(count):
                    rows.append((zone,ids,top+(bottom-top)*j/count,
                                 top+(bottom-top)*(j+1)/count,zone_names[zone]))
        lanes=[]
        for row_id,(zone, ids, a,b,role) in enumerate(rows):
            room=b-a
            base=min(room*occupancy*c['scale'],room-4)
            row_items=[item(i,base,room,role,row=row_id) for i in ids]
            nominal_gap=max(2.,room*gap_ratio)
            gap=max(2.,nominal_gap*c['spacing'])
            cells=sum(q['planned_width'] for q in row_items)
            natural=cells+gap*len(row_items)
            nominal=cells+nominal_gap*len(row_items)
            lanes.append(dict(zone=zone,items=row_items,top=a,bottom=b,gap=gap,natural=natural,
                              nominal=nominal,ids=ids,row=row_id))
        reference=max(q['nominal'] for q in lanes)
        for lane in lanes:
            lane['repeats']=max(1,math.floor(reference/lane['nominal']+1e-8))
        section_width=max(16,math.ceil(max(q['natural']*q['repeats'] for q in lanes)))
        width=section_width*horizontal_zones
        _profile({**snapshot['output_profile'], 'width': width})
        for lane in lanes:
            # Only whole selected sequences may repeat. Spare room becomes
            # equal spacing, never cropped motifs or a different size tier.
            repeats=lane['repeats']
            period=section_width/repeats
            actual_gap=(period-sum(q['planned_width'] for q in lane['items']))/len(lane['items'])
            left=lane['zone']*section_width
            cycle=dict(period=period,unit_period=width,groups=repeats,sequence_length=len(lane['ids']),
                       gap=actual_gap,boundary_gap=actual_gap,desired_gap=lane['gap'],
                       desired_boundary_gap=lane['gap'],row=lane['row'],
                       region=[left,lane['top'],left+section_width,lane['bottom']],
                       sequence=lane['ids'],natural_period=lane['natural'],arrangement='equal_zone_rows' if mode!='bordered' else 'explicit_border_roles')
            groups.append(cycle)
            for repeat in range(repeats):
                cursor=left+repeat*period+actual_gap/2
                for q in lane['items']:
                    part={**q,'x':cursor+q['planned_width']/2,'y':(lane['top']+lane['bottom'])/2,
                          'group':repeat,'region':(float(left),lane['top'],float(left+section_width),lane['bottom']),
                          'wrap':horizontal_zones==1,'repetition':cycle}
                    prepared.append(part)
                    cursor+=q['planned_width']+actual_gap
    if len(prepared)>original.MAX_PLACEMENTS:
        raise ValueError('完整循环单元包含过多图案，请调整图案或间距')
    # All local edits operate on the saved role geometry without moving another
    # pattern into its place. A conflicting edit is rejected rather than hidden.
    slot_caps={i:min(2.5,min((q['region'][3]-q['region'][1]-4)/q['nominal_height']
                            for q in prepared if q['asset_index']==i)) for i in range(n)}
    slot_scales={i:min(float(edits.get(slots[i],{}).get('scale',1.)),slot_caps[i]) for i in range(n)}
    for q in prepared:
        edit=edits.get(q['slot_id'],{})
        left,a,right,b=q['region']
        angle=q['rotation']+float(edit.get('rotation',0))
        tw,th,bw,bh=original._size(specs[q['asset_index']],q['nominal_height']*slot_scales[q['asset_index']],b-a,angle)
        if mode=='scene' and q['role']!='accent':
            q['y']=b-bh/2  # all main/support feet stay on the same ground
        q.update(target_width=tw,target_height=th,planned_width=bw,planned_height=bh,rotation=angle)
        dx=float(edit.get('offset_x',0));dy=float(edit.get('offset_y',0))
        if q['wrap']:
            q['x']=(q['x']+c['ox']+dx)%width
        else:
            span=right-left
            shifted=left+((q['x']+c['ox']-left)%span)
            q['x']=min(max(shifted,left+bw/2),right-bw/2)+dx
            if q['x']-bw/2<left-1e-7 or q['x']+bw/2>right+1e-7:
                raise ValueError('目标调整会越过分区边界，请减小偏移或图案')
        q['y']+=c['oy']+dy
        if q['y']-bh/2<a-1e-7 or q['y']+bh/2>b+1e-7:
            raise ValueError('目标调整会超出当前区域，请减小偏移或图案')
        q.pop('nominal_height')
        q.setdefault('repetition',groups[0])
    _validate_positions(prepared,width,0.,float(h))
    if {q['asset_index'] for q in prepared}!=set(range(n)):
        raise ValueError('完整单元未包含所有所选图案')
    return _structured_metadata(snapshot,specs,prepared,groups,width,h,c['dpi'],roles,slot_caps,slot_scales)


def _structured_metadata(snapshot,specs,placements,groups,width,h,dpi,roles,slot_caps,slot_scales):
    slots,_=previous._slots(snapshot)
    metrics={}
    for i,slot in enumerate(slots):
        copies=[q for q in placements if q['slot_id']==slot]
        metrics[slot]=dict(copies=len(copies),scale_ceiling=round(slot_caps[i],4),effective_scale=round(slot_scales[i],4),
                          target_width_px=[min(q['target_width'] for q in copies),max(q['target_width'] for q in copies)],
                          target_height_px=[min(q['target_height'] for q in copies),max(q['target_height'] for q in copies)],
                          rotations_deg=sorted({q['rotation'] for q in copies}),
                          free_up_px=round(min(q['y']-q['planned_height']/2-q['region'][1] for q in copies),2),
                          free_down_px=round(min(q['region'][3]-q['y']-q['planned_height']/2 for q in copies),2))
    arrangement=groups[0]['arrangement']
    summary=dict(slots=metrics,row_count=len(groups),arrangement=arrangement,placements=len(placements),
                 per_1000px=round(len(placements)*1000/width,4),
                 footprint_ratio=round(sum(q['target_width']*q['target_height'] for q in placements)/(width*h),5),
                 mean_gap_px=round(sum(g['gap'] for g in groups)/len(groups),2),pattern_roles=roles)
    payload=dict(engine=ENGINE,placements=placements,assets=snapshot['asset_refs'],pattern_roles=roles,
                 zone_background_refs=snapshot.get('zone_background_refs',{}),zone_colors=snapshot.get('zone_colors',{}),
                 background_tone=snapshot.get('background_tone','original'),background_color=snapshot.get('params',{}).get('background_color'),
                 border_ref=snapshot.get('border_ref'),background_ref=snapshot.get('background_ref'))
    signature=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    mode=snapshot['template_mode'];kind,notice=original.MODE_MATRIX[mode]
    verified=dict(passed=True,errors=[],source_coverage_complete=True,selected_asset_count=len(slots),
                  placement_count=len(placements),row_count=len(groups),complete_group_count=sum(g['groups'] for g in groups),
                  arrangement=arrangement,complete_rotated_bounds=True,pairwise_circular_clearance=True)
    metadata=dict(engine=ENGINE,kind=kind,loop_kind=kind,mode_notice=notice,period_px=width,natural_width=width,
                  height_px=h,dpi=dpi,groups=groups,specs=specs,metrics=summary,input_signature=signature,verification=verified)
    return placements,metadata


def _build_with_decorations(snapshot, specs, slots, edits, roles):
    primary = [i for i, slot in enumerate(slots) if roles[slot] != 'decoration']
    accents = [i for i, slot in enumerate(slots) if roles[slot] == 'decoration']
    if not 1 <= len(slots) <= 12 or len(specs) != len(slots):
        raise ValueError('请选择 1–12 个图案并核对其尺寸')
    if any(edits.get(slots[i]) for i in accents):
        raise ValueError('周围装饰不能使用旧版精修参数')
    primary_slots = [slots[i] for i in primary]
    mode = snapshot['template_mode']
    body, metadata = _build({
        **snapshot,
        'asset_refs': [snapshot['asset_refs'][i] for i in primary],
        'pattern_slots': primary_slots,
        'pattern_roles': {slot: roles[slot] for slot in primary_slots} if mode in ROLE_MODES else {},
        'slot_params': {slot: edits[slot] for slot in primary_slots if slot in edits},
    }, [specs[i] for i in primary])

    # The body retains its original sizes, centres and cyclic phase. Only
    # convert its indices back to the full, original user selection.
    primary_groups = {id(group): {**group, 'sequence': [primary[i] for i in group['sequence']]}
                      for group in metadata['groups']}
    for placement in body:
        placement['asset_index'] = primary[placement['asset_index']]
        placement['repetition'] = primary_groups[id(placement['repetition'])]
    width, height = metadata['period_px'], metadata['height_px']
    main = [part for part in body if roles[part['slot_id']] == 'main']
    decorations = place_decorations(mode, width, height, body, main,
                                   [(i, slots[i], specs[i]) for i in accents],
                                   int(snapshot.get('seed', 0)))
    placements = [*body, *decorations]
    if len(placements) > original.MAX_PLACEMENTS:
        raise ValueError('完整循环单元包含过多图案，请减少装饰或主体')
    metadata['groups'] = list(primary_groups.values())
    metadata['specs'] = specs
    metrics = metadata['metrics']
    slot_metrics = metrics['slots']
    for part in decorations:
        target_w, target_h = part['target_width'], part['target_height']
        top, bottom = part['region'][1], part['region'][3]
        half_height = part['planned_height'] / 2
        slot_metrics[part['slot_id']] = dict(copies=1, target_width_px=[target_w, target_w],
            target_height_px=[target_h, target_h], rotations_deg=[0.],
            free_up_px=round(part['y'] - half_height - top, 2),
            free_down_px=round(bottom - part['y'] - half_height, 2))
    metrics.update(slots={slot: slot_metrics[slot] for slot in slots}, pattern_roles=roles,
        placements=len(placements), per_1000px=round(len(placements) * 1000 / width, 4),
        footprint_ratio=round(sum(part['target_width'] * part['target_height']
                                  for part in placements) / (width * height), 5),
        decorations=len(decorations))
    metadata['verification'].update(selected_asset_count=len(slots), placement_count=len(placements),
        decoration_count=len(decorations), decorations_clear_of_patterns=True)
    binding = (metadata['input_signature'], snapshot['asset_refs'], roles,
               int(snapshot.get('seed', 0)), decorations)
    metadata['input_signature'] = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return placements, metadata


def _build(snapshot, specs):
    supplied = snapshot.get('pattern_roles', {})
    if isinstance(supplied, dict) and 'decoration' in supplied.values():
        slots, edits = previous._slots(snapshot)
        return _build_with_decorations(snapshot, specs, slots, edits, pattern_roles(snapshot, slots))
    if snapshot['template_mode'] == 'scatter':
        return _scatter(snapshot, specs)
    if snapshot['template_mode'] in ('scene','bordered','split','panels','stacked'):
        return _structured(snapshot,specs)
    slots,_=previous._slots(snapshot)
    pattern_roles(snapshot,slots)
    placements, metadata = previous._build(snapshot, specs)
    metadata['engine'] = ENGINE
    metadata['input_signature'] = hashlib.sha256((ENGINE + ':' + metadata['input_signature']).encode()).hexdigest()
    return placements, metadata


def resolve(snapshot, resolve_asset=None, *, specs=None):
    if snapshot.get('layout_engine') != ENGINE or snapshot.get('composite_ref'):
        raise ValueError('此排版引擎只处理明确绑定的新作品')
    specs = (original._normalize_specs(specs) if specs is not None else
             original.read_specs(snapshot['asset_refs'], resolve_asset))
    result = deepcopy(snapshot)
    result.setdefault('output_profile_source', deepcopy(result['output_profile']))
    result['output_profile'] = deepcopy(result['output_profile_source'])
    result.pop('loop', None)
    _, result['loop_layout'] = _build(result, specs)
    result['output_profile']['width'] = result['loop_layout']['period_px']
    return result


def plan(snapshot, specs=None):
    saved = snapshot['loop_layout']
    placements, metadata = _build(snapshot, original._normalize_specs(specs if specs is not None else saved['specs']))
    if metadata != saved or snapshot['output_profile']['width'] != metadata['period_px']:
        raise ValueError('保存的排法与本次图案或底纹不一致，请重新生成')
    return placements


def estimate(snapshot):
    placements = plan(snapshot)
    w, h = snapshot['output_profile']['width'], snapshot['output_profile']['height']
    sizes = {(p['asset_index'], p['target_width'], p['target_height'], p['rotation']): p for p in placements}
    return (png_space(w, h) + png_space(min(w,3600), min(h,1200)) +
            sum(png_space(p['planned_width'],p['planned_height']) for p in sizes.values()))


def compose(canvas, snapshot, resolve_asset, master_path):
    specs = original.read_specs(snapshot['asset_refs'], resolve_asset)
    placements = plan(snapshot, specs)
    transforms = original.paint(canvas, snapshot, resolve_asset, master_path, specs, placements, ENGINE)
    for row, placement in zip(transforms, placements):
        row['slot_id'] = placement['slot_id']
    return transforms
