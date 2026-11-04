"""Versioned short-unit composition; never used to reinterpret old masters."""
from contextlib import closing
from copy import deepcopy
import hashlib

from PIL import Image, ImageColor

from . import loop_layout
from .imaging import memory_bounded_operation

ENGINE = loop_layout.ENGINE


def _empty_background(background):
    if background.mode != 'RGBA':
        return False
    with background.getchannel('A') as alpha:
        return alpha.getbbox() is None


@memory_bounded_operation
def resolve(snapshot, resolve_asset):
    """Recalculate only a prospective version, using the bound height/profile."""
    from .imaging import PARAM_DEFAULTS, read_image
    from .loop_background import preferred_period
    result = deepcopy(snapshot)
    # The configured width is provenance, not a target to fill or crop.
    result.setdefault('output_profile_source', deepcopy(result['output_profile']))
    params = {**PARAM_DEFAULTS, **result.get('params', {})}
    period = None
    if not params['background_color']:
        with closing(read_image(resolve_asset(result['background_ref']))) as background:
            if not _empty_background(background):
                period = preferred_period(background, int(result['output_profile_source']['height']))
    result['output_profile'] = deepcopy(result['output_profile_source'])
    result.pop('loop', None)
    result.pop('loop_layout', None)
    return loop_layout.resolve(result, resolve_asset, background_period=period)


def compose(snapshot, resolve_asset, master_path, preview_path):
    """Create one unit directly; the UI reuses its immutable preview three times."""
    from .imaging import PARAM_DEFAULTS, read_image, _finish_render
    from .loop_background import periodize_background, assess_periodicity
    width, height = snapshot['output_profile']['width'], snapshot['output_profile']['height']
    geometry = snapshot['loop_layout']
    params = {**PARAM_DEFAULTS, **snapshot.get('params', {})}
    canvas = None
    try:
        blank = False
        if not params['background_color'] and geometry.get('background_period') is None:
            with closing(read_image(resolve_asset(snapshot['background_ref']))) as background:
                blank = _empty_background(background)
            if not blank:
                raise ValueError('底纹周期记录不完整，请重新生成此版本')
        if params['background_color'] or blank:
            # Historical RGB/PNG output composites an empty background over
            # white. It is a valid blank, not a damaged texture to quilt.
            canvas = Image.new('RGBA', (width, height), ImageColor.getrgb(params['background_color'] or '#ffffff'))
            background_report = dict(engine='solid-colour-v1', passed=True, status='checked', issues=[],
                                     verification_scope='exact_solid_colour', production_verified=False,
                                     period_px=1, pixel_sha256=hashlib.sha256(canvas.tobytes()).hexdigest())
        else:
            period = geometry['background_period']
            if type(period) is not int or period < 16 or width % period:
                raise ValueError('循环宽度不能容纳完整底纹周期，请重新生成此版本')
            with closing(read_image(resolve_asset(snapshot['background_ref']))) as background:
                tile, background_report = periodize_background(background, period, height)
            with closing(tile):
                canvas = Image.new('RGBA', (width, height))
                for x in range(0, width, period):
                    canvas.alpha_composite(tile, (x, 0))
            background_report['period_px'] = period
            background_report['repeat_count'] = width // period
            if snapshot.get('background_tone', 'original') == 'soft':
                with Image.new('RGBA', (width, height), (255, 255, 255, 140)) as veil:
                    canvas.alpha_composite(veil)
        # Check the uncovered background, including beneath the later designs.
        background_wrap = assess_periodicity(canvas)
        transforms = loop_layout.compose(canvas, snapshot, resolve_asset, master_path)
        final_wrap = assess_periodicity(canvas)
        issues = []
        if not background_report['passed']:
            issues.append(dict(code='background_join', severity='warning',
                               message='底纹接缝或图案完整性仍有疑问，可查看连续效果，或更换、精修底纹。'))
        if not background_wrap['passed']:
            issues.append(dict(code='background_wrap', severity='warning',
                               message='底纹连续显示可能有色差或断纹，可查看连续效果并调整底纹。'))
        if not final_wrap['passed']:
            issues.append(dict(code='raster_join', severity='warning',
                               message='交界附近的颜色或线条变化较大，可查看连续效果，调整间距或图案位置。'))
        source = snapshot['output_profile_source']
        loop = dict(engine=ENGINE, width=width, height=height, dpi=source['dpi'],
                    status='needs_review' if issues else 'checked', issues=issues,
                    kind=geometry['kind'], mode_notice=geometry['mode_notice'],
                    profile_source={k: source[k] for k in ('id', 'version', 'name', 'width', 'height', 'dpi', 'format', 'is_demo') if k in source},
                    geometry=deepcopy(geometry['verification']),
                    background=background_report, background_wrap=background_wrap,
                    final_wrap=final_wrap, production_verified=False,
                    verification_scope='period_construction_and_multiscale_pixel_checks')
        metadata = _finish_render(canvas, snapshot, master_path, preview_path, transforms)
        canvas = None
        metadata['loop'] = loop
        return metadata
    finally:
        if canvas is not None:
            canvas.close()


