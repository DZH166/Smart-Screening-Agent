from copy import deepcopy
import hashlib
from pathlib import Path

from PIL import Image
import pytest

from ribbon_backend.imaging import MODES, PARAM_DEFAULTS, render, seed_assets, template_thumbnail, validate_image


# Captured from the original eager renderer before the memory change. Synthetic
# seed artwork, overlapping motifs, rotation and edge wrapping; no business data.
ORIGINAL_RGBA_HASHES = {
    'grid': '0c604cf87e4d8d759a476f42cc77504dc54c0d1122cc930fb78d4f27c0638272',
    'stagger': 'c73b7659bf3310340b5f99dfaa28233d9f725d143748c82b8162836c4b6d4f57',
    'scatter': 'fae7e20e505f740aae278331cb8322aff5eab989f332146939ea15cc197c4e36',
    'single': '82923809b8bf5938d24f82a1b24aa6a56a9f86982ea421c4298449bd481bb13c',
    'ends': '3980bc9bea7f17f832eee61f766d6fa36872d90691c703edfd43cf8407718d45',
    'panels': 'd62a84e5e2740ef570fec99f8a21d892bfb88f7873a7bfe4f89278ef01fad365',
}


@pytest.fixture
def scene(tmp_path):
    assets = seed_assets(tmp_path / "assets")
    refs = {a["id"]: Path(a["path"]) for a in assets}
    snapshot = {"schema_version": 1, "asset_refs": ["demo-flower", "demo-star", "demo-ring"],
                "background_ref": "demo-bg-sage", "template_mode": "stagger", "template_rules": {},
                "params": dict(PARAM_DEFAULTS), "seed": 1729,
                "output_profile": {"width": 1800, "height": 400, "dpi": 144, "format": "PNG", "is_demo": True}}
    return snapshot, refs


@pytest.mark.parametrize('mode', MODES)
def test_memory_bounded_renderer_preserves_original_pixels(scene, tmp_path, mode):
    snapshot, refs = scene
    snapshot['template_mode'] = mode
    snapshot['params'].update(scale=1.9, spacing=.6, rotation=31, offset_x=-17, offset_y=9)
    master = tmp_path / f'{mode}-bounded.png'
    result = render(snapshot, refs.__getitem__, master, tmp_path / 'preview.png')
    with Image.open(master) as image:
        assert hashlib.sha256(image.tobytes()).hexdigest() == ORIGINAL_RGBA_HASHES[mode]
    assert [row['layer'] for row in result['object_transforms']] == list(range(len(result['object_transforms'])))
    assert not list(tmp_path.glob('ribbon-motifs-*'))


def test_only_one_full_size_pattern_remains_decoded(scene, tmp_path, monkeypatch):
    from ribbon_backend import imaging
    snapshot, refs = scene
    paths = {refs[key] for key in snapshot['asset_refs']}
    actual = imaging.read_image
    held_originals = []

    def observe(path):
        if path in paths:
            for original in held_originals:
                with pytest.raises(ValueError):
                    original.getpixel((0, 0))  # Earlier raw pattern must be closed.
        image = actual(path)
        if path in paths:
            held_originals.append(image)
        return image

    monkeypatch.setattr(imaging, 'read_image', observe)
    render(snapshot, refs.__getitem__, tmp_path / 'master.png', tmp_path / 'preview.png')
    assert len(held_originals) == len(snapshot['asset_refs'])
    for original in held_originals:
        with pytest.raises(ValueError):
            original.getpixel((0, 0))


def test_standalone_render_checks_free_space_before_output(scene, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from ribbon_backend import imaging
    snapshot, refs = scene
    monkeypatch.setattr(imaging.shutil, 'disk_usage', lambda directory: SimpleNamespace(free=1))
    with pytest.raises(OSError, match='空间'):
        render(snapshot, refs.__getitem__, tmp_path/'denied.png', tmp_path/'preview.png')
    assert not (tmp_path/'denied.png').exists()
    assert not list(tmp_path.glob('ribbon-motifs-*'))


def test_all_six_modes_are_distinct_decodable_and_keep_input_bytes(scene, tmp_path):
    snapshot, refs = scene
    input_hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in refs.items()}
    hashes = []
    for mode in MODES:
        snapshot["template_mode"] = mode
        master, preview = tmp_path/f"{mode}.png", tmp_path/f"{mode}-preview.png"
        metadata = render(snapshot, refs.__getitem__, master, preview)
        hashes.append(metadata["sha256"])
        assert metadata["object_transforms"]
        assert set(item["asset_ref"] for item in metadata["object_transforms"]) == set(snapshot["asset_refs"])
        assert validate_image(master, snapshot["output_profile"])["width"] == 1800
        with Image.open(preview) as image:
            assert image.size == (1800, 400)
    assert len(set(hashes)) == 6
    assert input_hashes == {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in refs.items()}


