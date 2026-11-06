"""Named design presets.

A preset only writes values the engine already understands (params, density,
background tone and per-slot scale). It deliberately does not change geometry:
existing works, saved snapshots and the merge with other layout work stay
untouched, and every preset stays reproducible from its own fields.

`classic` is the no-op preset so older clients and existing works keep the
current look.
"""

from __future__ import annotations

STYLES = {
    "classic": dict(
        label="经典等距",
        hint="保持原有节奏，不改变任何参数",
        density=None,
        params={},
        tone=None,
        scale=None,
    ),
    "airy": dict(
        label="留白高级",
        hint="图案略小、间距拉开、底纹压淡，适合简洁礼盒",
        density="airy",
        params={"spacing": 1.3, "scale": 0.92},
        tone="quiet",
        scale=1.0,
    ),
    "hierarchy": dict(
        label="主辅层级",
        hint="第一个图案做主图放大，其余缩小作辅图",
        density="balanced",
        params={"spacing": 1.08},
        tone="quiet",
        scale=(1.24, 0.78),
    ),
    "rhythm": dict(
        label="大小节奏",
        hint="图案按大小交替，重复后形成节奏而不是墙纸",
        density="balanced",
        params={"spacing": 1.0},
        tone="quiet",
        scale=(1.0, 0.8),
    ),
    "festive": dict(
        label="热闹饱满",
        hint="图案更大、间距更紧，适合节庆主题",
        density="rich",
        params={"spacing": 0.82, "scale": 1.06},
        tone="original",
        scale=None,
    ),
}

# Bounds copied from the refine contract; presets never exceed them.
SCALE_RANGE = (0.2, 2.5)


def public():
    return [
        dict(id=key, label=value["label"], hint=value["hint"])
        for key, value in STYLES.items()
    ]


PARAM_DEFAULTS = dict(scale=1.0, spacing=1.0, rotation=0.0, offset_x=0.0, offset_y=0.0, background_color=None)


def expand(style_id, slots, params, density, tone, *, density_given=False, tone_given=False):
    """Return (style_id, params, density, tone, slot_params) for a new work.

    The client always sends a full params object, so "not chosen" is expressed
    as the engine default. A preset fills those defaults and never overrides a
    value the employee actually changed. A missing or unknown id is `classic`.
    """
    style = STYLES.get(style_id) if isinstance(style_id, str) else None
    if style is None:
        return "classic", dict(params), density, tone, {}
    merged = dict(params)
    for key, value in style["params"].items():
        if key not in merged or merged[key] == PARAM_DEFAULTS.get(key):
            merged[key] = value
    merged["scale"] = _clamp(merged.get("scale", 1.0))
    merged["spacing"] = _clamp(merged.get("spacing", 1.0))
    slot_params = {}
    scale = style["scale"]
    if scale is not None and slots:
        hero, support = scale if isinstance(scale, tuple) else (scale, scale)
        for index, slot in enumerate(slots):
            factor = hero if index == 0 else support
            if abs(factor - 1.0) > 1e-9:
                slot_params[slot] = {"scale": _clamp(factor)}
    return (
        style_id,
        merged,
        density if density_given else (style["density"] or density),
        tone if tone_given else (style["tone"] or tone),
        slot_params,
    )


def _clamp(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    low, high = SCALE_RANGE
    return max(low, min(high, number))
