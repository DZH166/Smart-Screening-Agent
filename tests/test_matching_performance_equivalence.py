"""Small frozen-arithmetic controls for the matching IO-free optimizations.

These are synthetic regressions, not independent business accuracy evidence.
The references preserve the preceding float32 arithmetic and phase order so a
changed threshold, rounding result or accepted coverage is observable.
"""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import threading
import time

import cv2
import numpy as np
import pytest

from hsd_tool import matching
from hsd_tool import matching_verification as verification


def original_metrics(first, second, mask=None):
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


@pytest.mark.parametrize('dtype', [np.uint8, np.float32, np.float64])
@pytest.mark.parametrize('mask_kind', ['none', 'empty', 'sparse', 'all'])
def test_pixel_metrics_match_frozen_float32_arithmetic(dtype, mask_kind):
    rng = np.random.default_rng(907)
    boundaries = np.array([0, 9, 11, 12, 51, 52, 114, 115, 140, 141, 254, 255], dtype=dtype)
    first = rng.choice(boundaries, (19, 34, 3))[:, ::2]
    second = rng.choice(boundaries, (19, 34, 3))[:, ::2]
    if dtype != np.uint8:
        first += rng.uniform(-.001, .001, first.shape).astype(dtype)
        second += rng.uniform(-.001, .001, second.shape).astype(dtype)
    mask = (None if mask_kind == 'none' else np.zeros(first.shape[:2], bool)
            if mask_kind == 'empty' else np.ones(first.shape[:2], bool)
            if mask_kind == 'all' else rng.random(first.shape[:2]) < .07)
    assert verification.pixel_metrics(first, second, mask) == original_metrics(first, second, mask)
    assert verification.pixel_rms(first, second) == original_metrics(first, second)['rms']


@pytest.mark.parametrize('value', [0, 11, 12, 51, 52, 114, 115, 140, 141, 255])
def test_pixel_boundary_counts_are_not_relaxed(value):
    first = np.zeros((20, 50, 3), np.uint8)
    second = first.copy()
    second.reshape(-1, 3)[:16] = value
    assert verification.pixel_metrics(first, second) == original_metrics(first, second)
    expected = original_metrics(first, second)
    passed = (expected['rms'] <= .045 and expected['changed'] <= .015
              and expected['major_changed'] <= .003 and expected['worst'] <= .55)
    assert verification._verified_texture_metrics(first, second) == (expected if passed else None)


def frozen_error(first, second, mask=None):
    if mask is not None:
        first, second = first[mask], second[mask]
    error = np.subtract(first, second, dtype=np.float32)
    np.abs(error, out=error)
    error /= 255
    return error


def test_all_uint8_differences_preserve_exact_float32_values():
    values = np.arange(256, dtype=np.uint8)
    first = np.broadcast_to(values[:, None, None], (256, 256, 3)).copy()
    second = np.broadcast_to(values[None, :, None], (256, 256, 3)).copy()
    actual, expected = verification._pixel_error(first, second), frozen_error(first, second)
    assert actual.dtype == expected.dtype == np.float32
    assert actual.shape == expected.shape
    assert np.array_equal(actual.view(np.uint32), expected.view(np.uint32))
    assert np.array_equal(verification._channel_max(actual), expected.max(axis=-1))


@pytest.mark.parametrize('case', ['noncontiguous','transposed','fortran','masked','float32','float64','mixed',
                                 'broadcast','empty','zero_channels','one_channel','one_dimensional'])
