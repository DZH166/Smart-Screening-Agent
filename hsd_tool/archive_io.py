"""Stream ZIP members through their real end, checking CRC and declared length.

ZipExtFile normally truncates output at the directory's declared size. Counting
the inflater's output before that truncation also detects a forged short size
whose CRC was recalculated for a valid prefix. No product byte/ratio caps apply.
"""
from __future__ import annotations

import bz2
import lzma
import struct
import zipfile
import zlib

CHUNK_BYTES = 1024 * 1024


class _MeasuredInflater:
    def __init__(self, inflater):
        self.inflater = inflater
        self.count = 0

    def decompress(self, *args):
        block = self.inflater.decompress(*args)
        self.count += len(block)
        return block

    def flush(self, *args):
        block = self.inflater.flush(*args)
        self.count += len(block)
        return block

    def __getattr__(self, name):
        return getattr(self.inflater, name)


def _bounded_native_blocks(stream, info, chunk_size):
    """BZ2/LZMA need their native max_length API, absent from ZipExtFile.read."""
    pending = b''
    if info.compress_type == zipfile.ZIP_BZIP2:
        inflater = bz2.BZ2Decompressor()
    else:
        # ZIP LZMA adds version/property bytes before its raw LZMA stream.
        while len(pending) < 4:
            if not stream._compress_left:
                raise zipfile.BadZipFile('压缩包 LZMA 头部不完整。')
            pending += stream._read2(chunk_size)
        property_size = struct.unpack_from('<H', pending, 2)[0]
        while len(pending) < 4 + property_size:
            if not stream._compress_left:
                raise zipfile.BadZipFile('压缩包 LZMA 参数不完整。')
            pending += stream._read2(chunk_size)
        filters = [lzma._decode_filter_properties(lzma.FILTER_LZMA1, pending[4:4 + property_size])]
        inflater = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=filters)
        pending = pending[4 + property_size:]
    count, crc = 0, 0
    while not inflater.eof:
        if inflater.needs_input:
            if pending:
                raw, pending = pending, b''
            elif stream._compress_left:
                raw = stream._read2(chunk_size)
            elif info.compress_type == zipfile.ZIP_LZMA and not info.flag_bits & 2:
                # ZIP LZMA permits omission of EOS when bit 1 is clear; all
                # compressed input and buffered output still must be consumed.
                break
            else:
                raise zipfile.BadZipFile('压缩包压缩流未完整读取。')
        else:
            raw = b''
        block = inflater.decompress(raw, max_length=min(chunk_size, max(1, info.file_size - count + 1)))
        count += len(block)
        if count > info.file_size:
            raise zipfile.BadZipFile('压缩包实际展开长度不符。')
        if block:
            crc = zlib.crc32(block, crc)
            yield block
        elif not raw and not inflater.needs_input and not inflater.eof:
            raise zipfile.BadZipFile('压缩包压缩流无法继续解码。')
    if count != info.file_size or crc != info.CRC:
        raise zipfile.BadZipFile('压缩包文件长度或 CRC 校验失败。')
    if pending or stream._compress_left or getattr(inflater, 'unused_data', b''):
        raise zipfile.BadZipFile('压缩包压缩数据长度不符。')


def member_blocks(archive: zipfile.ZipFile, info, chunk_size=CHUNK_BYTES):
    """Yield bounded read blocks and refuse incomplete/extra encoded content.

    The small ZipExtFile adapter is deliberately covered for all compression
    methods supported by the bundled Python runtime. Header, overlap, filename
    and CRC validation continue to be provided by ZipFile.open/read.
    """
    if isinstance(info, str):
        info = archive.getinfo(info)
    if info.file_size < 0 or info.compress_size < 0:
        raise zipfile.BadZipFile('压缩包文件长度无效。')
    if info.compress_type == zipfile.ZIP_STORED and info.compress_size != info.file_size:
        raise zipfile.BadZipFile('压缩包实际展开长度不符。')
    with archive.open(info) as stream:
        if isinstance(stream, zipfile.ZipExtFile) and info.compress_type in {zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA}:
            try:
                yield from _bounded_native_blocks(stream, info, chunk_size)
            except (OSError, EOFError, lzma.LZMAError) as exc:
                raise zipfile.BadZipFile('压缩包压缩流损坏。') from exc
            return
        measured = None
        if isinstance(stream, zipfile.ZipExtFile) and stream._decompressor is not None:
            measured = _MeasuredInflater(stream._decompressor)
            stream._decompressor = measured
        count = 0
        while block := stream.read(chunk_size):
            count += len(block)
            if count > info.file_size or measured is not None and measured.count > info.file_size:
                raise zipfile.BadZipFile('压缩包实际展开长度不符。')
            yield block
        if count != info.file_size:
            raise zipfile.BadZipFile('压缩包文件未完整读取。')
        if measured is not None:
            # Exactly-boundary reads can leave only the compression end marker
            # unconsumed. Finish it, refusing even one further decoded byte.
            while not measured.eof:
                pending = getattr(measured, 'unconsumed_tail', b'')
                raw = pending or (stream._read2(chunk_size) if stream._compress_left else b'')
                extra = measured.decompress(raw, 1) if info.compress_type == zipfile.ZIP_DEFLATED else measured.decompress(raw)
                if extra or measured.count != info.file_size:
                    raise zipfile.BadZipFile('压缩包实际展开长度不符。')
                if not raw and not measured.eof:
                    raise zipfile.BadZipFile('压缩包压缩流未完整读取。')
            if stream._compress_left or getattr(measured, 'unused_data', b''):
                raise zipfile.BadZipFile('压缩包压缩数据长度不符。')
