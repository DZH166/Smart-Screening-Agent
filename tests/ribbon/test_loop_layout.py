"""Controlled full-sequence, aspect, phase and finite-panel verification."""
from copy import deepcopy
import hashlib
import math

from PIL import Image, ImageDraw
import pytest

from ribbon_backend import loop_layout as loop


def snapshot(mode='single', n=3, density='balanced', height=520):
    return dict(layout_engine=loop.ENGINE, asset_refs=[str(i) for i in range(n)],
                template_mode=mode, template_rules={}, design_density=density, params={}, seed=44,
                output_profile=dict(width=11811, height=height, dpi=300, format='PNG'))


def specs(shapes=((80, 160), (260, 70), (120, 120))):
    return [dict(width=w, height=h, bbox=[0, 0, w, h], source_size=[w, h]) for w, h in shapes]


@pytest.fixture
def artwork(tmp_path):
    refs = {}
    for index, (width, height) in enumerate(((80, 160), (260, 70), (120, 120), (60, 170), (190, 80))):
        image = Image.new('RGBA', (width + 80, height + 120))
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 60, 40 + width - 1, 60 + height - 1), fill=(30 + 35 * index, 70, 210, 255))
        draw.rectangle((45, 65, 52, 72), fill=(250, 230, 20, 255))
        # A different corner makes clipping and 180-degree phase detectable.
        draw.rectangle((40 + width - 12, 60 + height - 12, 40 + width - 1, 60 + height - 1), fill=(240, 40, 150, 255))
        path = tmp_path / f'controlled-{index}.png'
        image.save(path); image.close(); refs[str(index)] = path
    return refs


def composite(snap, refs, tmp_path, suffix='result'):
    resolved = loop.resolve(snap, refs.__getitem__)
    canvas = Image.new('RGBA', (resolved['output_profile']['width'], resolved['output_profile']['height']))
    rows = loop.compose(canvas, resolved, refs.__getitem__, tmp_path / f'{suffix}.png')
    return resolved, canvas, rows


def assert_safe(placements, height):
    for p in placements:
        assert 0 <= p['x'] < p['repetition']['unit_period']
        assert p['y'] - p['planned_height'] / 2 >= p['region'][1] - 1e-7
        assert p['y'] + p['planned_height'] / 2 <= p['region'][3] + 1e-7
        assert p['region'][1] >= height * .08 - 1e-7
        assert p['region'][3] <= height * .92 + 1e-7
        assert p['target_width'] >= 1 and p['target_height'] >= 1


@pytest.mark.parametrize('mode', loop.MODES)
@pytest.mark.parametrize('density', loop.DENSITIES)
def test_all_modes_all_densities_keep_selected_complete_sources(artwork, tmp_path, mode, density):
    n = 1 if mode == 'fullwidth' else (2 if mode == 'ends_open' else 5)
    snap = snapshot(mode, n, density)
    before = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in artwork.items()}
    resolved, canvas, rows = composite(snap, artwork, tmp_path)
    try:
        assert canvas.getbbox()
        assert {row['asset_ref'] for row in rows} == set(snap['asset_refs'])
        assert {row['layout_engine'] for row in rows} == {loop.ENGINE}
        assert resolved['output_profile']['height'] == 520
        assert resolved['output_profile']['dpi'] == 300
        assert snap['output_profile']['width'] == 11811  # immutable caller input
        assert resolved['loop_layout']['verification']['passed']
        assert resolved['loop_layout']['verification']['errors'] == []
        assert_safe(loop.plan(resolved), 520)
        assert [row['layer'] for row in rows] == list(range(len(rows)))
        assert all(row['width'] <= canvas.width for row in rows)
        assert all(row['height'] <= math.floor(row['safe_region'][3]) - math.ceil(row['safe_region'][1]) for row in rows)
        assert before == {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in artwork.items()}
        assert not list(tmp_path.glob('ribbon-loop-*'))
    finally:
        canvas.close()


def test_width_is_natural_complete_sequence_not_old_configured_width():
    source_specs = specs()
    first = loop.resolve(snapshot(), specs=source_specs)
    changed = snapshot(); changed['output_profile']['width'] = 4000
    second = loop.resolve(changed, specs=source_specs)
    assert first['output_profile']['width'] == second['output_profile']['width']
    assert first['output_profile']['width'] < 4000
    rows = loop.plan(first)
    assert [p['asset_index'] for p in rows] == [0, 1, 2]
    assert rows[0]['repetition']['groups'] == 1
    assert rows[0]['repetition']['sequence_length'] == 3
    assert rows[0]['repetition']['period'] == first['output_profile']['width']
    assert rows[1]['target_width'] / rows[1]['target_height'] == pytest.approx(260 / 70, abs=.05)
    assert rows[0]['target_width'] / rows[0]['target_height'] == pytest.approx(.5, abs=.01)


