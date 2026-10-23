"""One whole-image cleanup, one design-location call, deterministic local crops.

No decomposition/16-layer output request is sent. There is no upstream progress
percentage: stage transitions are emitted only as real work begins/completes.
"""
from __future__ import annotations

from dataclasses import replace
import math
import time
import uuid

from .ai_usage import empty_usage, merge_usage
from .material_ark import (ArkCancelled, ArkLayer, ArkMaterialProvider, ArkProviderError,
                           ArkResult, _cancelled, _decode, _encode)
from .material_locate import DeepSeekMaterialLocator


class MaterialPipelineProvider:
    supports_progress = True

    def __init__(self, config, ai_settings, *, key_pool=None, ark=None, locator=None, sleeper=None):
        self.ark = ark or ArkMaterialProvider(config["ark_key"], config["model_id"])
        self.locator = locator or DeepSeekMaterialLocator(ai_settings, key_pool=key_pool)
        self._sleep = sleeper or time.sleep

    def _run(self, raw, instructions, bounds, check_cancel, on_progress, on_attempt, *, edit):
        attempts = []
        provider_usage = {"seedream": {}, "deepseek": empty_usage()}

        def progress(code, message):
            if on_progress:
                on_progress(code, message)

        def cancel():
            if _cancelled(check_cancel):
                raise ArkCancelled()

        def publish(attempt):
            if on_attempt:
                on_attempt({**attempt, "usage": dict(attempt["usage"])})

        def stage(provider, operation, invoke):
            for number in range(2):
                cancel()
                attempt = {"id": uuid.uuid4().hex, "provider": provider, "operation": operation,
                           "number": number + 1, "state": "submitted", "usage": {}, "request_id": "",
                           "settled": False, "code": ""}
                attempts.append(attempt)
                publish(attempt)
                try:
                    result = invoke()
                    attempt.update(state="returned", usage=dict(result.usage), request_id=result.request_id, settled=True)
                    aggregate(provider, attempt["usage"])
                    publish(attempt)
                    return result
                except (ArkProviderError, ArkCancelled) as error:
                    attempt.update(state=("cancelled" if isinstance(error, ArkCancelled) else "failed")
                                   if error.settled else "unknown", usage=dict(error.usage),
                                   request_id=error.request_id, settled=error.settled, code=error.code)
                    aggregate(provider, attempt["usage"])
                    publish(attempt)
                    if (number == 0 and not isinstance(error, ArkCancelled)
                            and error.safe_retry and error.settled):
                        if provider == "seedream":
                            progress("cleanup", "清理服务暂忙，正在重试一次。")
                            cancel()
                            self._sleep(.5)
                        else:
                            progress("locating", "定位服务限流，等待后仅重试定位一次。")
                            for _ in range(60):
                                cancel()
                                self._sleep(1)
                        continue
                    raise
                except Exception:
                    # An unexpected transport/adapter failure after dispatch is
                    # not proof of an unbilled rejection. Preserve earlier paid
                    # stages and this unknown submission without leaking text.
                    attempt.update(state="unknown", settled=False, code="submission_unknown")
                    publish(attempt)
                    raise ArkProviderError("submission_unknown", "服务返回异常，结果尚未确认，未自动重发。",
                                           settled=False) from None

        def aggregate(provider, usage):
            if provider == "deepseek":
                merge_usage(provider_usage[provider], usage)
            else:
                for key, value in usage.items():
                    if type(value) is int and value >= 0:
                        provider_usage[provider][key] = provider_usage[provider].get(key, 0) + value

        try:
            progress("preparing", "正在检查图片和服务设置。")
            cancel()
            source = _decode(raw)
            if not edit:
                # Fail before paying for cleanup when locator is unavailable.
                self.locator.available()
            progress("cleanup", "正在清理水印和杂质，等待图片服务返回。")
            cleaned = stage("seedream", "edit" if edit else "cleanup", lambda: self.ark.clean(
                raw, instructions=instructions, bounds=bounds, check_cancel=check_cancel))
            cancel()
            if edit:
                progress("saving", "修改完成，正在保存图片。")
                return replace(cleaned, usage=provider_usage["seedream"], attempts=tuple(attempts),
                               provider_usage=provider_usage, rectangular_crops=True)
            progress("locating", "整图清理完成，正在识别每个完整设计的位置。")
            located = stage("deepseek", "locate", lambda: self.locator.locate(cleaned.base_png, check_cancel=check_cancel))
            cancel()
            canvas = _decode(cleaned.base_png, output=True)
            layers = []
            for index, design in enumerate(located.designs, 1):
                cancel()
                progress("cropping", f"正在裁剪第 {index} / {len(located.designs)} 个设计。")
                crop = canvas.crop(design.box)
                if not crop.getchannel("A").getbbox():
                    raise ArkProviderError("empty_crop", "定位到了空白区域，请框选完整设计后重试。")
                left, top, right, bottom = design.box
                x, y = math.floor(left / canvas.width * source.width), math.floor(top / canvas.height * source.height)
                raw_bounds = {"x": x, "y": y,
                              "width": min(source.width, math.ceil(right / canvas.width * source.width)) - x,
                              "height": min(source.height, math.ceil(bottom / canvas.height * source.height)) - y}
                notes = list(design.warnings)
                notes.append("裁剪范围由模型估计，可能切到设计或带入相邻图案；请核对，必要时重新框选。")
                if crop.getchannel("A").getextrema()[0] == 255:
                    notes.append("此结果保留矩形范围内的背景，未做透明抠图。")
                layers.append(ArkLayer(_encode(crop), design.label, "", raw_bounds, index, tuple(notes)))
            progress("saving", "裁剪完成，正在保存结果。")
            return ArkResult(tuple(layers), provider_usage["seedream"],
                             tuple(dict.fromkeys(cleaned.warnings + located.warnings)),
                             cleaned.base_png, cleaned.base_size, cleaned.request_id,
                             tuple(attempts), provider_usage, True)
        except (ArkProviderError, ArkCancelled) as error:
            # A later locator failure must NEVER replay the charged cleanup.
            error.safe_retry = error.retryable = False
            error.attempts = tuple(attempts)
            error.provider_usage = provider_usage
            error.usage = dict(provider_usage["seedream"])
            raise

    def extract(self, image_bytes, *, instructions="", check_cancel=None, on_progress=None, on_attempt=None):
        return self._run(image_bytes, instructions, None, check_cancel, on_progress, on_attempt, edit=False)

    def edit(self, image_bytes, *, instructions, bounds=None, check_cancel=None, on_progress=None, on_attempt=None):
        return self._run(image_bytes, instructions, bounds, check_cancel, on_progress, on_attempt, edit=True)
