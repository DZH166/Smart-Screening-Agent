"""The ZIP directory guard must reject an over-full archive before zipfile
materialises one ZipInfo per entry in the single worker.

Synthetic bytes only: no user files, no network.
"""
from __future__ import annotations

import struct
import zipfile
import io

import pytest

from hsd_tool.archive_io import check_directory_size


def eocd(entries, directory_bytes, *, comment=b"", disk=0, directory_disk=0, entries_disk=None):
    if entries_disk is None:
        entries_disk = entries
    return struct.pack("<4sHHHHIIH", b"PK\x05\x06", disk, directory_disk, entries_disk, entries,
                       directory_bytes, 0, len(comment)) + comment


def zip64_eocd(entries, directory_bytes):
    return struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0, entries, entries,
                       directory_bytes, 0)


def zip64_locator(offset):
    return struct.pack("<4sIQI", b"PK\x06\x07", 0, offset, 1)


def archive(path, *, entries, directory_bytes=0, zip64=False, comment=b""):
    body = b"PK\x03\x04" + b"\0" * 26 if not zip64 else b""
    if zip64:
        record = zip64_eocd(entries, directory_bytes)
        offset = len(body)
        body += record + zip64_locator(offset) + eocd(0xFFFF, 0xFFFFFFFF)
    else:
        body += eocd(entries, directory_bytes)
    path.write_bytes(body + comment)
    return path


def real_zip64(path, *, actual=5, declared=None, prefix=b'', extension=b'', sentinel=True, comment=b''):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as source:
        for n in range(actual):
            source.writestr(f'{n}.ai', b'x')
    raw = data.getvalue()
    end = zipfile._EndRecData(io.BytesIO(raw))
    position = end[zipfile._ECD_LOCATION]
    count = actual if declared is None else declared
    record = struct.pack('<4sQHHIIQQQQ', b'PK\x06\x06', 44 + len(extension), 45, 45,
                         0, 0, count, count, end[zipfile._ECD_SIZE], end[zipfile._ECD_OFFSET]) + extension
    tail = struct.pack('<4sHHHHIIH', b'PK\x05\x06', 0, 0,
                       0xffff if sentinel else count, 0xffff if sentinel else count,
                       0xffffffff if sentinel else end[zipfile._ECD_SIZE],
                       0xffffffff if sentinel else end[zipfile._ECD_OFFSET], len(comment)) + comment
    path.write_bytes(prefix + raw[:position] + record + zip64_locator(position) + tail)
    return path


def test_a_normal_archive_is_measured_once(tmp_path):
    path = tmp_path / "small.zip"
    with zipfile.ZipFile(path, "w") as archive_file:
        archive_file.writestr("a.ai", b"x" * 16)
        archive_file.writestr("b.ai", b"y" * 16)
    entries, directory_bytes = check_directory_size(path, max_entries=10)
    assert entries == 2 and 0 < directory_bytes < 10 * 2048


def test_an_over_full_directory_is_rejected_before_zipfile_reads_it(tmp_path):
    path = archive(tmp_path / "many.zip", entries=10_000)
    with pytest.raises(ValueError, match="过多"):
        check_directory_size(path, max_entries=9_999)


def test_zip64_declared_counts_are_honoured(tmp_path):
    # A Zip64 archive is allowed only when its real count fits.
    small = real_zip64(tmp_path / "zip64-small.zip")
    assert check_directory_size(small, max_entries=10)[0] == 5
    big = real_zip64(tmp_path / "zip64-big.zip", declared=200_000)
    with pytest.raises(ValueError, match="过多"):
        check_directory_size(big, max_entries=10_000)


def test_a_forged_huge_directory_is_rejected(tmp_path):
    path = archive(tmp_path / "forged.zip", entries=3, directory_bytes=400_000_000)
    with pytest.raises(zipfile.BadZipFile):
        check_directory_size(path, max_entries=10_000)


@pytest.mark.parametrize("payload", [b"", b"not a zip at all", b"PK\x05\x06" + b"\0" * 4])
def test_broken_archives_keep_a_clear_error(tmp_path, payload):
    path = tmp_path / "broken.zip"
    path.write_bytes(payload)
    with pytest.raises(zipfile.BadZipFile):
        check_directory_size(path, max_entries=10_000)


def test_multi_disk_archives_are_refused(tmp_path):
    path = tmp_path / "split.zip"
    path.write_bytes(b"\0" * 8 + eocd(2, 100, disk=1))
    with pytest.raises(ValueError, match="分卷"):
        check_directory_size(path, max_entries=10_000)
