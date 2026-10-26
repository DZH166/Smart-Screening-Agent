"""Per-design native extraction with the complete model canvas preserved.

DeepSeek locates complete designs after one whole-sheet cleanup. A shared whole
source reference and a target hint are sent to each native extraction, accepting one
nonempty foreground. The returned canvas and alpha are kept unchanged: no white
mask, connected-component deletion, content crop or server-added frame.
Generated pixels remain proposals; an employee must confirm each item.

Upstream concurrency was measured on 2026-10-25 with one key: 8 calls returned
in 23.0 s, 10 in 27.1 s, 16 in 34.3 s with one failed response.  Past eight the
queue grows without a meaningful throughput gain, so the pool stays at eight.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import threading
import uuid

from PIL import Image

from .ai_usage import empty_usage, merge_usage
from .material_ark import (ArkCancelled, ArkLayer, ArkMaterialProvider, ArkProviderError,
                           ArkResult, _cancelled, _decode, _encode)
from .material_locate import DeepSeekMaterialLocator

DEFAULT_WORKERS = 8
MAX_WORKERS = 8
PAD_RATIO = .12
MIN_PAD = 6
EDGE_PIXELS = 2
REFERENCE_MAX_PIXELS = 4_000_000

DESIGN_NOTE = (
    "只保留指定的这一个完整设计：人物全身、头发、裙摆、鞋子、文字、装饰及内部底板整体保留，"
    "其他图案和外加水印去掉，不要拆成零件或多个前景图层。"
    "设计外部用真实透明背景，不画白底、棋盘格或边框。"
    "四周自然留白，完整保留全部轮廓，不裁切人物、饰物和文字。"
    "保持原有文字、配色和平面印刷风格，不增删或编造图案。"
)


def pad_box(box, size, *, ratio=PAD_RATIO):
    """Grow the target hint without cutting any pixels from its whole-image context."""
    if (not isinstance(box, (list, tuple)) or len(box) != 4
            or any(type(value) is not int for value in box)):
        raise ArkProviderError("invalid_decision", "设计范围无效，请重新框选后重试。")
    width, height = size
    left, top, right, bottom = box
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ArkProviderError("invalid_decision", "设计范围超出图片，请重新框选后重试。")
    pad = max(MIN_PAD, round(min(right - left, bottom - top) * ratio))
    return (max(0, left - pad), max(0, top - pad), min(width, right + pad), min(height, bottom + pad))


def prepare_design_reference(source):
    """Encode one shared, proportionally bounded whole image, never a design crop.

    Callers reuse the bytes for all concurrent requests. Bounding the reference
    avoids decoding a 36 MP original separately in each of the eight requests.
    This downsampling only limits request resources; it does not restore detail.
    """
    image = source
    if source.width * source.height > REFERENCE_MAX_PIXELS:
        scale = math.sqrt(REFERENCE_MAX_PIXELS / (source.width * source.height))
        size = (max(2, math.floor(source.width * scale)), max(2, math.floor(source.height * scale)))
        image = source.resize(size, Image.Resampling.LANCZOS)
    return _encode(image), image.size


def design_target_bounds(box, source_size, reference_size):
    """Map an expanded target hint to the reference; the box never crops pixels."""
    left, top, right, bottom = pad_box(box, source_size)
    width, height = source_size
    ref_width, ref_height = reference_size
    x, y = math.floor(left * ref_width / width), math.floor(top * ref_height / height)
    return {"x": x, "y": y,
            "width": min(ref_width, math.ceil(right * ref_width / width)) - x,
            "height": min(ref_height, math.ceil(bottom * ref_height / height)) - y}


def preserve_design(image):
    """Read-only diagnostics; retain every returned pixel, including edge details."""
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    box = alpha.getbbox()
    if box is None:
        raise ArkProviderError("empty_crop", "图片服务返回了空白素材，请框选完整设计后重做。")
    notes = ["已保留模型返回的完整画布，系统没有裁剪或删除边缘内容。",
             "模型提取可能改变文字、配色或细节，请对照原图确认。"]
    if alpha.getextrema()[0] == 255:
        notes.append("图片服务未返回透明区域，已保留完整画布；请确认背景和设计内部底板。")
    elif (box[0] <= EDGE_PIXELS or box[1] <= EDGE_PIXELS
          or box[2] >= rgba.width - EDGE_PIXELS or box[3] >= rgba.height - EDGE_PIXELS):
        notes.append("模型返回内容触及画布边缘，可能不完整；系统未再裁剪，请核对。")
    if (box[2] - box[0]) * (box[3] - box[1]) < rgba.width * rgba.height * .15:
        notes.append("设计在画布中占比偏小，请放大核对或重新框选完整设计。")
    return _encode(rgba), notes


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
            with lock:
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
                progress("cleanup", "正在按标记位置修改素材并保留完整画布。")
                cleaned = call("seedream", "edit", lambda: self.ark.clean(
                    raw, instructions=self._note(instructions), bounds=bounds, check_cancel=check_cancel))
                cancel()
                png, notes = preserve_design(_decode(cleaned.layers[0].png, output=True))
                layer = ArkLayer(png, "修改后的素材", "", {"x": 0, "y": 0,
                                  "width": source.width, "height": source.height}, 1, tuple(notes))
                progress("saving")
                return ArkResult((layer,), provider_usage["seedream"],
                                 tuple(dict.fromkeys(cleaned.warnings + tuple(notes))),
                                 b"", source.size, cleaned.request_id, tuple(attempts), provider_usage, True, True)

            # A watermarked collage cannot be located reliably: the sheet-wide
            # watermark makes the model return duplicate or out-of-range boxes.
            # One whole-sheet pass fixes the location input; each design is
            # still extracted from the complete original context, not this pass.
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
        """One target per native extraction, sharing the complete source context."""
        total = len(designs)
        note = self._note(instructions)
        layers, failures = [], []
        finished = 0
        scale_x, scale_y = source.width / base.width, source.height / base.height
        reference_png, reference_size = prepare_design_reference(source)

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
            target = design_target_bounds(native, source.size, reference_size)
            cleaned = call("seedream", "extract_design", lambda: self.ark.extract_design(
                reference_png, bounds=target, instructions=note, check_cancel=check_cancel))
            if len(cleaned.layers) != 1:
                raise ArkProviderError("ambiguous_design", "图片服务没有返回唯一完整设计，请重新框选后重做。")
            png, crop_notes = preserve_design(_decode(cleaned.layers[0].png, output=True))
            return ArkLayer(png, design.label, "", bounds, index,
                            tuple(list(design.warnings) + list(cleaned.warnings) + crop_notes))

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
            "empty_crop": "没有可保留的内容", "empty_layer": "图片服务返回空白图层",
            "ambiguous_design": "模型将完整设计拆成多个图层，请重新框选",
            "no_designs": "图片服务未返回完整设计图层", "unsupported_model": "模型不支持"}.get(code, "处理失败")
