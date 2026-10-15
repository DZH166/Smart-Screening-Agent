"""Coverage proofs for measured image alignments, without identity heuristics.

The interior mask excludes interpolation boundaries.  Its excluded thin edge is
checked separately against real pixels before it can contribute to coverage.
Periodically repeated previews are accepted only when measured matching phases
also account for the entire candidate, not just the query's selected band.
"""
from __future__ import annotations

import cv2
import numpy as np
from functools import lru_cache


def pixel_metrics(first: np.ndarray, second: np.ndarray, mask=None) -> dict:
    error = np.abs(first.astype(np.float32) - second.astype(np.float32)) / 255
    if mask is not None:
        error = error[mask]
    if not error.size:
        return {'mae': 1., 'rms': 1., 'changed': 1., 'major_changed': 1., 'worst': 1.}
    pixels = error.max(axis=-1)
    return {'mae': float(error.mean()), 'rms': float(np.sqrt(np.mean(error ** 2))),
            'changed': float((pixels > .2).mean()),
            'major_changed': float((pixels > .45).mean()),
            'worst': float(np.percentile(pixels, 99.5))}


def geometry_pixels_ok(metrics: dict) -> bool:
    return (metrics['mae'] <= .045 and metrics['changed'] <= .08
            and metrics['major_changed'] <= .015)


