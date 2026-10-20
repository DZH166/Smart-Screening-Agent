"""Synthetic controls for AI routing; model suggestions are never proof."""
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from hsd_tool import matching
from test_matching import artwork, setup_case, stripes


def prepared_case(tmp_path, originals, queries=None, pages=1):
    source, rows = setup_case(tmp_path, originals, queries, pages=pages)
    prepared = matching.prepare_matching(str(source), rows, str(tmp_path / 'work'))
    return source, rows, prepared


def proposed(prepared, identity='f0001', verdict='same'):
    return {row['id']: {'file_id': identity, 'verdict': verdict} for row in prepared.rows}


def test_prepare_and_verify_render_once_and_keep_original_api(tmp_path, monkeypatch):
    image = artwork(104)
    source, rows = setup_case(tmp_path, [image, artwork(105)])
    render = matching._render
    calls = []

    def counted(record, directory):
        calls.append(record['id'])
        return render(record, directory)

    monkeypatch.setattr(matching, '_render', counted)
    prepared = matching.prepare_matching(str(source), rows, str(tmp_path / 'work'))
    assert len(calls) == 2
    baseline = matching.match_prepared(prepared, texture_workers=1)
    routed = matching.match_prepared(prepared, proposals=proposed(prepared), texture_workers=1)
    assert len(calls) == 2
    assert baseline['matches'][0]['status'] == routed['matches'][0]['status'] == 'auto'
    assert baseline['matches'][0]['file_id'] == routed['matches'][0]['file_id'] == 'f0001'
    assert 'bounded_geometry' in routed['matches'][0]['evidence']['competition']
    # The default route has no AI-derived evidence, even if a caller modifies
    # the separate original input row objects after preparation.
    rows[0]['issue'] = 'different caller state'
    assert prepared.rows[0]['issue'] is None
    assert 'bounded_geometry' not in baseline['matches'][0]['evidence']['competition']


@pytest.mark.parametrize('case', ['color', 'local', 'extra', 'partial', 'duplicate',
                                 'near', 'multi_artboard', 'uncertain', 'unknown'])
def test_proposal_does_not_remove_difference_or_hard_ambiguity(tmp_path, case):
    image = artwork(207)
    candidate = image.copy()
    pages = 1
    if case == 'color':
        candidate = candidate[:, :, ::-1].copy()
    elif case == 'local':
        candidate[80:150, 200:320] = (0, 0, 0)
    elif case == 'extra':
        candidate = np.concatenate([candidate, artwork(208)[:, :200]], axis=1)
    elif case == 'partial':
        image = np.concatenate([image[:, :300], artwork(209)[:, 300:]], axis=1)
    elif case == 'multi_artboard':
        pages = 2
    originals = [candidate]
    if case == 'duplicate':
        originals.append(candidate.copy())
    if case == 'near':
        near = candidate.copy()
        cv2.circle(near, (610, 180), 9, (80, 50, 120), -1)
        originals.append(near)
    _, _, prepared = prepared_case(tmp_path, originals, [image], pages)
    baseline = matching.match_prepared(prepared, texture_workers=1)
    hints = proposed(prepared, 'f9999' if case == 'unknown' else 'f0001',
                     'uncertain' if case == 'uncertain' else 'same')
    routed = matching.match_prepared(prepared, proposals=hints, texture_workers=1)
    if case in ('uncertain', 'unknown'):
        assert routed == baseline
    else:
        assert routed['matches'][0]['status'] != 'auto'
        assert routed['matches'][0]['file_id'] is None


def test_wrong_suggestion_still_checks_the_whole_library(tmp_path):
    image = artwork(303)
    _, _, prepared = prepared_case(tmp_path, [artwork(304), image], [image])
    result = matching.match_prepared(prepared, proposals=proposed(prepared), texture_workers=1)
    match = result['matches'][0]
    assert match['status'] == 'auto' and match['file_id'] == 'f0002'
    assert match['evidence']['competition']['evaluated_file_ids'] == ['f0001', 'f0002']
    assert 'bounded_geometry' not in match['evidence']['competition']


