"""Bounded image header inspection before Pillow may decode an entire WebP."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
import os
import struct
import warnings
from PIL import Image
from hsd_tool.image_budget import IMAGE_BUDGET, image_workspace_bytes
from hsd_tool.cancellation import check as cancellation_check


MAX_METADATA_CHUNK = 16 * 1024 * 1024
MAX_HEADER_METADATA = 32 * 1024 * 1024
MAX_PNG_CHUNKS = 100_000


def _metadata_limit():
    return ImageDecodeMemoryError("图片附加信息过多，解码需要的内存过多，请重新保存后重试。")


class _MetadataReader:
    """Limit header metadata reads, not image payload or upload byte size."""
    def __init__(self, stream):
        self.stream, self.remaining = stream, MAX_HEADER_METADATA

    def read(self, size=-1):
        if size < 0 or size > self.remaining:
            raise _metadata_limit()
        result = self.stream.read(size)
        self.remaining -= len(result)
        return result

    def __getattr__(self, name):
        return getattr(self.stream, name)


def _png_metadata(stream, encoded, check_cancel):
    # Scan chunk lengths without reading encoded image data. Pillow validates
    # normal small metadata/CRCs afterwards. Post-IDAT ancillary chunks can also
    # be read at load_end, so include them without inflating/capping any IDAT.
    stream.seek(8)
    metadata, chunks, found_ihdr, found_data = 0, 0, False, False
    while stream.tell() < encoded:
        check_cancel()
        raw = stream.read(8)
        if len(raw) != 8:
            raise ValueError("PNG 图片头部不完整，请重新保存后重试。")
        length, kind = struct.unpack(">I4s", raw)
        chunks += 1
        if chunks > MAX_PNG_CHUNKS:
            raise _metadata_limit()
        if length > 0x7fffffff or stream.tell() + length + 4 > encoded:
            raise ValueError("PNG 图片内部长度无效，请重新保存后重试。")
        if not found_ihdr:
            if kind != b"IHDR" or length != 13:
                raise ValueError("PNG 图片头部无效，请重新保存后重试。")
            found_ihdr = True
        if kind not in {b"IDAT", b"fdAT"}:
            metadata += length
            if length > MAX_METADATA_CHUNK or metadata > MAX_HEADER_METADATA:
                raise _metadata_limit()
        if kind == b"IDAT":
            found_data = True
        stream.seek(length + 4, 1)
        if kind == b"IEND":
            if length or not found_data:
                raise ValueError("PNG 图片缺少完整图像数据，请重新保存后重试。")
            return
    raise ValueError("PNG 图片未完整结束，请重新保存后重试。")


class AnimatedImageError(ValueError):
    pass


class ImageDecodeMemoryError(ValueError):
    pass


@dataclass(frozen=True)
class ImageHeader:
    format: str
    width: int
    height: int
    encoded_bytes: int

    @property
    def pixels(self):
        return self.width * self.height

    def workspace(self, output_pixels=0):
        return image_workspace_bytes(max(self.pixels, output_pixels)) + (2 * self.encoded_bytes if self.format == "WEBP" else 0)


@contextmanager
def _source(value):
    owned = isinstance(value, (str, os.PathLike, bytes, bytearray))
    stream = (BytesIO(value) if isinstance(value, (bytes, bytearray)) else
              open(value, "rb") if isinstance(value, (str, os.PathLike)) else value)
    position = stream.tell()
    try:
        stream.seek(0)
        yield stream
    finally:
        if owned:
            stream.close()
        else:
            stream.seek(position)


def image_header(value, *, max_pixels, formats=("PNG", "JPEG", "WEBP"), budget=IMAGE_BUDGET,
                 check_cancel=None):
    """Only fixed WebP bytes are read; PNG/JPEG use their restricted decoder.

    WebP's Pillow plugin reads the complete encoded source in Image.open,
    before reporting dimensions. Reserve native workspace before that call.
    No XLSX/ZIP/input upload byte limit is introduced by this decoder guard.
    """
    check_cancel = check_cancel or cancellation_check
    check_cancel()
    try:
        with _source(value) as stream:
            stream.seek(0, 2)
            encoded = stream.tell()
            stream.seek(0)
            prefix = stream.read(12)
            if prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
                if "WEBP" not in formats:
                    raise ValueError("图片格式不支持，请重新保存为 PNG 或 JPEG。")
                if encoded != struct.unpack_from("<I", prefix, 4)[0] + 8:
                    raise ValueError("WebP 文件不完整或有多余内容，请重新保存后重试。")
                chunk = stream.read(8)
                if len(chunk) != 8:
                    raise ValueError("WebP 图片头部不完整。")
                kind, length = struct.unpack("<4sI", chunk)
                if length + (length & 1) + 20 > encoded:
                    raise ValueError("WebP 图片头部长度无效。")
                head = stream.read(min(length, 10))
                if kind == b"VP8X" and length == 10 and len(head) == 10:
                    if head[0] & 2:
                        raise AnimatedImageError("暂不处理动图，请先保存为单张图片。")
                    width = int.from_bytes(head[4:7], "little") + 1
                    height = int.from_bytes(head[7:10], "little") + 1
                elif kind == b"VP8 " and len(head) == 10 and head[3:6] == b"\x9d\x01\x2a" and not head[0] & 1:
                    width, height = (n & 0x3fff for n in struct.unpack_from("<HH", head, 6))
                elif kind == b"VP8L" and len(head) >= 5 and head[0] == 0x2f:
                    bits = int.from_bytes(head[1:5], "little")
                    if bits >> 29:
                        raise ValueError("WebP 图片版本不支持，请重新保存。")
                    width, height = (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
                else:
                    raise ValueError("WebP 图片头部无法确认，请重新保存后重试。")
                result = ImageHeader("WEBP", width, height, encoded)
                if result.workspace() > budget.capacity:
                    raise ImageDecodeMemoryError("WebP 解码需要的内存过多，请重新保存为 PNG 或缩小图片后重试。")
            else:
                if prefix[:8] == b"\x89PNG\r\n\x1a\n":
                    _png_metadata(stream, encoded, check_cancel)
                stream.seek(0)
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(_MetadataReader(stream), formats=list(formats)) as header:
                        if getattr(header, "n_frames", 1) != 1:
                            raise AnimatedImageError("暂不处理动图，请先保存为单张图片。")
                        result = ImageHeader(header.format, header.width, header.height, encoded)
            if min(result.width, result.height) < 1 or result.pixels > max_pixels:
                raise ValueError("图片像素过大，请缩小后重试。")
            return result
    except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("图片无法读取或已损坏，请重新保存后重试。") from None
