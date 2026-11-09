"""Surrounding decoration uses the same complete foreground sequence and period."""
from copy import deepcopy
from hashlib import sha256
import json
import math

from PIL import Image
import pytest

from ribbon_backend import loop_layout_v3 as layout, loop_pipeline_v3 as pipeline


def snapshot(mode, assets, roles=None, density='balanced', seed=32):
    return dict(layout_engine=layout.ENGINE, template_mode=mode, template_rules={},
                asset_refs=assets, background_ref='background',
                pattern_slots=['slot-' + asset for asset in assets], pattern_roles=roles or {},
                seed=seed, params={}, design_density=density,
                output_profile=dict(width=11811, height=520, dpi=300, format='PNG'))


MAIN = [dict(width=100, height=180), dict(width=300, height=90)]
ORNAMENT = [dict(width=180, height=180), dict(width=240, height=42)]


@pytest.mark.parametrize('mode', layout.MODES)
@pytest.mark.parametrize('density', ('airy', 'balanced', 'rich'))
def test_all_layouts_keep_foreground_structure_and_place_each_ornament(mode, density):
    main = ['first'] if mode == 'fullwidth' else ['first', 'second']
    assets = ['round', *main, 'wide']
    roles = {'slot-round': 'decoration', 'slot-wide': 'decoration'}
    value = snapshot(mode, assets, roles, density)
    primary = snapshot(mode, main, density=density)
    with_ornaments = layout.resolve(value, specs=[ORNAMENT[0], *MAIN[:len(main)], ORNAMENT[1]])
    plain = layout.resolve(primary, specs=MAIN[:len(main)])
    p = layout.plan(with_ornaments)
    assert layout.plan(json.loads(json.dumps(with_ornaments, sort_keys=True))) == p
    assert with_ornaments['output_profile'] == plain['output_profile']
    body = [part for part in p if part['role'] != 'decoration']
    assert len(body) == len(layout.plan(plain))
    for actual, original in zip(body, layout.plan(plain)):
        assert assets[actual['asset_index']] == main[original['asset_index']]
        assert {k: v for k, v in actual.items() if k not in ('asset_index', 'repetition')} == {
            k: v for k, v in original.items() if k not in ('asset_index', 'repetition')}
        assert [assets[i] for i in actual['repetition']['sequence']] == [
            main[i] for i in original['repetition']['sequence']]
    ornaments = [part for part in p if part['role'] == 'decoration']
    assert [assets[part['asset_index']] for part in ornaments] == ['round', 'wide']
    assert with_ornaments['loop_layout']['verification']['decoration_count'] == 2
    width, height = with_ornaments['output_profile']['width'], with_ornaments['output_profile']['height']
    for index, part in enumerate(ornaments):
        left, top, right, bottom = part['region']
        x, y, tw, th = (part[k] for k in ('x', 'y', 'target_width', 'target_height'))
        assert 0 <= left <= x - part['planned_width'] / 2 < x + part['planned_width'] / 2 <= right <= width
        assert 0 <= top <= y - part['planned_height'] / 2 < y + part['planned_height'] / 2 <= bottom <= height
        assert max(tw, th) <= height * .17
        spec = ORNAMENT[index]
        assert abs(th - tw * spec['height'] / spec['width']) <= 1
        for other in (*body, *ornaments[:index]):
            dx = abs(x - other['x'])
            assert (min(dx, width - dx) >= (part['planned_width'] + other['planned_width']) / 2 + 2 - 1e-6
                    or abs(y - other['y']) >= (part['planned_height'] + other['planned_height']) / 2 + 2 - 1e-6)
        if mode in ('split', 'panels'):
            zone = width // (2 if mode == 'split' else 3)
            assert right - left == zone and left % zone == 0
        if mode == 'stacked':
            assert top == height // 2 or bottom == height // 2
        if mode == 'ends_open':
            left_end, right_end = sorted(body, key=lambda p: p['x'])
            assert (right <= left_end['x'] + left_end['planned_width'] / 2 or
                    left >= right_end['x'] - right_end['planned_width'] / 2)
        if mode == 'bordered':
            assert top >= height * .20 and bottom <= height * .80


