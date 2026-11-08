"""Fixed WebP metadata probes; sparse logical files never allocate their size."""
from io import BytesIO
import struct
import zlib

from PIL import Image, TiffImagePlugin
import pytest

from hsd_tool.image_budget import IMAGE_BUDGET
from hsd_tool.image_headers import image_header


def webp(mode="RGB", lossless=False):
    with Image.new(mode, (16, 24), (50, 90, 160, 128) if mode == "RGBA" else (50, 90, 160)) as image:
        output = BytesIO()
        image.save(output, "WEBP", lossless=lossless)
        return output.getvalue()


@pytest.mark.parametrize("mode,lossless,kind", [("RGB", False, b"VP8 "), ("RGB", True, b"VP8L"), ("RGBA", False, b"VP8X")])
def test_webp_dimensions_need_no_pillow_or_full_source_read(monkeypatch, mode, lossless, kind):
    data = webp(mode, lossless)
    assert data[12:16] == kind
    class Measured(BytesIO):
        read_bytes = 0
        def read(self, size=-1):
            assert 0 <= size <= 12, "Header probe attempted an unbounded read"
            result = super().read(size)
            self.read_bytes += len(result)
            return result
    source = Measured(data)
    source.seek(3)
    monkeypatch.setattr(Image, "open", lambda *args, **kwargs: pytest.fail("Preflight entered Pillow WebP decoder"))
    header = image_header(source, max_pixels=36_000_000)
    assert (header.width, header.height) == (16, 24) and header.format == "WEBP"
    assert header.encoded_bytes == len(data) and source.read_bytes <= 30
    assert source.tell() == 3 and not source.closed
    assert header.workspace() >= 2 * len(data)


def test_sparse_gigabyte_webp_is_rejected_before_native_or_full_read(monkeypatch):
    data = bytearray(webp("RGBA"))
    struct.pack_into("<I", data, 4, 1024**3 - 8)
    class Sparse(BytesIO):
        def seek(self, offset, whence=0):
            if whence == 2:
                self.at_end = True
                return 1024**3
            self.at_end = False
            return super().seek(offset, whence)
        def tell(self):
            return 1024**3 if getattr(self, "at_end", False) else super().tell()
        def read(self, size=-1):
            assert 0 <= size <= 12
            return super().read(size)
    monkeypatch.setattr(Image, "open", lambda *args, **kwargs: pytest.fail("Native decoder invoked"))
    with pytest.raises(ValueError, match="解码需要的内存过多"):
        image_header(Sparse(data[:30]), max_pixels=36_000_000)


@pytest.mark.parametrize("damage", ["trailing", "truncated", "chunk_length", "animated", "zero_dimension"])
def test_invalid_riff_or_dimensions_are_rejected_before_pillow(monkeypatch, damage):
    data = bytearray(webp("RGBA"))
    if damage == "trailing":
        data += b"extra"
    elif damage == "truncated":
        data = data[:25]
    elif damage == "chunk_length":
        struct.pack_into("<I", data, 16, 0xffffffff)
    elif damage == "animated":
        data[20] |= 2
    else:
        # VP8X stores size-1; the maximum 24-bit dimensions exceed pixel budget.
        data[24:30] = b"\xff" * 6
    monkeypatch.setattr(Image, "open", lambda *args, **kwargs: pytest.fail("Native decoder invoked"))
    with pytest.raises(ValueError):
        image_header(bytes(data), max_pixels=36_000_000)


@pytest.mark.parametrize("format", ["PNG", "JPEG"])
def test_supported_streaming_headers_keep_existing_formats(format):
    with Image.new("RGB", (12, 18), "red") as image:
        target = BytesIO()
        image.save(target, format)
    header = image_header(target.getvalue(), max_pixels=1000)
    assert (header.format, header.width, header.height) == (format, 12, 18)


def test_restricted_formats_do_not_enter_tiff_plugin(monkeypatch):
    with Image.new("RGB", (16, 16), "red") as image:
        target = BytesIO()
        image.save(target, "TIFF")
    monkeypatch.setattr(TiffImagePlugin.TiffImageFile, "_open", lambda *args: pytest.fail("Unsupported codec entered"))
    with pytest.raises(ValueError):
        image_header(target.getvalue(), max_pixels=1000)