def test_two_rows_cannot_allocate_the_same_suggested_file(tmp_path):
    image = artwork(404)
    _, _, prepared = prepared_case(tmp_path, [image, artwork(405)], [image, image])
    result = matching.match_prepared(prepared, proposals=proposed(prepared), texture_workers=1)
    assert [m['status'] for m in result['matches']] == ['review', 'review']
    assert all('ownership_conflict' in m['evidence']['failed_checks'] for m in result['matches'])


def test_texture_only_suggestion_uses_original_full_verification(tmp_path):
    image = stripes(width=720)
    _, _, prepared = prepared_case(tmp_path, [image], [image])
    baseline = matching.match_prepared(prepared, texture_workers=1)
    routed = matching.match_prepared(prepared, proposals=proposed(prepared), texture_workers=1)
    assert routed == baseline
    assert routed['matches'][0]['status'] == 'auto'
    assert 'bounded_geometry' not in routed['matches'][0]['evidence']['competition']


def test_changed_source_after_provider_wait_requires_reimport(tmp_path):
    image = artwork(507)
    source, _, prepared = prepared_case(tmp_path, [image])
    path = source / 'original_0.ai'
    original = path.read_bytes()
    path.write_bytes(original + b'\n% source was changed during retrieval\n')
    with pytest.raises(ValueError, match='源文件发生变化'):
        matching.match_prepared(prepared, proposals=proposed(prepared))


@pytest.mark.parametrize('kind', ['preview', 'row_image'])
def test_changed_encoded_image_cannot_reuse_older_in_memory_pixels(tmp_path, kind):
    image = artwork(508)
    _, _, prepared = prepared_case(tmp_path, [image])
    from pathlib import Path
    path = Path(prepared.files[0]['preview_path'] if kind == 'preview'
                else prepared.rows[0]['image_path'])
    path.write_bytes(path.read_bytes() + b'\nchanged image encoding\n')
    with pytest.raises(ValueError, match='源文件发生变化'):
        matching.match_prepared(prepared, proposals=proposed(prepared))


def test_file_change_during_verification_is_detected_before_publishing(tmp_path, monkeypatch):
    image = artwork(509)
    _, _, prepared = prepared_case(tmp_path, [image])
    from pathlib import Path
    path = Path(prepared.rows[0]['image_path'])

    def verify(*args, **kwargs):
        path.write_bytes(path.read_bytes() + b'\nchanged during local proof\n')
        return [{'status': 'auto', 'row_id': 'r2', 'file_id': 'f0001'}]

    monkeypatch.setattr(matching, '_match_appearances', verify)
    with pytest.raises(ValueError, match='源文件发生变化'):
        matching.match_prepared(prepared, proposals=proposed(prepared))


def test_correspondence_hull_upper_bound_contains_every_subset():
    candidate = SimpleNamespace(image=np.zeros((100, 300, 3), np.uint8))
    rng = np.random.default_rng(6001)
    points = rng.uniform((0, 0), (300, 100), (24, 2))
    bound = matching._geometric_score_upper_bound(points, candidate)
    for count in range(6, 25):
        for _ in range(12):
            subset = points[rng.choice(len(points), count, replace=False)]
            coverage = cv2.contourArea(cv2.convexHull(np.float32(subset))) / 30000
            score = min(1., count / 14) * min(1., coverage / .18)
            assert score <= bound


def test_bound_skips_expensive_geometry_only_when_competitor_cannot_close_gap(monkeypatch):
    candidate = SimpleNamespace(image=np.zeros((100, 300, 3), np.uint8))
    points = [(x, y) for x in (5., 9., 13.) for y in (5., 9., 13.)]
    monkeypatch.setattr(matching, '_feature_correspondences', lambda *args: (points, points))
    monkeypatch.setattr(cv2, 'estimateAffine2D', lambda *args, **kwargs:
                        pytest.fail('a proven low upper bound should avoid RANSAC'))
    result = matching._features(None, candidate, score_cutoff=.865)
    assert result['score_upper_bound'] < .865 and not result['strong']
    assert result['evaluated_by'] == 'geometric_score_upper_bound'