def test_ornaments_do_not_fill_a_missing_primary_slot():
    roles = {'slot-round': 'decoration', 'slot-wide': 'decoration'}
    with pytest.raises(ValueError, match='主体'):
        layout.resolve(snapshot('single', ['round', 'wide'], roles), specs=ORNAMENT)
    for mode in ('split', 'stacked'):
        with pytest.raises(ValueError, match='至少选择两个'):
            layout.resolve(snapshot(mode, ['first', 'round'], roles={'slot-round': 'decoration'}),
                           specs=[MAIN[0], ORNAMENT[0]])


def test_extreme_aspect_reports_no_safe_fit_instead_of_dropping_or_distorting():
    value = snapshot('fullwidth', ['first', 'thin'], {'slot-thin': 'decoration'})
    with pytest.raises(ValueError, match='没有足够空间完整放置装饰.*疏朗'):
        layout.resolve(value, specs=[MAIN[0], dict(width=10000, height=1)])


def test_dense_twelve_assets_retain_each_decoration_once():
    accents = [f'acc-{i}' for i in range(10)]
    value = snapshot('stacked', ['first', 'second', *accents],
                     {'slot-' + asset: 'decoration' for asset in accents}, density='rich')
    specs = [*MAIN, *[dict(width=120 + i * 10, height=160 - i * 9) for i in range(10)]]
    resolved = layout.resolve(value, specs=specs)
    decorations = [p for p in layout.plan(resolved) if p['role'] == 'decoration']
    assert [value['asset_refs'][p['asset_index']] for p in decorations] == accents
    assert all(max(p['target_width'], p['target_height']) >= 10 for p in decorations)
    assert {p['region'][1] == 260 for p in decorations} == {False, True}


@pytest.mark.parametrize('mode,original_role', [('scene', 'accent'), ('bordered', 'border')])
def test_surrounding_decorations_coexist_with_original_role(mode, original_role):
    value = snapshot(mode, ['first', 'second', 'round'],
                     {'slot-second': original_role, 'slot-round': 'decoration'})
    resolved = layout.resolve(value, specs=[*MAIN, ORNAMENT[0]])
    placements = layout.plan(resolved)
    assert {p['role'] for p in placements if p['asset_index'] == 1} == (
        {'top-border', 'bottom-border'} if mode == 'bordered' else {'accent'})
    assert [p['role'] for p in placements if p['asset_index'] == 2] == ['decoration']


def test_saved_decoration_mapping_is_bound_and_rejects_tampering():
    saved = layout.resolve(snapshot('grid', ['first', 'round'], {'slot-round': 'decoration'}),
                           specs=[MAIN[0], ORNAMENT[0]])
    modified = deepcopy(saved)
    modified['pattern_roles'].pop('slot-round')
    with pytest.raises(ValueError, match='保存的排法'):
        layout.plan(modified)
    modified = deepcopy(saved)
    modified['asset_refs'][1] = 'another'
    with pytest.raises(ValueError, match='保存的排法'):
        layout.plan(modified)


def test_actual_render_preserves_source_and_paints_distinct_decoration(tmp_path):
    assets = {}
    for name, size, color in [('first', (120, 180), '#d84444'), ('round', (100, 100), '#213cb9'),
                              ('background', (64, 64), '#f7f6f3')]:
        assets[name] = tmp_path / f'{name}.png'
        with Image.new('RGB', size, color) as im:
            im.save(assets[name])
    initial = {key: path.read_bytes() for key, path in assets.items()}
    value = snapshot('fullwidth', ['first', 'round'], {'slot-round': 'decoration'})
    resolved = pipeline.resolve(value, assets.__getitem__)
    master, preview = tmp_path / 'master.png', tmp_path / 'preview.png'
    composed = pipeline.compose(resolved, assets.__getitem__, master, preview)
    digest = sha256(master.read_bytes()).hexdigest()
    resolved['loop'] = {**composed['loop'], 'output_sha256': digest}
    pipeline.validate_binding(resolved, digest)
    with Image.open(preview) as image:
        assert image.format == 'PNG'
        image.verify()
    with Image.open(master) as image:
        for part in layout.plan(resolved):
            expected = (33, 60, 185) if part['role'] == 'decoration' else (216, 68, 68)
            assert image.getpixel((math.floor(part['x']), math.floor(part['y'])))[:3] == expected
    assert all(path.read_bytes() == initial[key] for key, path in assets.items())
