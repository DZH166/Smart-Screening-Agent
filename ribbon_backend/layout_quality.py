"""Visible-content layout for new, explicitly versioned ribbon snapshots.

This module never edits source files. Transparent padding is excluded only from
the derived rendering; every alpha>0 pixel participates in its content bounds.
Geometry is based on the actual (rotated) aspect of each complete design. One
complete sequence is the unit of horizontal repetition, including its phase.
"""
from __future__ import annotations

from contextlib import closing
import math
from pathlib import Path
import random
import tempfile

from PIL import Image

ENGINE = 'design-rhythm-v1'
DENSITIES = ('airy', 'balanced', 'rich')
MODES = ('grid', 'stagger', 'scatter', 'single', 'ends', 'panels', 'bordered',
         'scene', 'fullwidth', 'alternating', 'ends_open', 'split', 'stacked', 'opposed')
MAX_PLACEMENTS = 1200


def estimate(snapshot):
    """Conservative staging estimate without opening any source files.

    Complete groups are fitted inside their lane before staging. A four-master
    allowance covers the union of variants, rotated padding and fixed end/zone
    treatments; small-file overhead is added for every possible asset variant.
    """
    from .imaging import MAX_PIXELS, png_space
    p = snapshot['output_profile']
    w, h = int(p['width']), int(p['height'])
    count = len(snapshot.get('asset_refs', []))
    stage_pixels = min(MAX_PIXELS, (w + 4) * (h + 4))
    return (png_space(w, h) + png_space(min(w, 3600), min(h, 1200))
            + 4 * stage_pixels * 5 + count * 4 * 65536)


def _specs(refs, resolve_asset):
    from .imaging import read_image
    specs = []
    for ref in refs:
        with closing(read_image(resolve_asset(ref))) as image:
            with closing(image.getchannel('A')) as alpha:
                bbox = alpha.getbbox()
            if bbox is None:
                raise ValueError('图案没有可见内容，请更换图片')
            specs.append({'bbox': bbox, 'width': bbox[2] - bbox[0],
                          'height': bbox[3] - bbox[1], 'source_size': image.size})
    return specs


def _size(spec, target_height, maximum_width, maximum_height, angle):
    """Pre-rotation pixels, then a conservative expanded output rectangle."""
    a = math.radians(angle % 360)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    rw, rh = spec['width'] * c + spec['height'] * s, spec['width'] * s + spec['height'] * c
    ratio = min(max(1, target_height) / rh, max(1, maximum_width - 4) / rw,
                max(1, maximum_height - 4) / rh)
    tw, th = max(1, int(spec['width'] * ratio)), max(1, int(spec['height'] * ratio))
    return tw, th, math.ceil(tw * c + th * s) + 2, math.ceil(tw * s + th * c) + 2