def test_seed_reproduces_layout_and_params_change_real_pixels(scene, tmp_path):
    snapshot, refs = scene
    snapshot["template_mode"] = "scatter"
    first = render(snapshot, refs.__getitem__, tmp_path/"a.png", tmp_path/"ap.png")
    again = render(snapshot, refs.__getitem__, tmp_path/"b.png", tmp_path/"bp.png")
    assert first["sha256"] == again["sha256"]
    altered = deepcopy(snapshot)
    altered["params"].update(scale=.7, spacing=1.4, rotation=25, offset_x=12)
    edited = render(altered, refs.__getitem__, tmp_path/"c.png", tmp_path/"cp.png")
    assert edited["sha256"] != first["sha256"]
    assert len(edited["object_transforms"]) < len(first["object_transforms"])


def test_preview_derives_from_master_and_profile_validation(scene, tmp_path):
    snapshot, refs = scene
    snapshot["output_profile"].update(width=3600, height=800, dpi=300)
    render(snapshot, refs.__getitem__, tmp_path/"master.png", tmp_path/"preview.png")
    with Image.open(tmp_path/"master.png") as master, Image.open(tmp_path/"preview.png") as preview:
        expected = master.copy()
        expected.thumbnail((1800, 600), Image.Resampling.LANCZOS)
        assert preview.size == expected.size
        assert preview.tobytes() == expected.tobytes()
    with pytest.raises(ValueError, match="母版文件"):
        validate_image(tmp_path/"preview.png", snapshot["output_profile"])


def test_flattened_base_has_no_fake_layers_or_upscaling(scene, tmp_path):
    snapshot, refs = scene
    render(snapshot, refs.__getitem__, tmp_path/"original.png", tmp_path/"preview.png")
    refs["flat"] = tmp_path/"original.png"
    snapshot["composite_ref"] = "flat"
    result = render(snapshot, refs.__getitem__, tmp_path/"flat.png", tmp_path/"flat-preview.png")
    assert result["object_transforms"] == []
    assert result["render_kind"] == "composite"
    snapshot["params"]["scale"] = .8
    with pytest.raises(ValueError, match="独立图层"):
        render(snapshot, refs.__getitem__, tmp_path/"bad.png", tmp_path/"bad-preview.png")
    snapshot["params"] = dict(PARAM_DEFAULTS)
    snapshot["output_profile"]["width"] += 100
    with pytest.raises(ValueError, match="不能把低分辨率"):
        render(snapshot, refs.__getitem__, tmp_path/"bad.png", tmp_path/"bad-preview.png")


def test_thumbnails_exist_for_every_mode(tmp_path):
    for mode in MODES:
        path = tmp_path/f"{mode}.png"
        template_thumbnail(mode, path)
        with Image.open(path) as image:
            image.verify()
            assert image.size == (640, 200)


def test_tiny_background_tile_preserves_color_without_unbounded_paste_loop(scene, tmp_path):
    snapshot, refs = scene
    path = tmp_path/"tiny.png"
    Image.new("RGBA", (1, 1), "#123456").save(path)
    refs["tiny"] = path
    snapshot["background_ref"] = "tiny"
    render(snapshot, refs.__getitem__, tmp_path/"tiny-master.png", tmp_path/"tiny-preview.png")
    with Image.open(tmp_path/"tiny-master.png") as im:
        assert im.getpixel((0, 0)) == (18, 52, 86, 255)


def test_custom_template_rules_are_reflected_in_thumbnail(tmp_path):
    template_thumbnail("grid", tmp_path/"normal.png")
    template_thumbnail("grid", tmp_path/"custom.png", {"rows": 3, "motif_ratio": .15})
    assert (tmp_path/"normal.png").read_bytes() != (tmp_path/"custom.png").read_bytes()
