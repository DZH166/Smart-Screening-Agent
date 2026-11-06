"""Only technical regression checks; synthetic pictures are not model quality evidence."""
from PIL import Image, ImageDraw
import numpy as np
import pytest

from ribbon_backend.edit_quality import validate_edit_result
from ribbon_backend.providers import ProviderError


def source(path, *, padding=True):
    with Image.new('RGBA', (256, 256), (0, 0, 0, 0)) as image:
        ImageDraw.Draw(image).ellipse((32, 32, 224, 224) if padding else (-20, -20, 270, 270), fill='#6d8dca')
        ImageDraw.Draw(image).rectangle((70, 90, 100, 110), fill='black')
        image.save(path)
    return path


@pytest.mark.parametrize('change', ['same', 'noise', 'hidden_rgb', 'upscale'])
def test_copy_noise_and_resampling_are_not_a_success(tmp_path, change):
    original = source(tmp_path / 'source.png')
    output = tmp_path / 'output.png'
    with Image.open(original) as image:
        if change == 'upscale':
            with image.resize((1024, 1024), Image.Resampling.LANCZOS) as result:
                result.save(output)
        else:
            array = np.asarray(image).copy()
            if change == 'noise':
                rng = np.random.default_rng(1)
                array[:, :, :3] = np.clip(array[:, :, :3].astype(np.int16) + rng.integers(-1, 2, array[:, :, :3].shape), 0, 255)
            elif change == 'hidden_rgb':
                array[array[:, :, 3] == 0, :3] = 255
            with Image.fromarray(array) as result:
                result.save(output)
    with pytest.raises(ProviderError, match='可见变化'):
        validate_edit_result(original, output, target='asset')


def test_small_meaningful_local_detail_is_not_rejected(tmp_path):
    original = source(tmp_path / 'source.png')
    output = tmp_path / 'output.png'
    with Image.open(original) as image:
        ImageDraw.Draw(image).ellipse((123, 100, 134, 111), fill='yellow')
        image.save(output)
    result = validate_edit_result(original, output, target='asset')
    assert result['changed_sample_pixels'] >= 4
    assert result['semantic_verified'] is result['production_verified'] is False


def test_local_high_resolution_texture_survives_coarse_projection_limit(tmp_path):
    original, output = tmp_path / 'source.png', tmp_path / 'output.png'
    with Image.new('RGBA', (1024, 512), '#808080') as image:
        image.save(original)
        d = ImageDraw.Draw(image)
        # Four-pixel high-resolution textile strokes intentionally disappear
        # at 128px but are meaningful at the bounded 512px projection.
        for x in range(440, 496, 8):
            d.rectangle((x, 208, x + 3, 239), fill='#404040')
            d.rectangle((x + 4, 208, x + 7, 239), fill='#C0C0C0')
        image.save(output)
    result = validate_edit_result(original, output, target='background')
    coarse, fine = result['projections']
    assert max(coarse['size']) == 128 and max(fine['size']) == 512
    assert coarse['changed'] < 4
    assert fine['changed'] >= 4


def test_new_flat_cut_on_previously_clear_side_is_rejected(tmp_path):
    original = source(tmp_path / 'source.png')
    output = tmp_path / 'output.png'
    with Image.open(original) as image, image.crop((70, 0, 256, 256)) as cropped:
        cropped.save(output)
    with pytest.raises(ProviderError, match='截断'):
        validate_edit_result(original, output, target='asset')


def test_preexisting_border_and_opaque_background_are_not_called_truncated(tmp_path):
    original = source(tmp_path / 'source.png', padding=False)
    output = tmp_path / 'output.png'
    with Image.open(original) as image:
        ImageDraw.Draw(image).rectangle((120, 130, 150, 160), fill='yellow')
        image.save(output)
    validate_edit_result(original, output, target='asset')
    # A background may intentionally fill its complete output canvas.
    with Image.new('RGB', (200, 100), 'red') as image:
        image.save(original)
    with Image.new('RGB', (2048, 2048), 'blue') as image:
        image.save(output)
    validate_edit_result(original, output, target='background')