def test_potential_competitor_is_not_excluded_by_model_priority(monkeypatch):
    candidate = SimpleNamespace(image=np.zeros((100, 300, 3), np.uint8))
    points = [(x, y) for x in (5., 75., 150., 225., 295.) for y in (5., 50., 95.)]
    monkeypatch.setattr(matching, '_feature_correspondences', lambda *args: (points, points))
    calls = []

    def geometry(*args, **kwargs):
        calls.append(True)
        return None, None

    monkeypatch.setattr(cv2, 'estimateAffine2D', geometry)
    result = matching._features(None, candidate, score_cutoff=.865)
    assert calls == [True] and 'score_upper_bound' not in result


def test_failed_competitor_measurement_blocks_automatic_acceptance(tmp_path, monkeypatch):
    image = artwork(700)
    _, _, prepared = prepared_case(tmp_path, [image, artwork(701)])
    original = matching._features

    def evaluate(query, candidate, **kwargs):
        if candidate is prepared.file_images['f0002']:
            raise ValueError('synthetic unreadable competition')
        return original(query, candidate, **kwargs)

    monkeypatch.setattr(matching, '_features', evaluate)
    match = matching.match_prepared(prepared, proposals=proposed(prepared),
                                    texture_workers=1)['matches'][0]
    assert match['status'] == 'review' and match['file_id'] is None
    assert 'incomplete_candidate_validation' in match['evidence']['failed_checks']


@pytest.mark.parametrize('top_score,rival_score,rival_bound', [
    (.99, .90, .905), (.92, .83, .84), (.99, .87, .87)])
def test_upper_bound_preserves_credible_competitors_beyond_runner_up_gap(
        top_score, rival_score, rival_bound, monkeypatch):
    images = {f'f{i}': SimpleNamespace(digest=f'image-{i}', histogram=np.ones(1, np.float32))
              for i in range(1, 4)}
    query = SimpleNamespace(histogram=np.ones(1, np.float32))
    identities = {id(image): identity for identity, image in images.items()}
    measured = []

    def features(first, candidate, *, score_cutoff=None):
        identity = identities[id(candidate)]
        score = top_score if identity == 'f1' else rival_score if identity == 'f2' else .60
        bound = rival_bound if identity == 'f2' else .65
        if score_cutoff is not None and bound < score_cutoff and identity != 'f1':
            return {'score': bound, 'strong': False, 'method': 'features',
                    'score_upper_bound': bound}
        measured.append(identity)
        return {'score': score, 'strong': identity == 'f1', 'method': 'features',
                'inliers': 20 if identity == 'f1' else 8, 'coverage': .20,
                'mae': .005 if identity == 'f1' else .05, 'major_changed': .01}

    monkeypatch.setattr(matching, '_features', features)
    monkeypatch.setattr(matching, '_texture', lambda *args, **kwargs:
                        pytest.fail('an original strong-feature result uses no texture shortlist'))
    rows = [{'id': 'r1'}]
    files = [{'id': identity, 'issue': None} for identity in images]
    baseline = matching._match_appearances(rows, files, {'r1': query}, images,
                                           texture_workers=1)[0]
    measured.clear()
    routed = matching._match_appearances(rows, files, {'r1': query}, images,
                                         proposals={'r1': {'file_id': 'f1', 'verdict': 'same'}},
                                         texture_workers=1)[0]
    # These rivals are outside the .045 runner-up gap, but still lie inside
    # the wider .12 credible window. Their pattern proof must not disappear.
    assert top_score - rival_score >= .045
    assert 'f2' in measured and 'f3' not in measured
    competition = routed['evidence']['competition']
    assert competition['credible_candidate_ids'] == baseline['evidence']['competition']['credible_candidate_ids']
    assert competition['credible_candidate_ids'] == ['f1', 'f2']
    assert competition['unique'] is False
    assert competition['bounded_geometry']['cutoff'] == max(.55, top_score - .12)
    rival = next(item for item in competition['scores'] if item['file_id'] == 'f2')
    excluded = next(item for item in competition['scores'] if item['file_id'] == 'f3')
    assert rival['pattern_supported'] is True and 'score_kind' not in rival
    assert excluded['score_kind'] == 'geometric_upper_bound'
    assert routed['status'] == baseline['status']


