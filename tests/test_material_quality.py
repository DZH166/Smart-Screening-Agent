"""Generated controls; these never stand in for independent business labels."""
from io import BytesIO

from PIL import Image, ImageDraw
import pytest

from hsd_tool.material_quality import quality_hook


def png(image):
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def design():
    image = Image.new("RGBA", (160, 120))
    ImageDraw.Draw(image).ellipse((20, 20, 140, 100), fill=(180, 30, 55, 255))
    return image


BOX = {"x": 0, "y": 0, "width": 160, "height": 120}


def test_unchanged_single_transparent_design_has_independent_pixel_evidence():
    data = png(design())
    result = quality_hook(data, data, BOX)
    assert not result["auto_ready"]
    assert result["evidence"]["pixel_fidelity_verified"]
    assert result["evidence"]["basis"] == "unchanged_single_transparent_design"


@pytest.mark.parametrize("change", ["color", "missing", "added", "alpha", "text"])
def test_small_meaningful_changes_do_not_pass(change):
    source = design()
    layer = source.copy()
    d = ImageDraw.Draw(layer)
    if change == "color":
        d.rectangle((70, 50, 73, 54), fill=(30, 180, 55, 255))
    elif change == "missing":
        d.rectangle((70, 50, 73, 54), fill=(0, 0, 0, 0))
    elif change == "added":
        d.rectangle((4, 5, 7, 9), fill=(180, 30, 55, 255))
    elif change == "alpha":
        layer.putpixel((80, 60), (180, 30, 55, 254))
    else:
        d.text((45, 45), "X", fill="white")
    assert not quality_hook(png(source), png(layer), BOX)["auto_ready"]


def test_detached_design_text_and_parts_need_grouping_review():
    source = design()
    ImageDraw.Draw(source).rectangle((1, 1, 7, 5), fill="red")
    assert not quality_hook(png(source), png(source), BOX)["auto_ready"]


def test_connected_shared_board_is_not_proof_of_one_complete_design():
    source = Image.new("RGBA", (160, 120))
    draw = ImageDraw.Draw(source)
    draw.rectangle((10, 10, 150, 110), fill="green")
    draw.ellipse((15, 20, 60, 70), fill="red")
    draw.ellipse((90, 20, 135, 70), fill="blue")
    result = quality_hook(png(source), png(source), BOX)
    assert result["evidence"]["pixel_fidelity_verified"]
    assert not result["auto_ready"]  # Two separate designs can be connected.


@pytest.mark.parametrize("change", ["opaque", "size", "partial", "repair", "empty", "damaged", "bounds"])
def test_unproved_geometry_repair_and_unreadable_inputs_stay_review(change):
    source = design()
    layer = source.copy()
    bounds = dict(BOX)
    if change == "opaque":
        source = source.convert("RGB")
    if change == "size":
        layer = layer.resize((320, 240))
    if change == "partial":
        bounds["width"] = 150
    if change == "bounds":
        bounds["x"] = float("nan")
    if change == "empty":
        source = layer = Image.new("RGBA", source.size)
    result = quality_hook(b"broken" if change == "damaged" else png(source), png(layer), bounds,
                          corrected=change == "repair")
    assert not result["auto_ready"]
    assert result["warnings"]