def plan(snapshot, specs):
    """Return logical placements; source dimensions/bounds are private metadata."""
    from .imaging import PARAM_DEFAULTS
    p = snapshot['output_profile']; w, h = int(p['width']), int(p['height'])
    mode = snapshot['template_mode']; refs = snapshot['asset_refs']; n = len(refs)
    if mode not in MODES or not 1 <= n <= 12:
        raise ValueError('排版模式或图案数量不正确')
    if len(specs) != n:
        raise ValueError('图案尺寸记录不完整')
    if mode == 'bordered' and n < 2:
        raise ValueError('上下边饰至少选择两个图案')
    if mode == 'fullwidth' and n != 1:
        raise ValueError('整幅定位需要一张完整设计图')
    if mode == 'ends_open' and n not in (1, 2):
        raise ValueError('两端留白请选择一张或两张图案')
    if mode in ('split', 'stacked') and n < 2:
        raise ValueError('分区排版至少选择两个图案')
    params = {**PARAM_DEFAULTS, **snapshot.get('params', {})}
    rules = snapshot.get('template_rules', {})
    density = snapshot.get('design_density', 'balanced')
    if density not in DENSITIES:
        raise ValueError('请选择有效的排版疏密')
    density_scale, density_gap = {'airy': (.82, 1.35), 'balanced': (1., 1.), 'rich': (1.08, .7)}[density]
    scale = float(params['scale']) * float(rules.get('motif_ratio', .27)) / .27 * density_scale
    spacing = float(params['spacing']) * float(rules.get('step_ratio', .64)) / .64 * density_gap
    angle = float(params['rotation'])
    if not all(math.isfinite(v) and v > 0 for v in (scale, spacing)) or not math.isfinite(angle):
        raise ValueError('图案大小或间距参数不正确')
    ox, oy = float(params['offset_x']), float(params['offset_y'])
    if not math.isfinite(ox) or not math.isfinite(oy):
        raise ValueError('图案位置参数不正确')
    out = []
    rng = random.Random(int(snapshot.get('seed', 0)))

    def add(index, x, y, size, region, role, group=0, repetition=None, extra_angle=0, wrap=False,
            horizontal_offset=None):
        left, top, right, bottom = region
        tw, th, bw, bh = size
        shift = ox if horizontal_offset is None else horizontal_offset
        if wrap:
            # Normalize the translation before addition. Adding a whole-strip
            # float then taking modulo can flip .5-pixel rounding by one pixel.
            shift %= right - left
        x += shift
        y += oy
        # Only the ribbon's outer horizontal seam may split a complete motif.
        # Fixed panels retain their whole design inside their own region.
        if wrap:
            x = left + (x - left) % (right - left)
        else:
            x = max(left + bw / 2, min(right - bw / 2, x))
        y = max(top + bh / 2, min(bottom - bh / 2, y))
        out.append(dict(asset_index=index, x=x, y=y, target_width=tw, target_height=th,
                        planned_width=bw, planned_height=bh, rotation=angle + extra_angle,
                        role=role, group=group, repetition=repetition, region=region, wrap=wrap))

    def row(indices, region, occupancy, role, *, phase=0., wrap=False, variants=None,
            baseline=False, scatter=False, nominal_height=None, center_y=None):
        left, top, right, bottom = region; rw, rh = right - left, bottom - top
        natural_height = rh if nominal_height is None else nominal_height
        # The nominal rhythm and desired gap stay fixed at scale=1. The lane
        # may lend some inter-row whitespace to an explicit enlargement, while
        # its outer safety and shared row boundary remain hard constraints.
        maximum_height = rh if nominal_height is None else min(rh, natural_height * max(1., scale))
        variants = variants or [(i, 1., 0.) for i in indices]
        def fitted(group_scale):
            return [_size(specs[i], natural_height * occupancy * factor * scale * group_scale,
                          rw * .94, maximum_height, angle + extra) for i, factor, extra in variants]
        sizes = fitted(1.)
        natural = sum(s[2] for s in sizes)
        desired_gap = max(2., natural_height * .16 * spacing)
        groups = max(1, min(MAX_PLACEMENTS // max(1, len(variants)),
                            int(rw / (natural + len(variants) * desired_gap))))
        period = rw / groups
        # A full sequence must fit, even with twelve very wide source designs.
        if natural + len(variants) * 2 > period:
            low, high = 0., 1.
            for _ in range(24):
                middle = (low + high) / 2
                trial = fitted(middle)
                if sum(s[2] for s in trial) + len(variants) * 2 <= period:
                    low = middle
                else:
                    high = middle
            sizes = fitted(low)
            natural = sum(s[2] for s in sizes)
        if natural + len(variants) * 2 > period + .01:
            raise ValueError('当前区域容不下整组完整图案，请减少图案或更换排版')
        gap = max(0., (period - natural) / len(variants))
        cycle = dict(period=period, groups=groups, sequence_length=len(variants),
                     gap=gap, desired_gap=desired_gap, region=[left, top, right, bottom])
        # Fixed panels translate the complete sequence by its shared free
        # margin. Clamping each motif separately would pile them on one edge.
        fixed_offset = max(-gap / 2, min(gap / 2, ox)) if not wrap else None
        for group in range(groups):
            cursor = left + group * period + gap / 2 + phase * period
            for (i, _, extra), size in zip(variants, sizes):
                x = cursor + size[2] / 2
                y = bottom - size[3] / 2 if baseline else ((top + bottom) / 2 if center_y is None else center_y)
                if scatter:
                    x += rng.uniform(-.12, .12) * gap
                    y += rng.uniform(-.018, .018) * natural_height
                add(i, x, y, size, region, role, group, cycle, extra, wrap,
                    horizontal_offset=fixed_offset)
                cursor += size[2] + gap

    def fixed(index, region, occupancy, role):
        left, top, right, bottom = region
        size = _size(specs[index], (bottom - top) * occupancy * scale,
                     right - left, bottom - top, angle)
        add(index, (left + right) / 2, (top + bottom) / 2, size, region, role)

    full_safe = (0., h * .08, float(w), h * .92)
    all_ids = list(range(n))

    def lane_geometry(row_index, count, left=0., right=None):
        right = float(w) if right is None else right
        if count <= 2:
            lane = h / count
            pad = lane * (.12 if count == 1 else .16)
            nominal = lane - pad * 2
            capacity = (left, max(h * .08, row_index * lane), right,
                        min(h * .92, (row_index + 1) * lane))
            return capacity, nominal, (row_index + .5) * lane, 1.
        lane = h * .84 / count
        capacity = (left, h * .08 + row_index * lane, right,
                    h * .08 + (row_index + 1) * lane)
        return capacity, lane - h * .01, h * .08 + (row_index + .5) * lane, .90

    if mode in ('grid', 'stagger', 'scatter'):
        rows = max(1, min(4, int(rules.get('rows', 3 if density == 'rich' else 2))))
        for r in range(rows):
            region, nominal, cy, occupancy = lane_geometry(r, rows)
            indices = all_ids[r % n:] + all_ids[:r % n]
            row(indices, region, occupancy, 'scatter' if mode == 'scatter' else 'motif',
                phase=.5 / len(indices) if mode == 'stagger' and r % 2 else 0., wrap=True,
                scatter=mode == 'scatter', nominal_height=nominal, center_y=cy)
    elif mode == 'single':
        row(all_ids, full_safe, .76 / .84, 'motif', wrap=True)
    elif mode in ('alternating', 'opposed'):
        # lcm(2,n) closes both the asset sequence and large/small or 180° phase.
        count = math.lcm(2, n)
        variants = [(i % n, (.58 if i % 2 and mode == 'alternating' else 1.),
                     180. if i % 2 and mode == 'opposed' else 0.) for i in range(count)]
        row(all_ids, full_safe, .76 / .84, 'alternating' if mode == 'alternating' else 'opposed',
            wrap=True, variants=variants)
    elif mode == 'stacked':
        half = (n + 1) // 2
        for r, ids, role in ((0, all_ids[:half], 'top-zone'), (1, all_ids[half:], 'bottom-zone')):
            region, nominal, cy, occupancy = lane_geometry(r, 2)
            row(ids, region, occupancy, role, wrap=True, nominal_height=nominal, center_y=cy)
    elif mode == 'split':
        half = (n + 1) // 2
        for left, right, ids, role in ((0., w / 2, all_ids[:half], 'left-zone'),
                                      (w / 2, float(w), all_ids[half:], 'right-zone')):
            for r in range(2):
                region, nominal, cy, occupancy = lane_geometry(r, 2, left, right)
                row(ids[r % len(ids):] + ids[:r % len(ids)],
                    region, occupancy, role, nominal_height=nominal, center_y=cy)
    elif mode == 'bordered':
        row([0], (0., h * .23, float(w), h * .77), 1., 'main', wrap=True)
        for top, bottom, role in ((.08, .18, 'top-border'), (.82, .92, 'bottom-border')):
            row(all_ids[1:], (0., top * h, float(w), bottom * h), 1., role, wrap=True)
    elif mode == 'scene':
        factors = [1.] + [(.76, .84, .72)[(i - 1) % 3] for i in range(1, n)]
        row(all_ids, full_safe, .76 / .84, 'scene', wrap=True, baseline=True,
            variants=[(i, factors[i], 0.) for i in all_ids])
    elif mode in ('ends', 'ends_open'):
        zone = min(w * .44, h * 1.20)
        side_margin = min(h * .04, w * .02)
        fixed(0, (side_margin, h * .08, zone, h * .92), .92, 'left-end')
        fixed(1 if mode == 'ends_open' and n == 2 else 0,
              (w - zone, h * .08, w - side_margin, h * .92), .92, 'right-end')
        if mode == 'ends' and w - 2 * zone > 10:
            row(all_ids[1:] or [0], (zone, h * .20, w - zone, h * .80), .76, 'inner')
    elif mode == 'panels':
        third = w / 3
        for r in range(2):
            region, nominal, cy, occupancy = lane_geometry(r, 2, 0., third)
            row(all_ids[r % n:] + all_ids[:r % n],
                region, occupancy, 'left-panel', nominal_height=nominal, center_y=cy)
        row(all_ids, (third, h * .08, third * 2, h * .92), .76 / .84, 'middle-panel')
        side_margin = min(h * .04, third * .03)
        fixed(0, (third * 2 + side_margin, h * .08, w - side_margin, h * .92), .92, 'right-panel')
    elif mode == 'fullwidth':
        fixed(0, (w * .02, h * .08, w * .98, h * .92), 1., 'complete')
    if len(out) > MAX_PLACEMENTS * 4:
        raise ValueError('当前排版包含过多图案，请增加间距')
    return out


