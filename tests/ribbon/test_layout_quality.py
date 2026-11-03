"""Independent visible-content, sequence, containment and repeat checks."""
from copy import deepcopy
import hashlib

from PIL import Image, ImageDraw
import pytest

from ribbon_backend import layout_quality as quality


@pytest.fixture
def artwork(tmp_path):
    refs = {}
    for index, (width, height) in enumerate(((80, 160), (260, 70), (120, 120), (60, 170), (190, 80))):
        image = Image.new('RGBA', (width + 80, height + 120))
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 60, 40 + width - 1, 60 + height - 1), fill=(30 + 35 * index, 70, 210, 255))
        # Distinguishable internal text/ornament pixels belong to this design.
        draw.rectangle((45, 65, 52, 72), fill=(250, 230, 20, 255))
        path = tmp_path / f'input-{index}.png'
        image.save(path); image.close(); refs[str(index)] = path
    snapshot = dict(layout_engine=quality.ENGINE, asset_refs=list(refs), template_mode='single',
                    template_rules={}, params={}, seed=44,
                    output_profile=dict(width=4000, height=520, dpi=300, format='PNG'))
    return snapshot, refs


def render(snapshot, refs, tmp_path, suffix='result'):
    canvas = Image.new('RGBA', (snapshot['output_profile']['width'], snapshot['output_profile']['height']))
    transforms = quality.compose(canvas, snapshot, refs.__getitem__, tmp_path / (suffix + '.png'))
    return canvas, transforms


def assert_safe(rows):
    for r in rows:
        left, top, right, bottom = r['safe_region']
        assert top <= r['y'] - r['height'] / 2 + .01
        assert r['y'] + r['height'] / 2 <= bottom + .01
        if not r['horizontal_wrap']:
            assert left <= r['x'] - r['width'] / 2 + .01
            assert r['x'] + r['width'] / 2 <= right + .01


@pytest.mark.parametrize('mode', quality.MODES)
def test_real_all_layouts_use_complete_inputs_and_safe_geometry(artwork, tmp_path, mode):
    snapshot, refs = artwork
    snapshot['template_mode'] = mode
    if mode == 'fullwidth': snapshot['asset_refs'] = ['1']
    if mode == 'ends_open': snapshot['asset_refs'] = ['0', '1']
    before = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in refs.items()}
    canvas, rows = render(snapshot, refs, tmp_path)
    assert canvas.getbbox()
    assert set(r['asset_ref'] for r in rows) == set(snapshot['asset_refs'])
    assert_safe(rows)
    assert [r['layer'] for r in rows] == list(range(len(rows)))
    assert all(r['layout_engine'] == quality.ENGINE for r in rows)
    assert before == {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in refs.items()}
    assert not list(tmp_path.glob('ribbon-rhythm-*'))
    canvas.close()


def test_padding_does_not_change_visible_design_size_or_pixels(artwork, tmp_path):
    snapshot, refs = artwork; snapshot['asset_refs'] = ['0']
    first, rows = render(snapshot, refs, tmp_path)
    with Image.open(refs['0']) as source:
        content = source.crop(source.getchannel('A').getbbox())
        padded = Image.new('RGBA', (content.width + 600, content.height + 300))
        padded.paste(content, (177, 231)); content.close()
        padded.save(tmp_path / 'padded.png'); padded.close()
    second, padded_rows = render(snapshot, {'0': tmp_path / 'padded.png'}, tmp_path, 'padding')
    assert first.tobytes() == second.tobytes()
    assert rows[0]['content_bbox'] != padded_rows[0]['content_bbox']
    assert rows[0]['height'] > 380
    first.close(); second.close()


def test_faint_nontransparent_ornament_is_never_discarded(artwork, tmp_path):
    snapshot, refs = artwork; snapshot['asset_refs'] = ['0']
    with Image.open(refs['0']) as source:
        image = source.convert('RGBA')
    image.putpixel((0, 0), (255, 10, 10, 1)); image.save(refs['0']); image.close()
    canvas, rows = render(snapshot, refs, tmp_path)
    assert rows[0]['content_bbox'][:2] == [0, 0]
    canvas.close()


