"""Conservative, local pixel checks, independent of model confidence.

This is not a production-quality classifier. Even unchanged connected pixels
cannot prove that a sheet contains just one complete design: two designs can
share a board. Pixel evidence is recorded, but the unvalidated grouping path
does not grant automatic acceptance. Repairs and inferred detail need a person.
"""
from __future__ import annotations

import io
import math
import warnings

import cv2
import numpy as np
from PIL import Image


def _read(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= 30 * 1024 * 1024:
        raise ValueError("invalid pixels")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            if (image.format not in {"PNG", "JPEG", "WEBP"}
                    or getattr(image, "n_frames", 1) != 1
                    or image.width * image.height > 36_000_000):
                raise ValueError("invalid pixels")
            image.load()
            return image.convert("RGBA")


def quality_hook(source_png: bytes, layer_png: bytes, bounds: dict, *, corrected=False) -> dict:
    result = {"auto_ready": False, "warnings": [], "evidence": {
        "version": "material-pixel-fidelity-1", "scope": "pixel_fidelity_only"}}
    notes, evidence = result["warnings"], result["evidence"]
    try:
        source, layer = _read(source_png), _read(layer_png)
        width, height = source.size
        if (not isinstance(bounds, dict) or set(bounds) != {"x", "y", "width", "height"}
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds.values())
                or bounds["x"] < 0 or bounds["y"] < 0 or bounds["width"] <= 0 or bounds["height"] <= 0
                or bounds["x"] + bounds["width"] > width or bounds["y"] + bounds["height"] > height):
            raise ValueError("invalid bounds")
        if corrected:
            notes.append("修补或重做过的内容需要人工确认。")
            return result
        if any(abs(bounds[k] - v) > 0.001 for k, v in {
                "x": 0, "y": 0, "width": width, "height": height}.items()):
            notes.append("局部设计的完整范围尚需人工确认。")
            return result
        if source.getchannel("A").getextrema()[0] == 255:
            notes.append("原图没有透明底，文字、去背景和修补效果需要确认。")
            return result
        # Limit automatic proof to original pixels. Re-sampling may hide a
        # replaced small glyph or missing decoration; no broad similarity gate.
        if source.size != layer.size:
            notes.append("模型改变了图片尺寸，细节保真仍需确认。")
            return result
        a, b = np.asarray(source, dtype=np.int16), np.asarray(layer, dtype=np.int16)
        foreground = a[:, :, 3] > 8
        if not foreground.any():
            notes.append("原图没有可验证的有效图案。")
            return result
        visible = (a[:, :, 3] > 0) | (b[:, :, 3] > 0)
        alpha_error = int(np.abs(a[:, :, 3] - b[:, :, 3]).max())
        color_error = int(np.abs(a[:, :, :3][visible] - b[:, :, :3][visible]).max())
        count, _, stats, _ = cv2.connectedComponentsWithStats(foreground.astype(np.uint8), connectivity=8)
        areas = sorted((int(v) for v in stats[1:, cv2.CC_STAT_AREA]), reverse=True)
        # A detached letter or ornament is meaningful: even small separate
        # islands prevent claiming locally verified design grouping.
        significant = [v for v in areas if v >= 4]
        evidence.update(alpha_max_error=alpha_error, color_max_error=color_error,
                        visible_components=len(significant), source_size=list(source.size),
                        output_size=list(layer.size), full_canvas=True)
        if len(significant) != 1:
            notes.append("图案包含分离的文字或装饰，完整分组需要确认。")
        if alpha_error or color_error:
            notes.append("模型输出与原始可见像素有变化，需要确认颜色和细节。")
        evidence["pixel_fidelity_verified"] = not notes
        if evidence["pixel_fidelity_verified"]:
            evidence["basis"] = "unchanged_single_transparent_design"
            notes.append("像素保留一致，但完整设计分组尚未独立验证，需要确认。")
        return result
    except (OSError, ValueError, TypeError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, cv2.error):
        notes.append("图片或位置数据无法完整核验，需要人工确认。")
        return result
