"""Synthetic pre-allocation proofs; never allocate malicious dictionaries."""
import io
import lzma
import struct
import zipfile

import pytest

from hsd_tool import archive_io
from hsd_tool.cancellation import TaskCancelled, scope
from test_archive_directory_guard import real_zip64


def test_actual_directory_count_cannot_be_hidden_by_eocd(tmp_path, monkeypatch):
    path = tmp_path / 'forged-count.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        for n in range(101):
            archive.writestr(f'{n}.ai', b'')
    raw = bytearray(path.read_bytes())
    offset = raw.rfind(b'PK\x05\x06')
    struct.pack_into('<HH', raw, offset + 8, 1, 1)
    path.write_bytes(raw)
    monkeypatch.setattr(zipfile, 'ZipFile', lambda *a, **k: pytest.fail('Guard must run before ZipInfo allocation'))
    with pytest.raises(ValueError, match='过多'):
        archive_io.check_directory_size(path, max_entries=100)


@pytest.mark.parametrize('options', [
    {}, {'prefix': b'SYNTHETIC-SFX-ONLY'}, {'extension': b'synthetic-extension'},
    {'sentinel': False}, {'comment': b'c' * 65535}, {'actual': 0},
])
def test_zip64_parser_matches_supported_zipfile_semantics(tmp_path, options):
    path = real_zip64(tmp_path / 'compatible.zip', **options)
    with zipfile.ZipFile(path) as archive:
        expected = len(archive.infolist())
    assert archive_io.check_directory_size(path, max_entries=10)[0] == expected


def test_normal_sfx_and_empty_archives(tmp_path):
    for count in (0, 2):
        path = tmp_path / f'sfx-{count}.zip'
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for n in range(count):
                archive.writestr(f'{n}.ai', b'content')
        path.write_bytes(b'SYNTHETIC-PREFIX' + stream.getvalue())
        assert archive_io.check_directory_size(path, max_entries=10)[0] == count


@pytest.mark.parametrize('prefix', [b'', b'SYNTHETIC-SFX'])
def test_legacy_zip64_location_semantics_are_supported(tmp_path, monkeypatch, prefix):
    path = real_zip64(tmp_path / 'legacy-location.zip', prefix=prefix)
    assert archive_io.check_directory_size(path, max_entries=10)[0] == 5
    original = zipfile._EndRecData
    def legacy_location(stream):
        result = original(stream)
        # Python 3.12 releases predating the normalization patch return the
        # ordinary EOCD location, independently observed from the real bytes.
        stream.seek(0)
        ordinary = stream.read().rfind(b'PK\x05\x06')
        result[zipfile._ECD_LOCATION] = ordinary
        return result
    monkeypatch.setattr(zipfile, '_EndRecData', legacy_location)
    assert archive_io.check_directory_size(path, max_entries=10)[0] == 5


def test_inconsistent_but_under_limit_count_is_invalid(tmp_path):
    path = real_zip64(tmp_path / 'inconsistent.zip', actual=2, declared=1)
    with pytest.raises(zipfile.BadZipFile):
        archive_io.check_directory_size(path, max_entries=10)


def test_directory_scan_is_cooperatively_cancellable(tmp_path):
    path = real_zip64(tmp_path / 'cancel.zip')
    def cancel():
        raise TaskCancelled()
    with scope(cancel), pytest.raises(TaskCancelled):
        archive_io.check_directory_size(path, max_entries=10)


def lzma_zip(dictionary=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_LZMA) as archive:
        archive.writestr('synthetic.ai', b'SYNTHETIC small data' * 4)
    raw = bytearray(stream.getvalue())
    if dictionary is not None:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info = archive.infolist()[0]
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
            assert struct.unpack_from('<H', raw, offset + 2)[0] == 5
            struct.pack_into('<I', raw, offset + 5, dictionary)
    return bytes(raw)


def test_lzma_rejects_dictionary_before_native_allocator(monkeypatch):
    raw = lzma_zip(0xffffffff)
    monkeypatch.setattr(lzma, 'LZMADecompressor', lambda *a, **k: pytest.fail('Unsafe native allocation'))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive, pytest.raises(ValueError, match='LZMA 字典'):
        list(archive_io.member_blocks(archive, archive.infolist()[0]))


def test_lzma_supported_dictionary_boundary_reaches_decoder(monkeypatch):
    raw = lzma_zip(4096)
    monkeypatch.setattr(archive_io, 'MAX_LZMA_DICTIONARY_BYTES', 4096)
    class Checked(Exception):
        pass
    def decoder(*a, **kwargs):
        assert kwargs['filters'][0]['dict_size'] == 4096
        raise Checked()
    monkeypatch.setattr(lzma, 'LZMADecompressor', decoder)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive, pytest.raises(Checked):
        list(archive_io.member_blocks(archive, archive.infolist()[0]))


def test_standard_lzma_roundtrip_still_reads_complete_bytes():
    with zipfile.ZipFile(io.BytesIO(lzma_zip())) as archive:
        assert b''.join(archive_io.member_blocks(archive, archive.infolist()[0])) == b'SYNTHETIC small data' * 4