@pytest.mark.parametrize('mode', ('single', 'grid', 'stagger', 'opposed', 'alternating'))
def test_five_asset_sequence_and_alternation_close_at_repeat_seam(artwork, tmp_path, mode):
    snapshot, refs = artwork; snapshot['template_mode'] = mode
    canvas, rows = render(snapshot, refs, tmp_path)
    first_row = [r for r in rows if r['safe_region'] == rows[0]['safe_region']]
    seq_len = first_row[0]['repetition']['sequence_length']
    assert seq_len == (10 if mode in ('opposed', 'alternating') else 5)
    assert len(first_row) % seq_len == 0
    assert [r['asset_ref'] for r in first_row] == snapshot['asset_refs'] * (len(first_row) // 5)
    if mode == 'opposed':
        assert [r['rotation'] for r in first_row] == [0., 180.] * (len(first_row) // 2)
    assert first_row[0]['repetition']['period'] * first_row[0]['repetition']['groups'] == pytest.approx(4000)
    canvas.close()


@pytest.mark.parametrize('angle', (0, 37, 90, 177, -73))
def test_rotation_and_extreme_offsets_keep_complete_visible_height(artwork, tmp_path, angle):
    snapshot, refs = artwork
    snapshot['params'] = dict(rotation=angle, offset_y=4000, offset_x=-8500, scale=2.5)
    canvas, rows = render(snapshot, refs, tmp_path)
    assert_safe(rows)
    assert max(r['y'] + r['height'] / 2 for r in rows) <= 520 * .92 + .01
    canvas.close()


def test_portrait_and_wide_text_keep_aspect_and_comparable_visible_height(artwork, tmp_path):
    snapshot, refs = artwork; snapshot['asset_refs'] = ['0', '1']
    canvas, rows = render(snapshot, refs, tmp_path)
    first, second = rows[:2]
    assert first['height'] == pytest.approx(second['height'], abs=3)
    assert first['width'] / first['height'] == pytest.approx(.5, abs=.02)
    assert second['width'] / second['height'] == pytest.approx(260 / 70, abs=.05)
    assert second['x'] - first['x'] >= (first['width'] + second['width']) / 2
    canvas.close()


def test_scatter_is_deterministic_without_arbitrary_character_rotation(artwork, tmp_path):
    snapshot, refs = artwork; snapshot['template_mode'] = 'scatter'
    first, rows = render(snapshot, refs, tmp_path)
    second, again = render(deepcopy(snapshot), refs, tmp_path, 'again')
    assert first.tobytes() == second.tobytes() and rows == again
    assert {r['rotation'] for r in rows} == {0.}
    first.close(); second.close()


def test_fixed_zones_do_not_bleed_into_the_other_panel(artwork, tmp_path):
    snapshot, refs = artwork; snapshot['template_mode'] = 'split'
    snapshot['params'] = dict(offset_x=3900, offset_y=-3000, rotation=23, scale=2.)
    canvas, rows = render(snapshot, refs, tmp_path)
    assert_safe(rows)
    assert all(r['x'] + r['width'] / 2 <= 2000 for r in rows if r['role'] == 'left-zone')
    assert all(r['x'] - r['width'] / 2 >= 2000 for r in rows if r['role'] == 'right-zone')
    for role in ('left-zone', 'right-zone'):
        same_lane = [r for r in rows if r['role'] == role and r['safe_region'] ==
                     next(row['safe_region'] for row in rows if row['role'] == role)]
        same_lane.sort(key=lambda r: r['x'])
        assert all(a['x'] + a['width'] / 2 <= b['x'] - b['width'] / 2 + .01
                   for a, b in zip(same_lane, same_lane[1:]))
    canvas.close()


@pytest.mark.parametrize('mode', ('single', 'stagger', 'scene', 'opposed', 'bordered', 'stacked'))
def test_full_strip_horizontal_shift_is_same_repeat_phase(artwork, tmp_path, mode):
    snapshot, refs = artwork; snapshot['template_mode'] = mode
    first, _ = render(snapshot, refs, tmp_path)
    snapshot['params'] = dict(offset_x=snapshot['output_profile']['width'])
    second, _ = render(snapshot, refs, tmp_path, 'shifted')
    assert first.tobytes() == second.tobytes()
    first.close(); second.close()


def test_empty_image_fails_instead_of_silently_losing_selected_design(artwork, tmp_path):
    snapshot, refs = artwork; snapshot['asset_refs'] = ['0']
    Image.new('RGBA', (300, 300)).save(refs['0'])
    with pytest.raises(ValueError, match='没有可见内容'):
        render(snapshot, refs, tmp_path)


def test_held_out_new_proportions_need_no_name_or_id_rules(tmp_path):
    refs = {}
    for index, shape in enumerate(((31, 280), (920, 55), (83, 83), (251, 144), (90, 210), (420, 130), (75, 195))):
        key = f'unseen-{index}'
        image = Image.new('RGBA', shape, (18, 30 + index * 20, 180, 255))
        refs[key] = tmp_path / (key + '.png'); image.save(refs[key]); image.close()
    snapshot = dict(layout_engine=quality.ENGINE, asset_refs=list(refs), template_mode='single',
                    template_rules={}, params={}, output_profile=dict(width=11811, height=520, dpi=300))
    canvas, rows = render(snapshot, refs, tmp_path)
    assert_safe(rows)
    assert set(r['asset_ref'] for r in rows) == set(refs)
    assert len(rows) % 7 == 0
    assert quality.estimate(snapshot) > len(canvas.tobytes())
    canvas.close()


@pytest.mark.parametrize('mode', ('single', 'stagger', 'scene', 'opposed'))
def test_balanced_explicit_matches_default_pixels(artwork, tmp_path, mode):
    snapshot, refs = artwork; snapshot['template_mode'] = mode
    first, _ = render(snapshot, refs, tmp_path)
    snapshot['design_density'] = 'balanced'
    second, _ = render(snapshot, refs, tmp_path, 'explicit-balanced')
    assert first.tobytes() == second.tobytes()
    first.close(); second.close()


def test_density_changes_real_pixels_rows_and_motif_hierarchy(artwork, tmp_path):
    snapshot, refs = artwork; snapshot['template_mode'] = 'stagger'
    outputs = {}
    for density in quality.DENSITIES:
        snapshot['design_density'] = density
        image, rows = render(snapshot, refs, tmp_path, density)
        outputs[density] = (hashlib.sha256(image.tobytes()).hexdigest(), rows)
        assert_safe(rows)
        assert min(r['y'] - r['height'] / 2 for r in rows) >= .08 * 520
        assert max(r['y'] + r['height'] / 2 for r in rows) <= .92 * 520
        assert set(r['asset_ref'] for r in rows) == set(refs)
        assert {r['design_density'] for r in rows} == {density}
        image.close()
    assert len({row[0] for row in outputs.values()}) == 3
    assert len({tuple(r['safe_region']) for r in outputs['balanced'][1]}) == 2
    assert len({tuple(r['safe_region']) for r in outputs['rich'][1]}) == 3
    airy_height = next(r['height'] for r in outputs['airy'][1] if r['asset_ref'] == '0')
    balanced_height = next(r['height'] for r in outputs['balanced'][1] if r['asset_ref'] == '0')
    assert airy_height < balanced_height


@pytest.mark.parametrize('density', quality.DENSITIES)
@pytest.mark.parametrize('count', (3, 4))
def test_custom_row_count_obeys_global_safe_area_and_keeps_inputs(artwork, tmp_path, density, count):
    snapshot, refs = artwork; snapshot['template_mode'] = 'grid'
    snapshot['template_rules'] = {'rows': count}; snapshot['design_density'] = density
    image, rows = render(snapshot, refs, tmp_path)
    assert len({tuple(r['safe_region']) for r in rows}) == count
    assert_safe(rows)
    assert min(r['y'] - r['height'] / 2 for r in rows) >= .08 * 520
    assert max(r['y'] + r['height'] / 2 for r in rows) <= .92 * 520
    image.close()


def test_invalid_density_does_not_silently_choose_a_style(artwork, tmp_path):
    snapshot, refs = artwork; snapshot['design_density'] = 'invented'
    with pytest.raises(ValueError, match='排版疏密'):
        render(snapshot, refs, tmp_path)


@pytest.mark.parametrize('mode', ('ends', 'ends_open', 'panels'))
def test_narrow_legacy_profile_does_not_make_negative_fixed_regions(artwork, tmp_path, mode):
    snapshot, refs = artwork; snapshot['template_mode'] = mode; snapshot['asset_refs'] = ['0']
    snapshot['output_profile'].update(width=64, height=640)
    canvas, rows = render(snapshot, refs, tmp_path)
    assert_safe(rows)
    assert canvas.getbbox()
    assert all(r['safe_region'][0] < r['safe_region'][2] for r in rows)
    canvas.close()


@pytest.mark.parametrize('mode', ('grid', 'stagger', 'scatter', 'stacked', 'split', 'panels'))
def test_common_two_row_enlargement_has_real_headroom_without_collisions(artwork, tmp_path, mode):
    snapshot, refs = artwork; snapshot['template_mode'] = mode
    if mode == 'panels':
        # Leave width headroom too: five very wide designs in a third-width
        # zone legitimately hit its horizontal bound before the height bound.
        snapshot['asset_refs'] = ['0']
    first, original = render(snapshot, refs, tmp_path)
    snapshot['params'] = {'scale': 1.2}
    larger, rows = render(snapshot, refs, tmp_path, 'larger')
    assert first.tobytes() != larger.tobytes()
    # Compare the same complete first design in the first row. Its visible
    # size must grow, rather than a pixel-only translation imitating growth.
    before = next(r for r in original if r['asset_ref'] == '0')
    after = next(r for r in rows if r['asset_ref'] == '0')
    assert after['height'] > before['height'] * 1.12
    assert_safe(rows)
    for row in rows:
        assert row['y'] - row['height'] / 2 >= .08 * 520 - .01
        assert row['y'] + row['height'] / 2 <= .92 * 520 + .01
    # Safe halves are disjoint; each complete motif remains in its own half.
    upper = [r for r in rows if r['y'] < 260]
    lower = [r for r in rows if r['y'] > 260]
    if upper and lower:
        assert max(r['y'] + r['height'] / 2 for r in upper) <= min(r['y'] - r['height'] / 2 for r in lower)
    first.close(); larger.close()


@pytest.mark.parametrize('mode', ('grid', 'stagger'))
def test_two_row_nominal_size_and_shrink_are_preserved(artwork, tmp_path, mode):
    snapshot, refs = artwork; snapshot['template_mode'] = mode
    first, original = render(snapshot, refs, tmp_path)
    assert next(r for r in original if r['asset_ref'] == '0')['height'] == 172
    assert {round(r['y']) for r in original} == {130, 390}
    snapshot['params'] = {'scale': .6}
    smaller, rows = render(snapshot, refs, tmp_path, 'smaller')
    assert first.tobytes() != smaller.tobytes()
    assert next(r for r in rows if r['asset_ref'] == '0')['height'] < 172 * .65
    assert_safe(rows)
    first.close(); smaller.close()


@pytest.mark.parametrize('density', quality.DENSITIES)
@pytest.mark.parametrize('count', (1, 2, 5))
@pytest.mark.parametrize('main_ref', ('0', '1'))
def test_new_ends_keep_main_hierarchy_for_complete_portrait_and_landscape_art(
        artwork, tmp_path, density, count, main_ref):
    snapshot, refs = artwork
    snapshot.update(layout_engine=quality.END_HIERARCHY_ENGINE, template_mode='ends',
                    design_density=density)
    snapshot['output_profile']['width'] = 11811
    snapshot['asset_refs'] = [main_ref] + [r for r in refs if r != main_ref][:count - 1]
    canvas, rows = render(snapshot, refs, tmp_path)
    ends = [r for r in rows if r['role'] in ('left-end', 'right-end')]
    inner = [r for r in rows if r['role'] == 'inner']
    assert [r['role'] for r in ends] == ['left-end', 'right-end']
    assert {r['asset_ref'] for r in ends} == {main_ref}
    assert {r['asset_ref'] for r in inner} == set(snapshot['asset_refs'][1:] or [main_ref])
    assert ends[0]['width'] == ends[1]['width']
    assert ends[0]['height'] == ends[1]['height']
    assert ends[0]['height'] > max(r['height'] for r in inner) * 1.45
    assert all(not r['horizontal_wrap'] for r in rows)
    assert_safe(rows)
    expected_ratio = .5 if main_ref == '0' else 260 / 70
    assert ends[0]['width'] / ends[0]['height'] == pytest.approx(expected_ratio, rel=.02)
    # End treatments are anchored near the actual strip ends, not in large
    # fixed boxes whose width ignores the selected design's aspect ratio.
    assert ends[0]['x'] - ends[0]['width'] / 2 < 520 * .10
    assert 11811 - ends[1]['x'] - ends[1]['width'] / 2 < 520 * .10
    canvas.close()


@pytest.mark.parametrize('angle', (0, 37, 90))
@pytest.mark.parametrize('offset', (-30000, 0, 30000))
def test_new_ends_offset_rotation_and_layer_order_never_cover_end_art(
        artwork, tmp_path, monkeypatch, angle, offset):
    snapshot, refs = artwork
    snapshot.update(layout_engine=quality.END_HIERARCHY_ENGINE, template_mode='ends',
                    design_density='rich')
    snapshot['asset_refs'] = ['1', '0', '2', '3', '4']
    snapshot['output_profile']['width'] = 11811
    snapshot['params'] = dict(rotation=angle, offset_x=offset, offset_y=offset, scale=1.4)
    canvas, rows = render(snapshot, refs, tmp_path)
    assert_safe(rows)
    end = next(r for r in rows if r['role'] == 'left-end')
    inner = [r for r in rows if r['role'] == 'inner']
    assert end['height'] > max(r['height'] for r in inner) * 1.4
    assert end['x'] + end['width'] / 2 <= min(r['x'] - r['width'] / 2 for r in inner)
    right = next(r for r in rows if r['role'] == 'right-end')
    assert max(r['x'] + r['width'] / 2 for r in inner) <= right['x'] - right['width'] / 2
    assert canvas.getchannel('A').crop((0, 0, 1, 520)).getbbox() is None
    assert canvas.getchannel('A').crop((11810, 0, 11811, 520)).getbbox() is None
    original_plan = quality.plan
    monkeypatch.setattr(quality, 'plan', lambda s, specs: original_plan(s, specs)[::-1])
    reversed_canvas, _ = render(snapshot, refs, tmp_path, 'reverse-layers')
    assert reversed_canvas.tobytes() == canvas.tobytes()
    canvas.close(); reversed_canvas.close()


def test_extremely_wide_ends_cap_both_regions_and_keep_smaller_middle(artwork, tmp_path):
    snapshot, refs = artwork
    with Image.new('RGBA', (1500, 60), (30, 70, 210, 255)) as image:
        image.save(refs['0'])
    snapshot.update(layout_engine=quality.END_HIERARCHY_ENGINE, template_mode='ends',
                    design_density='rich', asset_refs=['0'])
    snapshot['output_profile']['width'] = 11811
    canvas, rows = render(snapshot, refs, tmp_path)
    end, inner = rows[0], rows[2]
    assert end['safe_region'][2] == pytest.approx(11811 * .44)
    assert end['height'] > inner['height'] * 1.45
    assert end['width'] / end['height'] == pytest.approx(25, rel=.02)
    assert inner['width'] / inner['height'] == pytest.approx(25, rel=.04)
    assert_safe(rows)
    canvas.close()


def test_v1_ends_and_unrelated_mode_pixels_remain_unchanged(artwork, tmp_path):
    snapshot, refs = artwork
    snapshot.update(template_mode='ends', design_density='rich', asset_refs=['1'])
    snapshot['output_profile']['width'] = 11811
    old_canvas, old_rows = render(snapshot, refs, tmp_path)
    # Preserve the original v1 sizing even though its landscape hierarchy is
    # weak; saved versions must never silently acquire a new composition.
    assert old_rows[0]['width'] == 599
    assert old_rows[0]['height'] < old_rows[2]['height']
    snapshot.pop('layout_engine')
    legacy_canvas, _ = render(snapshot, refs, tmp_path, 'missing-engine')
    assert legacy_canvas.tobytes() == old_canvas.tobytes()
    old_canvas.close(); legacy_canvas.close()
    for mode in quality.MODES:
        if mode == 'ends':
            continue
        before = dict(snapshot, layout_engine=quality.ENGINE, template_mode=mode)
        before['asset_refs'] = ['0', '1'] if mode in ('bordered', 'split', 'stacked') else ['0']
        after = dict(before, layout_engine=quality.END_HIERARCHY_ENGINE)
        first, _ = render(before, refs, tmp_path, mode + '-v1')
        second, _ = render(after, refs, tmp_path, mode + '-v2')
        assert first.tobytes() == second.tobytes(), mode
        first.close(); second.close()
