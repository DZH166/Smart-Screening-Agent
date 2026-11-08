"""Exact native-pixel checks with bounded difference arrays, no model calls."""
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
import pytest

from hsd_tool import material_quality as quality


def encoded(image):
    output = BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


@pytest.mark.parametrize('change', [False, True])
def test_native_large_result_is_checked_without_full_int16_arrays(monkeypatch, change):
    with Image.new('RGBA', (1536, 3072)) as source:
        ImageDraw.Draw(source).rectangle((10, 10, 1500, 3000), fill=(100, 140, 200, 255))
        with source.copy() as layer:
            if change:
                layer.putpixel((1025, 130), (255, 0, 0, 200))
            a, b = encoded(source), encoded(layer)
    original = np.asarray
    tiles = []
    def tile_array(image, *args, **kwargs):
        assert image.width <= quality.DIAGNOSTIC_TILE[0]
        assert image.height <= quality.DIAGNOSTIC_TILE[1]
        assert kwargs.get('dtype') != np.int16
        tiles.append(image.size)
        return original(image, *args, **kwargs)
    monkeypatch.setattr(quality.np, 'asarray', tile_array)
    result = quality.quality_hook(a, b, dict(x=0, y=0, width=1536, height=3072))
    assert tiles and result['auto_ready'] is False
    assert result['evidence']['pixel_fidelity_verified'] is (not change)
    assert result['evidence']['visible_components'] == 1
    if change:
        assert result['evidence']['alpha_max_error'] == 55
        assert result['evidence']['color_max_error'] == 200