def test_unverified_higher_competitor_restores_exact_texture_shortlist(monkeypatch):
    images = {f'f{i}': SimpleNamespace(digest=f'image-{i}', histogram=np.ones(1, np.float32))
              for i in range(1, 5)}
    query = SimpleNamespace(histogram=np.ones(1, np.float32))
    identities = {id(image): identity for identity, image in images.items()}
    full_scores = {'f1': .95, 'f2': .97, 'f3': .81, 'f4': .79}
    full_calls = []

    def features(first, candidate, *, score_cutoff=None):
        identity = identities[id(candidate)]
        result = {'score': full_scores[identity], 'strong': identity == 'f1',
                  'method': 'features'}
        if score_cutoff is not None and identity in ('f3', 'f4'):
            result.update(score=.824 if identity == 'f3' else .829,
                          score_upper_bound=.824 if identity == 'f3' else .829)
        else:
            full_calls.append(identity)
        return result

    def texture(first, candidate, *, precision=False, cache=None):
        identity = identities[id(candidate)]
        return {'score': .98 if precision and identity == 'f3' else .1,
                'strong': False, 'method': 'texture'}

    monkeypatch.setattr(matching, '_features', features)
    monkeypatch.setattr(matching, '_texture', texture)
    rows = [{'id': 'r1'}]
    files = [{'id': identity, 'issue': None} for identity in images]
    expected = matching._match_appearances(rows, files, {'r1': query}, images,
                                           texture_workers=1)
    full_calls.clear()
    actual = matching._match_appearances(rows, files, {'r1': query}, images,
                                         proposals={'r1': {'file_id': 'f1', 'verdict': 'same'}},
                                         texture_workers=1)
    assert actual == expected
    assert full_calls[-4:] == ['f1', 'f2', 'f3', 'f4']
    assert 'bounded_geometry' not in actual[0]['evidence']['competition']


def test_malformed_prepared_input_is_rejected():
    with pytest.raises(TypeError):
        matching.match_prepared({'files': []})


@pytest.mark.parametrize('subpixel', [False, True])
def test_texture_scan_fast_arithmetic_matches_original_float32(subpixel, monkeypatch):
    rng = np.random.default_rng(7100)
    tile = rng.integers(20, 240, (40, 100, 3), dtype=np.uint8)
    query = np.tile(tile, (2, 2, 1))[3:67, 7:147]
    query = cv2.resize(query, (140, 64))
    expected = {'score': 0.}
    with monkeypatch.context() as arithmetic:
        arithmetic.setattr(matching, '_pixel_error', lambda first, second:
                           np.abs(first.astype(np.float32) - second.astype(np.float32)) / 255)
        arithmetic.setattr(matching, '_channel_max', lambda error: error.max(axis=-1))
        for height in (36, 40, 44):
            matching._texture_scan(query, tile, height, expected, subpixel=subpixel)
    actual = {'score': 0.}
    for height in (36, 40, 44):
        matching._texture_scan(query, tile, height, actual, subpixel=subpixel)
    assert actual == expected


def test_losing_texture_scale_does_not_compute_unneeded_pixel_summary(monkeypatch):
    tile = np.full((40, 100, 3), 100, np.uint8)
    query = np.full((64, 140, 3), 100, np.uint8)
    monkeypatch.setattr(matching, '_channel_max', lambda error:
                        pytest.fail('a losing scale needs no changed/worst/coherent calculations'))
    best = {'score': 1.}
    matching._texture_scan(query, tile, 40, best)
    assert best == {'score': 1.}
