"""Per-design regeneration with a server-controlled frame.

DeepSeek locates every complete design on the uploaded sheet; each design is
then regenerated from its own padded crop, so a whole figure survives the trip
and the full pixel budget goes to one design instead of the whole sheet.

The final frame is never delegated to the model.  The server removes the plain
background, drops leftover neighbour fragments and adds one uniform margin, so
every result gets the same border instead of "sometimes too much, sometimes
cut off".  Generated pixels remain proposals: text, colour and detail can
change, and an employee has to confirm each item.

Upstream concurrency was measured on 2026-10-25 with one key: 8 calls returned
in 23.0 s, 10 in 27.1 s, 16 in 34.3 s with one failed response.  Past eight the
queue grows without a meaningful throughput gain, so the pool stays at eight.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import threading
import uuid

import cv2
import numpy as np
from PIL import Image

from .ai_usage import empty_usage, merge_usage
from .material_ark import (ArkCancelled, ArkLayer, ArkMaterialProvider, ArkProviderError,
                           ArkResult, _cancelled, _decode, _encode)
from .material_locate import DeepSeekMaterialLocator

DEFAULT_WORKERS = 8
MAX_WORKERS = 8
PAD_RATIO = .12
MIN_PAD = 6
MARGIN_RATIO = .035
MIN_MARGIN = 4
WHITE_LEVEL = 246
NEUTRAL_SPREAD = 6
EDGE_PIXELS = 2

DESIGN_NOTE = (
    "只保留画面中间这一个完整设计：完整保留人物、文字、装饰和内部底板，"
    "画面里其他图案和文字都是杂质，请全部去掉。"
    "背景改为纯白色，不要画棋盘格、不要添加边框或其他底板。"
    "完整保留在画面中央，四周自然留出约 8% 空白，不要裁切人物、饰物或文字。"
    "清除覆盖在设计上的斜向半透明外加水印，保持原有文字、配色和平面印刷风格，"
    "不要做成刺绣、毛线或油画质感，不要增删图案。"
)


def pad_box(box, size, *, ratio=PAD_RATIO):
    """Grow a design box so the whole figure survives the regeneration.

    A box that is slightly too small loses pixels nobody can recover; a box
    that is slightly too large only brings in neighbouring artwork, which the
    model is told to drop and the server then trims away.
    """
    if (not isinstance(box, (list, tuple)) or len(box) != 4
            or any(type(value) is not int for value in box)):
        raise ArkProviderError("invalid_decision", "设计范围无效，请重新框选后重试。")
    width, height = size
    left, top, right, bottom = box
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ArkProviderError("invalid_decision", "设计范围超出图片，请重新框选后重试。")
    pad = max(MIN_PAD, round(min(right - left, bottom - top) * ratio))
    return (max(0, left - pad), max(0, top - pad), min(width, right + pad), min(height, bottom + pad))


def remove_plain_background(image):
    """Make near-white background pixels truly transparent.

    The model often paints a checkerboard or a plain card instead of returning
    alpha.  Asking for pure white is the reliable request, and this local pass
    is what actually removes it.  Only background connected to the border is
    cleared, so enclosed white artwork survives.
    """
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    lowest = rgb.min(axis=2)
    mask = ((lowest >= WHITE_LEVEL) & (rgb.max(axis=2) - lowest <= NEUTRAL_SPREAD)).astype(np.uint8)
    plain = bool(mask.mean() >= .02)
    if not mask.any():
        return image.convert("RGBA"), plain
    _, labels = cv2.connectedComponents(mask, connectivity=4)
    border = np.unique(np.concatenate((labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1])))
    background = np.isin(labels, border[border != 0])
    alpha = np.where(background, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack((rgb.astype(np.uint8), alpha)), "RGBA"), plain


def trim_design(image, *, margin_ratio=MARGIN_RATIO):
    """Return the framed PNG and the notes an employee needs to see."""
    framed, plain = remove_plain_background(image)
    alpha = np.asarray(framed.getchannel("A"))
    solid = alpha > 0
    height, width = solid.shape
    core = max(2, round(min(width, height) * .10))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(solid.astype(np.uint8), connectivity=8)
    kept, dropped = [], 0
    for index in range(1, count):
        x, y, w, h, area = (int(value) for value in stats[index])
        # A leftover neighbour fragment sits at the frame edge and never reaches
        # the middle.  A real design, even a small one, is centred by the note.
        central = x + w > core and y + h > core and x < width - core and y < height - core
        if not central and area < width * height * .02:
            dropped += 1
            continue
        kept.append(index)
    if not kept:
        raise ArkProviderError("empty_crop", "素材没有可保留的内容，请重新框选后重做。")
    keep = np.isin(labels, kept)
    rows, columns = np.where(keep)
    box = (int(columns.min()), int(rows.min()), int(columns.max()) + 1, int(rows.max()) + 1)
    notes = []
    if not plain:
        notes.append("背景没有清理干净，可能残留底色，请确认后再使用。")
    if box[0] <= EDGE_PIXELS or box[1] <= EDGE_PIXELS or box[2] >= width - EDGE_PIXELS or box[3] >= height - EDGE_PIXELS:
        notes.append("设计可能被裁切（内容触及画面边缘），请仔细核对。")
    if (box[2] - box[0]) * (box[3] - box[1]) < width * height * .15:
        notes.append("设计在画面中占比偏小，建议重新框选后重做。")
    if dropped:
        notes.append("已去掉 %d 处边缘杂块。" % dropped)
    notes.append("模型重新绘制了这张设计，文字、配色和细节可能和原图不同，请确认。")
    content = framed.crop(box)
    margin = max(MIN_MARGIN, round(max(content.size) * margin_ratio))
    canvas = Image.new("RGBA", (content.width + margin * 2, content.height + margin * 2), (0, 0, 0, 0))
    canvas.paste(content, (margin, margin))
    return _encode(canvas), notes


class MaterialDesignProvider:
    """Locate once, then regenerate one design per call, eight at a time."""

    supports_progress = True
    no_upscale = True

    def __init__(self, config, ai_settings, *, key_pool=None, ark=None, locator=None,
                 workers=DEFAULT_WORKERS):
        self.ark = ark or ArkMaterialProvider(config["ark_key"], config["model_id"])
        self.locator = locator or DeepSeekMaterialLocator(ai_settings, key_pool=key_pool)
        self.workers = max(1, min(MAX_WORKERS, int(workers)))

    def _note(self, instructions):
        text = DESIGN_NOTE
        extra = (instructions or "").strip()
        if extra:
            text = text + "补充要求：" + extra
        return text[:1000]

    def extract(self, image_bytes, *, instructions="", check_cancel=None, on_progress=None, on_attempt=None):
        return self._run(image_bytes, instructions, check_cancel, on_progress, on_attempt, edit=False, bounds=None)

    def edit(self, image_bytes, *, instructions, bounds=None, check_cancel=None, on_progress=None, on_attempt=None):
        return self._run(image_bytes, instructions, check_cancel, on_progress, on_attempt, edit=True, bounds=bounds)

    def _run(self, raw, instructions, check_cancel, on_progress, on_attempt, *, edit, bounds):
        attempts, lock = [], threading.Lock()
        provider_usage = {"seedream": {}, "deepseek": empty_usage()}

        def progress(code, message="", **extra):
            if on_progress:
                on_progress(code, message, **extra)

        def cancel():
            if _cancelled(check_cancel):
                raise ArkCancelled()

        def publish(attempt):
            with lock:
                attempts.append(attempt)
            if on_attempt:
                on_attempt({**attempt, "usage": dict(attempt["usage"])})

        def aggregate(provider, values):
            if provider == "deepseek":
                merge_usage(provider_usage[provider], values)
            else:
                for key, value in values.items():
                    if type(value) is int and value >= 0:
                        provider_usage[provider][key] = provider_usage[provider].get(key, 0) + value

        def call(provider, operation, invoke):
            attempt = {"id": uuid.uuid4().hex, "provider": provider, "operation": operation,
                       "number": 1, "state": "submitted", "usage": {}, "request_id": "",
                       "settled": False, "code": ""}
            publish(attempt)
            try:
                result = invoke()
            except (ArkProviderError, ArkCancelled) as error:
                attempt.update(state=("cancelled" if isinstance(error, ArkCancelled) else
                                      ("failed" if error.settled else "unknown")),
                               usage=dict(error.usage), request_id=error.request_id,
                               settled=error.settled, code=error.code)
                aggregate(provider, attempt["usage"])
                publish(attempt)
                raise
            except Exception:
                # A transport failure after dispatch proves nothing about billing.
                attempt.update(state="unknown", settled=False, code="submission_unknown")
                publish(attempt)
                raise ArkProviderError("submission_unknown", "服务返回异常，结果尚未确认，未自动重发。",
                                       settled=False) from None
            attempt.update(state="returned", usage=dict(result.usage), request_id=result.request_id, settled=True)
            aggregate(provider, attempt["usage"])
            publish(attempt)
            return result

        try:
            progress("preparing", "正在检查图片和服务设置。")
            cancel()
            source = _decode(raw)
            self.locator.available()
            if edit:
                progress("cleanup", "正在按标记位置重新生成素材。")
                cleaned = call("seedream", "edit", lambda: self.ark.clean(
                    raw, instructions=self._note(instructions), bounds=bounds, check_cancel=check_cancel))
                cancel()
                png, notes = trim_design(_decode(cleaned.layers[0].png, output=True))
                layer = ArkLayer(png, "修改后的素材", "", {"x": 0, "y": 0,
                                  "width": source.width, "height": source.height}, 1, tuple(notes))
                progress("saving")
                return ArkResult((layer,), provider_usage["seedream"],
                                 tuple(dict.fromkeys(cleaned.warnings + tuple(notes))),
                                 b"", source.size, cleaned.request_id, tuple(attempts), provider_usage, True, True)

            # A watermarked collage cannot be located reliably: the sheet-wide
            # watermark makes the model return duplicate or out-of-range boxes.
            # One whole-sheet pass fixes the location input; each design is
            # still regenerated from its own native crop, not from this pass.
            progress("cleanup")
            cleaned = call("seedream", "cleanup", lambda: self.ark.clean(
                raw, instructions=instructions, check_cancel=check_cancel))
            cancel()
            base = _decode(cleaned.base_png, output=True)
            progress("locate")
            located = call("deepseek", "locate", lambda: self.locator.locate(cleaned.base_png,
                                                                             check_cancel=check_cancel))
            cancel()
            designs = list(located.designs)
            if not designs:
                raise ArkProviderError("invalid_decision", "未能可靠确定设计范围，请在原图框选后重试。")
            progress("designs", "", current=0, total=len(designs))
            layers, failures = self._generate(source, base, designs, instructions, check_cancel, progress, call)
            cancel()
            if not layers:
                raise ArkProviderError("provider_failed", "本张图片的所有设计都未能生成，请重试或联系管理员。")
            notes = list(cleaned.warnings) + list(located.warnings)
            notes.extend("第 %d 个设计（%s）未能生成：%s" % (index, _label(label), _reason(error))
                         for index, label, error in failures)
            progress("saving")
            return ArkResult(tuple(layers), provider_usage["seedream"], tuple(dict.fromkeys(notes)),
                             b"", source.size, cleaned.request_id, tuple(attempts), provider_usage, True, True)
        except (ArkProviderError, ArkCancelled) as error:
            # A later failure must never replay an already charged call.
            error.safe_retry = error.retryable = False
            error.attempts = tuple(attempts)
            error.provider_usage = provider_usage
            error.usage = dict(provider_usage["seedream"])
            raise

    def _generate(self, source, base, designs, instructions, check_cancel, progress, call):
        """One native crop per design, eight regenerations in flight."""
        total = len(designs)
        note = self._note(instructions)
        layers, failures = [], []
        finished = 0
        scale_x, scale_y = source.width / base.width, source.height / base.height

        def one(index, design):
            if _cancelled(check_cancel):
                raise ArkCancelled()
            left, top, right, bottom = design.box
            bounds = {"x": max(0, math.floor(left * scale_x)), "y": max(0, math.floor(top * scale_y)),
                      "width": max(1, round((right - left) * scale_x)),
                      "height": max(1, round((bottom - top) * scale_y))}
            bounds["width"] = min(bounds["width"], source.width - bounds["x"])
            bounds["height"] = min(bounds["height"], source.height - bounds["y"])
            native = (bounds["x"], bounds["y"], bounds["x"] + bounds["width"], bounds["y"] + bounds["height"])
            crop = source.crop(pad_box(native, source.size))
            cleaned = call("seedream", "cleanup", lambda: self.ark.clean(
                _encode(crop), instructions=note, check_cancel=check_cancel))
            png, crop_notes = trim_design(_decode(cleaned.layers[0].png, output=True))
            return ArkLayer(png, design.label, "", bounds, index,
                            tuple(list(design.warnings) + crop_notes))

        with ThreadPoolExecutor(max_workers=min(self.workers, total)) as pool:
            futures = {pool.submit(one, index, design): (index, design)
                       for index, design in enumerate(designs, 1)}
            for future in as_completed(futures):
                index, design = futures[future]
                try:
                    layers.append(future.result())
                except ArkCancelled:
                    continue
                except Exception as error:
                    failures.append((index, design.label, error))
                finished += 1
                progress("designs", "", current=finished, total=total)
        layers.sort(key=lambda layer: layer.z_index)
        failures.sort()
        return layers, failures


def _label(value):
    text = "".join(char for char in str(value or "") if char.isprintable()).strip()
    return (text or "素材")[:40]


def _reason(error):
    code = str(getattr(error, "code", "")) or "processing_failed"
    return {"provider_busy": "图片服务繁忙", "rate_limit": "图片服务限流",
            "provider_failed": "图片服务未完成本次处理", "invalid_response": "返回结果不完整",
            "submission_unknown": "结果尚未确认", "content_policy": "未通过内容检查",
            "empty_crop": "没有可保留的内容", "unsupported_model": "模型不支持"}.get(code, "处理失败")