def test_arithmetic_fast_paths_keep_generic_fallbacks(case):
    rng = np.random.default_rng(203)
    first = rng.integers(0, 256, (8, 12, 3), dtype=np.uint8)
    second = rng.integers(0, 256, first.shape, dtype=np.uint8)
    mask = None
    if case == 'noncontiguous':
        first, second = first[::-1, ::2, ::-1], second[::-1, ::2, ::-1]
    elif case == 'transposed':
        first, second = first.transpose(1,0,2), second.transpose(1,0,2)
    elif case == 'fortran':
        first, second = np.asfortranarray(first),np.asfortranarray(second)
    elif case == 'masked':
        mask = rng.random(first.shape[:2]) < .25
    elif case == 'float32':
        first, second = first.astype(np.float32) + .0001, second.astype(np.float32) - .0002
    elif case == 'float64':
        first, second = first.astype(np.float64) + 1e-8, second.astype(np.float64) - 1e-8
    elif case == 'mixed':
        second = second.astype(np.float64) + .0003
    elif case == 'broadcast':
        second = second[:1, :1]
    elif case == 'empty':
        first, second = first[:0], second[:0]
    elif case == 'zero_channels':
        first, second = first[..., :0], second[..., :0]
    elif case == 'one_channel':
        first, second = first[..., :1], second[..., :1]
    elif case == 'one_dimensional':
        first, second = first.ravel(), second.ravel()
    actual, expected = verification._pixel_error(first, second, mask), frozen_error(first, second, mask)
    assert actual.shape == expected.shape and actual.dtype == expected.dtype
    assert np.array_equal(actual.view(np.uint32), expected.view(np.uint32))
    assert verification.pixel_metrics(first, second, mask) == original_metrics(first, second, mask)


@pytest.mark.parametrize('channels', [1, 2, 3, 4, 7])
def test_channel_max_preserves_nan_and_infinity_behavior(channels):
    values = np.resize(np.array([0., -0., np.nan, np.inf, -np.inf, .2, .45], np.float32),
                       (5, 9, channels))
    actual, expected = verification._channel_max(values), values.max(axis=-1)
    np.testing.assert_array_equal(actual, expected)
    assert np.array_equal(np.isnan(actual), np.isnan(expected))
    finite = np.isfinite(actual) & np.isfinite(expected)
    assert np.array_equal(actual[finite].view(np.uint32), expected[finite].view(np.uint32))


def test_channel_max_zero_channels_keeps_empty_reduction_error():
    with pytest.raises(ValueError):
        verification._channel_max(np.empty((2, 3, 0), np.float32))


def test_float64_is_converted_before_subtraction_not_after():
    # Subtracting in float64 would retain the 1.0 difference. The existing
    # float32 input conversion rounds both operands to the same integer.
    first = np.full((2, 3, 3), 2**25 + 1., np.float64)
    second = np.full_like(first, 2**25)
    assert np.all(verification._pixel_error(first, second) == 0)


def test_nonfinite_float_inputs_keep_subtraction_and_metric_semantics():
    first = np.array([[[np.nan, np.inf, -np.inf], [0., -0., .2]],
                      [[1., 2., 3.], [np.inf, 0., 4.]]],np.float64)
    second = np.array([[[0., np.inf, np.inf], [-0., 0., .45]],
                       [[2., 4., 6.], [1., np.nan, 3.]]],np.float64)
    with np.errstate(invalid='ignore'):
        np.testing.assert_array_equal(verification._pixel_error(first,second),frozen_error(first,second))
        expected = original_metrics(first,second)
        actual = verification.pixel_metrics(first,second)
    for key in expected:
        if np.isnan(expected[key]): assert np.isnan(actual[key])
        else: assert actual[key] == expected[key]


def test_percentile_is_skipped_only_after_a_definite_unchanged_failure(monkeypatch):
    first = np.zeros((10, 20, 3), np.uint8)
    second = np.full_like(first, 64)
    assert original_metrics(first, second)['rms'] > .045
    monkeypatch.setattr(verification.np, 'percentile', lambda *args, **kwargs: pytest.fail('unneeded percentile'))
    assert verification._verified_texture_metrics(first, second) is None


@pytest.mark.parametrize('period', [1, 2, 7, 11])
def test_phase_axis_is_exactly_sorted_unique_modular_pixels(period):
    for length in range(period * 3 + 1):
        for offset in range(-2, period * 2 + 1):
            assert np.array_equal(verification._phase_axis(length, offset, period),
                                  np.unique((np.arange(length) + offset) % period))


