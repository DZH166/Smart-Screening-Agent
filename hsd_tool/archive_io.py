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
from .cancellation import check

CHUNK_BYTES = 1024 * 1024

_EOCD = b"PK\x05\x06"
_ZIP64_EOCD = b"PK\x06\x06"
_ZIP64_LOCATOR = b"PK\x06\x07"
_EOCD_BYTES = 22
_TAIL_BYTES = 66_000


def check_directory_size(path, *, max_entries, too_many="压缩包内文件过多，请分批上传。",
                         invalid="压缩包结构无效，无法读取。"):
    """Reject an over-full ZIP before zipfile builds its entry list.

    ``zipfile.ZipFile(path)`` reads the whole central directory and keeps one
    ZipInfo per entry. With a single worker capped at 2 GiB, a small upload
    whose directory declares millions of entries could exhaust memory before
    the caller's ``len(infolist())`` check runs. Reading only the end records
    is constant work and catches that case first.
    """
    with open(path, "rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        if size < _EOCD_BYTES:
            raise zipfile.BadZipFile(invalid)
        tail_start = max(0, size - _TAIL_BYTES)
        stream.seek(tail_start)
        tail = stream.read(size - tail_start)
        entries, directory_bytes = _directory_facts(stream, tail, tail_start, invalid)
    if entries > max_entries:
        raise ValueError(too_many)
    if directory_bytes > max_entries * 2048:
        raise zipfile.BadZipFile(invalid)
    return entries, directory_bytes


def _directory_facts(stream, tail, tail_start, invalid):
    index = tail.rfind(_EOCD)
    if index < 0 or index + _EOCD_BYTES > len(tail):
        raise zipfile.BadZipFile(invalid)
    (disk, directory_disk, entries_disk, entries,
     directory_bytes, directory_offset, comment) = struct.unpack("<HHHHIIH", tail[index + 4:index + 22])
    if index + _EOCD_BYTES + comment > len(tail):
        raise zipfile.BadZipFile(invalid)
    if disk or directory_disk or entries != entries_disk:
        raise ValueError("暂不支持分卷压缩包，请重新打包后上传。")
    if 0xFFFF not in (entries, entries_disk) and directory_bytes != 0xFFFFFFFF:
        return entries, directory_bytes
    locator = tail.rfind(_ZIP64_LOCATOR, 0, index)
    if locator < 0 or locator + 20 > len(tail):
        raise zipfile.BadZipFile(invalid)
    (offset,) = struct.unpack("<Q", tail[locator + 8:locator + 16])
    stream.seek(offset)
    record = stream.read(56)
    if len(record) != 56 or record[:4] != _ZIP64_EOCD:
        raise zipfile.BadZipFile(invalid)
    entries, directory_bytes = struct.unpack("<QQ", record[32:48])
    return entries, directory_bytes



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
        check()
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
            check()
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
