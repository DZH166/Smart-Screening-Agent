"""Synthetic geometry checks for additional layouts; no company art or models."""
from copy import deepcopy
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw
import pytest

from ribbon_backend import imaging


@pytest.fixture
def artwork(tmp_path):
    refs = {}
    for name, size, color in [('main', (80, 120), '#1357bf'),
                              ('flower', (90, 90), '#d62828'),
                              ('leaf', (120, 60), '#267534')]:
        path = tmp_path / (name + '.png')
        image = Image.new('RGBA', size, color)
        ImageDraw.Draw(image).rectangle((size[0] // 3, size[1] // 3, size[0] * 2 // 3,
                                        size[1] * 2 // 3), fill='#ffc400')
        image.save(path)
        image.close()
        refs[name] = path
    complete = Image.new('RGBA', (1000, 100), '#557799')
    draw = ImageDraw.Draw(complete)
    draw.rectangle((0, 0, 39, 99), fill='#d62828')
    draw.rectangle((960, 0, 999, 99), fill='#267534')
    draw.rectangle((450, 30, 550, 70), fill='#ffc400')
    refs['complete'] = tmp_path / 'complete.png'
    complete.save(refs['complete'])
    complete.close()
    refs['background'] = tmp_path / 'background.png'
    Image.new('RGBA', (1, 1), 'white').save(refs['background'])
    snapshot = dict(schema_version=1, asset_refs=['main', 'flower', 'leaf'],
                    background_ref='background', template_mode='scene', template_rules={},
                    params=dict(imaging.PARAM_DEFAULTS), seed=1729,
                    output_profile=dict(width=1200, height=240, dpi=300, format='PNG', is_demo=True))
    return snapshot, refs


def compose(tmp_path, snapshot, refs, name='output'):
    master, preview = tmp_path / (name + '.png'), tmp_path / (name + '-preview.png')
    result = imaging.render(snapshot, refs.__getitem__, master, preview)
    return result, master, preview


def pixels(path):
    with Image.open(path) as image:
        return image.convert('RGBA').tobytes()


def colors(image):
    with image.convert('RGB') as rgb:
        raw = rgb.tobytes()
    return set(zip(raw[::3], raw[1::3], raw[2::3]))


def select_for_mode(snapshot, mode):
    snapshot['template_mode'] = mode
    if mode == 'fullwidth':
        snapshot['asset_refs'] = ['complete']
    elif mode == 'ends_open':
        snapshot['asset_refs'] = snapshot['asset_refs'][:2]


@pytest.mark.parametrize('mode', imaging.EXTENSION_MODES)
def test_new_layouts_have_real_geometry_keep_input_and_repeat_deterministically(artwork, tmp_path, mode):
    snapshot, refs = artwork
    select_for_mode(snapshot, mode)
    original = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in refs.items()}
    first, master, preview = compose(tmp_path, snapshot, refs)
    again, second, _ = compose(tmp_path, deepcopy(snapshot), refs, 'again')
    assert first['sha256'] == again['sha256'] and pixels(master) == pixels(second)
    assert set(row['asset_ref'] for row in first['object_transforms']) == set(snapshot['asset_refs'])
    assert [row['layer'] for row in first['object_transforms']] == list(range(len(first['object_transforms'])))
    assert first['render_kind'] == 'layered'
    assert imaging.validate_image(master, snapshot['output_profile'])['width'] == 1200
    with Image.open(preview) as image:
        assert image.size == (1200, 240)
    assert original == {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in refs.items()}
    assert not list(tmp_path.glob('ribbon-motifs-*'))


def test_borders_use_first_subject_and_other_patterns_in_separate_narrow_bands(artwork, tmp_path):
    snapshot, refs = artwork
    snapshot['template_mode'] = 'bordered'
    result, _, _ = compose(tmp_path, snapshot, refs)
    rows = result['object_transforms']
    main = [row for row in rows if row['role'] == 'main']
    top = [row for row in rows if row['role'] == 'top-border']
    bottom = [row for row in rows if row['role'] == 'bottom-border']
    assert main and top and bottom
    assert {row['asset_ref'] for row in main} == {'main'}
    assert {row['asset_ref'] for row in top} == {row['asset_ref'] for row in bottom} == {'flower', 'leaf'}
    assert max(row['y'] + row['height'] / 2 for row in top) < min(row['y'] - row['height'] / 2 for row in main)
    assert max(row['y'] + row['height'] / 2 for row in main) < min(row['y'] - row['height'] / 2 for row in bottom)
    assert max(row['height'] for row in top + bottom) < max(row['height'] for row in main)


def test_scene_repeats_the_entire_group_with_same_internal_relations(artwork, tmp_path):
    snapshot, refs = artwork
    result, _, _ = compose(tmp_path, snapshot, refs)
    groups = {}
    for row in result['object_transforms']:
        groups.setdefault(row['group'], []).append(row)
    assert len(groups) >= 2
    first, second = groups[0], groups[1]
    assert [row['asset_ref'] for row in first] == snapshot['asset_refs']
    assert len({row['y'] for row in first}) > 1
    translations = [b['x'] - a['x'] for a, b in zip(first, second)]
    assert translations == pytest.approx([translations[0]] * len(first))
    assert [(row['y'], row['width'], row['height']) for row in first] == [
        (row['y'], row['width'], row['height']) for row in second]


def test_complete_scene_is_not_split_and_preserves_its_internal_aspect(artwork, tmp_path):
    snapshot, refs = artwork
    snapshot['asset_refs'] = ['complete']
    snapshot['output_profile']['width'] = 5000
    result, _, _ = compose(tmp_path, snapshot, refs)
    objects = result['object_transforms']
    assert len(objects) >= 2
    assert {row['asset_ref'] for row in objects} == {'complete'}
    assert all(row['width'] / row['height'] == pytest.approx(10, abs=.12) for row in objects)


@pytest.mark.parametrize('angle', [0, 37, -80, 180])
def test_fullwidth_contains_one_complete_design_without_stretching_or_default_crop(artwork, tmp_path, angle):
    snapshot, refs = artwork
    snapshot['asset_refs'] = ['complete']
    snapshot['template_mode'] = 'fullwidth'
    snapshot['params']['rotation'] = angle
    result, path, _ = compose(tmp_path, snapshot, refs)
    objects = result['object_transforms']
    assert len(objects) == 1
    row = objects[0]
    assert row['role'] == 'complete'
    assert row['x'] - row['width'] / 2 >= 0
    assert row['x'] + row['width'] / 2 <= 1200
    assert row['y'] - row['height'] / 2 >= 0
    assert row['y'] + row['height'] / 2 <= 240
    if angle == 0:
        assert row['width'] / row['height'] == pytest.approx(10, abs=.06)
        with Image.open(path) as image:
            left = round(row['x'] - row['width'] / 2 + 12), round(row['y'])
            right = round(row['x'] + row['width'] / 2 - 12), round(row['y'])
            assert image.getpixel(left)[:3] == (214, 40, 40)
            assert image.getpixel(right)[:3] == (38, 117, 52)


@pytest.mark.parametrize('mode', imaging.EXTENSION_MODES)
@pytest.mark.parametrize('parameter,value', [('scale', .6), ('rotation', 29), ('offset_x', 35), ('offset_y', -11)])
def test_edit_parameters_change_actual_new_layout_pixels(artwork, tmp_path, mode, parameter, value):
    snapshot, refs = artwork
    select_for_mode(snapshot, mode)
    _, before, _ = compose(tmp_path, snapshot, refs, 'before')
    snapshot['params'][parameter] = value
    _, after, _ = compose(tmp_path, snapshot, refs, 'after')
    assert pixels(before) != pixels(after)


@pytest.mark.parametrize('mode', ['scene', 'bordered', 'alternating', 'split', 'stacked', 'opposed'])
def test_repeat_spacing_changes_actual_density(artwork, tmp_path, mode):
    snapshot, refs = artwork
    snapshot['template_mode'] = mode
    first, before, _ = compose(tmp_path, snapshot, refs)
    snapshot['params']['spacing'] = 2
    second, after, _ = compose(tmp_path, snapshot, refs, 'sparse')
    assert len(second['object_transforms']) < len(first['object_transforms'])
    assert pixels(before) != pixels(after)


def test_fullwidth_has_no_repeat_density_parameter(artwork, tmp_path):
    snapshot, refs = artwork
    snapshot.update(template_mode='fullwidth', asset_refs=['complete'])
    first, before, _ = compose(tmp_path, snapshot, refs)
    snapshot['params']['spacing'] = 2
    second, after, _ = compose(tmp_path, snapshot, refs, 'no-spacing')
    assert first['object_transforms'] == second['object_transforms']
    assert pixels(before) == pixels(after)


@pytest.mark.parametrize('mode', imaging.EXTENSION_MODES)
def test_conservative_estimate_covers_each_actual_png_write(artwork, tmp_path, monkeypatch, mode):
    snapshot, refs = artwork
    select_for_mode(snapshot, mode)
    snapshot['params'].update(scale=1.35, rotation=31, spacing=.75)
    estimate = imaging.estimate_render_space(snapshot)
    writes = []
    save = imaging._save_png
    def observe(image, path, dpi=144):
        writes.append(imaging.png_space(*image.size))
        return save(image, path, dpi)
    monkeypatch.setattr(imaging, '_save_png', observe)
    compose(tmp_path, snapshot, refs)
    assert sum(writes) <= estimate


@pytest.mark.parametrize('mode,refs', [('bordered', ['main']), ('fullwidth', ['main', 'flower']),
                                     ('ends_open', ['main', 'flower', 'leaf']), ('split', ['main']),
                                     ('stacked', ['main'])])
def test_unsupported_source_counts_fail_before_decode_or_output(artwork, tmp_path, monkeypatch, mode, refs):
    snapshot, paths = artwork
    snapshot.update(template_mode=mode, asset_refs=refs)
    monkeypatch.setattr(imaging, 'read_image', lambda path: pytest.fail('Invalid selection decoded a source'))
    with pytest.raises(ValueError, match='至少|一张'):
        compose(tmp_path, snapshot, paths)
    assert not list(tmp_path.glob('output*.png'))


@pytest.mark.parametrize('mode', imaging.EXTENSION_MODES)
def test_new_thumbnail_is_real_algorithm_output(tmp_path, mode):
    target = tmp_path / (mode + '.png')
    imaging.template_thumbnail(mode, target)
    with Image.open(target) as image:
        image.verify()
        assert image.size == (640, 200)


@pytest.mark.parametrize('mode', ['scene', 'bordered', 'alternating', 'split', 'stacked', 'opposed'])
def test_many_selected_patterns_are_not_silently_dropped_in_a_narrow_profile(artwork, tmp_path, mode):
    snapshot, refs = artwork
    selected = []
    for index in range(12):
        key = f'pattern-{index}'
        refs[key] = refs['main' if index == 0 else 'flower']
        selected.append(key)
    snapshot.update(template_mode=mode, asset_refs=selected)
    snapshot['output_profile'].update(width=128, height=400)
    result, _, _ = compose(tmp_path, snapshot, refs)
    assert {row['asset_ref'] for row in result['object_transforms']} == set(selected)


def test_complete_design_honors_exif_orientation_when_fitting(artwork, tmp_path):
    snapshot, refs = artwork
    oriented = Image.new('RGBA', (400, 100), '#1357bf')
    exif = Image.Exif()
    exif[274] = 6
    refs['oriented'] = tmp_path / 'oriented.png'
    oriented.save(refs['oriented'], exif=exif)
    oriented.close()
    snapshot.update(template_mode='fullwidth', asset_refs=['oriented'])
    result, _, _ = compose(tmp_path, snapshot, refs)
    row = result['object_transforms'][0]
    assert row['height'] / row['width'] == pytest.approx(4, abs=.1)
    assert row['height'] <= 240 and row['width'] <= 1200


@pytest.mark.parametrize('mode', imaging.EXTENSION_MODES)
def test_new_paths_refuse_insufficient_space_before_decoding(artwork, tmp_path, monkeypatch, mode):
    from types import SimpleNamespace
    snapshot, refs = artwork
    select_for_mode(snapshot, mode)
    monkeypatch.setattr(imaging.shutil, 'disk_usage', lambda directory: SimpleNamespace(free=1))
    monkeypatch.setattr(imaging, 'read_image', lambda path: pytest.fail('Storage failure decoded a source'))
    with pytest.raises(OSError, match='空间'):
        compose(tmp_path, snapshot, refs)
    assert not list(tmp_path.glob('output*.png'))


def test_alternating_really_changes_size_and_preserves_large_small_seam_order(artwork, tmp_path):
    snapshot, refs = artwork
    snapshot.update(template_mode='alternating', asset_refs=['main'])
    result, _, _ = compose(tmp_path, snapshot, refs)
    objects = result['object_transforms']
    assert len(objects) >= 2 and len(objects) % 2 == 0
    assert [row['role'] for row in objects] == ['large', 'small'] * (len(objects) // 2)
    assert min(row['height'] for row in objects[::2]) > max(row['height'] for row in objects[1::2])
    assert objects[0]['role'] != objects[-1]['role']


@pytest.mark.parametrize('mode', ['alternating', 'split', 'stacked', 'opposed'])
def test_new_repeated_layout_step_rule_changes_real_density(artwork, tmp_path, mode):
    snapshot, refs = artwork
    snapshot['template_mode'] = mode
    first, before, _ = compose(tmp_path, snapshot, refs)
    snapshot['template_rules']['step_ratio'] = 1.28
    second, after, _ = compose(tmp_path, snapshot, refs, 'wide-steps')
    assert len(second['object_transforms']) < len(first['object_transforms'])
    assert pixels(before) != pixels(after)


@pytest.mark.parametrize('selected', [['main'], ['main', 'flower']])
@pytest.mark.parametrize('profile', [(1200, 240), (128, 400)])
def test_open_ends_use_exactly_two_complete_objects_and_keep_the_middle_empty(artwork, tmp_path, selected, profile):
    snapshot, refs = artwork
    snapshot.update(template_mode='ends_open', asset_refs=selected)
    width, height = profile
    snapshot['output_profile'].update(width=width, height=height)
    result, path, _ = compose(tmp_path, snapshot, refs)
    objects = result['object_transforms']
    assert len(objects) == 2
    assert [row['role'] for row in objects] == ['left-end', 'right-end']
    assert [row['asset_ref'] for row in objects] == [selected[0], selected[-1]]
    for row in objects:
        assert row['x'] - row['width'] / 2 >= -1
        assert row['x'] + row['width'] / 2 <= width + 1
        assert row['y'] - row['height'] / 2 >= -1
        assert row['y'] + row['height'] / 2 <= height + 1
    left_edge = round(objects[0]['x'] + objects[0]['width'] / 2) + 1
    right_edge = round(objects[1]['x'] - objects[1]['width'] / 2) - 1
    assert left_edge < right_edge
    with Image.open(path) as image:
        with image.crop((left_edge, 0, right_edge, height)) as middle:
            assert colors(middle) == {(255, 255, 255)}


def test_open_ends_do_not_invent_repeat_spacing_or_steps(artwork, tmp_path):
    snapshot, refs = artwork
    snapshot.update(template_mode='ends_open', asset_refs=['main', 'flower'])
    first, before, _ = compose(tmp_path, snapshot, refs)
    snapshot['params']['spacing'] = 2
    snapshot['template_rules']['step_ratio'] = 1.28
    second, after, _ = compose(tmp_path, snapshot, refs, 'still-two-ends')
    assert first['object_transforms'] == second['object_transforms']
    assert pixels(before) == pixels(after)


def test_split_assigns_front_half_to_left_and_back_half_to_right(artwork, tmp_path):
    snapshot, refs = artwork
    snapshot['template_mode'] = 'split'
    result, _, _ = compose(tmp_path, snapshot, refs)
    left = [row for row in result['object_transforms'] if row['role'] == 'left-zone']
    right = [row for row in result['object_transforms'] if row['role'] == 'right-zone']
    assert {row['asset_ref'] for row in left} == {'main', 'flower'}
    assert {row['asset_ref'] for row in right} == {'leaf'}
    assert all(row['clip_x'] == [0, 600] for row in left)
    assert all(row['clip_x'] == [600, 1200] for row in right)
    assert all(row['x'] - row['width'] / 2 >= 0 and row['x'] + row['width'] / 2 <= 600 for row in left)
    assert all(row['x'] - row['width'] / 2 >= 600 and row['x'] + row['width'] / 2 <= 1200 for row in right)


@pytest.mark.parametrize('offset', [-120, 120])
def test_split_never_paints_the_other_region_even_after_explicit_large_edits(artwork, tmp_path, offset):
    snapshot, refs = artwork
    for key, color in [('left-solid', 'red'), ('right-solid', 'blue')]:
        path = tmp_path / (key + '.png')
        Image.new('RGBA', (100, 100), color).save(path)
        refs[key] = path
    snapshot.update(template_mode='split', asset_refs=['left-solid', 'right-solid'])
    snapshot['params'].update(scale=2.5, rotation=47, offset_x=offset)
    _, path, _ = compose(tmp_path, snapshot, refs)
    with Image.open(path) as image:
        with image.crop((0, 0, 600, 240)) as left, image.crop((600, 0, 1200, 240)) as right:
            left_colors = colors(left)
            right_colors = colors(right)
    assert (255, 0, 0) in left_colors and (0, 0, 255) in right_colors
    assert (0, 0, 255) not in left_colors and (255, 0, 0) not in right_colors


def test_opposed_is_a_true_180_degree_rotation_and_not_a_mirror(artwork, tmp_path):
    snapshot, refs = artwork
    asymmetric = Image.new('RGBA', (100, 100), '#ddeeff')
    draw = ImageDraw.Draw(asymmetric)
    draw.rectangle((10, 10, 20, 90), fill='black')
    draw.rectangle((10, 10, 80, 20), fill='red')
    draw.rectangle((10, 40, 60, 50), fill='blue')
    refs['asymmetric'] = tmp_path / 'asymmetric.png'
    asymmetric.save(refs['asymmetric'])
    asymmetric.close()
    snapshot.update(template_mode='opposed', asset_refs=['asymmetric'])
    result, path, _ = compose(tmp_path, snapshot, refs)
    objects = result['object_transforms']
    assert len(objects) % 2 == 0 and len(objects) >= 2
    assert [row['rotation'] for row in objects] == [0, 180] * (len(objects) // 2)
    assert {row['y'] for row in objects} == {120}
    first, second = objects[:2]
    def bounds(row):
        left, top = round(row['x'] - row['width'] / 2), round(row['y'] - row['height'] / 2)
        return left, top, left + row['width'], top + row['height']
    with Image.open(path) as image:
        with image.crop(bounds(first)) as upright, image.crop(bounds(second)) as inverted:
            with upright.transpose(Image.Transpose.ROTATE_180) as rotated:
                assert rotated.tobytes() == inverted.tobytes()
            with upright.transpose(Image.Transpose.FLIP_LEFT_RIGHT) as mirrored:
                assert mirrored.tobytes() != inverted.tobytes()


def test_stacked_assigns_front_half_to_top_and_back_half_to_bottom(artwork, tmp_path):
    snapshot, refs = artwork
    snapshot['template_mode'] = 'stacked'
    result, _, _ = compose(tmp_path, snapshot, refs)
    top = [row for row in result['object_transforms'] if row['role'] == 'top-zone']
    bottom = [row for row in result['object_transforms'] if row['role'] == 'bottom-zone']
    assert {row['asset_ref'] for row in top} == {'main', 'flower'}
    assert {row['asset_ref'] for row in bottom} == {'leaf'}
    assert all(row['clip_y'] == [0, 120] for row in top)
    assert all(row['clip_y'] == [120, 240] for row in bottom)
    assert all(row['y'] - row['height'] / 2 >= 0 and row['y'] + row['height'] / 2 <= 120 for row in top)
    assert all(row['y'] - row['height'] / 2 >= 120 and row['y'] + row['height'] / 2 <= 240 for row in bottom)


@pytest.mark.parametrize('offset', [-40, 40])
def test_stacked_never_paints_the_other_region_after_explicit_large_edits(artwork, tmp_path, offset):
    snapshot, refs = artwork
    for key, color in [('top-solid', 'red'), ('bottom-solid', 'blue')]:
        path = tmp_path / (key + '.png')
        Image.new('RGBA', (100, 100), color).save(path)
        refs[key] = path
    snapshot.update(template_mode='stacked', asset_refs=['top-solid', 'bottom-solid'])
    snapshot['params'].update(scale=2.5, rotation=47, offset_y=offset)
    _, path, _ = compose(tmp_path, snapshot, refs)
    with Image.open(path) as image:
        with image.crop((0, 0, 1200, 120)) as top, image.crop((0, 120, 1200, 240)) as bottom:
            top_colors, bottom_colors = colors(top), colors(bottom)
    assert (255, 0, 0) in top_colors and (0, 0, 255) in bottom_colors
    assert (0, 0, 255) not in top_colors and (255, 0, 0) not in bottom_colors