def original_phase_coverage(tiled, query, differences, tile_shape):
    th, tw = tile_shape
    qh, qw = query.shape[:2]
    seen = np.zeros((th, tw), bool)
    accepted = []
    limit = (.045 * 255) ** 2 * float(qh * qw * 3)
    possible = np.flatnonzero(differences.ravel() <= limit)
    if not possible.size:
        return {'source_coverage': 0., 'source_ink_coverage': 0., 'residual': 1., 'phases': []}
    order = possible[np.argsort(differences.ravel()[possible], kind='stable')]
    for index in order:
        y, x = np.unravel_index(int(index), differences.shape)
        target = np.ix_(np.unique((np.arange(qh) + y) % th),
                        np.unique((np.arange(qw) + x) % tw))
        if seen[target].all():
            continue
        patch = tiled[y:y + qh, x:x + qw]
        metrics = original_metrics(query, patch)
        if (metrics['rms'] > .045 or metrics['changed'] > .015
                or metrics['major_changed'] > .003 or metrics['worst'] > .55):
            continue
        if verification.coherent_difference(query, patch) > 0:
            continue
        seen[target] = True
        accepted.append([int(x), int(y)])
        if seen.all() or len(accepted) >= 32:
            break
    ink = tiled[:th, :tw].min(axis=2) < 250
    source_ink = float(seen[ink].mean()) if ink.any() else float(seen.mean())
    return {'source_coverage': float(seen.mean()), 'source_ink_coverage': source_ink,
            'residual': 1 - source_ink, 'phases': accepted}


@pytest.mark.parametrize('change', ['none', 'color', 'local', 'partial', 'extra'])
def test_phase_coverage_preserves_frozen_order_and_all_content_checks(change):
    tile = np.full((12, 24, 3), 245, np.uint8)
    tile[2:9, 3:7] = (20, 80, 180)
    tile[3:8, 14:20] = (90, 160, 30)
    query = np.tile(tile, (1, 2, 1))
    if change == 'color':
        query = query[:, :, ::-1].copy()
    elif change == 'local':
        query = query.copy(); query[2:9, 3:7] = (180, 40, 30)
    elif change == 'partial':
        query = query[:7, :15]
    elif change == 'extra':
        tile = tile.copy(); tile[9:12, 20:24] = (0, 0, 0)
    tiled = np.tile(tile, (2, 3, 1))
    differences = cv2.matchTemplate(tiled, query, cv2.TM_SQDIFF)
    assert verification.phase_coverage(tiled, query, differences, tile.shape[:2]) == original_phase_coverage(
        tiled, query, differences, tile.shape[:2])


class NoFeatures:
    def detectAndCompute(self, image, mask):
        return [], None


def prepared_image(value=220):
    image = np.full((96, 120, 3), value, np.uint8)
    return matching._appearance(image, NoFeatures())


def test_prepared_pixels_and_digest_cannot_be_accidentally_modified():
    image = prepared_image()
    with pytest.raises(ValueError):
        image.image[0, 0] = 0
    with pytest.raises(FrozenInstanceError):
        image.digest = 'stale-digest'
    changed_pixels = image.image.copy()
    changed_pixels[0, 0] = 0
    rebuilt = matching._appearance(changed_pixels, NoFeatures())
    assert rebuilt.digest != image.digest


def test_coarse_texture_is_reused_without_rescaling_final_score(monkeypatch):
    query, candidate = prepared_image(), prepared_image()
    cache = matching._TextureCache()
    raw = {'score': .9, 'rms': .1, 'changed': .2, 'major_changed': .01, 'worst': .9,
           'height': 64, 'method': 'texture', 'strong': False, 'trimmed': False,
           'residual': 1., 'source_coverage': 0., 'source_ink_coverage': 0.,
           'coherent_difference': 1.}
    calls, refined = [], []
    def coarse(*args, **kwargs):
        calls.append(1)
        return copy.deepcopy(raw)
    monkeypatch.setattr(matching, '_texture_search', coarse)
    monkeypatch.setattr(matching, '_texture_scan', lambda *args, **kwargs: refined.append(1))
    first = matching._texture(query, candidate, cache=cache)
    second = matching._texture(query, candidate, cache=cache)
    precise = matching._texture(query, candidate, precision=True, cache=cache)
    assert calls == [1]
    assert refined
    assert first == second == precise
    assert first['score'] == raw['score'] * .94
    assert raw['score'] == .9


