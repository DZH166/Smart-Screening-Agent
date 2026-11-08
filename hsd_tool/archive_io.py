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
# Limit the decoder's dictionary, not the upload or expanded file length.
# The default ZIP-LZMA dictionary is 8 MiB; unusually large dictionaries can
# allocate gigabytes before max_length has a chance to bound any output.
MAX_LZMA_DICTIONARY_BYTES = 64 * 1024 * 1024

_EOCD_BYTES = 22


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
        # Use the same bounded end-record parser as ZipFile, including ZIP64
        # extensible records and self-extracting prefixes. It creates no
        # ZipInfo objects. Never trust the declared count as the actual count.
        try:
            end = zipfile._EndRecData(stream)
        except (OSError, OverflowError, struct.error) as exc:
            raise zipfile.BadZipFile(invalid) from exc
        if not end:
            raise zipfile.BadZipFile(invalid)
        entries = end[zipfile._ECD_ENTRIES_TOTAL]
        directory_bytes = end[zipfile._ECD_SIZE]
        directory_end = _central_directory_end(stream, end, invalid)
        if (end[zipfile._ECD_DISK_NUMBER] or end[zipfile._ECD_DISK_START]
                or entries != end[zipfile._ECD_ENTRIES_THIS_DISK]):
            raise ValueError("暂不支持分卷压缩包，请重新打包后上传。")
        if entries > max_entries:
            raise ValueError(too_many)
        if directory_bytes > max_entries * 2048 or directory_bytes > directory_end:
            raise zipfile.BadZipFile(invalid)
        position, actual = directory_end - directory_bytes, 0
        stream.seek(position)
        while position < directory_end:
            check()
            header = stream.read(zipfile.sizeCentralDir)
            if len(header) != zipfile.sizeCentralDir or header[:4] != zipfile.stringCentralDir:
                raise zipfile.BadZipFile(invalid)
            filename, extra, comment = struct.unpack_from('<HHH', header, 28)
            length = zipfile.sizeCentralDir + filename + extra + comment
            if position + length > directory_end:
                raise zipfile.BadZipFile(invalid)
            actual += 1
            if actual > max_entries:
                raise ValueError(too_many)
            position += length
            stream.seek(position)
        if actual != entries:
            raise zipfile.BadZipFile(invalid)
    return entries, directory_bytes


def _central_directory_end(stream, end, invalid):
    """Observe physical records, not a version-specific private tuple meaning.

    Older supported Python ZIP64 parsers leave LOCATION at the normal EOCD;
    newer patched parsers normalize it to the ZIP64 record. Verify bytes and
    lengths so both work, including the same SFX fallback as ZipFile itself.
    """
    location = end[zipfile._ECD_LOCATION]
    stream.seek(location)
    signature = stream.read(4)
    if end[zipfile._ECD_SIGNATURE] != zipfile.stringEndArchive64:
        if signature != zipfile.stringEndArchive:
            raise zipfile.BadZipFile(invalid)
        return location
    if signature == zipfile.stringEndArchive64:
        return location
    locator_position = location - zipfile.sizeEndCentDir64Locator
    if signature != zipfile.stringEndArchive or locator_position < 0:
        raise zipfile.BadZipFile(invalid)
    stream.seek(locator_position)
    locator = stream.read(zipfile.sizeEndCentDir64Locator)
    if len(locator) != zipfile.sizeEndCentDir64Locator:
        raise zipfile.BadZipFile(invalid)
    marker, disk, relative, disks = struct.unpack(zipfile.structEndArchive64Locator, locator)
    if marker != zipfile.stringEndArchive64Locator or disk or disks != 1:
        raise zipfile.BadZipFile(invalid)
    for position in dict.fromkeys((relative, locator_position - zipfile.sizeEndCentDir64)):
        if not 0 <= position <= locator_position - zipfile.sizeEndCentDir64:
            continue
        stream.seek(position)
        record = stream.read(zipfile.sizeEndCentDir64)
        if record[:4] != zipfile.stringEndArchive64 or len(record) != zipfile.sizeEndCentDir64:
            continue
        length = struct.unpack_from('<Q', record, 4)[0] + 12
        if position + length == locator_position:
            return position
    raise zipfile.BadZipFile(invalid)


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
        properties = lzma._decode_filter_properties(lzma.FILTER_LZMA1, pending[4:4 + property_size])
        if properties.get('dict_size', 0) > MAX_LZMA_DICTIONARY_BYTES:
            raise ValueError('压缩包的 LZMA 字典占用内存过高，请改用标准 ZIP 压缩后上传。')
        filters = [properties]
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
