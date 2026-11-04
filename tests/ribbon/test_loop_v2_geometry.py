"""v2 visual contracts: real spacing/density, slot isolation and closed repeats."""

from copy import deepcopy
import pytest
from PIL import Image

from ribbon_backend import loop_layout_v2 as engine, loop_pipeline_v2 as pipe
from ribbon_backend.imaging import render


def snap(mode, density='balanced', **updates):
    n = 1 if mode == 'fullwidth' else 2 if mode == 'ends_open' else 3
    return dict(
        layout_engine=engine.ENGINE,
        template_mode=mode,
        asset_refs=list('abc'[:n]),
        output_profile=dict(width=11811, height=520, dpi=300, format='PNG'),
        design_density=density,
        seed=42,
        background_ref='bkg',
        **updates
    )


def resolved(mode, density='balanced', **updates):
    s = snap(mode, density, **updates)
    shapes = [(80, 160), (260, 70), (120, 120)][: len(s['asset_refs'])]
    return engine.resolve(s, specs=[dict(width=w, height=h) for w, h in shapes])


@pytest.mark.parametrize('mode', engine.MODES)
def test_density_changes_foreground_and_spacing_stays_effective(mode):
    states = [resolved(mode, d) for d in ('airy', 'balanced', 'rich')]
    coverage = [s['loop_layout']['metrics']['footprint_ratio'] for s in states]
    assert coverage[0] < coverage[1] < coverage[2]
    a, b, c = [resolved(mode, params={'spacing': step})['loop_layout'] for step in (0.8, 1.0, 1.25)]
    assert a['period_px'] < b['period_px'] < c['period_px']
    for rows in zip(a['groups'], b['groups'], c['groups']):
        assert rows[0]['gap'] < rows[1]['gap'] < rows[2]['gap']


def test_scatter_has_distinct_rotations_and_varies_both_axes_at_fixed_seed():
    a = resolved('scatter')
    b = resolved('scatter')
    p = engine.plan(a)
    assert p == engine.plan(b)
    assert {q['rotation'] for q in p} == {-18, -9, 9, 18}
    assert len({round(q['y'], 2) for q in p if q['row'] == 0}) > 1
    rows = a['loop_layout']['groups']
    assert rows[0]['sequence'] != rows[1]['sequence']
    assert set(rows[0]['sequence']) == set(rows[1]['sequence']) == {0, 1, 2}
    assert (
        a['loop_layout']['input_signature']
        != engine.resolve({**snap('scatter'), 'seed': 43}, specs=a['loop_layout']['specs'])['loop_layout'][
            'input_signature'
        ]
    )


def test_local_translation_changes_only_target_within_original_unit():
    base = resolved('single')
    before = engine.plan(base)
    for dx in (-20, 20):
        edited = resolved('single', slot_params={'pattern-1': {'offset_x': dx}})
        assert base['output_profile'] == edited['output_profile']
        for old, new in zip(before, engine.plan(edited)):
            assert new['x'] - old['x'] == pytest.approx(dx if old['asset_index'] == 0 else 0)
    with pytest.raises(ValueError, match='重叠'):
        resolved('single', slot_params={'pattern-1': {'offset_x': -170}})


@pytest.mark.parametrize('mode,ratio', [('alternating', 0.58), ('scene', 0.76), ('ends', 0.60)])
def test_enlargement_preserves_group_hierarchy(mode, ratio):
    for scale in (1.0, 1.8, 2.5):
        p = engine.plan(resolved(mode, params={'scale': scale}))
        assert p[1]['target_height'] / p[0]['target_height'] == pytest.approx(ratio, abs=0.015)


