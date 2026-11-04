"""Bounded, deterministic horizontal texture quilting for saved loop units.

Only background pixels belong here. Foreground designs must be composited later
from their original files. A minimum-error overlap cut follows Efros/Freeman's
image quilting; it copies source samples, without mirroring, smearing a seam,
painting over it, or changing the source aspect ratio. This is a conservative
pixel-continuity check, never semantic or print approval.

Reference: https://people.eecs.berkeley.edu/~efros/research/quilting.html
Callers serialize large raster operations using imaging.memory_bounded_operation.
"""
from __future__ import annotations

import hashlib

import cv2
import numpy as np
from PIL import Image, ImageColor

ENGINE = 'background-quilting-v1'
MAX_PIXELS = 40_000_000
MAX_SIDE = 16000
_REVIEW_WARNING = '像素检查不代替设计师的视觉和印刷验收，可按需查看连续效果。'


class BackgroundLoopError(ValueError):
    def __init__(self, report):
        super().__init__('底纹未通过循环连续性检查，请更换底纹或人工检查后调整')
        self.report = report


def preferred_period(background: Image.Image, height: int) -> int:
    """Fit source height uniformly and reserve 1/6 of the unit for overlap.

    A square texture at height 520 gives a preferred period of 446 pixels. The
    foreground loop can use an integer multiple, repeating these exact pixels.
    This suggestion is geometry only, not evidence that the source is seamless.
    """
    _dimensions(background.width, background.height)
    if not isinstance(height, int) or not 16 <= height <= MAX_SIDE:
        raise ValueError('循环底纹高度超出允许范围')
    period = max(16, round(height * background.width / background.height * 6 / 7))
    overlap = max(8, min(512, round(period / 6)))
    if period + overlap > MAX_SIDE or (period + overlap) * height > MAX_PIXELS:
        raise ValueError('底纹按当前高度等比循环后尺寸过大，请改用较接近方形的底纹；没有拉伸或截短原图')
    return period


def _dimensions(width, height):
    if (not isinstance(width, int) or not isinstance(height, int)
            or width < 1 or height < 1 or width > MAX_SIDE or height > MAX_SIDE
            or width * height > MAX_PIXELS):
        raise ValueError('循环底纹像素数量或尺寸超出允许范围')


def _opaque(background, background_color):
    color = ImageColor.getrgb(background_color) if isinstance(background_color, str) else tuple(background_color)
    if len(color) != 3 or any(not 0 <= value <= 255 for value in color):
        raise ValueError('循环底纹合成底色不正确')
    if background.mode == 'RGB':
        return background.copy(), None, 1.0
    with background.convert('RGBA') as rgba, rgba.getchannel('A') as alpha:
        bbox = alpha.getbbox()
        if bbox is None:
            raise ValueError('底纹没有可见内容，请更换图片')
        # Composite before resizing/measurement. Hidden RGB in alpha=0 pixels
        # cannot influence matching, and partial alpha is measured as printed.
        opaque = Image.new('RGB', background.size, color)
        opaque.paste(rgba, (0, 0), alpha)
        visible = sum(index * count for index, count in enumerate(alpha.histogram())) / (255 * background.width * background.height)
        return opaque, list(bbox), round(visible, 6)