def test_cache_is_bounded_content_bound_and_does_not_cache_failures():
    cache = matching._TextureCache(max_bytes=100, max_entries=2)
    first = np.zeros((4, 4, 3), np.uint8)
    altered = first.copy(); altered[0, 0] = 1
    digest = lambda image: hashlib.sha256(image.tobytes()).hexdigest()
    first_scaled = cache.resized(first, (digest(first), first.shape), 4)
    assert cache.resized(first, (digest(first), first.shape), 4) is first_scaled
    changed = cache.resized(altered, (digest(altered), altered.shape), 4)
    assert not np.array_equal(first_scaled, changed)
    cache.resized(np.full_like(first, 2), ('different-content', first.shape), 4)
    assert len(cache._items) <= 2 and cache.bytes <= 100
    attempts = []
    def failed():
        attempts.append(1)
        raise ValueError('synthetic failure')
    for _ in range(2):
        with pytest.raises(ValueError): cache.get(('failure',), failed)
    assert attempts == [1, 1]
    fresh = matching._TextureCache(max_bytes=100, max_entries=2)
    assert fresh.resized(first, (digest(first), first.shape), 4) is not first_scaled


def test_coarse_result_survives_scale_eviction_for_its_precision_pass():
    cache = matching._TextureCache(max_bytes=2048, max_entries=8)
    calls = []
    def coarse():
        calls.append(1)
        return {'score': .9}
    raw = cache.get(('coarse', 'query-pixel-digest', 'candidate-pixel-digest'), coarse)
    for index in range(6):
        cache.get(('resize', index), lambda: np.zeros((20, 20, 3), np.uint8))
    assert cache.get(('coarse', 'query-pixel-digest', 'candidate-pixel-digest'), coarse) is raw
    assert calls == [1] and cache.bytes <= 2048


def test_nominal_width_never_allocates_a_scaled_image(monkeypatch):
    image = np.empty((19, 700, 3), np.uint8)
    monkeypatch.setattr(cv2, 'resize', lambda *args, **kwargs: pytest.fail('width computation must not resize'))
    for height in [1, 18, 32, 64, 96, 256]:
        assert matching._resized_width(image, height) == min(4096, max(2, round(700 * height / 19)))


@pytest.mark.parametrize('coarse,fine', [([.97, .78, .76], [.82, .94, .77]),
                                        ([.85, .77, .76], [.99, None, .79])])
def test_texture_parallelism_preserves_dynamic_ranking_and_ownership(monkeypatch, coarse, fine):
    images = {f'f{index}': prepared_image(180 + index * 10) for index in range(3)}
    identity_by_digest = {image.digest: identity for identity, image in images.items()}
    query = prepared_image()
    rows = [{'id':'r1'}, {'id':'r2'}]
    files = [{'id':identity,'issue':None} for identity in images]
    geometry_threads = []
    def features(*args):
        geometry_threads.append(threading.get_ident())
        return {'score': .5, 'strong': False, 'method':'features'}
    def texture(first, candidate, *, precision=False, cache=None):
        index = int(identity_by_digest[candidate.digest][1:])
        # Deliberately reverse completion order, without using model or sample labels.
        time.sleep((3 - index) * .001)
        score = (fine if precision else coarse)[index]
        if score is None:
            raise ValueError('synthetic optional verification failure')
        return {'score':score,'strong':False,'method':'texture','rms':.01,'changed':.001,
                'major_changed':0.,'worst':.04,'color_distance':0.,'source_coverage':1.,
                'source_ink_coverage':1.,'residual':0.,'coherent_difference':0.}
    monkeypatch.setattr(matching, '_features', features)
    monkeypatch.setattr(matching, '_texture', texture)
    serial = matching._match_appearances(rows, files, {'r1':query,'r2':query}, images, texture_workers=1)
    parallel = matching._match_appearances(rows, files, {'r1':query,'r2':query}, images, texture_workers=2)
    assert serial == parallel
    assert set(geometry_threads) == {threading.get_ident()}
    assert [row['status'] for row in serial] == ['review', 'review']
    assert all('ownership_conflict' in row['evidence']['failed_checks'] for row in serial)
    # In the second control, the first detailed result makes candidate 2
    # ineligible. Its speculative failure must not become a real failed check.
    if fine[1] is None:
        assert serial[0]['evidence']['competition']['failures'] == []


def test_texture_cache_concurrent_duplicate_miss_publishes_one_entry():
    from concurrent.futures import ThreadPoolExecutor
    cache = matching._TextureCache(max_bytes=1024, max_entries=4)
    gate = threading.Barrier(2)
    def get():
        def prepare():
            gate.wait(timeout=2)
            return np.zeros((4, 4, 3), np.uint8)
        return cache.get(('same-content',), prepare)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: get(), range(2)))
    assert first is second
    assert cache.bytes == 48 and len(cache._items) == 1