def compose(canvas, snapshot, resolve_asset, master_path):
    """Composite into an existing background and return immutable diagnostics."""
    from .imaging import read_image, _save_png, MAX_PIXELS
    refs = snapshot['asset_refs']; specs = _specs(refs, resolve_asset)
    placements = plan(snapshot, specs)
    Path(master_path).parent.mkdir(parents=True, exist_ok=True)
    result = []
    with tempfile.TemporaryDirectory(prefix='ribbon-rhythm-', dir=Path(master_path).parent) as staged:
        prepared = {}
        for index, ref in enumerate(refs):
            variants = {(p['target_width'], p['target_height'], p['rotation'])
                        for p in placements if p['asset_index'] == index}
            with closing(read_image(resolve_asset(ref))) as image:
                with closing(image.crop(specs[index]['bbox'])) as content:
                    for tw, th, angle in variants:
                        if tw * th > MAX_PIXELS:
                            raise ValueError('图案中间图像过大，请减小图案')
                        motif = content.resize((tw, th), Image.Resampling.LANCZOS)
                        if angle % 360:
                            rotated = motif.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
                            motif.close(); motif = rotated
                        path = Path(staged) / f'{len(prepared)}.png'
                        try:
                            if motif.width * motif.height > MAX_PIXELS:
                                raise ValueError('旋转后图案过大，请减小图案')
                            _save_png(motif, path)
                        finally:
                            motif.close()
                        prepared[index, tw, th, angle] = path
        for layer, p in enumerate(placements):
            i = p['asset_index']; key = (i, p['target_width'], p['target_height'], p['rotation'])
            with closing(read_image(prepared[key])) as motif:
                left, top, right, bottom = p['region']
                # Pillow's rotated integer bounds can differ by one pixel from
                # analytic bounds. Fit that exact canvas inside the safe lane.
                x = p['x']
                if not p['wrap']:
                    x = max(left + motif.width / 2, min(right - motif.width / 2, x))
                y = max(top + motif.height / 2, min(bottom - motif.height / 2, p['y']))
                position = round(x - motif.width / 2), round(y - motif.height / 2)
                shifts = [0]
                if p['wrap']:
                    if position[0] < left: shifts.append(round(right - left))
                    if position[0] + motif.width > right: shifts.append(-round(right - left))
                for shift in shifts:
                    px, py = position[0] + shift, position[1]
                    l, t = max(0, math.ceil(left), px), max(0, math.ceil(top), py)
                    r, b = min(canvas.width, math.floor(right), px + motif.width), min(canvas.height, math.floor(bottom), py + motif.height)
                    if r > l and b > t:
                        with closing(motif.crop((l - px, t - py, r - px, b - py))) as tile:
                            canvas.alpha_composite(tile, (l, t))
                row = dict(asset_ref=refs[i], x=x, y=y, width=motif.width, height=motif.height,
                           size=max(motif.size), rotation=p['rotation'], layer=layer, role=p['role'],
                           group=p['group'], content_bbox=list(specs[i]['bbox']),
                           source_size=list(specs[i]['source_size']), layout_engine=ENGINE,
                           design_density=snapshot.get('design_density', 'balanced'),
                           safe_region=list(p['region']), horizontal_wrap=p['wrap'],
                           repetition=p['repetition'])
                result.append(row)
    return result