def _minimum_path(cost):
    height, width = cost.shape
    guard = max(2, width // 16)
    parents = np.zeros((height, width), dtype=np.int8)
    previous = cost[0].copy()
    previous[:guard] = previous[-guard:] = np.inf
    # Explicit centre tie-break, too small to override a one-level pixel error.
    previous += np.abs(np.arange(width) - (width - 1) / 2) * .00001
    for y in range(1, height):
        candidates = np.empty((3, width), dtype=np.float32)
        candidates[0, 0] = candidates[2, -1] = np.inf
        candidates[0, 1:] = previous[:-1]
        candidates[1] = previous
        candidates[2, :-1] = previous[1:]
        choices = candidates.argmin(axis=0)
        previous = cost[y] + candidates[choices, np.arange(width)]
        previous[:guard] = previous[-guard:] = np.inf
        parents[y] = choices.astype(np.int8) - 1
    path = np.empty(height, dtype=np.int32)
    path[-1] = previous.argmin()
    for y in range(height - 1, 0, -1):
        path[y - 1] = path[y] + parents[y, path[y]]
    return path


def _cut_diagnostics(left, right, path):
    rows = np.arange(len(path))
    a = left[rows, path].astype(np.float32)
    b = right[rows, path].astype(np.float32)
    previous_a = left[rows, path - 1].astype(np.float32)
    previous_b = right[rows, path - 1].astype(np.float32)
    error = np.maximum(np.max(np.abs(a - b), axis=1),
                       np.max(np.abs(previous_a - previous_b), axis=1))
    ga, gb = a - previous_a, b - previous_b
    gradient = np.max(np.abs(ga - gb), axis=1)
    previous_rows = np.maximum(0, rows - 1)
    gy_a = a - left[previous_rows, path].astype(np.float32)
    gy_b = b - right[previous_rows, path].astype(np.float32)
    gradient = np.maximum(gradient, np.max(np.abs(gy_a - gy_b), axis=1))
    stats = dict(mean=float(error.mean()), p95=float(np.percentile(error, 95)),
                 maximum=float(error.max()), gradient_mean=float(gradient.mean()),
                 gradient_p95=float(np.percentile(gradient, 95)),
                 gradient_maximum=float(gradient.max()))
    # Absolute colour/structure limits prevent a high-contrast image's own
    # variance from excusing a severed line or abrupt join.
    stats['passed'] = (stats['mean'] <= 12 and stats['p95'] <= 28
                       and stats['maximum'] <= 72 and stats['gradient_mean'] <= 10
                       and stats['gradient_p95'] <= 30 and stats['gradient_maximum'] <= 96)
    return {key: round(value, 4) if isinstance(value, float) else value for key, value in stats.items()}


def _band_delta(pixels, rows, positions, radius):
    width = pixels.shape[1]
    before = (positions[:, None] + np.arange(-radius, 0)) % width
    after = (positions[:, None] + np.arange(radius)) % width
    a = pixels[rows[:, None], before].astype(np.float32).mean(axis=1)
    b = pixels[rows[:, None], after].astype(np.float32).mean(axis=1)
    return np.max(np.abs(a - b), axis=1)


def _multiscale(pixels, paths):
    """Check joins against interior transitions, including bands beyond edges.

    At most 1024 evenly spaced rows are sampled here; the actual cut's native
    full-height colour/gradient measurements are separate and unsampled.
    """
    height, width = pixels.shape[:2]
    rows = np.unique(np.linspace(0, height - 1, min(height, 1024)).round().astype(int))
    scales = [value for value in (1, 2, 4, 8, 16, 32) if value <= max(1, width // 12)]
    records = []
    for radius in scales:
        baseline = []
        for x in np.unique(np.linspace(radius, width - radius, min(25, width - 2 * radius + 1)).round().astype(int)):
            baseline.append(_band_delta(pixels, rows, np.full(len(rows), x), radius))
        baseline = np.concatenate(baseline)
        mean_reference = float(np.percentile(baseline, 90))
        peak_reference = float(np.percentile(baseline, 99))
        # Relative thresholds cover natural textures; hard cut checks above
        # remain necessary because relative thresholds alone excuse motifs.
        mean_limit = max(5.0, mean_reference * 2.5 + 2)
        peak_limit = max(16.0, peak_reference * 2.0 + 4)
        for name, positions in paths.items():
            values = _band_delta(pixels, rows, positions[rows], radius)
            mean, p95 = float(values.mean()), float(np.percentile(values, 95))
            records.append(dict(join=name, radius=radius, mean=round(mean, 4), p95=round(p95, 4),
                                interior_p90=round(mean_reference, 4), interior_p99=round(peak_reference, 4),
                                mean_limit=round(mean_limit, 4), p95_limit=round(peak_limit, 4),
                                passed=bool(mean <= mean_limit and p95 <= peak_limit)))
    return records


def _feature_diagnostics(image):
    """Conservative high-contrast feature guard, deliberately not called OCR.

    Thin line textures are allowed. Large connected colour regions or thick
    marks need review: quilting cannot establish that cropping them is safe.
    Small text, low-contrast subjects and semantic importance remain unknown.
    """
    ratio = min(1., 1024 / max(image.size))
    with image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.Resampling.BOX) as sample:
        pixels = np.asarray(sample)
        median = np.median(pixels.reshape(-1, 3), axis=0)
        mask = (np.max(np.abs(pixels.astype(np.int16) - median), axis=2) >= 48).astype(np.uint8)
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        height, width = mask.shape
        regions = []
        for x, y, w, h, area in stats[1:count]:
            # Full-height one-pixel lines are a valid texture, unlike a broad
            # letter, badge or illustrated subject. Guard uses BOTH dimensions.
            if (area >= max(24, width * height * .006)
                    and max(w, h) >= height * .32 and min(w, h) >= height * .065):
                regions.append(dict(box=[int(round(value / ratio)) for value in (x, y, x + w, y + h)],
                                    area_fraction=round(float(area / (width * height)), 6)))
        return dict(large_high_contrast_regions=regions[:16], region_count=len(regions),
                    method='dominant_colour_components_not_semantic_detection', passed=not regions)


def assess_periodicity(tile: Image.Image) -> dict:
    """Measure a supplied tile's wrap seam at six scales, not just edge columns.

    This does not know whether an internal splice exists, and does not approve
    semantics. periodize_background additionally inspects its actual cut.
    """
    _dimensions(tile.width, tile.height)
    opaque, _, _ = _opaque(tile, '#ffffff')
    try:
        pixels = np.asarray(opaque)
        checks = _multiscale(pixels, {'wrap': np.zeros(tile.height, dtype=np.int32)})
        return dict(passed=all(row['passed'] for row in checks), multiscale=checks,
                    verification_scope='pixel_continuity_only', production_verified=False,
                    warnings=[_REVIEW_WARNING])
    finally:
        opaque.close()


def periodize_background(background: Image.Image, unit_width: int, height: int, *,
                         background_color='#ffffff', strict=False) -> tuple[Image.Image, dict]:
    """Return an exact-width RGBA tile plus immutable-ready diagnostic metadata.

    The centred source window is uniformly scaled to W+overlap by H. Its right
    overlap is quilted onto its left overlap; every pixel from overlap to W is
    copied unchanged. Wrap samples then follow contiguous source pixels. A bad
    match stays visible and returns needs_review, never a fabricated success.
    strict=True instead raises BackgroundLoopError carrying the same report.
    Decode/resource/empty-alpha errors always raise. The source is never edited.
    """
    _dimensions(background.width, background.height)
    _dimensions(unit_width, height)
    if unit_width < 16 or height < 16:
        raise ValueError('循环底纹单元至少为16像素')
    overlap = max(8, min(512, round(unit_width / 6)))
    if overlap >= unit_width:
        raise ValueError('循环底纹单元过窄')
    cover_width = unit_width + overlap
    _dimensions(cover_width, height)
    opaque, alpha_bbox, alpha_coverage = _opaque(background, background_color)
    ratio = max(cover_width / background.width, height / background.height)
    source_width, source_height = cover_width / ratio, height / ratio
    left = (background.width - source_width) / 2
    top = (background.height - source_height) / 2
    box = (left, top, left + source_width, top + source_height)
    try:
        source_features = _feature_diagnostics(opaque)
        # A floating source box gives identical x/y sampling scale. Unlike a
        # rounded intermediate resize there is no anisotropic pixel fitting.
        cropped = opaque.resize((cover_width, height), Image.Resampling.LANCZOS, box=box)
    finally:
        opaque.close()
    try:
        source = np.asarray(cropped)
        a, b = source[:, :overlap], source[:, unit_width:]
        difference = a.astype(np.float32) - b.astype(np.float32)
        cost = np.mean(difference * difference, axis=2)
        del difference
        # Derivative agreement discourages cutting across mismatched outlines.
        da = np.diff(a.astype(np.float32), axis=1, prepend=a[:, :1])
        db = np.diff(b.astype(np.float32), axis=1, prepend=b[:, :1])
        cost += np.mean((da - db) ** 2, axis=2) * .5
        del da, db
        da = np.diff(a.astype(np.float32), axis=0, prepend=a[:1])
        db = np.diff(b.astype(np.float32), axis=0, prepend=b[:1])
        cost += np.mean((da - db) ** 2, axis=2) * .5
        del da, db
        path = _minimum_path(cost)
        del cost
        cut = _cut_diagnostics(a, b, path)
        result = source[:, :unit_width].copy()
        for y, x in enumerate(path):
            result[y, :x] = b[y, :x]
        checks = _multiscale(result, {'wrap': np.zeros(height, dtype=np.int32), 'quilt_cut': path})
        features = _feature_diagnostics(cropped)
        features['source_features'] = source_features
        features['passed'] = features['passed'] and source_features['passed']
        issues = []
        if not cut['passed']:
            issues.append(dict(code='overlap_colour_or_structure_mismatch', message='底纹两侧颜色或线条无法可靠衔接'))
        if not all(row['passed'] for row in checks):
            issues.append(dict(code='multiscale_join_discontinuity', message='平铺连接在局部或较宽色带上仍有突变'))
        if not features['passed']:
            issues.append(dict(code='large_high_contrast_background_features', message='底纹含较大高对比图形，无法确认裁取和循环完整性'))
        report = dict(engine=ENGINE, passed=not issues, status='needs_review' if issues else 'pixel_checks_passed',
                      verification_scope='pixel_continuity_only', production_verified=False,
                      source_size=list(background.size), source_alpha_bbox=alpha_bbox,
                      source_alpha_coverage=alpha_coverage, alpha_policy='composite_before_resample_and_measurement',
                      background_color=list(ImageColor.getrgb(background_color) if isinstance(background_color, str) else background_color),
                      source_crop_box=[round(value, 8) for value in box], uniform_scale=round(ratio, 10),
                      working_size=[cover_width, height], tile_size=[unit_width, height], overlap=overlap,
                      preserved_working_rectangle=[overlap, 0, unit_width, height],
                      cut_path=path.tolist(), cut=cut, multiscale=checks, features=features,
                      issues=issues, warnings=[row['message'] for row in issues] + [_REVIEW_WARNING],
                      limitations=['No OCR or subject recognition', 'No print-quality approval',
                                   'Multiscale bands sample at most 1024 rows; cut measurements use every row'],
                      pixel_sha256=hashlib.sha256(result.tobytes()).hexdigest())
        if strict and issues:
            raise BackgroundLoopError(report)
        with Image.fromarray(result) as rgb:
            tile = rgb.convert('RGBA')
        return tile, report
    finally:
        cropped.close()
