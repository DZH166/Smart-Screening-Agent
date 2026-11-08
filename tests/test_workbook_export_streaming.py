"""Synthetic whole-workbook streaming exports; no business/model data."""
import builtins
from hashlib import sha256
import io
from pathlib import Path
import struct
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from hsd_tool import workbook
from hsd_tool.cancellation import TaskCancelled, scope


MAIN = workbook.MAIN
REL = workbook.REL
SHEET = "xl/worksheets/sheet1.xml"


def book(tmp_path, sheet):
    source = tmp_path / "original.xlsx"
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        archive.comment = b"retain exact archive comment"
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets><sheet name="test" r:id="r1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", f'<Relationships><Relationship Id="r1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        if callable(sheet):
            with archive.open(SHEET, "w") as stream:
                sheet(stream)
        else:
            archive.writestr(SHEET, sheet)
        archive.writestr("xl/cellimages.xml", b"<cellImages preserve='WPS' />")
        archive.writestr("xl/media/original.bin", bytes(range(256)) * 20)
        archive.writestr("docProps/custom.xml", b"<custom>\r\n byte-preserved </custom>")
    return source


def worksheet(rows):
    return f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN}"><sheetData>{rows}</sheetData><extLst/></worksheet>'.encode()


def block_read(archive, name):
    with archive.open(name) as stream:
        return b"".join(iter(lambda: stream.read(65536), b""))


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16-le", "utf-16-be"])
def test_streaming_preserves_encoding_non_target_bytes_and_wps(tmp_path, monkeypatch, encoding):
    declaration = "UTF-8" if encoding == "utf-8" else "UTF-16"
    text = (f'<?xml version="1.0" encoding="{declaration}"?><x:worksheet xmlns:x="{MAIN}">'
            '<x:extLst><!-- fake <row r="2"><c r="A2"/></row> -->'
            '<x:ext><![CDATA[<row r="2"><c r="A2"/></row>]]></x:ext></x:extLst>'
            '<x:sheetData><x:row r="2" custom="a &gt; b"><x:c r="A2" s="3"/><x:c r="B2"><x:v>5</x:v></x:c></x:row>'
            '<x:row r="3"><x:c r="B3"/></x:row></x:sheetData></x:worksheet>')
    bom = b"" if encoding == "utf-8" else b"\xff\xfe" if encoding == "utf-16-le" else b"\xfe\xff"
    original = bom + text.encode(encoding)
    source = book(tmp_path, original)
    source_before = source.read_bytes()
    destination = tmp_path / "numbered.xlsx"
    monkeypatch.setattr(ZipFile, "read", lambda *args, **kwargs: pytest.fail("Export materialized an archive member"))
    workbook.write_numbered_workbook(str(source), str(destination), "test", {2: "HSD0012"})
    assert source.read_bytes() == source_before
    with ZipFile(source) as before, ZipFile(destination) as after:
        assert before.namelist() == after.namelist() and before.comment == after.comment
        for name in before.namelist():
            if name != SHEET:
                assert block_read(before, name) == block_read(after, name)
        result = block_read(after, SHEET)
    assert result.startswith(bom) and result.decode(encoding).count("HSD0012") == 1
    old_cell = '<x:c r="A2" s="3"/>'.encode(encoding)
    new_cell = ('<x:c r="A2" s="3" t="inlineStr"><x:is><x:t xml:space="preserve">HSD0012</x:t></x:is></x:c>').encode(encoding)
    assert result == original.replace(old_cell, new_cell)


def test_self_closing_final_row_does_not_consume_parent_close(tmp_path):
    source = book(tmp_path, worksheet('<row r="2"/>'))
    destination = tmp_path / "numbered.xlsx"
    workbook.write_numbered_workbook(str(source), str(destination), "test", {2: "HSD0012"})
    with ZipFile(destination) as archive:
        text = block_read(archive, SHEET)
    assert b'</row></sheetData>' in text and text.count(b"HSD0012") == 1


def test_sheet_larger_than_workspace_is_streamed_without_archive_read(tmp_path, monkeypatch):
    def large(stream):
        stream.write(f'<worksheet xmlns="{MAIN}"><sheetData>'.encode())
        for first in range(1, 220001, 1000):
            stream.write(b"".join(f'<row r="{r}"><c r="B{r}" t="n"><v>1234</v></c></row>'.encode() for r in range(first, first + 1000)))
        stream.write(b"</sheetData></worksheet>")
    source = book(tmp_path, large)
    destination = tmp_path / "numbered.xlsx"
    with ZipFile(source) as archive:
        assert archive.getinfo(SHEET).file_size > workbook.IO_CHUNK_BYTES * 8
    monkeypatch.setattr(ZipFile, "read", lambda *args, **kwargs: pytest.fail("Whole member read"))
    workbook.write_numbered_workbook(str(source), str(destination), "test", {219999: "HSD4321"})
    with ZipFile(destination) as archive, archive.open(SHEET) as stream:
        seen, tail = 0, b""
        while block := stream.read(65536):
            sample = tail + block
            seen += sample.count(b"HSD4321")
            tail = sample[-16:]
    assert seen == 1