@pytest.mark.parametrize('mode', ('single', 'grid', 'stagger', 'scatter', 'scene', 'alternating', 'opposed', 'stacked', 'bordered'))
def test_selected_order_and_phase_close_for_odd_count(mode):
    snap = snapshot(mode, 5)
    resolved = loop.resolve(snap, specs=specs(((80, 160), (260, 70), (120, 120), (60, 170), (190, 80))))
    rows = loop.plan(resolved)
    for cycle in resolved['loop_layout']['groups']:
        members = [p for p in rows if p['row'] == cycle['row']]
        assert len(members) == cycle['groups'] * cycle['sequence_length']
        assert [p['asset_index'] for p in members] == cycle['sequence'] * cycle['groups']
        assert cycle['period'] * cycle['groups'] == pytest.approx(resolved['output_profile']['width'])
    if mode in ('alternating', 'opposed'):
        assert len(rows) == 10
        assert [p['asset_index'] for p in rows] == [0, 1, 2, 3, 4] * 2
    if mode == 'opposed':
        assert [p['rotation'] for p in rows] == [0., 180.] * 5
    if mode == 'alternating':
        for large, small in zip(rows[::2], rows[1::2]):
            assert large['planned_height'] > small['planned_height']


@pytest.mark.parametrize('mode', ('bordered', 'stacked', 'grid'))
def test_shared_period_enlarges_gaps_or_complete_groups_without_resizing(mode):
    snap = snapshot(mode)
    source_specs = specs()
    original = loop.resolve(snap, specs=source_specs)
    enlarged = loop.resolve(snap, specs=source_specs, background_period=446,
                            target_period=original['output_profile']['width'] + 700)
    assert enlarged['output_profile']['width'] % 446 == 0
    assert enlarged['output_profile']['width'] >= original['output_profile']['width'] + 700
    assert enlarged['loop_layout']['natural_width'] == original['loop_layout']['natural_width']
    variants = lambda s: {(p['asset_index'], p['target_width'], p['target_height'], p['rotation']) for p in loop.plan(s)}
    assert variants(enlarged) == variants(original)
    for cycle in enlarged['loop_layout']['groups']:
        assert cycle['gap'] >= cycle['desired_gap'] - 1e-7
        assert cycle['period'] * cycle['groups'] == pytest.approx(enlarged['output_profile']['width'])
        assert cycle['groups'] >= 1


@pytest.mark.parametrize('mode', loop.MODES)
def test_offsets_are_whole_unit_phase_and_keep_full_vertical_content(mode):
    n = 1 if mode == 'fullwidth' else 2
    snap = snapshot(mode, n)
    snap['params'] = dict(offset_x=-912345., offset_y=20000., rotation=37)
    source_specs = specs(((80, 160), (260, 70)))[:n]
    first = loop.resolve(snap, specs=source_specs)
    changed = deepcopy(snap)
    changed['params']['offset_x'] += first['output_profile']['width'] * 29
    second = loop.resolve(changed, specs=source_specs)
    first_rows, second_rows = loop.plan(first), loop.plan(second)
    assert [(p['x'], p['y']) for p in first_rows] == [(p['x'], p['y']) for p in second_rows]
    assert_safe(first_rows, 520)


def test_phase_wrap_raster_is_exactly_a_cyclic_shift(artwork, tmp_path):
    snap = snapshot('single', 3)
    resolved, original, _ = composite(snap, artwork, tmp_path, 'original')
    snap['params']['offset_x'] = 137
    _, shifted, _ = composite(snap, artwork, tmp_path, 'shift')
    expected = Image.new('RGBA', original.size)
    expected.alpha_composite(original, (137, 0))
    expected.alpha_composite(original, (137 - original.width, 0))
    assert shifted.tobytes() == expected.tobytes()
    snap['params']['offset_x'] += 11 * resolved['output_profile']['width']
    _, again, _ = composite(snap, artwork, tmp_path, 'whole-phase')
    assert again.tobytes() == shifted.tobytes()
    original.close(); shifted.close(); again.close(); expected.close()


def test_grid_columns_align_and_stagger_changes_only_row_phase():
    grid = loop.resolve(snapshot('grid'), specs=specs())
    stagger = loop.resolve(snapshot('stagger'), specs=specs())
    grid_rows, stagger_rows = loop.plan(grid), loop.plan(stagger)
    first = [p for p in grid_rows if p['row'] == 0]
    second = [p for p in grid_rows if p['row'] == 1]
    assert [(p['asset_index'], p['x']) for p in first] == [(p['asset_index'], p['x']) for p in second]
    assert [p['asset_index'] for p in grid_rows] == [p['asset_index'] for p in stagger_rows]
    assert [p['x'] for p in grid_rows] != [p['x'] for p in stagger_rows]