def test_webp_source_decodes_with_unchanged_alpha_and_pixels():
    from hsd_tool import material_service
    data = webp("RGBA", lossless=True)
    with material_service._image_workspace(data):
        with material_service._decode(data) as normalized, Image.open(BytesIO(data)) as original:
            with original.convert("RGBA") as expected:
                assert normalized.size == expected.size
                assert normalized.tobytes() == expected.tobytes()
    assert IMAGE_BUDGET._used == 0


def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def small_png():
    with Image.new("RGBA", (16, 24), (90, 10, 20, 128)) as image:
        target = BytesIO()
        image.save(target, "PNG")
        return target.getvalue()


@pytest.mark.parametrize("location", ["before", "after"])
def test_png_metadata_limit_applies_before_and_after_image_data(monkeypatch, location):
    from hsd_tool import image_headers as headers
    data = small_png()
    marker = data.index(b"IDAT") - 4 if location == "before" else data.index(b"IEND") - 4
    data = data[:marker] + png_chunk(b"iCCP", b"x" * 256) + data[marker:]
    monkeypatch.setattr(headers, "MAX_METADATA_CHUNK", 128)
    monkeypatch.setattr(Image, "open", lambda *args, **kwargs: pytest.fail("Oversize metadata entered Pillow"))
    with pytest.raises(headers.ImageDecodeMemoryError, match="附加信息过多"):
        image_header(data, max_pixels=1000)


def test_png_many_small_metadata_chunks_and_empty_data_chunks_are_bounded(monkeypatch):
    from hsd_tool import image_headers as headers
    data = small_png()
    marker = data.index(b"IEND") - 4
    monkeypatch.setattr(headers, "MAX_HEADER_METADATA", 140)
    extra = png_chunk(b"tEXt", b"x" * 64) * 3
    with pytest.raises(headers.ImageDecodeMemoryError):
        image_header(data[:marker] + extra + data[marker:], max_pixels=1000)
    monkeypatch.setattr(headers, "MAX_HEADER_METADATA", 32 * 1024 * 1024)
    monkeypatch.setattr(headers, "MAX_PNG_CHUNKS", 4)
    extra = png_chunk(b"IDAT", b"") * 5
    with pytest.raises(headers.ImageDecodeMemoryError):
        image_header(data[:marker] + extra + data[marker:], max_pixels=1000)


def test_png_image_payload_is_only_sought_not_read(monkeypatch):
    data = small_png()
    begin = data.index(b"IDAT") + 4
    length = struct.unpack_from(">I", data, begin - 8)[0]
    class PayloadGuard(BytesIO):
        def read(self, count=-1):
            assert not begin <= self.tell() < begin + length, "Metadata scan read image payload"
            return super().read(count)
    # Verify the metadata pass itself; normal Pillow still reads the image
    # header afterwards and later performs normal decoding/CRC validation.
    from hsd_tool import image_headers as headers
    headers._png_metadata(PayloadGuard(data), len(data), lambda: None)


@pytest.mark.parametrize("format", ["PNG", "TIFF", "BMP", "GIF"])
def test_static_legacy_headers_keep_normal_metadata_and_pixels(format):
    from PIL import ImageCms
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    with Image.new("RGB", (16, 24), (90, 10, 20)) as image:
        target = BytesIO()
        options = {"icc_profile": profile} if format in {"PNG", "TIFF"} else {}
        image.save(target, format, **options)
    data = target.getvalue()
    header = image_header(data, max_pixels=1000, formats=(format,))
    assert (header.width, header.height, header.format) == (16, 24, format)
    with Image.open(BytesIO(data)) as image:
        assert image.size == (16, 24)
        if options:
            assert image.info["icc_profile"] == profile


def test_tiff_header_large_tag_is_rejected_by_metadata_reader(monkeypatch):
    from hsd_tool import image_headers as headers
    from PIL import ImageFile
    with Image.new("RGB", (1, 1), "red") as image:
        target = BytesIO()
        image.save(target, "TIFF", icc_profile=b"x" * 1024)
    # Small resource weights exercise the very same _safe_read accumulation
    # path as the observed 256MiB tag; no large input/native allocation occurs.
    monkeypatch.setattr(headers, "MAX_HEADER_METADATA", 256)
    monkeypatch.setattr(ImageFile, "SAFEBLOCK", 64)
    with pytest.raises(headers.ImageDecodeMemoryError, match="附加信息过多"):
        image_header(target.getvalue(), max_pixels=1000, formats=("TIFF",))
