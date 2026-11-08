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
from .image_budget import IMAGE_BUDGET, image_workspace_bytes
from .cancellation import check


# Keep the existing source-pixel range. Differences are calculated in fixed
# tiles; only the uint8 foreground and native connectivity map span the canvas.
MAX_DIAGNOSTIC_PIXELS = 36_000_000
DIAGNOSTIC_TILE = (1024, 128)


class _DiagnosticWorkspaceLimit(ValueError):
    pass


def _read(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= 30 * 1024 * 1024:
        raise ValueError("invalid pixels")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG", "WEBP"]) as image:
            if (image.format not in {"PNG", "JPEG", "WEBP"}
                    or getattr(image, "n_frames", 1) != 1
                    or image.width * image.height > 36_000_000):
                raise ValueError("invalid pixels")
            if image.width * image.height > MAX_DIAGNOSTIC_PIXELS:
                raise _DiagnosticWorkspaceLimit()
            image.load()
            return image.convert("RGBA")


def quality_hook(source_png: bytes, layer_png: bytes, bounds: dict, *, corrected=False) -> dict:
    with IMAGE_BUDGET.reserve(check_cancel=check):
        return _quality_hook(source_png, layer_png, bounds, corrected=corrected)


def _quality_hook(source_png: bytes, layer_png: bytes, bounds: dict, *, corrected=False) -> dict:
    result = {"auto_ready": False, "warnings": [], "evidence": {
        "version": "material-pixel-fidelity-1", "scope": "pixel_fidelity_only"}}
    notes, evidence = result["warnings"], result["evidence"]
    source = layer = None
    try:
        source = _read(source_png)
        layer = _read(layer_png)
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
        with source.getchannel("A") as alpha:
            opaque_source = alpha.getextrema()[0] == 255
        if opaque_source:
            notes.append("原图没有透明底，文字、去背景和修补效果需要确认。")
            return result
        # Limit automatic proof to original pixels. Re-sampling may hide a
        # replaced small glyph or missing decoration; no broad similarity gate.
        if source.size != layer.size:
            notes.append("模型改变了图片尺寸，细节保真仍需确认。")
            return result
        foreground = np.empty((height, width), dtype=np.uint8)
        alpha_error = color_error = 0
        tile_width, tile_height = DIAGNOSTIC_TILE
        for y in range(0, height, tile_height):
            for x in range(0, width, tile_width):
                check()
                box = (x, y, min(width, x + tile_width), min(height, y + tile_height))
                with source.crop(box) as source_tile, layer.crop(box) as layer_tile:
                    a, b = np.asarray(source_tile), np.asarray(layer_tile)
                    foreground[y:box[3], x:box[2]] = a[:, :, 3] > 8
                    alpha_error = max(alpha_error, int(np.abs(a[:, :, 3].astype(np.int16) - b[:, :, 3].astype(np.int16)).max()))
                    visible = (a[:, :, 3] > 0) | (b[:, :, 3] > 0)
                    if visible.any():
                        difference = np.abs(a[:, :, :3].astype(np.int16) - b[:, :, :3].astype(np.int16))
                        color_error = max(color_error, int(difference[visible].max()))
        if not foreground.any():
            notes.append("原图没有可验证的有效图案。")
            return result
        count, labels, stats, centres = cv2.connectedComponentsWithStats(foreground, connectivity=8)
        del labels, centres
        # A detached letter or ornament is meaningful: even small separate
        # islands prevent claiming locally verified design grouping.
        significant = int(np.count_nonzero(stats[1:, cv2.CC_STAT_AREA] >= 4))
        evidence.update(alpha_max_error=alpha_error, color_max_error=color_error,
                        visible_components=significant, source_size=list(source.size),
                        output_size=list(layer.size), full_canvas=True)
        if significant != 1:
            notes.append("图案包含分离的文字或装饰，完整分组需要确认。")
        if alpha_error or color_error:
            notes.append("模型输出与原始可见像素有变化，需要确认颜色和细节。")
        evidence["pixel_fidelity_verified"] = not notes
        if evidence["pixel_fidelity_verified"]:
            evidence["basis"] = "unchanged_single_transparent_design"
            notes.append("像素保留一致，但完整设计分组尚未独立验证，需要确认。")
        return result
    except _DiagnosticWorkspaceLimit:
        evidence.update(pixel_fidelity_verified=False, diagnostic_complete=False,
                        diagnostic_limit="component_workspace")
        notes.append("图片较大，未执行完整像素核对，请自行检查文字、颜色和完整性。")
        return result
    except (OSError, ValueError, TypeError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, cv2.error):
        notes.append("图片或位置数据无法完整核验，需要人工确认。")
        return result
    finally:
        if source is not None:
            source.close()
        if layer is not None:
            layer.close()


def native_edge_diagnostics(layer_png: bytes) -> dict:
    """Cheap local check for a returned native layer; never changes pixels.

    A white pasteboard border around a transparent design is the most common
    visible defect of image-model extraction. We only measure it so the employee
    can be told to look; nothing is cropped, eroded or re-generated here.
    """
    result = {"white_edge_ratio": None, "opaque_ratio": None, "warnings": []}
    try:
        with Image.open(io.BytesIO(layer_png), formats=["PNG"]) as image:
            if (image.format != "PNG" or getattr(image, "n_frames", 1) != 1
                    or image.width * image.height > 36_000_000):
                return result
            with IMAGE_BUDGET.reserve(image_workspace_bytes(image.width * image.height)):
                with image.convert("RGBA") as rgba:
                    work = rgba.copy()
                    try:
                        work.thumbnail((512, 512), Image.Resampling.LANCZOS)
                    except BaseException:
                        work.close()
                        raise
    except (OSError, ValueError, Image.DecompressionBombError):
        return result
    with work:
        with work.getchannel("A") as channel:
            alpha = np.asarray(channel)
        with work.convert("RGB") as colors:
            rgb = np.asarray(colors, dtype=np.int16)
    foreground = alpha > 8
    if not foreground.any():
        return result
    # Pixels on the foreground boundary: foreground touching transparency.
    kernel = np.ones((3, 3), np.uint8)
    eroded = cv2.erode(foreground.astype(np.uint8), kernel) > 0
    boundary = foreground & ~eroded
    if not boundary.any():
        return result
    near_white = (rgb[:, :, 0] > 232) & (rgb[:, :, 1] > 232) & (rgb[:, :, 2] > 232)
    near_white &= (rgb.max(axis=2) - rgb.min(axis=2)) < 14
    result["white_edge_ratio"] = round(float((boundary & near_white).sum()) / float(boundary.sum()), 4)
    result["opaque_ratio"] = round(float((alpha >= 250).sum()) / float(foreground.sum()), 4)
    if result["white_edge_ratio"] >= 0.03:
        result["warnings"].append(
            "这个设计的边缘有一圈偏白的像素，可能有白色贴边；请对照原图，必要时重新框选补提。")
    return result