def validate_binding(snapshot, master_sha256):
    """Validate recovery/commit metadata against its immutable result binding."""
    loop = snapshot.get('loop') or {}
    profile, geometry = snapshot['output_profile'], snapshot.get('loop_layout') or {}
    source = snapshot.get('output_profile_source') or {}
    if (loop.get('engine') != ENGINE or geometry.get('engine') != ENGINE
            or loop.get('width') != profile['width'] or loop.get('height') != profile['height']
            or geometry.get('period_px') != profile['width']
            or geometry.get('height_px') != profile['height']
            or source.get('height') != profile['height'] or source.get('dpi') != profile['dpi']
            or loop.get('output_sha256') != master_sha256
            or loop.get('status') not in ('checked', 'needs_review')
            or not isinstance(loop.get('issues'), list)
            or (loop['status'] == 'checked' and loop['issues'])
            or loop.get('production_verified') is not False):
        raise ValueError('循环信息与保存文件不一致，未提交新版本')
    loop_layout.plan(snapshot)
    reports = (loop.get('background'), loop.get('background_wrap'), loop.get('final_wrap'))
    if (any(not isinstance(r, dict) or type(r.get('passed')) is not bool for r in reports)
            or geometry.get('verification', {}).get('passed') is not True
            or loop.get('geometry') != geometry['verification']
            or loop['status'] != ('checked' if all(r['passed'] for r in reports) else 'needs_review')
            or bool(loop['issues']) != any(not r['passed'] for r in reports)
            or loop.get('dpi') != source.get('dpi')
            or any(profile.get(k) != v for k, v in source.items() if k != 'width')
            or loop['background'].get('period_px') != (geometry.get('background_period') or 1)):
        raise ValueError('循环检查记录与实际判定不一致，未提交新版本')
    for report in reports:
        if report.get('production_verified') is not False:
            raise ValueError('循环检查不能替代印刷验收，未提交新版本')
        if report.get('engine') == 'solid-colour-v1':
            if report.get('verification_scope') != 'exact_solid_colour' or not report['passed']:
                raise ValueError('纯色循环检查记录无效')
            continue
        scales = report.get('multiscale')
        if (report.get('verification_scope') != 'pixel_continuity_only'
                or not isinstance(scales, list) or not scales
                or any(not isinstance(s, dict) or type(s.get('passed')) is not bool for s in scales)):
            raise ValueError('循环多尺度检查记录不完整')
        expected = all(s['passed'] for s in scales)
        if report is loop['background']:
            cut, features = report.get('cut') or {}, report.get('features') or {}
            if type(cut.get('passed')) is not bool or type(features.get('passed')) is not bool:
                raise ValueError('底纹接缝检查记录不完整')
            expected = expected and cut['passed'] and features['passed']
        if report['passed'] != expected:
            raise ValueError('循环检查结论与检查项不一致')