def test_zone_assets_bound_to_equal_areas_and_recovery_checks(tmp_path):
    refs = {}
    for key, col in [
        ('a', 'black'),
        ('b', 'navy'),
        ('c', 'green'),
        ('left-bg', 'red'),
        ('right-bg', 'blue'),
        ('bkg', 'white'),
    ]:
        refs[key] = tmp_path / (key + '.png')
        with Image.new('RGBA', (65, 85), col) as im:
            im.save(refs[key])
    s = pipe.resolve(
        snap('split', zone_background_refs={'left': 'left-bg', 'right': 'right-bg'}), refs.__getitem__
    )
    path = tmp_path / 'master.png'
    metadata = render(s, refs.__getitem__, path, tmp_path / 'preview.png')
    with Image.open(path) as result:
        assert result.getpixel((result.width // 2 - 1, 1))[:3] == (255, 0, 0)
        assert result.getpixel((result.width // 2, 1))[:3] == (0, 0, 255)
    s['loop'] = metadata['loop']
    s['loop']['output_sha256'] = 'test-hash'
    s['loop']['inputs'] = [
        {'id': k, 'sha256': 'placeholder'} for k in refs
    ]  # service verifies actual file hashes
    pipe.validate_binding(s, 'test-hash')
    recolor = pipe.resolve(
        {**s, 'zone_colors': {'left': '#551144'}, 'params': {'background_color': '#AABBCC'}}, refs.__getitem__
    )
    render(recolor, refs.__getitem__, tmp_path / 'tinted.png', tmp_path / 'tinted-thumb.png')
    with Image.open(tmp_path / 'tinted.png') as im:
        assert im.getpixel((1, 1))[:3] == (85, 17, 68)
        assert im.getpixel((im.width - 1, 1))[:3] == (0, 0, 255)
    broken = deepcopy(s)
    broken['loop']['background']['zones'][0]['ref'] = 'right-bg'
    with pytest.raises(ValueError):
        pipe.validate_binding(broken, 'test-hash')


def test_bordered_draws_continuous_lines_and_binds_complete_strip(tmp_path):
    refs = {}
    for k, col in [('a', 'red'), ('b', 'green'), ('c', 'blue'), ('bkg', 'white'), ('strip', 'purple')]:
        refs[k] = tmp_path / (k + '.png')
        with Image.new('RGBA', (80, 15) if k == 'strip' else (60, 70), col) as im:
            im.save(refs[k])
    s = pipe.resolve(snap('bordered', border_ref='strip'), refs.__getitem__)
    result = render(s, refs.__getitem__, tmp_path / 'master.png', tmp_path / 'thumb.png')
    border = result['loop']['background']['border']
    assert border['source'] == 'strip' and border['strip']['count'] >= 1
    with Image.open(tmp_path / 'master.png') as im:
        y = round(im.height * 0.08) + round(im.height * 0.115) // 2
        assert all(im.getpixel((x, y))[:3] != (255, 255, 255) for x in range(im.width))


def test_slot_enlargement_respects_repeated_size_ratio_at_the_limit():
    s = snap('alternating', slot_params={'pattern-1': {'scale': 2.5}})
    s['asset_refs'] = ['a']
    r = engine.resolve(s, specs=[dict(width=80, height=160)])
    big, small = engine.plan(r)
    assert small['target_height'] / big['target_height'] == pytest.approx(0.58, abs=0.01)


def test_scene_fits_complete_background_panels_without_white_gutters():
    with Image.new('RGBA', (160, 160), 'red') as scene, Image.new('RGBA', (190, 80), 'white') as layer:
        record = pipe._whole_pattern(layer, scene, backdrop=True)
        assert record['count'] == 3
        assert all(layer.getpixel((x, 40))[:3] == (255, 0, 0) for x in range(layer.width))


def test_realistic_portrait_background_crop_avoids_subpixel_negative_origin():
    from ribbon_backend.loop_background import periodize_background

    # This aspect and width cause 928*1.0000000000000002 in the naive crop.
    with Image.new('RGB', (928, 1232), '#e3c8ba') as background:
        image, report = periodize_background(background, 202, 256)
        with image:
            assert image.size == (202, 256) and report['passed']
