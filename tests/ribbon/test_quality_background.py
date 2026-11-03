"""Background fitting is derived presentation, with bounded allocations."""
import pytest
from PIL import Image, ImageDraw
from ribbon_backend.imaging import _quality_background


def test_texture_is_uniformly_fitted_and_output_is_complete():
    source = Image.new('RGBA', (80, 80), 'white')
    ImageDraw.Draw(source).ellipse((20, 20, 60, 60), fill='red')
    original = source.tobytes()
    with _quality_background(source, 1000, 100) as result:
        assert result.size == (1000, 100)
        assert result.getpixel((50, 50)) == (255, 0, 0, 255)
        assert result.getpixel((950, 50)) == (255, 0, 0, 255)
        assert result.crop((0, 0, 100, 100)).tobytes() == result.crop((900, 0, 1000, 100)).tobytes()
    assert source.tobytes() == original
    source.close()


@pytest.mark.parametrize('shape', [(1, 1), (20, 100), (100, 20), (13, 17)])
def test_small_transparent_texture_covers_every_column(shape):
    with Image.new('RGBA', shape, (0, 0, 255, 100)) as source:
        with _quality_background(source, 1181, 52) as output:
            assert output.getchannel('A').getextrema() == (255, 255)
            # No uncovered white rounding gap in the last column.
            assert output.getpixel((1180, 20))[2] == 255
            assert output.getpixel((1180, 20))[0] < 255


def test_extreme_background_does_not_allocate_gigantic_resize():
    with Image.new('RGBA', (10000, 1), 'red') as source:
        with pytest.raises(ValueError, match='狭长'):
            _quality_background(source, 11811, 520)


def test_explicit_solid_color_does_not_resize_unused_texture(tmp_path):
    from ribbon_backend.imaging import render
    motif, texture = tmp_path/'motif.png', tmp_path/'texture.png'
    with Image.new('RGBA', (10, 20), 'red') as source:
        source.save(motif)
    with Image.new('RGBA', (40000, 1), 'green') as source:
        source.save(texture)
    snapshot = dict(layout_engine='design-rhythm-v1', template_mode='single',
                    asset_refs=['motif'], background_ref='texture', params={'background_color':'#123456'},
                    background_tone='soft', output_profile={'width':11811,'height':520,'dpi':300,'format':'PNG'})
    render(snapshot, {'motif':motif,'texture':texture}.__getitem__, tmp_path/'master.png', tmp_path/'preview.png')
    with Image.open(tmp_path/'master.png') as master:
        assert master.getpixel((0,0)) == (18,52,86,255)


def test_unknown_layout_engine_never_silently_falls_back(tmp_path):
    from ribbon_backend.imaging import render
    with pytest.raises(ValueError, match='引擎'):
        render({'layout_engine':'unknown-future'}, lambda _:None, tmp_path/'out.png', tmp_path/'preview.png')