def test_cancelled_patch_cleans_spools_and_never_publishes_destination(tmp_path, monkeypatch):
    source = book(tmp_path, worksheet('<row r="2"><c r="A2"/></row><row r="3"/>'))
    destination = tmp_path / "numbered.xlsx"
    digest = sha256(source.read_bytes()).hexdigest()
    cancelled = False
    original_patch = workbook._patch_row
    def patch(*args):
        nonlocal cancelled
        result = original_patch(*args)
        cancelled = True
        return result
    def check():
        if cancelled:
            raise TaskCancelled()
    monkeypatch.setattr(workbook, "_patch_row", patch)
    with scope(check), pytest.raises(TaskCancelled):
        workbook.write_numbered_workbook(str(source), str(destination), "test", {2: "HSD0001"})
    assert not destination.exists() and not list(tmp_path.glob(".hsd-workbook-*"))
    assert sha256(source.read_bytes()).hexdigest() == digest


def test_cancelled_final_copy_removes_only_its_new_destination(tmp_path, monkeypatch):
    source = book(tmp_path, worksheet('<row r="2"/>'))
    destination = tmp_path / "numbered.xlsx"
    digest = sha256(source.read_bytes()).hexdigest()
    cancelled = False
    def opened(path, mode="r", *args, **kwargs):
        nonlocal cancelled
        result = builtins.open(path, mode, *args, **kwargs)
        if mode == "rb" and Path(path).name.startswith(".hsd-workbook-"):
            cancelled = True
        return result
    def check():
        if cancelled:
            raise TaskCancelled()
    monkeypatch.setattr(workbook, "open", opened, raising=False)
    with scope(check), pytest.raises(TaskCancelled):
        workbook.write_numbered_workbook(str(source), str(destination), "test", {2: "HSD0001"})
    assert not destination.exists() and not list(tmp_path.glob(".hsd-workbook-*"))
    assert sha256(source.read_bytes()).hexdigest() == digest


def test_zip_copy_failure_preserves_source_and_removes_output(tmp_path, monkeypatch):
    source = book(tmp_path, worksheet('<row r="2"/>'))
    destination = tmp_path / "numbered.xlsx"
    digest = sha256(source.read_bytes()).hexdigest()
    original_copy = workbook._copy_member
    def broken(archive, info, stream):
        if info.filename.endswith("original.bin"):
            stream.write(b"partial")
            raise ValueError("Synthetic CRC/copy failure")
        return original_copy(archive, info, stream)
    monkeypatch.setattr(workbook, "_copy_member", broken)
    with pytest.raises(ValueError, match="Synthetic"):
        workbook.write_numbered_workbook(str(source), str(destination), "test", {2: "HSD0001"})
    assert not destination.exists() and not list(tmp_path.glob(".hsd-workbook-*"))
    assert sha256(source.read_bytes()).hexdigest() == digest


def test_real_non_sheet_member_crc_failure_never_publishes_destination(tmp_path):
    source = book(tmp_path, worksheet('<row r="2"/>'))
    value = bytearray(source.read_bytes())
    offset = 0
    while True:
        offset = value.find(b"PK\x01\x02", offset)
        assert offset >= 0
        length = struct.unpack_from("<H", value, offset + 28)[0]
        if value[offset + 46:offset + 46 + length] == b"xl/media/original.bin":
            crc = struct.unpack_from("<I", value, offset + 16)[0]
            struct.pack_into("<I", value, offset + 16, crc ^ 1)
            break
        offset += 4
    source.write_bytes(value)
    digest = sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "numbered.xlsx"
    with pytest.raises(ValueError, match="无法导出"):
        workbook.write_numbered_workbook(str(source), str(destination), "test", {2: "HSD0001"})
    assert not destination.exists() and not list(tmp_path.glob(".hsd-workbook-*"))
    assert sha256(source.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("failure", ["prepared_open", "destination_close"])
def test_publication_open_and_close_failures_remove_only_new_output(tmp_path, monkeypatch, failure):
    source = book(tmp_path, worksheet('<row r="2"/>'))
    destination = tmp_path / "numbered.xlsx"
    before = source.read_bytes()
    class CloseFailure:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            self.stream.__enter__()
            return self.stream
        def __exit__(self, *args):
            self.stream.__exit__(*args)
            raise OSError("Synthetic final flush failure")
    def opened(path, mode="r", *args, **kwargs):
        if failure == "prepared_open" and mode == "rb" and Path(path).name.startswith(".hsd-workbook-"):
            raise OSError("Synthetic prepared-open failure")
        stream = builtins.open(path, mode, *args, **kwargs)
        return CloseFailure(stream) if failure == "destination_close" and mode == "xb" else stream
    monkeypatch.setattr(workbook, "open", opened, raising=False)
    with pytest.raises(OSError, match="Synthetic"):
        workbook.write_numbered_workbook(str(source), str(destination), "test", {2: "HSD0001"})
    assert not destination.exists() and not list(tmp_path.glob(".hsd-workbook-*"))
    assert source.read_bytes() == before
