"""Resolution of a complete foreground repeat, independent of the background texture."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import random

from . import loop_layout as original
from .imaging import _profile, png_space

ENGINE = 'seamless-unit-v2'
MODES = original.MODES
ZONE_IDS = {'split': ('left', 'right'), 'panels': ('left', 'center', 'right'), 'stacked': ('top', 'bottom')}
DENSITY = {'airy': (0.55, 0.45), 'balanced': (0.72, 0.28), 'rich': (0.86, 0.16)}


@dataclass
class Lane:
    indices: list
    role: str
    top: float = 0.08
    bottom: float = 0.92
    phase: float = 0.0
    repeat: bool = True
    factors: tuple = ()
    rotations: tuple = ()
    roles: tuple = ()


def _sections(mode, n, rows):
    ids = list(range(n))

    def lanes(indices, role, count, stagger=False):
        return [
            Lane(
                indices,
                role,
                0.08 + 0.84 * j / count,
                0.08 + 0.84 * (j + 1) / count,
                0.5 / len(indices) if stagger and j % 2 else 0.0,
            )
            for j in range(count)
        ]

    if mode in ('grid', 'stagger', 'scatter'):
        return [lanes(ids, mode, rows, mode == 'stagger')]
    if mode in ('single', 'fullwidth'):
        return [[Lane(ids, 'complete' if mode == 'fullwidth' else 'motif')]]
    if mode in ('alternating', 'opposed'):
        seq = ids * (2 if n % 2 else 1)
        return [
            [
                Lane(
                    seq,
                    mode,
                    factors=tuple(0.58 if mode == 'alternating' and i % 2 else 1.0 for i in range(len(seq))),
                    rotations=tuple(180 if mode == 'opposed' and i % 2 else 0 for i in range(len(seq))),
                )
            ]
        ]
    if mode in ('split', 'stacked'):
        partition = (n + 1) // 2
        left, right = ids[:partition], ids[partition:]
        if mode == 'stacked':
            return [[Lane(left, 'top-zone', 0.08, 0.50), Lane(right, 'bottom-zone', 0.50, 0.92)]]
        return [lanes(left, 'left-zone', 2), lanes(right, 'right-zone', 2)]
    if mode == 'panels':
        # Three consecutive subgroups; one or two inputs retain useful distinct roles.
        groups = [ids[i * n // 3 : (i + 1) * n // 3] or [ids[min(i, n - 1)]] for i in range(3)]
        return [
            lanes(groups[0], 'left-panel', 2),
            [Lane(groups[1], 'middle-panel')],
            [Lane(groups[2], 'right-panel')],
        ]
    if mode == 'bordered':
        border_lanes = [Lane([0], 'main', 0.23, 0.77)]
        if n > 1:
            border_lanes.extend(
                [Lane(ids[1:], 'top-border', 0.08, 0.195), Lane(ids[1:], 'bottom-border', 0.805, 0.92)]
            )
        return [border_lanes]
    if mode == 'scene':
        return [
            [Lane(ids, 'scene', factors=tuple([1.0] + [(0.76, 0.84, 0.72)[i % 3] for i in range(n - 1)]))]
        ]
    inner = ids[1:] or [0]
    if mode == 'ends':
        return [
            [
                Lane(
                    [0, *inner, 0],
                    'ends',
                    repeat=False,
                    factors=(1.0, *([0.6] * len(inner)), 1.0),
                    roles=('left-end', *(['inner'] * len(inner)), 'right-end'),
                )
            ]
        ]
    return [[Lane([0, n - 1], 'ends-open', repeat=False, roles=('left-end', 'right-end'))]]


def _slots(snapshot):
    refs = snapshot['asset_refs']
    slots = snapshot.get('pattern_slots', [f'pattern-{i+1}' for i in range(len(refs))])
    if (
        not isinstance(slots, list)
        or len(slots) != len(refs)
        or not all(isinstance(key, str) and 0 < len(key) <= 128 for key in slots)
        or len(set(slots)) != len(slots)
    ):
        raise ValueError('图案编号与素材不一致')
    edits = snapshot.get('slot_params', {})
    if not isinstance(edits, dict) or set(edits) - set(slots):
        raise ValueError('精修目标已变化，请重新选择图案')
    for change in edits.values():
        if not isinstance(change, dict) or set(change) - {'scale', 'rotation', 'offset_x', 'offset_y'}:
            raise ValueError('精修参数暂不支持')
        for key, val in change.items():
            original._number(val, '精修数值无效', positive=key == 'scale')
    return slots, edits


def _build(snapshot, specs):
    # Reuse the validated mode/rule/profile contract. Density is applied below
    # to real lane occupancy and pixel clearance, never to provider text alone.
    c = original._configuration({**snapshot, 'design_density': 'balanced'}, specs, independent_border=True)
    mode, h = c['mode'], c['height']
    density = snapshot.get('design_density', 'balanced')
    if density not in DENSITY:
        raise ValueError('请选择有效的画面密度')
    occupancy, gap_ratio = DENSITY[density]
    slots, edits = _slots(snapshot)
    rows = c['rules'].get('rows', 3 if density == 'rich' else 2)
    if type(rows) is not int or not 1 <= rows <= 4:
        raise ValueError('模板行数必须在一至四行之间')
    sections = _sections(mode, c['n'], rows)
    rng = random.Random(int(snapshot.get('seed', 0)))
    angles = [-18.0, -9.0, 9.0, 18.0]
    rng.shuffle(angles)
    if mode == 'scatter':
        # Small selections still get several distinct positions per period.
        # Every lane contains the entire ordered input set before shuffling;
        # this avoids the recognizable diagonal columns of staggered grids.
        previous = None
        for lane in sections[0]:
            seq = list(lane.indices) * math.ceil(4 / len(lane.indices))
            rng.shuffle(seq)
            if seq == previous and len(set(seq)) > 1:
                seq = seq[1:] + seq[:1]
            lane.indices = seq
            lane.factors = tuple(rng.choice((0.76, 0.86, 1.0)) for _ in seq)
            previous = seq
    # Use one effective multiplier per slot for every role and repetition.
    # Independent caps on large and small variants destroy their ratio.
    slot_caps = {i: 2.5 for i in range(len(slots))}
    for section in sections:
        for lane in section:
            room = (lane.bottom - lane.top) * h
            base = min(room - 4, room * occupancy * c['scale'])
            if base <= 0:
                raise ValueError('当前高度容不下完整图案，请调整行数或输出高度')
            for i, index in enumerate(lane.indices):
                factor = lane.factors[i] if lane.factors else 1.0
                slot_caps[index] = min(slot_caps[index], (room - 4) / (base * factor))
    slot_scales = {
        i: min(float(edits.get(key, {}).get('scale', 1.0)), slot_caps[i]) for i, key in enumerate(slots)
    }
    serial = 0
    prepared = []
    for section in sections:
        band = []
        for lane in section:
            top, bottom = lane.top * h, lane.bottom * h
            room = bottom - top
            # Cap the group's baseline ONCE, before applying variant ratios.
            base = min(room - 4, room * occupancy * c['scale'])
            nominal_gap = max(2.0, room * gap_ratio)
            gap = max(2.0, nominal_gap * c['spacing'])
            elements = []
            for i, index in enumerate(lane.indices):
                edit = edits.get(slots[index], {})
                angle = c['angle'] + float(edit.get('rotation', 0))
                if mode == 'scatter':
                    angle += angles[serial % len(angles)]
                if lane.rotations:
                    angle += lane.rotations[i]
                factor = lane.factors[i] if lane.factors else 1.0
                size = original._size(specs[index], base * factor * slot_scales[index], room, angle)
                dx, dy = (float(edit.get(k, 0)) for k in ('offset_x', 'offset_y'))
                elements.append((index, lane.roles[i] if lane.roles else lane.role, size, angle, dx, dy))
                serial += 1
            boundary = gap
            nominal_boundary = nominal_gap
            if mode in ('ends', 'ends_open'):
                end_width = max(elements[0][2][2], elements[-1][2][2])
                boundary = max(gap, 0.35 * end_width)
                nominal_boundary = max(nominal_gap, 0.35 * end_width)
                if mode == 'ends_open':
                    nominal_gap = (
                        max(h * 1.2, 0.7 * (elements[0][2][2] + elements[-1][2][2])) * gap_ratio / 0.28
                    )
                    gap = max(2.0, nominal_gap * c['spacing'])
            cells = sum(size[2] for _, _, size, _, _, _ in elements)
            width = cells + gap * (len(elements) - 1) + boundary
            reference_width = cells + nominal_gap * (len(elements) - 1) + nominal_boundary
            band.append((lane, elements, gap, boundary, cells, width, reference_width))
        prepared.append(band)

    # Equal, integer-aligned sections. All lanes retain their full sequence.
    # Set repeat counts from the unedited spacing. Changing spacing must not
    # insert an extra group and unexpectedly bring existing copies closer.
    reference = max(row[-1] for band in prepared for row in band)

    def repeat_count(row):
        return max(1, math.floor(reference / row[-1] + 1.0e-8)) if row[0].repeat else 1

    section_width = max(16, math.ceil(max(row[-2] * repeat_count(row) for band in prepared for row in band)))
    width = section_width * len(sections)
    _profile({**snapshot['output_profile'], 'width': width})
    placements, diagnostics = [], []
    for z, band in enumerate(prepared):
        for row in band:
            lane, elements, requested, seam, cells, natural, _ = row
            groups = repeat_count(row)
            if len(placements) + groups * len(elements) > original.MAX_PLACEMENTS:
                raise ValueError('完整循环单元包含过多图案，请调整图案尺寸或间隔')
            period = section_width / groups
            # Normal interior gaps remain as requested. Spread unavoidable
            # residue evenly for repeating patterns; finite panels keep their clearance.
            extra = max(0.0, period - natural)
            gap = requested + extra / len(elements)
            boundary = seam + extra / len(elements)
            top, bottom = lane.top * h, lane.bottom * h
            row_id = len(diagnostics)
            cycle = dict(
                period=period,
                unit_period=width,
                groups=groups,
                sequence_length=len(elements),
                gap=gap,
                boundary_gap=boundary,
                desired_gap=requested,
                desired_boundary_gap=seam,
                row=row_id,
                region=[z * section_width, top, (z + 1) * section_width, bottom],
                sequence=lane.indices,
                natural_period=natural,
            )
            diagnostics.append(cycle)
            phase = (
                (0.26 + rng.random() * 0.17) * period / len(elements) * row_id
                if mode == 'scatter'
                else lane.phase * period
            )
            for group in range(groups):
                cursor = z * section_width + group * period + phase + boundary / 2
                for index, role, size, angle, dx, dy in elements:
                    tw, th, bw, bh = size
                    cell = bw
                    x = cursor + cell / 2 + dx
                    y = bottom - bh / 2 if mode == 'scene' else (bottom + top) / 2
                    if mode == 'scatter':
                        x += rng.uniform(-0.28, 0.28) * min(gap, boundary)
                        y += rng.uniform(-0.46, 0.46) * max(0.0, bottom - top - bh)
                    if len(sections) > 1:
                        # Zone layouts shift inside their own section: a global
                        # circular shift would move a motif into another panel,
                        # which contradicts the per-zone composition (and used
                        # to pass because the crossing check ran before wrap).
                        left, right = z * section_width, (z + 1) * section_width
                        span = right - left
                        if bw > span + 1e-7:
                            raise ValueError('图案比分区还宽，无法在分区内完整排出')
                        candidate = x + c['ox']
                        shifted = left + ((candidate - left) % span)
                        options = (shifted, shifted - span, shifted + span)
                        fit = next((value for value in options
                                    if value - bw / 2 >= left - 1e-7 and value + bw / 2 <= right + 1e-7), None)
                        # A motif that would leave its panel stops at the panel
                        # edge instead of crossing into the neighbour.
                        x = fit if fit is not None else min(max(candidate, left + bw / 2), right - bw / 2)
                    else:
                        x = (x + c['ox'] % width) % width
                    y = max(top + bh / 2, min(bottom - bh / 2, y + c['oy'] + dy))
                    placements.append(
                        dict(
                            asset_index=index,
                            slot_id=slots[index],
                            x=x,
                            y=y,
                            target_width=tw,
                            target_height=th,
                            planned_width=bw,
                            planned_height=bh,
                            rotation=angle,
                            role=role,
                            group=group,
                            row=row_id,
                            repetition=cycle,
                            region=(0.0, top, float(width), bottom),
                            wrap=True,
                        )
                    )
                    cursor += cell + gap
    # Verify pairwise horizontal clearance in each disjoint lane, including
    # the wrap neighbor. A targeted translation must never move another slot.
    for row_id in range(len(diagnostics)):
        row = sorted((p for p in placements if p['row'] == row_id), key=lambda p: p['x'])
        for i, first in enumerate(row):
            other = row[(i + 1) % len(row)]
            distance = other['x'] - first['x'] + (width if i + 1 == len(row) else 0.0)
            if distance + 1e-7 < (first['planned_width'] + other['planned_width']) / 2:
                raise ValueError('目标位置会与相邻图案重叠，请减小横向偏移或增大间距')
    if {p['asset_index'] for p in placements} != set(range(c['n'])):
        raise ValueError('完整单元未包含所有图案')
    # Hash all resolved placement geometry to bind zone/slot offsets at commit.
    hash_payload = [
        (p['slot_id'], p['role'], p['x'], p['y'], p['target_width'], p['target_height'], p['rotation'])
        for p in placements
    ]
    signature = hashlib.sha256(
        json.dumps(
            [
                hash_payload,
                snapshot['asset_refs'],
                snapshot.get('zone_background_refs', {}),
                snapshot.get('zone_colors', {}),
                snapshot.get('background_tone', 'original'),
                snapshot.get('params', {}).get('background_color'),
                snapshot.get('border_ref'),
                snapshot.get('background_ref'),
            ],
            separators=(',', ':'),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    slot_metrics = {}
    for i, slot in enumerate(slots):
        copies = [p for p in placements if p['asset_index'] == i]
        slot_metrics[slot] = dict(
            copies=len(copies),
            scale_ceiling=round(slot_caps[i], 4),
            effective_scale=round(slot_scales[i], 4),
            target_width_px=[min(p['target_width'] for p in copies), max(p['target_width'] for p in copies)],
            target_height_px=[
                min(p['target_height'] for p in copies),
                max(p['target_height'] for p in copies),
            ],
            rotations_deg=sorted({p['rotation'] for p in copies}),
            free_up_px=round(min(p['y'] - p['planned_height'] / 2 - p['region'][1] for p in copies), 2),
            free_down_px=round(min(p['region'][3] - p['planned_height'] / 2 - p['y'] for p in copies), 2),
        )
    metrics = dict(
        slots=slot_metrics,
        row_count=len(diagnostics),
        placements=len(placements),
        per_1000px=round(len(placements) * 1000 / width, 4),
        footprint_ratio=round(
            sum(p['target_width'] * p['target_height'] for p in placements) / (width * h), 5
        ),
        mean_gap_px=round(sum(row['gap'] for row in diagnostics) / len(diagnostics), 2),
    )
    verified = dict(
        passed=True,
        errors=[],
        source_coverage_complete=True,
        selected_asset_count=c['n'],
        placement_count=len(placements),
        row_count=len(diagnostics),
        complete_group_count=sum(g['groups'] for g in diagnostics),
    )
    meta = dict(
        engine=ENGINE,
        kind=original.MODE_MATRIX[mode][0],
        loop_kind=original.MODE_MATRIX[mode][0],
        mode_notice=original.MODE_MATRIX[mode][1],
        period_px=width,
        natural_width=width,
        height_px=h,
        dpi=c['dpi'],
        groups=diagnostics,
        specs=specs,
        metrics=metrics,
        input_signature=signature,
        verification=verified,
    )
    return placements, meta


def resolve(snapshot, resolve_asset=None, *, specs=None):
    if snapshot.get('layout_engine') != ENGINE or snapshot.get('composite_ref'):
        raise ValueError('此排版引擎只处理明确绑定的新作品')
    specs = (
        original._normalize_specs(specs)
        if specs is not None
        else original.read_specs(snapshot['asset_refs'], resolve_asset)
    )
    result = deepcopy(snapshot)
    result.setdefault('output_profile_source', deepcopy(result['output_profile']))
    result['output_profile'] = deepcopy(result['output_profile_source'])
    result.pop('loop', None)
    _, result['loop_layout'] = _build(result, specs)
    result['output_profile']['width'] = result['loop_layout']['period_px']
    return result


def plan(snapshot, specs=None):
    saved = snapshot['loop_layout']
    placements, meta = _build(
        snapshot, original._normalize_specs(specs if specs is not None else saved['specs'])
    )
    if meta != saved or snapshot['output_profile']['width'] != meta['period_px']:
        raise ValueError('保存的排法与本次图案或底纹不一致，请重新生成')
    return placements


def estimate(snapshot):
    placements = plan(snapshot)
    w, h = snapshot['output_profile']['width'], snapshot['output_profile']['height']
    sizes = {(p['asset_index'], p['target_width'], p['target_height'], p['rotation']): p for p in placements}
    return (
        png_space(w, h)
        + png_space(min(w, 3600), min(h, 1200))
        + sum(png_space(p['planned_width'], p['planned_height']) for p in sizes.values())
    )


def compose(canvas, snapshot, resolve_asset, master_path):
    specs = original.read_specs(snapshot['asset_refs'], resolve_asset)
    placements = plan(snapshot, specs)
    transforms = original.paint(canvas, snapshot, resolve_asset, master_path, specs, placements, ENGINE)
    for row, p in zip(transforms, placements):
        row['slot_id'] = p['slot_id']
    return transforms
