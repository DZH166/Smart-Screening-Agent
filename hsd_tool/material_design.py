"""Per-design native extraction with the complete model canvas preserved.

DeepSeek locates complete designs after one whole-sheet cleanup. A shared whole
source reference and a target hint are sent to each native extraction, accepting one
nonempty foreground. The returned canvas and alpha are kept unchanged: no white
mask, connected-component deletion, content crop or server-added frame.
Each design is extracted once with the HD requirements in the same request;
only an explicit employee edit submits it again. Generated pixels remain
proposals; an employee must confirm each item.

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
from .material_ark import (MAX_INPUT_BYTES, ArkCancelled, ArkLayer, ArkMaterialProvider, ArkProviderError,
                           ArkResult, _cancelled, _decode, _encode)
from .material_locate import DeepSeekMaterialLocator

DEFAULT_WORKERS = 8
MAX_WORKERS = 8
PAD_RATIO = .12
MIN_PAD = 6
EDGE_PIXELS = 2
REFERENCE_MAX_PIXELS = 16_000_000
CONCURRENT_REFERENCE_PIXELS = 32_000_000

DESIGN_NOTE = (
    "把参考图中的这一个完整设计重画成清晰素材：人物全身、头发、裙摆、鞋子、文字、装饰和内部底板整体保留。"
    "线条、文字和配饰边缘要锐利清楚，不要发虚、不要像素颗粒感。"
    "主体尽量占满画面，四周只留很窄的透明空隙，不裁切。"
    "背景必须是真透明：不要白色底、不要白色贴纸边、不要白色或彩色外描边、不要光晕和投影。"
    "保持原文字、配色和平面印刷风格，不编造细节。"
)
# Below this share of the sheet one design gets too few reference pixels to stay sharp,
# so it is drawn from an enlarged crop of itself instead of the whole sheet.
DENSE_TARGET_SHARE = .04
MAGNIFIED_PIXELS = 2_400_000
MAGNIFIED_MAX_PIXELS = 4_000_000
MAGNIFIED_PAD_RATIO = .30


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
    width, height = source.size
    scale = min(1.0, math.sqrt(REFERENCE_MAX_PIXELS / (width * height)))
    while True:
        size = (max(2, math.floor(width * scale)), max(2, math.floor(height * scale)))
        image = source if size == source.size else source.resize(size, Image.Resampling.LANCZOS)
        png = _encode(image)
        if len(png) <= MAX_INPUT_BYTES:
            return png, image.size
        # High-entropy RGBA PNG can exceed30MB even below the pixel budget.
        # Shrink the complete source proportionally, never cut it or drop alpha.
        if size == (2, 2):
            raise ArkProviderError("image_resource_limit", "完整参考图超过图片服务资源要求，请缩小后重试。")
        scale *= min(.9, math.sqrt(MAX_INPUT_BYTES / len(png)) * .95)


def reference_workers(size, requested=MAX_WORKERS):
    """Bound decoded concurrent input pixels while retaining the eight-call cap."""
    pixels = max(1, size[0] * size[1])
    return max(1, min(MAX_WORKERS, int(requested), CONCURRENT_REFERENCE_PIXELS // pixels))


def design_target_bounds(box, source_size, reference_size):
    """Map an expanded target hint to the reference; the box never crops pixels."""
    left, top, right, bottom = pad_box(box, source_size)
    width, height = source_size
    ref_width, ref_height = reference_size
    x, y = math.floor(left * ref_width / width), math.floor(top * ref_height / height)
    return {"x": x, "y": y,
            "width": min(ref_width, math.ceil(right * ref_width / width)) - x,
            "height": min(ref_height, math.ceil(bottom * ref_height / height)) - y}


def design_share(box, size):
    """How much of the sheet a single design covers, as a fraction."""
    left, top, right, bottom = box
    width, height = size
    return max(0, right - left) * max(0, bottom - top) / float(max(1, width * height))


def magnified_reference(source, box):
    """Encode one design enlarged, for sheets too dense to show it clearly.

    The crop only feeds the model's view of the target; the returned layer canvas is
    still kept whole. Enlarging an already tiny region adds no real detail, it only
    lets the model redraw the shape from a cleaner, isolated view.
    """
    region = pad_box(box, source.size, ratio=MAGNIFIED_PAD_RATIO)
    crop = source.crop(region)
    width, height = crop.size
    pixels = float(max(1, width * height))
    scale = min(math.sqrt(MAGNIFIED_MAX_PIXELS / pixels),
                max(1.0, math.sqrt(MAGNIFIED_PIXELS / pixels)))
    size = (max(2, round(width * scale)), max(2, round(height * scale)))
    image = crop if size == crop.size else crop.resize(size, Image.Resampling.LANCZOS)
    while True:
        png = _encode(image)
        if len(png) <= MAX_INPUT_BYTES or max(image.size) <= 64:
            return png, region, image.size
        # Only a pathological PNG reaches here: shrink the view, never cut it.
        factor = min(.9, math.sqrt(MAX_INPUT_BYTES / len(png)) * .95)
        image = image.resize((max(2, round(image.width * factor)),
                              max(2, round(image.height * factor))), Image.Resampling.LANCZOS)


def design_hint_in_region(box, region, reference_size):
    """Project the source target into the final encoded reference's pixels."""
    left, top, right, bottom = box
    width, height = region[2] - region[0], region[3] - region[1]
    ref_width, ref_height = reference_size
    x = max(0, min(ref_width - 1, math.floor((left - region[0]) * ref_width / width)))
    y = max(0, min(ref_height - 1, math.floor((top - region[1]) * ref_height / height)))
    right = min(ref_width, max(x + 1, math.ceil((right - region[0]) * ref_width / width)))
    bottom = min(ref_height, max(y + 1, math.ceil((bottom - region[1]) * ref_height / height)))
    return {"x": x, "y": y, "width": right - x, "height": bottom - y}


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
                # A stopped wait does not prove that an already sent request
                # settled. Preserve unknown billing before labelling cancellation.
                attempt.update(state=("unknown" if not error.settled else
                                      ("cancelled" if isinstance(error, ArkCancelled) else "failed")),
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
                # Preserve real transparency for edits; an opaque card cannot
                # become a transparent input merely by converting its mode.
                edit_call = self.ark.edit if source.getchannel("A").getextrema()[0] < 255 else self.ark.clean
                cleaned = call("seedream", "edit", lambda: edit_call(
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
            if any(attempt.get("state") == "unknown" for attempt in attempts):
                # Parallel cancellation may raise a fresh outer cancellation
                # after its unknown child was drained. Never turn that history
                # into a claim that every dispatched request is settled.
                error.settled = False
                if isinstance(error, ArkCancelled):
                    error.code = "submission_unknown"
            raise

    def _native_box(self, design, source, base):
        """Design box in the original sheet's pixels, clamped to the image."""
        scale_x, scale_y = source.width / base.width, source.height / base.height
        left, top, right, bottom = design.box
        x = max(0, math.floor(left * scale_x))
        y = max(0, math.floor(top * scale_y))
        width = min(max(1, round((right - left) * scale_x)), source.width - x)
        height = min(max(1, round((bottom - top) * scale_y)), source.height - y)
        return (x, y, x + width, y + height)

    def _generate(self, source, base, designs, instructions, check_cancel, progress, call):
        """One target per native extraction; dense sheets get an enlarged local view."""
        total = len(designs)
        note = self._note(instructions)
        layers, failures = [], []
        finished = 0
        targets = [(index, design, self._native_box(design, source, base))
                   for index, design in enumerate(designs, 1)]
        shares = {index: design_share(native, source.size) for index, _, native in targets}
        # The whole sheet is only shared when at least one design is big enough to stay
        # legible inside it; otherwise every design is drawn from its own enlarged crop.
        need_sheet = any(share >= DENSE_TARGET_SHARE for share in shares.values())
        reference_png, reference_size = prepare_design_reference(source) if need_sheet else (b"", source.size)
        workers = reference_workers(reference_size, self.workers)
        # Every request shares this one reference, so the pool size alone bounds
        # both concurrent input pixels and the eight-call limit. No automatic
        # second generation is planned from a target's size or transparency.

        def one(index, design, native):
            if _cancelled(check_cancel):
                raise ArkCancelled()
            share = shares[index]
            if share < DENSE_TARGET_SHARE:
                payload, region, encoded_size = magnified_reference(source, native)
                target = design_hint_in_region(native, region, encoded_size)
                dense_note = ("本设计只占原图约 %d%%，已放大局部参考图重画；清晰度仍受原图分辨率限制。"
                              % max(1, round(share * 100)))
            else:
                payload = reference_png
                target = design_target_bounds(native, source.size, reference_size)
                dense_note = ""
            cleaned = call("seedream", "extract_design", lambda: self.ark.extract_design(
                payload, bounds=target, instructions=note, check_cancel=check_cancel))
            if len(cleaned.layers) != 1:
                raise ArkProviderError("ambiguous_design", "图片服务没有返回唯一完整设计，请重新框选后重做。")
            native_image = _decode(cleaned.layers[0].png, output=True)
            extra_notes = list(cleaned.warnings) + list(cleaned.layers[0].warnings)
            png, crop_notes = preserve_design(native_image)
            # Persist source coordinates in ArkLayer's public bounds contract;
            # reference hints and native (left, top, right, bottom) are private.
            bounds = {"x": native[0], "y": native[1],
                      "width": native[2] - native[0], "height": native[3] - native[1]}
            return ArkLayer(png, design.label, "", bounds, index,
                            tuple(dict.fromkeys(list(design.warnings) + extra_notes + crop_notes
                                                + ([dense_note] if dense_note else []))))

        with ThreadPoolExecutor(max_workers=min(workers, total)) as pool:
            futures = {pool.submit(one, index, design, native): (index, design)
                       for index, design, native in targets}
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
