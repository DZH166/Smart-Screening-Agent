"""Controlled texture tests; no model calls or business/reference assets."""
import hashlib
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from ribbon_backend.loop_background import (BackgroundLoopError, assess_periodicity,
                                            periodize_background, preferred_period)


def _hash(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


def test_uniform_scale_and_original_central_texture_are_preserved():
    # A square forces a nontrivial vertical crop. The original fine horizontal
    # line and all interior pixels must survive exactly as uniformly resampled.
    with Image.new('RGB', (240, 240), '#e8e2d8') as source:
        draw = ImageDraw.Draw(source)
        draw.line((0, 120, 239, 120), fill='#1d3529', width=2)
        before = _hash(source)
        tile, report = periodize_background(source, 240, 120)
        try:
            assert _hash(source) == before
            assert tile.size == (240, 120) and tile.mode == 'RGBA'
            assert tile.getextrema()[3] == (255, 255)
            box = report['source_crop_box']
            scale_x = report['working_size'][0] / (box[2] - box[0])
            scale_y = report['working_size'][1] / (box[3] - box[1])
            assert scale_x == pytest.approx(scale_y, abs=1e-8)
            with source.resize(tuple(report['working_size']), Image.Resampling.LANCZOS, box=box) as working:
                overlap = report['overlap']
                actual = np.asarray(tile)[:, overlap:, :3]
                assert np.array_equal(actual, np.asarray(working)[:, overlap:240])
            assert report['passed'] is True
            assert report['cut']['maximum'] == 0
            assert report['production_verified'] is False
            assert report['verification_scope'] == 'pixel_continuity_only'
            assert report['warnings']
        finally:
            tile.close()


def test_actual_520_height_period_is_short_and_exactly_repeatable():
    with Image.new('RGB', (2048, 2048), '#e8e4d9') as source:
        draw = ImageDraw.Draw(source)
        for y in range(0, 2048, 32):
            draw.line((0, y, 2047, y), fill='#e1ddcf', width=2)
        width = preferred_period(source, 520)
        assert width == 446
        tile, report = periodize_background(source, width, 520, strict=True)
        try:
            assert report['passed'] is True
            with Image.new('RGBA', (width * 3, 520)) as repeated:
                for x in range(3):
                    repeated.paste(tile, (x * width, 0))
                pixels = np.asarray(repeated)
                assert np.array_equal(pixels[:, :width], pixels[:, width:width * 2])
                assert np.array_equal(pixels[:, :width], pixels[:, width * 2:])
            assert max(row['mean'] for row in report['multiscale']) < 1
        finally:
            tile.close()


def test_minimum_error_cut_is_local_and_does_not_blur_thin_lines():
    with Image.new('RGB', (280, 240), '#eae5da') as source:
        draw = ImageDraw.Draw(source)
        draw.line((0, 100, 279, 100), fill='#223b2a', width=2)
        draw.ellipse((2, 20, 10, 28), fill='#c76c59')
        tile, report = periodize_background(source, 240, 240)
        try:
            assert report['passed']
            path = report['cut_path']
            assert all(2 <= x < report['overlap'] - 2 for x in path)
            # The working canvas is exactly this source. Every output sample
            # must be copied from one of two source locations, never averaged.
            out = np.asarray(tile)[:, :, :3]
            original = np.asarray(source)
            for y, x in enumerate(path):
                assert np.array_equal(out[y, :x], original[y, 240:240 + x])
                assert np.array_equal(out[y, x:], original[y, x:240])
            assert np.array_equal(out[100, 40:], original[100, 40:240])
            assert all(row['passed'] for row in report['multiscale'])
        finally:
            tile.close()


@pytest.mark.parametrize('kind', ['half_colour', 'gradient', 'thick_text', 'large_motif'])
def test_unsafe_backgrounds_return_review_status_and_strict_mode_fails(kind):
    with Image.new('RGB', (280, 240), '#efeadd') as source:
        draw = ImageDraw.Draw(source)
        if kind == 'half_colour':
            draw.rectangle((0, 0, 139, 239), fill='#ff0000')
            draw.rectangle((140, 0, 279, 239), fill='#0000ff')
        elif kind == 'gradient':
            for x in range(280):
                draw.line((x, 0, x, 239), fill=(round(x / 279 * 255),) * 3)
        elif kind == 'thick_text':
            draw.text((8, 8), 'TEST', fill='black', font_size=160)
        else:
            draw.ellipse((50, 30, 230, 210), fill='navy')
        tile, report = periodize_background(source, 240, 240)
        tile.close()
        assert report['passed'] is False and report['status'] == 'needs_review'
        assert report['issues'] and report['production_verified'] is False
        with pytest.raises(BackgroundLoopError) as caught:
            periodize_background(source, 240, 240, strict=True)
        assert caught.value.report == report


def test_severed_one_row_line_fails_even_when_mean_and_p95_are_tiny():
    with Image.new('RGB', (280, 240), 'white') as source:
        draw = ImageDraw.Draw(source)
        draw.line((0, 40, 39, 40), fill='black')
        draw.line((240, 80, 279, 80), fill='black')
        tile, report = periodize_background(source, 240, 240)
        tile.close()
        assert report['cut']['mean'] < 3
        assert report['cut']['p95'] == 0
        assert report['cut']['maximum'] == 255
        assert report['cut']['passed'] is False
        assert report['passed'] is False
        assert any(row['code'] == 'overlap_colour_or_structure_mismatch' for row in report['issues'])


def test_equal_edge_columns_do_not_hide_nearby_colour_band_discontinuity():
    with Image.new('RGB', (240, 80), 'red') as source:
        draw = ImageDraw.Draw(source)
        draw.rectangle((120, 0, 239, 79), fill='blue')
        draw.line((0, 0, 0, 79), fill='white')
        draw.line((239, 0, 239, 79), fill='white')
        assert np.array_equal(np.asarray(source)[:, 0], np.asarray(source)[:, -1])
        report = assess_periodicity(source)
        assert report['multiscale'][0]['passed'] is True
        assert report['passed'] is False
        assert any(row['radius'] > 1 and not row['passed'] for row in report['multiscale'])


def test_large_motif_outside_selected_crop_is_reported_not_silently_discarded():
    with Image.new('RGB', (280, 800), '#eee9dc') as source:
        ImageDraw.Draw(source).ellipse((60, 0, 220, 260), fill='black')
        tile, report = periodize_background(source, 240, 120)
        tile.close()
        assert report['source_crop_box'][1] > 260
        assert report['features']['source_features']['region_count'] > 0
        assert report['passed'] is False


def test_hidden_rgb_cannot_change_alpha_compositing_or_diagnostics():
    reports = []
    for hidden in ('red', 'blue'):
        with Image.new('RGBA', (280, 240), hidden) as source:
            source.putalpha(0)
            ImageDraw.Draw(source).rectangle((30, 20, 250, 220), fill=(220, 225, 210, 64))
            tile, report = periodize_background(source, 240, 240)
            try:
                assert tile.getextrema()[3] == (255, 255)
                assert report['source_alpha_bbox'] == [30, 20, 251, 221]
                assert 0 < report['source_alpha_coverage'] < 1
                reports.append(report)
            finally:
                tile.close()
    assert reports[0] == reports[1]


def test_empty_alpha_is_not_accepted_as_successful_solid_background():
    with Image.new('RGBA', (100, 100), (255, 0, 0, 0)) as source:
        with pytest.raises(ValueError, match='没有可见内容'):
            periodize_background(source, 100, 100)


def test_report_and_pixels_are_deterministic_and_serializable():
    with Image.new('RGBA', (140, 80), '#e9e1d2') as source:
        first, a = periodize_background(source, 120, 80)
        second, b = periodize_background(source, 120, 80)
        try:
            assert a == b and _hash(first) == _hash(second)
            assert json.loads(json.dumps(a)) == a
            assert a['tile_size'] == [120, 80]
            assert len(a['cut_path']) == 80
        finally:
            first.close()
            second.close()


def test_resource_guard_includes_overlap_before_allocating_working_image():
    with Image.new('RGB', (16, 16), 'white') as source:
        # The requested unit alone meets 40 MP; its working overlap does not.
        with pytest.raises(ValueError, match='像素数量或尺寸'):
            periodize_background(source, 10000, 4000)
        with pytest.raises(ValueError):
            periodize_background(source, 15, 80)