@pytest.mark.parametrize('angle', (0, 1, 37, 45, 89, 90, 133, 177, -73))
@pytest.mark.parametrize('offset_y', (-20000, 20000))
def test_actual_rotated_alpha_mass_preserves_every_complete_motif(artwork, tmp_path, angle, offset_y):
    snap = snapshot('single', 3)
    snap['params'] = dict(rotation=angle, offset_y=offset_y, offset_x=-2345)
    resolved, canvas, _ = composite(snap, artwork, tmp_path, f'rotated-{angle}-{offset_y}')
    expected_mass = 0
    for p in loop.plan(resolved):
        with Image.open(artwork[str(p['asset_index'])]) as source:
            content = source.crop(resolved['loop_layout']['specs'][p['asset_index']]['bbox'])
        resized = content.resize((p['target_width'], p['target_height']), Image.Resampling.LANCZOS)
        content.close()
        if angle % 360:
            rotated = resized.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
            resized.close(); resized = rotated
        with resized.getchannel('A') as alpha:
            expected_mass += sum(value * count for value, count in enumerate(alpha.histogram()))
        resized.close()
    with canvas.getchannel('A') as alpha:
        actual_mass = sum(value * count for value, count in enumerate(alpha.histogram()))
    assert actual_mass == expected_mass  # no clipping, including at both seams
    canvas.close()


@pytest.mark.parametrize('mode', ('ends', 'ends_open', 'fullwidth', 'panels', 'split'))
def test_finite_panel_modes_are_explicit_and_never_become_grid(mode):
    n = 1 if mode == 'fullwidth' else 2
    resolved = loop.resolve(snapshot(mode, n), specs=specs(((220, 70), (80, 160)))[:n])
    assert resolved['loop_layout']['kind'] == 'panel'
    assert '面板' in resolved['loop_layout']['mode_notice']
    rows = loop.plan(resolved)
    if mode == 'ends':
        assert [p['role'] for p in rows] == ['left-end', 'inner', 'right-end']
        assert len(rows) == 3
    if mode == 'ends_open':
        assert [p['role'] for p in rows] == ['left-end', 'right-end']
    if mode == 'fullwidth':
        assert [p['role'] for p in rows] == ['complete']
    if mode == 'panels':
        assert {p['role'] for p in rows} == {'left-panel', 'middle-panel', 'right-panel'}
    if mode == 'split':
        assert {p['role'] for p in rows} == {'left-zone', 'right-zone'}


@pytest.mark.parametrize('n', (1, 2, 5))
@pytest.mark.parametrize('main_shape', ((160, 80), (900, 90), (40, 180)))
def test_ends_keep_two_large_complete_mains_one_inner_sequence_and_boundary_clearance(n, main_shape):
    source_specs = specs((main_shape,) + ((70, 130),) * (n - 1))
    resolved = loop.resolve(snapshot('ends', n), specs=source_specs)
    rows = loop.plan(resolved)
    ends = [p for p in rows if p['role'] in ('left-end', 'right-end')]
    inner = [p for p in rows if p['role'] == 'inner']
    assert [p['asset_index'] for p in ends] == [0, 0]
    assert [p['asset_index'] for p in inner] == (list(range(1, n)) or [0])
    assert min(p['planned_height'] for p in ends) > max(p['planned_height'] for p in inner)
    cycle = rows[0]['repetition']
    assert cycle['boundary_gap'] >= cycle['gap'] - 1e-7
    assert cycle['boundary_gap'] >= .35 * max(p['planned_width'] for p in ends) - 1e-7
    # Three copies have the same explicit main-main gap at both joins, rather
    # than two end motifs meeting with zero clearance at the unit boundary.
    width = resolved['output_profile']['width']
    right_edge = ends[1]['x'] + ends[1]['planned_width'] / 2
    next_left_edge = width + ends[0]['x'] - ends[0]['planned_width'] / 2
    assert next_left_edge - right_edge == pytest.approx(cycle['boundary_gap'])
    assert 2 * width + ends[0]['x'] - ends[0]['planned_width'] / 2 - (width + right_edge) == pytest.approx(cycle['boundary_gap'])


