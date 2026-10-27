"""Server-only Volcengine Ark material image adapter.

The image API is synchronous: a lost reply has no documented job-status lookup
and must never trigger another paid POST automatically.  Each call here submits
exactly once.  The task service owns the at-most-one *definite failure* retry.

Schema checked against the official Ark image generation API on 2026-10-22:
https://console.volcengine.com/ark/region:cn-beijing/docs/image-generation-api

Only base64 output is accepted. No provider-controlled URL is fetched, so signed
links cannot redirect this service into a private network. Keys, input metadata,
upstream messages and complete response bodies never cross the error boundary.
Model labels, layers and repairs are suggestions, not evidence of fidelity.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
import io
import http.client
import json
import math
import re
import socket
import time
from typing import Callable, Mapping
import urllib.error
import urllib.request
import warnings

from PIL import Image, ImageOps
try:
    from PIL import ImageCms
except ImportError:  # An ICC-bearing image must fail closed without colour CMS.
    ImageCms = None

from .cancellation import TaskCancelled


ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MAX_INPUT_BYTES = 30 * 1024 * 1024  # Upstream per-image resource requirement.
MAX_INPUT_PIXELS = 36_000_000
MAX_OUTPUT_BYTES = 30 * 1024 * 1024
MAX_OUTPUT_PIXELS = 8_000_000
MAX_TOTAL_OUTPUT_PIXELS = 80_000_000
MAX_RESPONSE_BYTES = 128 * 1024 * 1024
MAX_LAYERS = 16
CLEAN_TARGET_PIXELS = 2048 * 2048  # Native 2K canvas; preserve aspect ratio.
_MODEL = re.compile(r"(?:doubao-seedream-5-0-(?:pro|flash)-[A-Za-z0-9._-]+|ep-[A-Za-z0-9][A-Za-z0-9_-]*)\Z")
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,160}\Z")
_RETRYABLE_RATE_CODES = frozenset({
    "RateLimitExceeded", "RateLimitExceeded.EndpointRPMExceeded",
    "RateLimitExceeded.EndpointTPMExceeded", "RateLimitExceeded.EndpointFlexTPMExceeded",
    "ModelAccountRpmRateLimitExceeded", "ModelAccountTpmRateLimitExceeded",
    "ModelAccountFlexTpmRateLimitExceeded", "ModelAccountIpmRateLimitExceeded",
    "APIAccountRpmRateLimitExceeded", "AccountRateLimitExceeded",
    "ServerOverloaded", "RequestBurstTooFast", "InflightBatchsizeExceeded",
})
_INVENTORY_PROMPT = (
    "提取图中所有独立的完整设计，每个完整设计单独作为一个图层。"
    "同一设计的人物、文字、装饰和内部底板必须整体保留，不要拆散。"
    "只去掉设计外部背景和外加水印，包含覆盖在设计上的重复斜向半透明水印文字；不要误删设计自身的文字或签名。"
    "尽量保持原始配色、文字、形状和细节，不主动增艳、换色、改字或增加图案、渐变、描边和阴影。"
    "实物上的设计尽量展平，遮挡和模糊处仅谨慎修补，不要凭空添加内容。"
)
_SINGLE_DESIGN_PROMPT = (
    "只提取指定的一个完整设计，作为一个前景图层返回，不拆零件。"
    "去掉外部背景、邻近设计和外加水印，保留完整轮廓、文字、配色及内部底板。"
    "用真实PNG透明通道，不画白底或棋盘格。"
    "不新增白色贴纸边、黑色外描边、光晕或投影；保留原设计内部线条和白色内容。"
)
_FIDELITY_WARNING = "模型拆分可能改变细节，需核对完整设计、文字和配色。"


class ArkProviderError(Exception):
    """A static, secret-free error with honest submission settlement metadata."""

    def __init__(self, code: str, message: str, *, retryable=False, safe_retry=None, settled=True,
                 usage=None, request_id=""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = bool(retryable if safe_retry is None else safe_retry)
        self.safe_retry = self.retryable
        self.settled = bool(settled)
        self.usage = dict(usage or {})
        self.request_id = request_id


class ArkCancelled(TaskCancelled):
    def __init__(self, *, settled=True, usage=None, request_id=""):
        super().__init__("本批素材处理已停止。" if settled else "本机已停止等待，图片服务的处理结果尚未确认。")
        self.code = "cancelled" if settled else "submission_unknown"
        self.settled = bool(settled)
        self.retryable = self.safe_retry = False
        self.usage = dict(usage or {})
        self.request_id = request_id


@dataclass(frozen=True)
class HttpReply:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    url: str = ""


@dataclass(frozen=True)
class ArkLayer:
    png: bytes = field(repr=False)
    label: str
    description: str
    bounds: dict[str, int]
    z_index: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArkResult:
    layers: tuple[ArkLayer, ...]
    usage: dict[str, int]
    warnings: tuple[str, ...]
    base_png: bytes = field(repr=False)
    base_size: tuple[int, int]
    request_id: str = ""
    attempts: tuple[dict, ...] = ()
    provider_usage: dict = field(default_factory=dict)
    rectangular_crops: bool = False
    no_upscale: bool = False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_transport(request, *, timeout, max_bytes):
    # A hard, whole-response deadline prevents a slow stream from keeping the
    # single worker occupied forever by repeatedly refreshing socket timeouts.
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        if response.geturl() != ENDPOINT:
            raise ArkProviderError("redirect_blocked", "图片服务地址发生跳转，未重复提交。", settled=False)
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isascii() or not length.isdigit() or int(length) > max_bytes):
            raise ArkProviderError("response_resource_limit", "图片服务返回数据过大，未重复提交。", settled=False)
        blocks, total = [], 0
        reader = getattr(response, "read1", response.read)
        while True:
            if time.monotonic() >= deadline:
                raise ArkProviderError("submission_unknown", "图片服务返回超时，结果未确认，未自动重复提交。", settled=False)
            # Lower the per-receive timeout as the total deadline approaches.
            try:
                response.fp.raw._sock.settimeout(max(0.01, deadline - time.monotonic()))
            except AttributeError:
                pass
            block = reader(min(64 * 1024, max_bytes + 1 - total))
            if time.monotonic() >= deadline:
                raise ArkProviderError("submission_unknown", "图片服务返回超时，结果未确认，未自动重复提交。", settled=False)
            if not block:
                break
            blocks.append(block)
            total += len(block)
            if total > max_bytes:
                raise ArkProviderError("response_resource_limit", "图片服务返回数据过大，未重复提交。", settled=False)
        return HttpReply(response.status, b"".join(blocks), dict(response.headers), response.geturl())


def _cancelled(check_cancel):
    if check_cancel is None:
        return False
    try:
        return check_cancel() is True
    except TaskCancelled:
        return True


def _strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = item
        return result

    def constant(_):
        raise ValueError("nonfinite value")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=constant)


def _encode(image):
    output = io.BytesIO()
    clean = image.copy()
    clean.info.clear()
    clean.save(output, "PNG")
    return output.getvalue()


def normalise_rgba(image):
    """Orient pixels and convert embedded colour profiles before stripping metadata.

    Discarding an Adobe RGB/CMYK profile while keeping its raw channel values
    changes the displayed colours. Convert in the original image mode first;
    never attach a CMYK profile to already-naively-converted RGB pixels. The
    returned pixels are sRGB RGBA and contain no EXIF, comments or ICC payload.
    This colour conversion is not a proof that generative output kept colours.
    """
    oriented = ImageOps.exif_transpose(image)
    profile = oriented.info.get("icc_profile")
    if profile:
        try:
            if ImageCms is None or not isinstance(profile, bytes) or len(profile) > 2 * 1024 * 1024:
                raise ValueError("invalid colour profile")
            alpha = oriented.convert("RGBA").getchannel("A")
            working = oriented if oriented.mode in {"RGB", "CMYK", "L", "LAB"} else oriented.convert("RGB")
            converted = ImageCms.profileToProfile(
                working, ImageCms.ImageCmsProfile(io.BytesIO(profile)), ImageCms.createProfile("sRGB"), outputMode="RGB")
            result = converted.convert("RGBA")
            result.putalpha(alpha)
        except Exception:
            raise ValueError("图片的颜色配置无法读取，请重新保存为 sRGB 图片后再试。") from None
    else:
        result = oriented.convert("RGBA")
    result.info.clear()
    return result


def _decode(value, *, output=False, require_alpha=False):
    limit = MAX_OUTPUT_BYTES if output else MAX_INPUT_BYTES
    if not isinstance(value, bytes) or not 0 < len(value) <= limit:
        raise ArkProviderError("invalid_image", "图片数据为空或超过图片服务的单次资源要求。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(value)) as opened:
                if (opened.format not in ({"PNG"} if output else {"PNG", "JPEG", "WEBP"})
                        or getattr(opened, "n_frames", 1) != 1
                        or opened.width < 2 or opened.height < 2
                        or opened.width * opened.height > (MAX_OUTPUT_PIXELS if output else MAX_INPUT_PIXELS)):
                    raise ValueError("invalid image")
                alpha = "A" in opened.getbands() or "transparency" in opened.info
                if require_alpha and not alpha:
                    raise ArkProviderError("missing_alpha", "图片服务未返回透明通道，不能当作透明素材。")
                opened.load()
                return normalise_rgba(opened)
    except ArkProviderError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ArkProviderError("invalid_image", "图片无法读取，或像素数量超过安全资源要求。") from None


def _input(value, *, decomposition):
    image = _decode(value)
    source_size = image.size
    width, height = source_size
    if not 1 / 16 <= width / height <= 16:
        raise ArkProviderError("unsupported_ratio", "图片过长，请先框选一个完整设计再处理。")
    notes = []
    if decomposition and width * height < 512 * 512:
        ratio = math.sqrt(512 * 512 / (width * height))
        image = image.resize((math.ceil(width * ratio), math.ceil(height * ratio)), Image.Resampling.LANCZOS)
        notes.append("原图像素偏少，放大仅满足接口尺寸要求，不代表恢复细节。")
    elif not decomposition and (width <= 14 or height <= 14):
        raise ArkProviderError("invalid_image", "素材尺寸太小，无法进行局部修改。")
    encoded = _encode(image)
    if len(encoded) > MAX_INPUT_BYTES:
        raise ArkProviderError("image_resource_limit", "图片转换后超过图片服务的单次资源要求，请缩小图片后重试。")
    return image, source_size, "data:image/png;base64," + base64.b64encode(encoded).decode("ascii"), notes


def _usage(payload):
    value = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items()
            if key in {"input_images", "generated_images", "output_tokens", "total_tokens"}
            and type(item) is int and 0 <= item <= 1_000_000_000}


def _request_id(reply, secret):
    for key, value in reply.headers.items():
        if str(key).lower() in {"x-request-id", "x-tt-logid", "request-id"}:
            if isinstance(value, str) and _REQUEST_ID.fullmatch(value) and secret not in value:
                return value
    return ""


def _safe_text(value, fallback, secret, limit=240):
    if not isinstance(value, str):
        return fallback
    value = "".join(c for c in value.strip() if c.isprintable())
    value = value.replace(secret, "[已隐藏]")
    return value[:limit] or fallback


def _image_field(item):
    # Deliberately do not accept data URLs or external download links. Base64 is
    # requested explicitly and means no provider URL can become an SSRF target.
    value = item.get("b64_json")
    if (not isinstance(value, str) or not value
            or len(value) > 4 * math.ceil(MAX_OUTPUT_BYTES / 3)):
        raise ArkProviderError("invalid_response", "图片服务未按约定返回图片数据，未重复提交。")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ArkProviderError("invalid_response", "图片服务返回的图片数据不完整，未重复提交。") from None


def _size(item, image):
    value = item.get("size")
    if (not isinstance(value, str) or value != f"{image.width}x{image.height}"
            or item.get("output_format", "png") != "png"):
        raise ArkProviderError("invalid_response", "图片服务返回的尺寸与图片内容不一致。")


def _bounds(item, base_size, source_size):
    bounds = item.get("bounding_box")
    if not isinstance(bounds, dict):
        raise ArkProviderError("invalid_bounds", "图片服务没有返回有效的图层位置。")
    absolute = bounds.get("absolute")
    if (not isinstance(absolute, list) or len(absolute) != 4
            or not all(type(v) is int for v in absolute)):
        raise ArkProviderError("invalid_bounds", "图片服务返回的图层位置格式不正确。")
    left, top, right, bottom = absolute
    width, height = base_size
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ArkProviderError("invalid_bounds", "图片服务返回的图层超出原图范围。")
    normalized = bounds.get("normalized")
    if normalized is not None:
        if (not isinstance(normalized, list) or len(normalized) != 4
                or not all(type(v) is int and 0 <= v <= 1000 for v in normalized)
                or any(abs(given - expected) > 2 for given, expected in zip(
                    normalized, [left / width * 1000, top / height * 1000,
                                 right / width * 1000, bottom / height * 1000]))):
            raise ArkProviderError("invalid_bounds", "图片服务返回的两组图层位置互相矛盾。")
    source_width, source_height = source_size
    x = math.floor(left / width * source_width)
    y = math.floor(top / height * source_height)
    return {"x": x, "y": y,
            "width": min(source_width, math.ceil(right / width * source_width)) - x,
            "height": min(source_height, math.ceil(bottom / height * source_height)) - y}


def _prompt_bounds(bounds, size):
    """Input interaction boxes use 0..999, unlike response boxes' 0..1000.

    Official Seedream pro/flash interactive editing guide (2026-10-15):
    https://console.volcengine.com/ark/region%3Acn-beijing/docs/seedream-5-0-pro-editing-guide
    Keep a valid one-unit hint for tiny source regions without cropping pixels.
    """
    width, height = size
    if (not isinstance(bounds, dict) or set(bounds) != {"x", "y", "width", "height"}
            or not all(type(value) is int for value in bounds.values())
            or bounds["x"] < 0 or bounds["y"] < 0 or bounds["width"] <= 0 or bounds["height"] <= 0
            or bounds["x"] + bounds["width"] > width or bounds["y"] + bounds["height"] > height):
        raise ArkProviderError("invalid_bounds", "目标设计位置超出参考图片，请重新框选后重试。")
    left = min(998, math.floor(bounds["x"] * 1000 / width))
    top = min(998, math.floor(bounds["y"] * 1000 / height))
    right = min(999, max(left + 1, math.ceil((bounds["x"] + bounds["width"]) * 1000 / width)))
    bottom = min(999, max(top + 1, math.ceil((bounds["y"] + bounds["height"]) * 1000 / height)))
    return left, top, right, bottom


class ArkMaterialProvider:
    """Exactly-one-submission Ark adapter; no credentials are read implicitly."""

    def __init__(self, api_key: str, model_id: str, *, transport=None, timeout=240):
        if (not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096
                or any(ord(c) < 33 or ord(c) > 126 for c in api_key.strip())):
            raise ArkProviderError("not_configured", "请先由管理员配置火山方舟 API Key。")
        if not isinstance(model_id, str) or len(model_id) > 128 or not _MODEL.fullmatch(model_id):
            raise ArkProviderError("unsupported_model", "素材提取需要支持图层拆分的 Seedream 5.0 pro、flash 或对应接入点。")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 1 <= timeout <= 600:
            raise ValueError("invalid timeout")
        self._key = api_key.strip()
        self.model_id = model_id
        self._transport = transport or _default_transport
        self.timeout = timeout

    def _submit(self, payload, check_cancel):
        if _cancelled(check_cancel):
            raise ArkCancelled()
        request = urllib.request.Request(
            ENDPOINT, data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._key},
            method="POST")
        try:
            reply = self._transport(request, timeout=self.timeout, max_bytes=MAX_RESPONSE_BYTES)
            if (not isinstance(reply, HttpReply) or reply.url not in {"", ENDPOINT}
                    or type(reply.status) is not int or not isinstance(reply.body, bytes)
                    or len(reply.body) > MAX_RESPONSE_BYTES):
                raise ArkProviderError("invalid_response", "图片服务返回异常，结果未确认，未重复提交。", settled=False)
        except ArkProviderError as error:
            if _cancelled(check_cancel):
                raise ArkCancelled(settled=error.settled, usage=error.usage, request_id=error.request_id) from None
            raise
        except (OSError, TimeoutError, socket.timeout, urllib.error.URLError, http.client.HTTPException):
            if _cancelled(check_cancel):
                raise ArkCancelled(settled=False) from None
            raise ArkProviderError("submission_unknown", "图片服务连接中断或超时，结果未确认，未自动重复提交。", settled=False) from None
        request_id = _request_id(reply, self._key)
        try:
            parsed = _strict_json(reply.body)
            if not isinstance(parsed, dict):
                raise ValueError("invalid object")
        except (ValueError, UnicodeError, RecursionError):
            if _cancelled(check_cancel):
                raise ArkCancelled(settled=False, request_id=request_id) from None
            raise ArkProviderError("invalid_response", "图片服务返回格式异常，结果未确认，未重复提交。",
                                   settled=False, request_id=request_id) from None
        usage = _usage(parsed)
        error = parsed.get("error")
        if error is not None or not 200 <= reply.status < 300:
            definite = (400 <= reply.status < 500 and isinstance(error, dict) and isinstance(error.get("code"), str)
                        and bool(error["code"]) and not parsed.get("data")
                        and usage.get("generated_images", 0) == 0
                        and (not isinstance(parsed.get("usage"), dict)
                             or "generated_images" not in parsed["usage"]
                             or type(parsed["usage"]["generated_images"]) is int
                             and parsed["usage"]["generated_images"] == 0))
            if _cancelled(check_cancel):
                raise ArkCancelled(settled=definite, usage=usage, request_id=request_id)
            if reply.status in {401, 403}:
                code, message = "provider_auth", "图片服务未接受当前 Key 或模型权限，请联系管理员检查。"
            elif reply.status == 429:
                code, message = "provider_busy", "图片服务当前繁忙，稍后可重试。"
            else:
                code, message = "provider_failed", "图片服务未能完成本次处理，请检查设置或稍后重试。"
            # A 5xx may be a gateway failure after upstream work was accepted.
            # Neither a JSON error nor a missing image proves it was unbilled.
            raise ArkProviderError(code, message, retryable=definite and reply.status == 429
                                   and error.get("code") in _RETRYABLE_RATE_CODES,
                                   settled=definite, usage=usage, request_id=request_id)
        if _cancelled(check_cancel):
            # The synchronous POST returned. Do not prematurely abort its socket
            # before receiving settlement/known usage just to make Stop look fast.
            raise ArkCancelled(usage=usage, request_id=request_id)
        return parsed, usage, request_id

    def clean(self, image_bytes: bytes, *, instructions="", bounds=None,
              check_cancel: Callable | None = None) -> ArkResult:
        """Clean one complete canvas; no decomposition or invented separate items.

        Seedream 5.0 flash/pro do not support upstream streaming (official API,
        checked 2026-10-23). Callers emit honest start/wait/returned stage events.
        Rectangular crops preserve these returned pixels, including any opaque
        background; merely converting a PNG to RGBA is not background removal.
        """
        if _cancelled(check_cancel):
            raise ArkCancelled()
        if not isinstance(instructions, str) or len(instructions) > 1000:
            raise ArkProviderError("invalid_instructions", "处理要求过长，请简要描述。")
        image, source_size, data_uri, notes = _input(image_bytes, decomposition=False)
        area = image.width * image.height
        factor = math.sqrt(CLEAN_TARGET_PIXELS / area)
        width, height = max(15, math.ceil(image.width * factor)), max(15, math.ceil(image.height * factor))
        location = ""
        if bounds is not None:
            left, top, right, bottom = _prompt_bounds(bounds, source_size)
            location = f"只修改归一化范围<bbox>{left} {top} {right} {bottom}</bbox>，其他区域保持原样。"
        prompt = ("清理整张图片的外加水印、污点及无关信息。彻底去除背景和人物脸部、皮肤、衣服、装饰上覆盖的"
                  "重复、斜向、半透明水印字样与印记，按周围纹理谨慎修复，不留残影；设计自身文字、签名不视为水印。"
                  "保持原图比例、构图和设计数量、位置、大小、间距；不移动、不拆分，不单独生成图层。"
                  "保留人物、文字、装饰和内部底板，不改色、不改字、不增艳或添图。"
                  "不新增贴纸白边、黑色外描边、光晕、投影；保留内部线条和原白色内容。"
                  "输出高清图像画质和清晰度，保持线条、轮廓、五官和纹理清楚，避免模糊、涂抹、锯齿；看不清的内容不要编造。"
                  "将设计外部背景设为真正透明（PNG Alpha 通道），保留设计内部底板；不要用白底或棋盘格图案假装透明。"
                  + location + ("补充要求：" + instructions.strip() if instructions.strip() else ""))
        parsed, usage, request_id = self._submit(
            {"model": self.model_id, "image": data_uri, "prompt": prompt,
             "layer_decomposition": False, "size": f"{width}x{height}",
             "output_format": "png", "response_format": "b64_json", "watermark": False}, check_cancel)
        try:
            data = parsed.get("data")
            if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict) or "error" in data[0]:
                raise ArkProviderError("invalid_response", "图片服务没有返回一张完整的清理图片。")
            output = _decode(_image_field(data[0]), output=True)
            _size(data[0], output)
            if abs(output.width / output.height / (image.width / image.height) - 1) > .015:
                raise ArkProviderError("invalid_bounds", "图片服务改变了整图比例，请检查结果后再处理。")
            if not output.getchannel("A").getbbox():
                raise ArkProviderError("empty_layer", "图片服务返回了空白图片。")
            if output.width * output.height < width * height * .9:
                notes.append("图片服务返回尺寸低于高清目标，细节可能不足；可框选单个设计重新处理。")
            notes.append("清理可能改变文字、配色或细节，请对照原图确认。")
            encoded = _encode(output)
            layer = ArkLayer(encoded, "清理后的整图", "", {"x": 0, "y": 0,
                             "width": source_size[0], "height": source_size[1]}, 1, tuple(notes))
            return ArkResult((layer,), usage, tuple(notes), encoded, output.size, request_id,
                             rectangular_crops=True)
        except ArkProviderError as error:
            raise ArkProviderError(error.code, error.message, usage=usage, request_id=request_id) from None

    def extract(self, image_bytes: bytes, *, instructions="", check_cancel: Callable | None = None) -> ArkResult:
        return self._extract_layers(image_bytes, instructions=instructions, check_cancel=check_cancel,
                                    single_design=False, bounds=None)

    def extract_design(self, image_bytes: bytes, *, instructions="", bounds=None,
                       check_cancel: Callable | None = None) -> ArkResult:
        """One paid native-alpha extraction, accepting exactly one foreground.

        Preserve the provider's complete layer canvas. Multiple layers are an
        unresolved grouping decision, never a reason to choose the largest,
        delete fragments locally or issue another paid generation automatically.
        """
        return self._extract_layers(image_bytes, instructions=instructions, check_cancel=check_cancel,
                                    single_design=True, bounds=bounds)

    def _extract_layers(self, image_bytes, *, instructions, check_cancel, single_design, bounds):
        if _cancelled(check_cancel):
            raise ArkCancelled()
        if not isinstance(instructions, str) or len(instructions) > 1000:
            raise ArkProviderError("invalid_instructions", "处理要求过长，请简要描述。")
        image, source_size, data_uri, notes = _input(image_bytes, decomposition=True)
        target = ""
        if bounds is not None:
            left, top, right, bottom = _prompt_bounds(bounds, source_size)
            target = (f"目标归一化范围<bbox>{left} {top} {right} {bottom}</bbox>。"
                      "位置框只用于辨认目标；身体、文字或饰物延伸到框外时仍整体保留，不按框切图，其他独立设计不要提取。")
        payload = {"model": self.model_id, "image": data_uri,
                   "prompt": (_SINGLE_DESIGN_PROMPT if single_design else _INVENTORY_PROMPT) +
                             target +
                             ("补充要求：" + instructions if instructions.strip() else ""),
                   "layer_decomposition": True, "size": "2K", "output_format": "png",
                   "response_format": "b64_json", "watermark": False}
        parsed, usage, request_id = self._submit(payload, check_cancel)
        try:
            data = parsed.get("data")
            if not isinstance(data, list) or not 2 <= len(data) <= MAX_LAYERS + 1 or not all(isinstance(v, dict) for v in data):
                raise ArkProviderError("no_designs", "图片服务未返回完整设计图层，请框选设计后重试。")
            if single_design and len(data) != 2:
                raise ArkProviderError("ambiguous_design", "图片服务把这个设计拆成了多个图层，请重新框选完整设计后重做。")
            indices = [item.get("z_index") for item in data]
            if (not all(type(v) is int for v in indices) or set(indices) != set(range(len(data)))
                    or any("error" in item for item in data)):
                raise ArkProviderError("invalid_response", "图片服务返回的图层不完整或顺序有误。")
            data = sorted(data, key=lambda item: item["z_index"])
            base = _decode(_image_field(data[0]), output=True)
            _size(data[0], base)
            if abs(base.width / base.height / (image.width / image.height) - 1) > 0.015:
                raise ArkProviderError("invalid_bounds", "图片服务改变了整图比例，图层位置无法核对。")
            layers, total_pixels = [], base.width * base.height
            for item in data[1:]:
                if _cancelled(check_cancel):
                    raise ArkCancelled(usage=usage, request_id=request_id)
                layer = _decode(_image_field(item), output=True, require_alpha=True)
                _size(item, layer)
                total_pixels += layer.width * layer.height
                if total_pixels > MAX_TOTAL_OUTPUT_PIXELS:
                    raise ArkProviderError("response_resource_limit", "本次返回的图层像素过多，未自动重复提交。")
                alpha = layer.getchannel("A")
                if not alpha.getbbox():
                    raise ArkProviderError("empty_layer", "图片服务返回了空白图层，请框选设计后重试。")
                bounds = _bounds(item, base.size, source_size)
                notes_layer = [_FIDELITY_WARNING]
                if alpha.getextrema()[0] == 255:
                    notes_layer.append("此图层没有透明区域，请确认保留的是设计内部底板。")
                layers.append(ArkLayer(_encode(layer), _safe_text(item.get("name"), f"素材 {item['z_index']}", self._key),
                                       _safe_text(item.get("description"), "", self._key, 600),
                                       bounds, item["z_index"], tuple(notes_layer)))
            if len(layers) == MAX_LAYERS:
                notes.append("本次已达到最多 16 个图层，原图可能还有未提取设计，请查看整图并按需框选补提。")
            return ArkResult(tuple(layers), usage, tuple(notes), _encode(base), base.size, request_id)
        except ArkProviderError as error:
            # A valid successful provider reply has already settled, even when
            # its images fail local safety/fidelity checks. Never pay to resubmit.
            raise ArkProviderError(error.code, error.message, usage=usage, request_id=request_id) from None

    def refine_design(self, image_bytes: bytes, *, instructions="",
                      check_cancel: Callable | None = None) -> ArkResult:
        """One planned clarity pass on an already extracted transparent design.

        This is not a failed-request retry or local upscaling. Reframe the full
        subject on its own native 2K canvas; never crop/morph the input/output.
        """
        if _cancelled(check_cancel):
            raise ArkCancelled()
        if not isinstance(instructions, str) or len(instructions) > 1000:
            raise ArkProviderError("invalid_instructions", "处理要求过长，请简要描述。")
        image, source_size, data_uri, notes = _input(image_bytes, decomposition=False)
        if image.getchannel("A").getextrema()[0] == 255:
            raise ArkProviderError("missing_alpha", "精修需要已提取且带真实透明区域的完整设计。")
        prompt = (
            "将这一张透明素材中的完整设计高清精修，作为单独一张透明PNG返回。"
            "整个人物、头发、手脚、裙摆、文字、装饰和内部底板一起保留，自然居中，占画面约80%，四周留透明空隙。"
            "清楚呈现轮廓、五官和纹理，不模糊涂抹，不裁边，不新增内容。"
            "忠于原文字、配色、形状和风格；去除外加水印。"
            "不新增白色贴纸边、黑色外描边、光晕或投影，保留原设计内部线条及白色内容。"
            + ("补充要求：" + instructions.strip() if instructions.strip() else ""))
        return self._transparent_single(data_uri, source_size, prompt, notes,
                                        "高清精修后的素材", check_cancel)

    def _transparent_single(self, data_uri, source_size, prompt, notes, label, check_cancel):
        parsed, usage, request_id = self._submit(
            {"model": self.model_id, "image": data_uri, "prompt": prompt,
             "size": "2K", "output_format": "png", "response_format": "b64_json",
             "background": "transparent", "watermark": False}, check_cancel)
        try:
            data = parsed.get("data")
            if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict) or "error" in data[0]:
                raise ArkProviderError("invalid_response", "图片服务没有返回唯一完整的处理结果。")
            output = _decode(_image_field(data[0]), output=True, require_alpha=True)
            _size(data[0], output)
            if not output.getchannel("A").getbbox():
                raise ArkProviderError("empty_layer", "图片服务返回了空白素材。")
            if output.getchannel("A").getextrema()[0] == 255:
                notes.append("图片服务未返回透明区域，已保留完整画布，请确认背景。")
            notes.append("精修内容由模型生成，文字、配色和完整性仍需对照确认。")
            layer = ArkLayer(_encode(output), label, "", {"x": 0, "y": 0, "width": source_size[0], "height": source_size[1]},
                             1, tuple(notes))
            return ArkResult((layer,), usage, tuple(notes), b"", output.size, request_id,
                             rectangular_crops=True, no_upscale=True)
        except ArkProviderError as error:
            raise ArkProviderError(error.code, error.message, usage=usage, request_id=request_id) from None

    def edit(self, image_bytes: bytes, *, instructions: str, bounds=None,
             check_cancel: Callable | None = None) -> ArkResult:
        if _cancelled(check_cancel):
            raise ArkCancelled()
        if not isinstance(instructions, str) or not instructions.strip() or len(instructions) > 1000:
            raise ArkProviderError("invalid_instructions", "请简要选择或填写需要修改的内容。")
        image, source_size, data_uri, notes = _input(image_bytes, decomposition=False)
        if image.getchannel("A").getextrema()[0] == 255:
            raise ArkProviderError("missing_alpha", "局部修改需要先提取带透明背景的素材。")
        location = ""
        if bounds is not None:
            left, top, right, bottom = _prompt_bounds(bounds, source_size)
            location = f"只修改归一化范围<bbox>{left} {top} {right} {bottom}</bbox>，范围之外的全部设计保持原样。"
        prompt = ("在透明背景上修改这张完整设计，保留原图人物、文字、装饰和内部底板；"
                  "不主动换色、改字、增艳或增加内容，不新增贴纸白边、外描边、光晕或投影；保留内部线条和白色内容。"
                  + location + "修改要求：" + instructions.strip())
        if bounds:
            notes.append("已按标记位置提出修改要求，模型仍可能改变其他区域，请对照确认。")
        return self._transparent_single(data_uri, source_size, prompt, notes,
                                        "修改后的素材", check_cancel)