def coherent_difference(first: np.ndarray, second: np.ndarray, mask=None) -> float:
    """Detect a real filled change that an average over a large background hides.

    Renderer/interpolation errors usually form a thin contour. A changed motif
    or low-contrast replacement has a connected interior as well. Require both
    meaningful area and a substantial 5x5 interior, so a thin stripe edge is
    not classified as a replaced design. The 9-level floor exceeds the observed
    1-2-level integer renderer rounding, without normalising away colour changes.
    """
    changed = np.max(cv2.absdiff(first, second), axis=2) > 9
    if mask is not None:
        changed &= mask
    # A tiny unobserved border must not magnify a few rounding pixels into a
    # large percentage. Significance always uses the complete comparison frame.
    area = changed.size
    if not changed.any() or not area:
        return 0.
    changed = changed.astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(changed, 8)
    core = cv2.erode(changed, np.ones((5, 5), np.uint8),
                     borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    cores = np.bincount(labels[core], minlength=count)
    substantial = [int(stats[index, cv2.CC_STAT_AREA]) for index in range(1, count)
                   if stats[index, cv2.CC_STAT_AREA] >= max(9, area * .0005)
                   and cores[index] / stats[index, cv2.CC_STAT_AREA] >= .3]
    return sum(substantial) / area


def affine_coverage(query: np.ndarray, candidate: np.ndarray,
                    transforms: list[np.ndarray]) -> dict:
    """Recheck interpolation edges in both image planes for proven transforms."""
    qh, qw = query.shape[:2]
    ch, cw = candidate.shape[:2]
    qmask = np.zeros((qh, qw), bool)
    cmask = np.zeros((ch, cw), bool)
    qinner = qmask.copy()
    cinner = cmask.copy()
    qerror = np.full(query.shape, np.inf, np.float32)
    qextrap = np.full(query.shape, 255., np.float32)
    cextrap = np.full(candidate.shape, 255., np.float32)
    first = cv2.GaussianBlur(query, (3, 3), .6)
    original = cv2.GaussianBlur(candidate, (3, 3), .6)
    edge_checks = []
    for transform in transforms:
        raw = cv2.warpAffine(np.ones((ch, cw), np.uint8), transform,
                            (qw, qh), flags=cv2.INTER_NEAREST).astype(bool)
        interior = cv2.erode(raw.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        aligned = cv2.warpAffine(candidate, transform, (qw, qh),
                                 borderMode=cv2.BORDER_REPLICATE)
        aligned = cv2.GaussianBlur(aligned, (3, 3), .6)
        inner_values = pixel_metrics(first, aligned, interior)
        if not geometry_pixels_ok(inner_values):
            edge_checks.append({'accepted': False, 'reason': 'interior_difference',
                                'query': inner_values})
            continue
        qinner |= interior
        edge = raw & ~interior
        edge_values = pixel_metrics(first, aligned, edge) if edge.any() else inner_values
        usable = raw if not edge.any() or geometry_pixels_ok(edge_values) else interior
        qmask |= usable
        difference = np.abs(first.astype(np.float32) - aligned.astype(np.float32)) / 255
        qextrap = np.minimum(qextrap, difference * 255)
        qerror[usable] = np.minimum(qerror[usable], difference[usable])
        reverse = cv2.invertAffineTransform(transform)
        source_raw = cv2.warpAffine(np.ones((qh, qw), np.uint8), reverse,
                                   (cw, ch), flags=cv2.INTER_NEAREST).astype(bool)
        source_inner = cv2.erode(source_raw.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        cinner |= source_inner
        source_edge = source_raw & ~source_inner
        back = cv2.warpAffine(query, reverse, (cw, ch), borderMode=cv2.BORDER_REPLICATE)
        back = cv2.GaussianBlur(back, (3, 3), .6)
        cextrap = np.minimum(cextrap, cv2.absdiff(original, back).astype(np.float32))
        reverse_values = (pixel_metrics(original, back, source_edge)
                          if source_edge.any() else inner_values)
        cmask |= (source_raw if not source_edge.any() or geometry_pixels_ok(reverse_values)
                  else source_inner)
        edge_checks.append({'accepted': True, 'query': edge_values,
                            'candidate': reverse_values})
    ink = candidate.min(axis=2) < 250
    coverage = float(qmask.mean())
    values = qerror[qmask]
    q_unknown = coherent_difference(np.zeros(query.shape, np.uint8),
        np.clip(qextrap, 0, 255).astype(np.uint8), ~qmask & (query.min(axis=2) < 250))
    c_unknown = coherent_difference(np.zeros(candidate.shape, np.uint8),
        np.clip(cextrap, 0, 255).astype(np.uint8), ~cmask & ink)
    return {'query_coverage': coverage, 'candidate_coverage': float(cmask.mean()),
            'candidate_ink_coverage': float(cmask[ink].mean()) if ink.any() else float(cmask.mean()),
            'edge_verified_coverage': float((qmask & ~qinner).mean()),
            'candidate_edge_verified_coverage': float((cmask & ~cinner).mean()),
            'global_mae': float(values.mean()) if values.size and coverage >= .95 else 1.,
            'global_changed': float((values.max(axis=1) > .2).mean()) if values.size and coverage >= .95 else 1.,
            'unverified_query_coherent': q_unknown,
            'unverified_candidate_coherent': c_unknown,
            'edge_checks': edge_checks}


def phase_coverage(tiled: np.ndarray, query: np.ndarray, differences: np.ndarray,
                   tile_shape: tuple[int, int]) -> dict:
    """Only actual matching query placements may explain candidate pixels.

    A cheap SQDIFF screen is followed by changed-area and major-change checks.
    Every useful accepted phase contributes its rectangle modulo the candidate
    tile.  Thus an unrelated second design outside a matched band stays unknown.
    """
    th, tw = tile_shape
    qh, qw = query.shape[:2]
    seen = np.zeros((th, tw), bool)
    accepted = []
    area = float(qh * qw * 3)
    limit = (.045 * 255) ** 2 * area
    possible = np.flatnonzero(differences.ravel() <= limit)
    if not possible.size:
        return {'source_coverage': 0., 'source_ink_coverage': 0., 'residual': 1., 'phases': []}
    order = possible[np.argsort(differences.ravel()[possible], kind='stable')]
    for index in order:
        y, x = np.unravel_index(int(index), differences.shape)
        ys = (np.arange(qh) + y) % th
        xs = (np.arange(qw) + x) % tw
        target = np.ix_(np.unique(ys), np.unique(xs))
        if seen[target].all():
            continue
        patch = tiled[y:y + qh, x:x + qw]
        metrics = pixel_metrics(query, patch)
        if (metrics['rms'] > .045 or metrics['changed'] > .015
                or metrics['major_changed'] > .003 or metrics['worst'] > .55):
            continue
        if coherent_difference(query, patch) > 0:
            continue
        seen[target] = True
        accepted.append([int(x), int(y)])
        if seen.all():
            break
        # Bounded diagnostic size; coverage remains conservative when the limit
        # is reached, rather than declaring unseen pixels equivalent.
        if len(accepted) >= 32:
            break
    tile = tiled[:th, :tw]
    ink = tile.min(axis=2) < 250
    source_ink = float(seen[ink].mean()) if ink.any() else float(seen.mean())
    return {'source_coverage': float(seen.mean()), 'source_ink_coverage': source_ink,
            'residual': 1 - source_ink, 'phases': accepted}


def _axis_period(image: np.ndarray, axis: int) -> dict | None:
    """Find a translation actually supported across several observed repeats.

    A profile only nominates offsets. Every nominated fractional offset must
    reproduce the full 2-D RGB image, so similar density or an average colour is
    never a periodicity proof.
    """
    array = image if axis == 1 else image.transpose(1, 0, 2)
    height, length = array.shape[:2]
    if length < 12:
        return None
    if np.max(np.std(array.astype(np.float32), axis=1)) <= .75:
        return {'period': 1., 'constant': True, 'rms': 0., 'changed': 0., 'major_changed': 0.}
    view = cv2.resize(array, (length, min(height, 24)), interpolation=cv2.INTER_AREA)
    window = max(8, length // 3)
    profile = cv2.matchTemplate(view, view[:, :window], cv2.TM_SQDIFF)[0]
    limit = min(len(profile) - 1, int(length / 2.5))
    nominated = [i for i in range(4, limit) if profile[i] <= profile[i - 1] and profile[i] <= profile[i + 1]]
    nominated = sorted(nominated, key=lambda i: profile[i])[:8]
    best = None
    for offset in nominated:
        for adjustment in (0., -.5, -.375, -.25, -.125, .125, .25, .375, .5):
            period = offset + adjustment
            width = int(np.floor(length - period))
            xs = (np.arange(width, dtype=np.float32) + period)[None, :]
            xs = np.broadcast_to(xs, (height, width)).copy()
            ys = np.broadcast_to(np.arange(height, dtype=np.float32)[:, None], (height, width)).copy()
            shifted = cv2.remap(array, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            values = pixel_metrics(array[:, :width], shifted)
            if (values['rms'] <= .045 and values['changed'] <= .015
                    and values['major_changed'] <= .003 and values['worst'] <= .55):
                item = dict(values, period=float(period), constant=False)
                # Prefer the smallest independently verified repeat, so a
                # misleading large fragment cannot hide a local replacement.
                if best is None or period < best['period'] - 1 or (abs(period - best['period']) <= 1 and values['rms'] < best['rms']):
                    best = item
    return best


@lru_cache(maxsize=32)
def _periods_cached(shape: tuple, pixels: bytes) -> tuple:
    image = np.frombuffer(pixels, np.uint8).reshape(shape)
    return _axis_period(image, 1), _axis_period(image, 0)


def periodic_extension(query: np.ndarray, tile: np.ndarray, location: tuple[int, int]) -> dict | None:
    """Explain the entire candidate using independently measured query periods.

    This is deliberately different from wrapping the artboard: its edge is not
    assumed to be a period. Both periods must first be visible and verified in
    the query itself, and the resulting model must reproduce every source pixel.
    """
    periods = _periods_cached(query.shape, query.tobytes())
    if any(period is None for period in periods):
        return None
    px, py = (period['period'] for period in periods)
    h, w = tile.shape[:2]
    # A search placement can be in the second copy of the source canvas. That
    # canvas width is not a measured motif period and must not shift the phase.
    x, y = location[0] % w, location[1] % h
    best = None
    for dy in (0., -.5, .5):
        for dx in (0., -.5, .5):
            xs = ((np.arange(w, dtype=np.float32) - x + dx) % px)[None, :]
            ys = ((np.arange(h, dtype=np.float32) - y + dy) % py)[:, None]
            model = cv2.remap(query, np.broadcast_to(xs, (h, w)).copy(),
                              np.broadcast_to(ys, (h, w)).copy(), cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
            values = pixel_metrics(tile, model)
            if best is None or values['rms'] < best['rms']:
                best = dict(values, periods={'x': periods[0], 'y': periods[1]},
                            phase_adjustment=[dx, dy])
    if (best['rms'] <= .045 and best['changed'] <= .015 and best['major_changed'] <= .003
            and best['worst'] <= .55):
        dx, dy = best['phase_adjustment']
        xs = ((np.arange(w, dtype=np.float32) - x + dx) % px)[None, :]
        ys = ((np.arange(h, dtype=np.float32) - y + dy) % py)[:, None]
        model = cv2.remap(query, np.broadcast_to(xs, (h, w)).copy(),
                          np.broadcast_to(ys, (h, w)).copy(), cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)
        coherent = coherent_difference(tile, model)
        if coherent == 0:
            return dict(best, coherent_difference=coherent,
                        source_coverage=1., source_ink_coverage=1., residual=0.)
        return dict(best, coherent_difference=coherent,
                    source_coverage=0., source_ink_coverage=0., residual=1.)
    return dict(best, source_coverage=0., source_ink_coverage=0., residual=1.)
