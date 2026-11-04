"""Height-derived, aspect-preserving horizontal repeat units.

Only new explicitly bound snapshots use this module. ``resolve`` creates a new
snapshot; no old profile, source, or historical engine is rewritten. A unit is
one complete selected sequence (or a declared finite panel), never a sample of
a longer, arbitrarily truncated fixed-width render.
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import tempfile

from PIL import Image

ENGINE = 'seamless-unit-v1'
DENSITIES = ('airy', 'balanced', 'rich')
MAX_PLACEMENTS = 4800
MODE_MATRIX = {
    'grid': ('sequence', '完整序列逐行排列，各行共用一个循环周期。'),
    'stagger': ('sequence', '完整序列逐行错位，隔行错开半个平均位置。'),
    'scatter': ('sequence', '完整序列作固定散点变化，整套散点随单元重复。'),
    'single': ('sequence', '一行完整序列，两侧半间隔在拼接时合为一个间隔。'),
    'alternating': ('sequence', '完整顺序和大小相位一起闭合，奇数图案使用两套序列。'),
    'opposed': ('sequence', '完整顺序和正倒相位一起闭合，倒置为180度旋转。'),
    'stacked': ('sequence', '上下分区共用周期，每个分区保留自己的完整图案序列。'),
    'bordered': ('sequence', '主图和上下边饰共用周期，短序列只增加完整组和间隔。'),
    'scene': ('sequence', '完整场景组合按同一底线排列，整组循环。'),
    'ends': ('panel', '两端主图和一次完整中间辅图序列作为面板循环，接缝保留主图间隔。'),
    'ends_open': ('panel', '两端留白为完整面板；连续打印重复整个面板，不代表整条丝带只有两个端图。'),
    'fullwidth': ('panel', '整幅定位保留完整设计比例；连续打印重复整个面板。'),
    'split': ('panel', '完整左右分区作为面板循环，横向偏移使两个分区整体移动。'),
    'panels': ('panel', '完整三区拼接作为面板循环，横向偏移使三个区整体移动。'),
}
MODES = tuple(MODE_MATRIX)


def read_specs(refs, resolve_asset):
    """Read full alpha bounds, including faint pixels; never change inputs."""
    from .layout_quality import _specs
    return _normalize_specs(_specs(refs, resolve_asset))


def _normalize_specs(specs):
    result = []
    for source in specs:
        try:
            width, height = int(source['width']), int(source['height'])
            bbox = tuple(int(v) for v in source.get('bbox', (0, 0, width, height)))
            source_size = tuple(int(v) for v in source.get('source_size', (width, height)))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError('图案尺寸记录不完整') from exc
        if (width < 1 or height < 1 or len(bbox) != 4 or len(source_size) != 2
                or bbox[0] < 0 or bbox[1] < 0 or bbox[2] > source_size[0]
                or bbox[3] > source_size[1] or bbox[2] - bbox[0] != width
                or bbox[3] - bbox[1] != height):
            raise ValueError('图案可见内容尺寸记录不正确')
        result.append(dict(width=width, height=height, bbox=list(bbox), source_size=list(source_size)))
    return result


def _number(value, message, *, positive=False):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(message)
    return number


def _integer_period(value):
    number = _number(value, '循环周期必须为正整数像素', positive=True)
    if not number.is_integer():
        raise ValueError('循环周期必须为正整数像素')
    return int(number)


def _configuration(snapshot, specs, *, independent_border=False):
    from .imaging import PARAM_DEFAULTS, _profile
    refs = snapshot.get('asset_refs', [])
    mode = snapshot.get('template_mode', 'stagger')
    if mode not in MODES or not 1 <= len(refs) <= 12 or len(specs) != len(refs):
        raise ValueError('排版模式、图案数量或尺寸记录不正确')
    n = len(refs)
    if mode == 'bordered' and n < 2 and not independent_border:
        raise ValueError('上下边饰至少选择两个图案')
    if mode == 'fullwidth' and n != 1:
        raise ValueError('整幅定位需要一张完整设计图')
    if mode == 'ends_open' and n not in (1, 2):
        raise ValueError('两端留白请选择一张或两张图案')
    if mode in ('split', 'stacked') and n < 2:
        raise ValueError('分区排版至少选择两个图案')
    profile = snapshot['output_profile']
    # The former configured width has no geometric authority for this engine.
    # Height, DPI and format are still validated through the internal contract.
    _, height, dpi = _profile({**profile, 'width': 16})
    density = snapshot.get('design_density', 'balanced')
    if density not in DENSITIES:
        raise ValueError('请选择有效的排版疏密')
    density_scale, density_gap = {'airy': (.82, 1.35), 'balanced': (1., 1.), 'rich': (1.08, .7)}[density]
    params = {**PARAM_DEFAULTS, **snapshot.get('params', {})}
    rules = snapshot.get('template_rules', {})
    scale = (_number(params['scale'], '图案大小不正确', positive=True)
             * _number(rules.get('motif_ratio', .27), '模板图案大小不正确', positive=True) / .27
             * density_scale)
    spacing = (_number(params['spacing'], '图案间距不正确', positive=True)
               * _number(rules.get('step_ratio', .64), '模板间距不正确', positive=True) / .64
               * density_gap)
    if not math.isfinite(scale) or not math.isfinite(spacing):
        raise ValueError('图案大小或间距超出本地几何范围')
    angle = _number(params['rotation'], '图案旋转角度不正确')
    ox = _number(params['offset_x'], '图案横向位置不正确')
    oy = _number(params['offset_y'], '图案纵向位置不正确')
    return dict(mode=mode, n=n, height=height, dpi=dpi, scale=scale, spacing=spacing,
                angle=angle, ox=ox, oy=oy, rules=rules, density=density)


def _size(spec, target_height, maximum_height, angle):
    """Fit complete rotated content only to height, never to a fixed width."""
    from .imaging import MAX_PIXELS
    radians = math.radians(angle % 360)
    cosine, sine = abs(math.cos(radians)), abs(math.sin(radians))
    if cosine < 1e-12: cosine = 0.
    if sine < 1e-12: sine = 0.
    rotated_height = spec['width'] * sine + spec['height'] * cosine
    capacity = maximum_height - 4
    if capacity < 1:
        raise ValueError('配置高度容不下完整图案安全区域，请调整内部高度或行数')
    ratio = min(target_height, capacity) / rotated_height
    if min(spec['width'] * ratio, spec['height'] * ratio) < 1:
        raise ValueError('图案比例过于狭长，当前配置高度无法保持完整比例，请调整图案大小或内部高度')
    tw, th = max(1, int(spec['width'] * ratio)), max(1, int(spec['height'] * ratio))
    bw, bh = math.ceil(tw * cosine + th * sine) + 2, math.ceil(tw * sine + th * cosine) + 2
    if tw * th > MAX_PIXELS or bw * bh > MAX_PIXELS or bw > 16000:
        raise ValueError('完整图案的等比尺寸超出本地资源范围，请减少图案大小或调整内部高度')
    if bh > maximum_height + 1e-7:
        raise ValueError('配置高度容不下完整旋转图案，请调整内部高度或行数')
    return tw, th, bw, bh


def _signature(snapshot, specs):
    from .imaging import PARAM_DEFAULTS
    params = {**PARAM_DEFAULTS, **snapshot.get('params', {})}
    payload = dict(asset_refs=snapshot['asset_refs'], mode=snapshot['template_mode'],
                   density=snapshot.get('design_density', 'balanced'), seed=snapshot.get('seed', 0),
                   rules=snapshot.get('template_rules', {}),
                   params={key: params[key] for key in ('scale', 'spacing', 'rotation', 'offset_x', 'offset_y')},
                   profile={key: snapshot['output_profile'].get(key) for key in ('height', 'dpi', 'format')},
                   specs=specs)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _build(snapshot, specs, *, background_period=None, target_period=None):
    c = _configuration(snapshot, specs)
    mode, n, h = c['mode'], c['n'], c['height']
    scale, spacing, angle = c['scale'], c['spacing'], c['angle']
    all_ids = list(range(n))
    sections = []

    def make_row(indices, top, bottom, nominal_height, occupancy, role, *, variants=None,
                 phase=0., center_y=None, baseline=False, scatter=False, repeat=True,
                 boundary_gap=None, internal_gap=None):
        variants = variants or [(index, 1., 0., role) for index in indices]
        sizes = [_size(specs[index], nominal_height * occupancy * factor * scale,
                       bottom - top, angle + extra) for index, factor, extra, _ in variants]
        gap = max(2., nominal_height * .16 * spacing) if internal_gap is None else internal_gap
        boundary = gap if boundary_gap is None else boundary_gap
        natural = sum(size[2] for size in sizes) + (len(sizes) - 1) * gap + boundary
        return dict(variants=variants, sizes=sizes, top=top, bottom=bottom,
                    center_y=(top + bottom) / 2 if center_y is None else center_y,
                    baseline=baseline, scatter=scatter, repeat=repeat, phase=phase,
                    desired_gap=gap, desired_boundary_gap=boundary, natural=natural, role=role)

    def lane(row, count):
        if count <= 2:
            lane_height = h / count
            top, bottom = max(h * .08, row * lane_height), min(h * .92, (row + 1) * lane_height)
            nominal = lane_height * (1 - 2 * (.12 if count == 1 else .16))
            return top, bottom, nominal, (row + .5) * lane_height, 1.
        lane_height = h * .84 / count
        top = h * .08 + row * lane_height
        return top, top + lane_height, lane_height - h * .01, top + lane_height / 2, .90

    def lane_row(indices, row, count, role, **kwargs):
        top, bottom, nominal, cy, occupancy = lane(row, count)
        return make_row(indices, top, bottom, nominal, occupancy, role, center_y=cy, **kwargs)

    def section(rows, role):
        sections.append(dict(rows=rows, role=role, natural=max(row['natural'] for row in rows)))

    if mode in ('grid', 'stagger', 'scatter'):
        try:
            count = int(c['rules'].get('rows', 3 if c['density'] == 'rich' else 2))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('模板行数不正确') from exc
        if not 1 <= count <= 4:
            raise ValueError('模板行数必须在一至四行之间')
        rows = []
        for row in range(count):
            # A grid has aligned columns even when adjacent designs have very
            # different aspects. Stagger's phase, rather than a changed source
            # order, is the explicit difference between those two modes.
            indices = all_ids
            rows.append(lane_row(indices, row, count, 'scatter' if mode == 'scatter' else 'motif',
                                 phase=.5 / n if mode == 'stagger' and row % 2 else 0., scatter=mode == 'scatter'))
        section(rows, mode)
    elif mode == 'single':
        section([make_row(all_ids, h * .08, h * .92, h * .84, .76 / .84, 'motif')], mode)
    elif mode in ('alternating', 'opposed'):
        count = math.lcm(2, n)
        variants = [(i % n, .58 if i % 2 and mode == 'alternating' else 1.,
                     180. if i % 2 and mode == 'opposed' else 0., mode) for i in range(count)]
        section([make_row(all_ids, h * .08, h * .92, h * .84, .76 / .84, mode, variants=variants)], mode)
    elif mode == 'stacked':
        half = (n + 1) // 2
        section([lane_row(all_ids[:half], 0, 2, 'top-zone'),
                 lane_row(all_ids[half:], 1, 2, 'bottom-zone')], mode)
    elif mode == 'bordered':
        section([make_row([0], h * .23, h * .77, h * .54, 1., 'main'),
                 make_row(all_ids[1:], h * .08, h * .18, h * .10, 1., 'top-border'),
                 make_row(all_ids[1:], h * .82, h * .92, h * .10, 1., 'bottom-border')], mode)
    elif mode == 'scene':
        factors = [1.] + [(.76, .84, .72)[(i - 1) % 3] for i in range(1, n)]
        section([make_row(all_ids, h * .08, h * .92, h * .84, .76 / .84, mode,
                          variants=[(i, factors[i], 0., mode) for i in all_ids], baseline=True)], mode)
    elif mode in ('ends', 'ends_open'):
        main = _size(specs[0], h * .84 * .92 * scale, h * .84, angle)
        # Only ends_open assigns a second full-size end design. In ends, the
        # second selected source is an inner motif, fitted below at the actual
        # small height; validating it as a large end can reject a valid unit.
        other = (_size(specs[1], h * .84 * .92 * scale, h * .84, angle)
                 if mode == 'ends_open' and n == 2 else main)
        gap = max(2., h * .84 * .16 * spacing)
        boundary = max(gap, .35 * max(main[2], other[2] if mode == 'ends_open' else main[2]))
        if mode == 'ends':
            inner = all_ids[1:] or [0]
            # The small target derives from fitted main height; density and
            # scale are already accounted for, preserving main/inner hierarchy.
            small_factor = max(1., main[3] - 2.) * .60 / (h * .84 * .92 * scale)
            variants = [(0, 1., 0., 'left-end')] + [(i, small_factor, 0., 'inner') for i in inner] + [(0, 1., 0., 'right-end')]
            section([make_row(all_ids, h * .08, h * .92, h * .84, .92, 'ends', variants=variants,
                              repeat=False, boundary_gap=boundary, internal_gap=gap)], mode)
        else:
            blank = max(h * 1.20 * spacing, (main[2] + other[2]) * .70)
            variants = [(0, 1., 0., 'left-end'), (1 if n == 2 else 0, 1., 0., 'right-end')]
            section([make_row(all_ids, h * .08, h * .92, h * .84, .92, 'ends-open', variants=variants,
                              repeat=False, boundary_gap=boundary, internal_gap=blank)], mode)
    elif mode == 'fullwidth':
        row = make_row([0], h * .08, h * .92, h * .84, 1., 'complete', repeat=False)
        row['desired_boundary_gap'] = max(row['desired_gap'], row['sizes'][0][2] * .04)
        row['natural'] = row['sizes'][0][2] + row['desired_boundary_gap']
        section([row], mode)
    elif mode == 'split':
        half = (n + 1) // 2
        for ids, role in ((all_ids[:half], 'left-zone'), (all_ids[half:], 'right-zone')):
            section([lane_row(ids[row % len(ids):] + ids[:row % len(ids)], row, 2, role)
                     for row in range(2)], role)
    elif mode == 'panels':
        section([lane_row(all_ids[row % n:] + all_ids[:row % n], row, 2, 'left-panel')
                 for row in range(2)], 'left-panel')
        section([make_row(all_ids, h * .08, h * .92, h * .84, .76 / .84, 'middle-panel')], 'middle-panel')
        section([make_row([0], h * .08, h * .92, h * .84, .92, 'right-panel', repeat=False)], 'right-panel')

    natural_width = max(16, math.ceil(sum(item['natural'] for item in sections)))
    width = natural_width
    if target_period is not None:
        target_period = _integer_period(target_period)
        if target_period < natural_width:
            raise ValueError('指定循环周期小于完整序列的自然宽度，不能压缩或截断图案')
        width = target_period
    if background_period is not None:
        background_period = _integer_period(background_period)
        width = math.ceil(width / background_period) * background_period
    from .imaging import _profile
    try:
        _profile({**snapshot['output_profile'], 'width': width})
    except ValueError as exc:
        raise ValueError(f'完整循环单元需要{width}×{h}像素，超出本地16000边长或4000万像素限制；请减少图案大小或调整内部高度') from exc

    # Extra width is shared between finite sections proportionally. Each row
    # fills its section using complete groups and gaps; motif sizes never change.
    multiplier = width / sum(item['natural'] for item in sections)
    placements, diagnostics = [], []
    cursor = 0.
    rng = random.Random(int(snapshot.get('seed', 0)))
    for section_index, item in enumerate(sections):
        section_width = width - cursor if section_index == len(sections) - 1 else item['natural'] * multiplier
        for row in item['rows']:
            count = max(1, int((section_width + 1e-7) / row['natural'])) if row['repeat'] else 1
            sequence_length = len(row['variants'])
            if len(placements) + count * sequence_length > MAX_PLACEMENTS:
                raise ValueError('完整循环单元包含过多图案，请增加间距或减小循环周期')
            period = section_width / count
            free = period - sum(size[2] for size in row['sizes'])
            total_gap = row['desired_gap'] * (sequence_length - 1) + row['desired_boundary_gap']
            gap = free * row['desired_gap'] / total_gap
            boundary = free * row['desired_boundary_gap'] / total_gap
            if min(gap, boundary) < 1.999999:
                raise ValueError('完整图案间隔不足，不能通过压缩或截断序列生成')
            row_id = len(diagnostics)
            cycle = dict(period=period, unit_period=width, groups=count, sequence_length=sequence_length,
                         gap=gap, boundary_gap=boundary, desired_gap=row['desired_gap'],
                         desired_boundary_gap=row['desired_boundary_gap'], row=row_id,
                         region=[cursor, row['top'], cursor + section_width, row['bottom']],
                         sequence=[v[0] for v in row['variants']], natural_period=row['natural'])
            diagnostics.append(cycle)
            for group in range(count):
                x_cursor = cursor + group * period + boundary / 2 + row['phase'] * period
                for variant, size in zip(row['variants'], row['sizes']):
                    index, _, extra_angle, role = variant
                    tw, th, bw, bh = size
                    x = x_cursor + bw / 2
                    y = row['bottom'] - bh / 2 if row['baseline'] else row['center_y']
                    if row['scatter']:
                        x += rng.uniform(-.12, .12) * min(gap, boundary)
                        y += rng.uniform(-.018, .018) * (row['bottom'] - row['top'])
                    # Normalize before addition for exact equivalence under an
                    # offset changed by a whole integer number of units.
                    x = (x + c['ox'] % width) % width
                    y = max(row['top'] + bh / 2, min(row['bottom'] - bh / 2, y + c['oy']))
                    placements.append(dict(asset_index=index, x=x, y=y, target_width=tw, target_height=th,
                                           planned_width=bw, planned_height=bh, rotation=angle + extra_angle,
                                           role=role, group=group, row=row_id, repetition=cycle,
                                           region=(0., row['top'], float(width), row['bottom']), wrap=True))
                    x_cursor += bw + gap
        cursor += section_width

    coverage = sorted({p['asset_index'] for p in placements})
    errors = []
    if coverage != all_ids: errors.append('存在未放入循环单元的所选图案')
    for p in placements:
        if not p['region'][1] <= p['y'] - p['planned_height'] / 2 + 1e-7:
            errors.append('完整图案超出上安全边')
        if not p['y'] + p['planned_height'] / 2 <= p['region'][3] + 1e-7:
            errors.append('完整图案超出下安全边')
    if errors:
        raise ValueError('；'.join(sorted(set(errors))))
    metadata = dict(engine=ENGINE, kind=MODE_MATRIX[mode][0], loop_kind=MODE_MATRIX[mode][0],
                    mode_notice=MODE_MATRIX[mode][1], natural_width=natural_width, period_px=width,
                    height_px=h, dpi=c['dpi'], background_period=background_period,
                    target_period=target_period, groups=diagnostics, specs=specs,
                    input_signature=_signature(snapshot, specs),
                    verification=dict(passed=True, errors=[], source_coverage_complete=True,
                                      selected_asset_count=n, placement_count=len(placements), row_count=len(diagnostics),
                                      complete_group_count=sum(row['groups'] for row in diagnostics)))
    return placements, metadata


def resolve(snapshot, resolve_asset=None, *, specs=None, background_period=None, target_period=None):
    """Return a new snapshot with immutable auto width and construction audit.

    ``background_period`` selects an integer multiple of a verified texture's
    period. ``target_period`` may enlarge a natural unit, never squeeze it.
    Neither option changes the configured height/DPI or original source aspect.
    """
    if snapshot.get('layout_engine', ENGINE) != ENGINE:
        raise ValueError('不能用新循环引擎重写历史排版快照')
    if snapshot.get('composite_ref'):
        raise ValueError('整幅编辑底层不能重新解析为独立循环图案')
    if specs is None:
        if resolve_asset is None:
            raise ValueError('解析循环单元需要原图尺寸和素材读取器')
        specs = read_specs(snapshot.get('asset_refs', []), resolve_asset)
    specs = _normalize_specs(specs)
    result = deepcopy(snapshot)
    result['layout_engine'] = ENGINE
    _, metadata = _build(result, specs, background_period=background_period, target_period=target_period)
    result['output_profile']['width'] = metadata['period_px']
    result['loop_layout'] = metadata
    return result


def plan(snapshot, specs=None):
    """Return logical placements compatible with the existing render contract."""
    saved = snapshot.get('loop_layout')
    if specs is None:
        if not saved:
            raise ValueError('循环单元尚未解析，请先计算完整序列宽度')
        specs = saved['specs']
    specs = _normalize_specs(specs)
    placements, actual = _build(snapshot, specs,
                                background_period=saved.get('background_period') if saved else None,
                                target_period=saved.get('period_px') if saved else None)
    if saved:
        # These are construction facts, not caller-provided assessments. Check
        # every saved row, size and coverage/count against a fresh deterministic
        # build, including when both public/private report copies were altered.
        # ``target_period`` deliberately differs on reconstruction: a resolved
        # unit's period is now the requested minimum, even if its initial build
        # used the natural width or rounded up to a background multiple.
        construction_fields = ('verification', 'groups', 'natural_width', 'kind', 'loop_kind',
                               'height_px', 'dpi', 'specs', 'background_period', 'mode_notice')
        if (saved.get('engine') != ENGINE or saved.get('input_signature') != actual['input_signature']
                or saved.get('period_px') != actual['period_px']
                or int(snapshot['output_profile']['width']) != actual['period_px']
                or any(saved.get(key) != actual[key] for key in construction_fields)):
            raise ValueError('循环单元与已保存参数不一致，请生成新版本重新解析，不能覆盖旧版本')
    return placements


def estimate(snapshot):
    """Conservative disk allowance for resolved master, preview and variants."""
    from .imaging import png_space
    placements = plan(snapshot)
    width, height = int(snapshot['output_profile']['width']), int(snapshot['output_profile']['height'])
    unique = {(p['asset_index'], p['target_width'], p['target_height'], p['rotation']): p for p in placements}
    return (png_space(width, height) + png_space(min(width, 3600), min(height, 1200))
            + sum(png_space(p['planned_width'], p['planned_height']) for p in unique.values()))


def compose(canvas, snapshot, resolve_asset, master_path):
    """Render complete source content; phase wrapping occurs only at unit seam."""
    if canvas.size != (snapshot['output_profile']['width'], snapshot['output_profile']['height']):
        raise ValueError('循环画布与已保存版本尺寸不一致')
    refs = snapshot['asset_refs']
    specs = read_specs(refs, resolve_asset)
    placements = plan(snapshot, specs)
    return paint(canvas, snapshot, resolve_asset, master_path, specs, placements, ENGINE)


def paint(canvas, snapshot, resolve_asset, master_path, specs, placements, engine):
    """Paint a verified version-specific plan using the original source pixels."""
    from .imaging import read_image, _save_png, MAX_PIXELS
    refs = snapshot['asset_refs']
    Path(master_path).parent.mkdir(parents=True, exist_ok=True)
    result = []
    with tempfile.TemporaryDirectory(prefix='ribbon-loop-', dir=Path(master_path).parent) as staged:
        prepared = {}
        for index, ref in enumerate(refs):
            variants = {(p['target_width'], p['target_height'], p['rotation'])
                        for p in placements if p['asset_index'] == index}
            with closing(read_image(resolve_asset(ref))) as image:
                with closing(image.crop(specs[index]['bbox'])) as content:
                    for tw, th, angle in sorted(variants):
                        if tw * th > MAX_PIXELS:
                            raise ValueError('完整图案中间图像过大，请减小图案')
                        motif = content.resize((tw, th), Image.Resampling.LANCZOS)
                        if angle % 360:
                            rotated = motif.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
                            motif.close(); motif = rotated
                        path = Path(staged) / f'{len(prepared)}.png'
                        try:
                            if motif.width * motif.height > MAX_PIXELS:
                                raise ValueError('完整旋转图案过大，请减小图案')
                            _save_png(motif, path)
                        finally:
                            motif.close()
                        prepared[index, tw, th, angle] = path
        for layer, p in enumerate(placements):
            index = p['asset_index']
            with closing(read_image(prepared[index, p['target_width'], p['target_height'], p['rotation']])) as motif:
                left, top, right, bottom = p['region']
                if motif.width > p['planned_width'] or motif.height > p['planned_height']:
                    raise ValueError('真实旋转图案超出已验证尺寸，请保留原版并调整参数')
                # Use integer safe edges for the actual raster; rounding a
                # fractional edge down and then clipping would lose one row.
                safe_top, safe_bottom = math.ceil(top), math.floor(bottom)
                y = max(safe_top + motif.height / 2, min(safe_bottom - motif.height / 2, p['y']))
                # Half-up rounding is invariant under integer translations;
                # banker's rounding can flip a .5 edge after an odd offset.
                position = (math.floor(p['x'] - motif.width / 2 + .5),
                            math.floor(y - motif.height / 2 + .5))
                shifts = [0]
                if position[0] < 0: shifts.append(canvas.width)
                if position[0] + motif.width > canvas.width: shifts.append(-canvas.width)
                for shift in shifts:
                    px, py = position[0] + shift, position[1]
                    l, t = max(0, px), max(math.ceil(top), py)
                    r, b = min(canvas.width, px + motif.width), min(math.floor(bottom), py + motif.height)
                    if r > l and b > t:
                        with closing(motif.crop((l - px, t - py, r - px, b - py))) as tile:
                            canvas.alpha_composite(tile, (l, t))
                result.append(dict(asset_ref=refs[index], x=p['x'], y=y, width=motif.width, height=motif.height,
                                   size=max(motif.size), rotation=p['rotation'], layer=layer, role=p['role'],
                                   group=p['group'], row=p['row'], content_bbox=specs[index]['bbox'],
                                   source_size=specs[index]['source_size'], layout_engine=engine,
                                   design_density=snapshot.get('design_density', 'balanced'),
                                   safe_region=list(p['region']), horizontal_wrap=True, repetition=p['repetition']))
    return result
