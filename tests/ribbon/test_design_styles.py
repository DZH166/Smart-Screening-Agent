"""Named design presets only write existing snapshot fields."""
import pytest

from ribbon_backend.design_style import STYLES, expand, public


def test_public_catalog_lists_classic_first():
    styles = public()
    assert styles[0]["id"] == "classic" and styles[0]["label"]
    assert {row["id"] for row in styles} == set(STYLES)


def test_classic_is_a_no_op():
    params = dict(scale=1.0, spacing=1.0, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None)
    style, out, density, tone, slots = expand("classic", ["pattern-1"], params, "balanced", "original")
    assert style == "classic"
    assert out == params and density == "balanced" and tone == "original" and slots == {}


def test_hierarchy_lifts_one_hero_and_keeps_supports_smaller():
    params = dict(scale=1.0, spacing=1.0, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None)
    style, out, density, tone, slots = expand(
        "hierarchy", ["pattern-1", "pattern-2", "pattern-3"], params, "balanced", "original"
    )
    assert style == "hierarchy"
    assert slots["pattern-1"]["scale"] == pytest.approx(1.24)
    assert slots["pattern-2"]["scale"] == pytest.approx(0.78)
    assert slots["pattern-3"]["scale"] == pytest.approx(0.78)
    assert out["spacing"] == pytest.approx(1.08)
    assert tone == "quiet"


def test_explicit_values_win_over_the_preset():
    params = dict(scale=1.0, spacing=1.4, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None)
    _, out, _, _, _ = expand("airy", ["pattern-1"], params, "balanced", "original")
    assert out["spacing"] == pytest.approx(1.4)  # client asked for 1.4 first


def test_unknown_or_malformed_styles_fall_back_to_classic():
    params = dict(scale=1.0, spacing=1.0, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None)
    assert expand("nope", ["pattern-1"], params, "balanced", "original")[0] == "classic"
    assert expand(None, ["pattern-1"], params, "balanced", "original")[0] == "classic"