def test_padding_and_faint_ornaments_remain_complete(artwork, tmp_path):
    snap = snapshot('single', 1)
    first, canvas, _ = composite(snap, artwork, tmp_path, 'first')
    with Image.open(artwork['0']) as source:
        with source.getchannel('A') as alpha:
            content = source.crop(alpha.getbbox())
        padded = Image.new('RGBA', (content.width + 600, content.height + 300))
        padded.paste(content, (177, 231)); content.close()
        path = tmp_path / 'padded.png'; padded.save(path); padded.close()
    second, other, _ = composite(snap, {'0': path}, tmp_path, 'padded')
    assert first['output_profile']['width'] == second['output_profile']['width']
    assert canvas.tobytes() == other.tobytes()
    with Image.open(path) as source:
        modified = source.convert('RGBA')
    modified.putpixel((0, 0), (255, 10, 10, 1)); modified.save(path); modified.close()
    faint = loop.read_specs(['0'], {'0': path}.__getitem__)
    assert faint[0]['bbox'][:2] == [0, 0]
    canvas.close(); other.close()


def test_two_asset_ends_fits_wide_inner_at_its_real_small_height():
    # At main height this 50:1 auxiliary design would exceed 16000px. Its
    # intended small height and the two actual mains fit the full unit safely.
    resolved = loop.resolve(snapshot('ends', 2), specs=specs(((80, 160), (1000, 20))))
    rows = loop.plan(resolved)
    assert [p['role'] for p in rows] == ['left-end', 'inner', 'right-end']
    assert [p['asset_index'] for p in rows] == [0, 1, 0]
    assert resolved['output_profile']['height'] == 520
    assert resolved['output_profile']['width'] < 16000
    assert rows[1]['planned_width'] > 10000
    assert rows[1]['planned_height'] < min(rows[0]['planned_height'], rows[2]['planned_height'])
    assert rows[1]['target_width'] / rows[1]['target_height'] == pytest.approx(50, rel=.01)
    assert resolved['loop_layout']['verification']['source_coverage_complete'] is True


def test_saved_geometry_cannot_silently_drift_or_rewrite_legacy():
    snap = snapshot()
    resolved = loop.resolve(snap, specs=specs())
    drift = deepcopy(resolved); drift['params']['scale'] = .9
    with pytest.raises(ValueError, match='不一致'):
        loop.plan(drift)
    drift = deepcopy(resolved); drift['output_profile']['width'] += 1
    with pytest.raises(ValueError, match='不一致'):
        loop.plan(drift)
    old = snapshot(); old['layout_engine'] = 'design-rhythm-v2'
    with pytest.raises(ValueError, match='历史'):
        loop.resolve(old, specs=specs())


@pytest.mark.parametrize('mode,n', (('fullwidth', 2), ('bordered', 1), ('ends_open', 3), ('split', 1), ('stacked', 1)))
def test_invalid_mode_selections_fail_clearly(mode, n):
    with pytest.raises(ValueError):
        loop.resolve(snapshot(mode, n), specs=specs(((100, 100),) * n))


def test_resource_limits_fail_instead_of_squashing_or_omitting():
    many = snapshot('single', 12)
    with pytest.raises(ValueError, match='完整循环单元'):
        loop.resolve(many, specs=specs(((800, 80),) * 12))
    with pytest.raises(ValueError, match='完整图案'):
        loop.resolve(snapshot('single', 1), specs=specs(((16000, 20),)))
    with pytest.raises(ValueError, match='无法保持完整比例'):
        loop.resolve(snapshot('single', 1), specs=specs(((1, 16000),)))
    normal = loop.resolve(snapshot(), specs=specs())
    with pytest.raises(ValueError, match='不能压缩或截断'):
        loop.resolve(snapshot(), specs=specs(), target_period=normal['output_profile']['width'] - 1)
    with pytest.raises(ValueError, match='正整数'):
        loop.resolve(snapshot(), specs=specs(), background_period=23.5)
    huge_height = snapshot('single', 3, height=15000)
    with pytest.raises(ValueError, match='完整循环单元'):
        loop.resolve(huge_height, specs=specs(((1, 10),) * 3))


def test_scale_spacing_density_and_rotation_each_have_real_geometry_paths():
    base = snapshot('single', 2)
    source_specs = specs(((80, 160), (260, 70)))
    baseline = loop.resolve(base, specs=source_specs)
    sizes = lambda resolved: [(p['target_width'], p['target_height'], p['rotation']) for p in loop.plan(resolved)]
    for key, value in (('scale', .7), ('rotation', 27)):
        changed = deepcopy(base); changed['params'][key] = value
        modified = loop.resolve(changed, specs=source_specs)
        assert sizes(modified) != sizes(baseline)
    changed = deepcopy(base); changed['params']['spacing'] = 1.7
    modified = loop.resolve(changed, specs=source_specs)
    assert sizes(modified) == sizes(baseline)
    assert modified['output_profile']['width'] > baseline['output_profile']['width']
    variants = [sizes(loop.resolve({**base, 'design_density': density}, specs=source_specs)) for density in loop.DENSITIES]
    assert len({str(value) for value in variants}) == 3
