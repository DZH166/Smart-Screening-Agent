"""Render role-aware v3 periods without mutating the saved v2 renderer.

Background construction is deliberately frozen at the v2 baseline. Only the
foreground geometry/engine is upgraded; old versions keep their own path.
"""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import math

from PIL import Image, ImageChops, ImageColor, ImageDraw

from . import loop_layout_v3 as layout
from .imaging import _finish_render, memory_bounded_operation, read_image
from .loop_background import assess_periodicity, periodize_background
from .loop_pipeline import _empty_background

ENGINE = layout.ENGINE


@memory_bounded_operation
def resolve(snapshot, resolve_asset):
    return layout.resolve(snapshot, resolve_asset)


def _zones(snapshot):
    w, h = snapshot['output_profile']['width'], snapshot['output_profile']['height']
    mode = snapshot['template_mode']
    roles = layout.ZONE_IDS.get(mode, ('whole',))
    refs = snapshot.get('zone_background_refs', {})
    colors = snapshot.get('zone_colors', {})
    if not isinstance(colors, dict) or set(colors) - set(roles):
        raise ValueError('底色分区与当前排法不匹配')
    if not isinstance(refs, dict) or set(refs) - set(roles):
        raise ValueError('分区底纹与当前排法不匹配')
    for i, role in enumerate(roles):
        if mode == 'stacked':
            box = (0, i * h // len(roles), w, (i + 1) * h // len(roles))
        else:
            box = (i * w // len(roles), 0, (i + 1) * w // len(roles), h)
        yield role, refs.get(role, snapshot['background_ref']), box


def _repeats(width, preferred):
    """Integer pixels approximate equal repeats; adjacent tiles differ by at most one."""
    count = max(1, min(width // 16, max(1, round(width / max(preferred, 16)))))
    return [round(i * width / count) for i in range(count + 1)]


def _whole_pattern(surface, source, *, backdrop):
    """Place complete equal-aspect copies of a scene/strip, including edge designs."""
    w, h = surface.size
    natural_width = h * source.width / source.height
    if backdrop:
        # Fit complete scene panels edge to edge without vertical white gutters.
        # Keep the ground at the bottom; spare sky above gets a flat source tone.
        count = max(1, math.ceil(w / max(1.0, natural_width)))
        if count > layout.original.MAX_PLACEMENTS:
            raise ValueError('场景底图过于狭长，无法完整循环，请选择较宽的底图')
        edges = [round(i * w / count) for i in range(count + 1)]
        with source.crop((0, 0, source.width, 1)) as sky, sky.resize((1, 1), Image.Resampling.BOX) as swatch:
            with Image.new('RGBA', (1, 1), 'white') as matte:
                matte.alpha_composite(swatch)
                surface.paste(matte.getpixel((0, 0)), (0, 0, w, h))
    else:
        edges = _repeats(w, natural_width)
    for a, b in zip(edges, edges[1:]):
        ratio = min((b - a) / source.width, h / source.height)
        size = (max(1, round(source.width * ratio)), max(1, round(source.height * ratio)))
        with source.resize(size, Image.Resampling.LANCZOS) as fitted:
            surface.alpha_composite(
                fitted, (a + (b - a - size[0]) // 2, h - size[1] if backdrop else (h - size[1]) // 2)
            )
    return dict(kind='complete_background' if backdrop else 'complete_strip', count=len(edges) - 1)


def _fill(zone, source, scene):
    if _empty_background(source):
        return dict(kind='blank', passed=True)
    if scene:
        return {**_whole_pattern(zone, source, backdrop=True), 'passed': True}
    w, h = zone.size
    if w < 16 or h < 16:
        return {**_whole_pattern(zone, source, backdrop=True), 'passed': True}
    # Already-periodic full-width textures should not be cut into a 6/7
    # quilt needlessly. This path is deliberately narrow: preserve the source
    # horizontal period and its uniform scale, sample at least 98% of its
    # height, and verify the exact sampled tile. It never changes foreground
    # geometry. Incompatible widths use the existing conservative quilt path.
    natural = h * source.width / source.height
    count = max(1, min(w // 16, math.floor(w / natural)))
    native_edges = [round(i * w / count) for i in range(count + 1)]
    native_lengths = sorted({b - a for a, b in zip(native_edges, native_edges[1:])})
    fractions = [h / (length / source.width) / source.height for length in native_lengths]
    if len(native_lengths) == 1 and all(.98 <= fraction <= 1.0 + 1e-9 for fraction in fractions):
        source_check = assess_periodicity(source)
        if source_check['passed']:
            checks = []
            tiles = []
            try:
                for length, fraction in zip(native_lengths, fractions):
                    sampled_height = min(source.height, source.height * fraction)
                    top = (source.height - sampled_height) / 2
                    box = (0., top, float(source.width), top + sampled_height)
                    tile = source.resize((length, h), Image.Resampling.LANCZOS, box=box)
                    if tile.mode != 'RGBA':
                        rgba = tile.convert('RGBA')
                        tile.close()
                        tile = rgba
                    tiles.append((length, tile))
                    checks.append(dict(width=length, source_box=list(box),
                                       uniform_scale=length / source.width,
                                       vertical_sample_fraction=fraction,
                                       check=assess_periodicity(tile)))
                if all(row['check']['passed'] for row in checks):
                    for length, tile in tiles:
                        for a, b in zip(native_edges, native_edges[1:]):
                            if b - a == length:
                                zone.alpha_composite(tile, (a, 0))
                    return dict(kind='native_periodic_texture', count=count,
                                source_dimensions=list(source.size), source_check=source_check,
                                tiles=checks, passed=True)
            finally:
                for _, tile in tiles:
                    tile.close()
    preferred = h * source.width / source.height * 6 / 7
    edges = _repeats(w, preferred)
    reports = []
    # At most two tile widths need quilting. Keep only one such native tile in memory.
    for length in sorted({b - a for a, b in zip(edges, edges[1:])}):
        tile, report = periodize_background(source, length, h)
        with closing(tile):
            for a, b in zip(edges, edges[1:]):
                if b - a == length:
                    zone.alpha_composite(tile, (a, 0))
        reports.append(report)
    return dict(
        kind='quilted_texture', count=len(edges) - 1, tiles=reports, passed=all(r['passed'] for r in reports)
    )


def _make_background(snapshot, resolve_asset):
    w, h = snapshot['output_profile']['width'], snapshot['output_profile']['height']
    colour = snapshot.get('params', {}).get('background_color')
    canvas = Image.new('RGBA', (w, h), ImageColor.getrgb(colour or '#ffffff'))
    zones = []
    zone_count = len(layout.ZONE_IDS.get(snapshot['template_mode'], ('whole',)))
    try:
        for role, ref, box in _zones(snapshot):
            left, top, right, bottom = box
            zone_colour = snapshot.get('zone_colors', {}).get(role)
            if zone_colour or (colour and not snapshot.get('zone_background_refs', {}).get(role)):
                fill = ImageColor.getrgb(zone_colour or colour)
                canvas.paste((*fill, 255), box)
                report = dict(kind='solid_colour', color=list(fill), passed=True)
            else:
                with closing(read_image(resolve_asset(ref))) as source, Image.new(
                    'RGBA', (right - left, bottom - top), 'white'
                ) as zone:
                    report = _fill(zone, source, snapshot['template_mode'] == 'scene')
                    if snapshot.get('background_tone') == 'soft':
                        with Image.new('RGBA', zone.size, (255, 255, 255, 140)) as veil:
                            zone.alpha_composite(veil)
                    offset = int(round(snapshot.get('params', {}).get('offset_x', 0))) % zone.width
                    if offset and zone_count > 1:
                        # Zone backgrounds stay inside their panel: shifting the
                        # whole canvas swapped colours/textures between panels.
                        with ImageChops.offset(zone, offset, 0) as shifted:
                            canvas.paste(shifted, (left, top))
                    else:
                        canvas.paste(zone, (left, top))
            zones.append(dict(role=role, ref=ref, box=list(box), construction=report))
        return canvas, zones
    except BaseException:
        canvas.close()
        raise


def _borders(canvas, snapshot, resolve_asset):
    w, h = canvas.size
    # Borrow the edge colour from the foreground, averaged with alpha weighting.
    slots = snapshot.get('pattern_slots', [f'pattern-{i+1}' for i in range(len(snapshot['asset_refs']))])
    roles = layout.pattern_roles(snapshot, slots)
    main_index = next(i for i, slot in enumerate(slots) if roles[slot] == 'main')
    with closing(read_image(resolve_asset(snapshot['asset_refs'][main_index]))) as main, main.resize(
        (1, 1), Image.Resampling.BOX
    ) as swatch:
        color = swatch.getpixel((0, 0))[:3]
    stroke = max(1, round(h * 0.005))
    band_h = max(1, round(h * 0.115))
    source_ref = snapshot.get('border_ref')
    report = dict(style='continuous_lines', width=stroke, color=list(color), source=source_ref)
    for top_ratio in (0.08, 0.805):
        top = round(h * top_ratio)
        y = top + band_h // 2
        ImageDraw.Draw(canvas).line((0, y, w - 1, y), fill=(*color, 255), width=stroke)
        if source_ref:
            with closing(read_image(resolve_asset(source_ref))) as strip, Image.new(
                'RGBA', (w, band_h)
            ) as band:
                bbox = strip.getbbox()
                if bbox is None:
                    raise ValueError('所选边饰没有可见内容')
                with strip.crop(bbox) as content:
                    report['strip'] = _whole_pattern(band, content, backdrop=False)
                canvas.alpha_composite(band, (0, top))
    return report


def compose(snapshot, resolve_asset, master_path, preview_path):
    canvas, zones = _make_background(snapshot, resolve_asset)
    try:
        border = (
            _borders(canvas, snapshot, resolve_asset) if snapshot['template_mode'] == 'bordered' else None
        )
        bg_wrap = assess_periodicity(canvas)
        transforms = layout.compose(canvas, snapshot, resolve_asset, master_path)
        final_wrap = assess_periodicity(canvas)
        issues = []
        if not all(z['construction']['passed'] for z in zones):
            issues.append(
                dict(code='background_join', message='底纹接缝或较大花纹可再核对。', severity='warning')
            )
        if not bg_wrap['passed'] or not final_wrap['passed']:
            issues.append(
                dict(
                    code='raster_join',
                    message='单元交界颜色或线条变化较大，可查看连续效果。',
                    severity='warning',
                )
            )
        profile = snapshot['output_profile']
        geometry = snapshot['loop_layout']
        loop = dict(
            engine=ENGINE,
            width=canvas.width,
            height=canvas.height,
            dpi=profile['dpi'],
            status='needs_review' if issues else 'checked',
            issues=issues,
            kind=geometry['kind'],
            mode_notice=geometry['mode_notice'],
            geometry=deepcopy(geometry['verification']),
            background=dict(
                zones=zones, border=border, passed=all(z['construction']['passed'] for z in zones)
            ),
            background_wrap=bg_wrap,
            final_wrap=final_wrap,
            motif_resolution=dict(
                max_upscale=round(_upscale_ratio(snapshot['loop_layout']), 3),
                note=(
                    '有图案被放大约 %.1f 倍，细节可能变糊；建议换更大的图案或减少行数。'
                    % _upscale_ratio(snapshot['loop_layout'])
                    if _upscale_ratio(snapshot['loop_layout']) > 1.5 else ''
                ),
            ),
            production_verified=False,
            verification_scope='period_construction_and_multiscale_pixel_checks',
            profile_source=deepcopy(snapshot['output_profile_source']),
        )
        result = _finish_render(canvas, snapshot, master_path, preview_path, transforms)
        loop['evidence_digest'] = _digest(loop)
        result['loop'] = loop
        return result
    finally:
        canvas.close()


def _upscale_ratio(geometry):
    """Largest target/source width ratio of any pattern copy in this unit."""
    slots = list(((geometry.get('metrics') or {}).get('slots') or {}).values())
    specs = geometry.get('specs') or []
    ratio = 1.0
    for index, spec in enumerate(specs):
        try:
            source = float(spec['width'])
            target = float(slots[index]['target_width_px'][-1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if source > 0:
            ratio = max(ratio, target / source)
    return ratio


def _digest(loop):
    report = {k: v for k, v in loop.items() if k not in ('output_sha256', 'evidence_digest', 'inputs')}
    return hashlib.sha256(json.dumps(report, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_binding(snapshot, master_sha256):
    layout.plan(snapshot)
    loop = snapshot.get('loop') or {}
    profile, source = snapshot['output_profile'], snapshot['output_profile_source']
    if (
        loop.get('engine') != ENGINE
        or loop.get('output_sha256') != master_sha256
        or loop.get('evidence_digest') != _digest(loop)
        or loop.get('profile_source') != source
        or loop.get('geometry') != snapshot['loop_layout']['verification']
        or any(loop.get(k) != profile[k] for k in ('width', 'height', 'dpi'))
        or any(profile.get(k) != v for k, v in source.items() if k != 'width')
        or loop.get('production_verified') is not False
    ):
        raise ValueError('循环检查记录与版本文件不一致')
    zones = loop['background']['zones']
    if [(z['role'], z['ref'], z['box']) for z in zones] != [(r, f, list(b)) for r, f, b in _zones(snapshot)]:
        raise ValueError('分区底纹与保存版本不一致')
    border = loop['background'].get('border')
    if (snapshot['template_mode'] == 'bordered') != isinstance(border, dict) or (
        border is not None and border.get('source') != snapshot.get('border_ref')
    ):
        raise ValueError('保存的边饰来源与版本不一致')
    for zone in zones:
        build = zone['construction']
        if build['kind'] == 'quilted_texture':
            tiles = build['tiles']
            checks = [
                tile['cut']['passed']
                and tile['features']['passed']
                and all(check['passed'] for check in tile['multiscale'])
                for tile in tiles
            ]
            if not checks or [tile['passed'] for tile in tiles] != checks or build['passed'] != all(checks):
                raise ValueError('底纹检查与像素报告不一致')
        elif build['kind'] == 'native_periodic_texture':
            tiles = build.get('tiles', [])
            if (not tiles or not build.get('source_check', {}).get('passed') or not build['passed']
                    or any(not .98 <= t['vertical_sample_fraction'] <= 1.0 + 1e-9
                           or t['source_box'][0] != 0 or t['source_box'][2] != build['source_dimensions'][0]
                           or not t['check']['passed'] or not t['check']['multiscale']
                           or not all(s['passed'] for s in t['check']['multiscale']) for t in tiles)):
                raise ValueError('原生底纹周期检查与采样记录不一致')
        elif (
            build['kind'] not in ('blank', 'solid_colour', 'complete_background')
            or build['passed'] is not True
        ):
            raise ValueError('底纹构造记录不完整')
    passed = all(z['construction']['passed'] for z in zones)
    joins = [loop['background_wrap'], loop['final_wrap']]
    if (
        loop.get('status') not in ('checked', 'needs_review')
        or loop['background']['passed'] != passed
        or any(
            j.get('verification_scope') != 'pixel_continuity_only'
            or j.get('production_verified') is not False
            or not j.get('multiscale')
            or j['passed'] != all(s['passed'] for s in j['multiscale'])
            for j in joins
        )
        or (loop.get('status') == 'checked') != (passed and all(j['passed'] for j in joins))
        or bool(loop.get('issues')) != (loop.get('status') == 'needs_review')
    ):
        raise ValueError('循环像素检查未绑定实际结论')
