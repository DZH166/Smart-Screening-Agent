"""Place declared ribbon ornaments in open space around a fixed foreground."""
from __future__ import annotations

import math
import random
from statistics import median


def _regions(mode, width, height, main):
    top, bottom = height * .025, height * .975
    if mode in ('split', 'panels'):
        zones = 2 if mode == 'split' else 3
        return [(width * i // zones, top, width * (i + 1) // zones, bottom)
                for i in range(zones)]
    if mode == 'stacked':
        return [(0, top, width, height // 2), (0, height // 2, width, bottom)]
    if mode == 'bordered':
        # Stay between the independently rendered continuous bands.
        return [(0, height * .20, width, height * .80)]
    if mode == 'ends_open':
        left, right = sorted(main, key=lambda part: part['x'])
        # The centre between the two complete end graphics remains empty.
        return [(0, top, left['x'] + left['planned_width'] / 2, bottom),
                (right['x'] - right['planned_width'] / 2, top, width, bottom)]
    return [(0, top, width, bottom)]


def _clear(x, y, half_w, half_h, fixed, period):
    for other_x, other_y, other_half_w, other_half_h in fixed:
        dx = abs(x - other_x)
        if (min(dx, period - dx) < half_w + other_half_w + 2
                and abs(y - other_y) < half_h + other_half_h + 2):
            return False
    return True


def _positions(region, anchors, half_w, half_h, rng):
    left, top, right, bottom = region
    left, right = math.ceil(left) + half_w + 2, math.floor(right) - half_w - 2
    top, bottom = math.ceil(top) + half_h + 2, math.floor(bottom) - half_h - 2
    if left > right or top > bottom:
        return
    around = ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1))
    for x, y, anchor_w, anchor_h in anchors:
        # The primary candidates are adjacent to complete figures rather than
        # scattered across unrelated blank areas. Clamp only the decoration.
        for dx, dy in around:
            near_x = min(max(x + dx * (anchor_w + half_w + 3), left), right)
            near_y = min(max(y + dy * (anchor_h + half_h + 3), top), bottom)
            yield near_x, near_y
    # Bounded secondary probes can use gaps between several close figures.
    for _ in range(80):
        yield rng.uniform(left, right), rng.uniform(top, bottom)


def _box(part):
    return (part['x'], part['y'], part['planned_width'] / 2, part['planned_height'] / 2)


def place_decorations(mode, width, height, body, main, assets, seed):
    """Fit each decoration once per unit, preserving every primary placement."""
    fixed = [_box(part) for part in body]
    boxes = [_box(part) for part in main]
    regions = _regions(mode, width, height, main)
    anchors = [
        [box for box in boxes if l <= box[0] <= r and t <= box[1] <= b]
        for l, t, r, b in regions
    ]
    rng = random.Random(seed)
    for group in anchors:
        # Keep effort bounded even for unusually dense internal templates.
        rng.shuffle(group)
        del group[48:]
    counts = [0] * len(regions)
    result = []
    long_edge = min(height * .17, median(max(p['target_width'], p['target_height']) for p in main) * .36)
    area = median(p['target_width'] * p['target_height'] for p in main) * .18
    # Leave room for the full selection when several ornaments share a unit.
    long_edge *= min(1., math.sqrt(4 / len(assets)))

    def size(asset):
        w, h = asset[2]['width'], asset[2]['height']
        scale = min(long_edge / max(w, h), math.sqrt(area / (w * h)))
        return w * scale, h * scale

    # Largest ornaments have fewer options; their original order remains
    # bound by asset_index and is restored in the returned paint list.
    for index, slot, spec in sorted(assets, key=lambda item: -math.prod(size(item))):
        wanted_w, wanted_h = size((index, slot, spec))
        choices = sorted((i for i, group in enumerate(anchors) if group),
                         key=lambda i: (counts[i], rng.random()))
        chosen = None
        for reduction in (1., .82, .67, .55, .44, .35):
            tw, th = int(wanted_w * reduction), int(wanted_h * reduction)
            if min(tw, th) < 1 or max(tw, th) < max(4, round(height * .02)):
                break
            half_w, half_h = (tw + 2) / 2, (th + 2) / 2
            for i in choices:
                chosen = next(((i, x, y) for x, y in _positions(regions[i], anchors[i], half_w, half_h, rng)
                               if _clear(x, y, half_w, half_h, fixed, width)), None)
                if chosen is not None:
                    break
            if chosen is not None:
                break
        if chosen is None:
            raise ValueError('主图周围没有足够空间完整放置装饰，请减少装饰、换用较紧凑的图案或选择疏朗')
        i, x, y = chosen
        counts[i] += 1
        fixed.append((x, y, half_w, half_h))
        region = regions[i]
        result.append(dict(asset_index=index, slot_id=slot, role='decoration', x=x, y=y,
            target_width=tw, target_height=th, planned_width=tw + 2, planned_height=th + 2,
            rotation=0., group=0, row=-1, region=region, wrap=False,
            repetition=dict(period=width, unit_period=width, groups=1, sequence_length=1,
                            sequence=[index], region=list(region), arrangement='surrounding_decoration')))
    return sorted(result, key=lambda part: part['asset_index'])
