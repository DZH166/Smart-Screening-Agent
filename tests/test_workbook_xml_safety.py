"""Streaming XML safety with small synthetic inputs and lowered budgets."""
import io
import struct
import zipfile
import zlib

import pytest

from hsd_tool import workbook, xml_stream
from hsd_tool.cancellation import TaskCancelled, scope


def archive_bytes(part, body):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(part, body)
    return output.getvalue()


def read(archive, kind):
    if kind == 'rows':
        return list(workbook._iter_rows(archive, 'sheet.xml'))
    if kind == 'strings':
        return workbook._strings(archive, {0})
    return workbook._xml(archive, 'meta.xml')


def sample(kind, declaration=''):
    if kind == 'rows':
        return 'sheet.xml', declaration + '<worksheet><sheetData><row r="1"><c r="A1"><v>1</v></c></row></sheetData></worksheet>'
    if kind == 'strings':
        return 'xl/sharedStrings.xml', declaration + '<sst><si><t>value</t></si></sst>'
    return 'meta.xml', declaration + '<root><child>value</child></root>'


@pytest.mark.parametrize('kind', ['rows', 'strings', 'metadata'])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le', 'utf-16-be'])
def test_all_xml_paths_reject_dtd_before_entity_expansion(kind, encoding):
    part, xml = sample(kind, '<!DOCTYPE x [<!ENTITY safe "SAFE">]>')
    bom = b'' if encoding == 'utf-8' else (b'\xff\xfe' if encoding.endswith('le') else b'\xfe\xff')
    with zipfile.ZipFile(io.BytesIO(archive_bytes(part, bom + xml.encode(encoding)))) as archive:
        with pytest.raises(ValueError, match='XML 声明'):
            read(archive, kind)


@pytest.mark.parametrize('kind', ['rows', 'strings', 'metadata'])
def test_all_xml_paths_observe_cancelled_task(kind):
    part, xml = sample(kind)
    calls = []
    def cancel():
        calls.append(True)
        raise TaskCancelled()
    with zipfile.ZipFile(io.BytesIO(archive_bytes(part, xml.encode()))) as archive, scope(cancel):
        with pytest.raises(TaskCancelled):
            read(archive, kind)
    assert calls


@pytest.mark.parametrize('kind', ['rows', 'strings', 'metadata'])
def test_forged_valid_xml_prefix_cannot_hide_extra_inflated_bytes(kind):
    part, xml = sample(kind)
    prefix = xml.encode()
    raw = bytearray(archive_bytes(part, prefix + b'UNVERIFIED TRAILING CONTENT'))
    directory = raw.index(b'PK\x01\x02')
    crc = zlib.crc32(prefix)
    struct.pack_into('<I', raw, 14, crc)
    struct.pack_into('<I', raw, 22, len(prefix))
    struct.pack_into('<I', raw, directory + 16, crc)
    struct.pack_into('<I', raw, directory + 24, len(prefix))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive, pytest.raises(zipfile.BadZipFile):
        read(archive, kind)


def test_completed_rows_can_stream_far_beyond_one_record_budget(monkeypatch):
    monkeypatch.setattr(xml_stream, 'MAX_XML_NODES', 4)
    body = '<worksheet><sheetData>' + ''.join(f'<row r="{n}"><c>value</c></row>\n' for n in range(1000)) + '</sheetData></worksheet>'
    with zipfile.ZipFile(io.BytesIO(archive_bytes('sheet.xml', body.encode()))) as archive:
        assert sum(1 for _ in workbook._iter_rows(archive, 'sheet.xml')) == 1000


def test_one_oversized_record_and_unreleased_metadata_are_bounded(monkeypatch):
    monkeypatch.setattr(xml_stream, 'MAX_XML_NODES', 4)
    for part, xml, kind in [
        ('sheet.xml', '<worksheet><sheetData><row>' + '<c/>' * 5 + '</row></sheetData></worksheet>', 'rows'),
        ('meta.xml', '<root>' + '<child/>' * 5 + '</root>', 'metadata'),
    ]:
        with zipfile.ZipFile(io.BytesIO(archive_bytes(part, xml.encode()))) as archive, pytest.raises(ValueError, match='复杂'):
            read(archive, kind)


def test_text_depth_and_unfinished_token_are_bounded(monkeypatch):
    monkeypatch.setattr(xml_stream, 'MAX_XML_TEXT', 64)
    with pytest.raises(ValueError, match='复杂'):
        list(xml_stream.parse_blocks([b'<root>' + b'x' * 65 + b'</root>']))
    monkeypatch.setattr(xml_stream, 'MAX_XML_DEPTH', 3)
    with pytest.raises(ValueError, match='复杂'):
        list(xml_stream.parse_blocks([b'<a><b><c><d/></c></b></a>']))
    monkeypatch.setattr(xml_stream, 'MAX_XML_TOKEN_BYTES', 32)
    with pytest.raises(ValueError, match='复杂'):
        list(xml_stream.parse_blocks([b'<a attr="'] + [b'x' * 8] * 8))


def test_retained_metadata_whitespace_counts_toward_workspace(monkeypatch):
    monkeypatch.setattr(xml_stream, 'MAX_XML_TEXT', 16)
    with pytest.raises(ValueError, match='复杂'):
        list(xml_stream.parse_blocks([b'<root><a/>          <b/>          <c/></root>']))


def test_only_actual_record_indentation_is_released(monkeypatch):
    monkeypatch.setattr(xml_stream, 'MAX_XML_TEXT', 64)
    body = b'<worksheet><sheetData>' + b'<row><c>x</c></row>          ' * 100 + b'</sheetData></worksheet>'
    assert sum(event == 'end' and node.tag == 'row' for event, node in
               xml_stream.parse_blocks([body], record='row', events=True)) == 100
    retained = b'<worksheet><sheetData><junk/>' + b' ' * 40 + b'<other/>' + b' ' * 40 + b'</sheetData></worksheet>'
    with pytest.raises(ValueError, match='复杂'):
        list(xml_stream.parse_blocks([retained], record='row', events=True))


@pytest.mark.parametrize('record,root,container', [('row', 'worksheet', 'sheetData'), ('si', 'sst', 'sst')])
def test_nested_lookalike_records_do_not_reset_metadata_budget(monkeypatch, record, root, container):
    monkeypatch.setattr(xml_stream, 'MAX_XML_NODES', 4)
    xml = f'<{root}><unexpected>' + f'<{record}/>' * 10 + f'</unexpected></{root}>'
    with pytest.raises(ValueError, match='复杂'):
        list(xml_stream.parse_blocks([xml.encode()], record=record, events=True))


def test_extension_row_is_not_returned_as_a_business_row():
    xml = b'<worksheet><unexpected><row r="99"/></unexpected><sheetData><row r="1"/></sheetData></worksheet>'
    with zipfile.ZipFile(io.BytesIO(archive_bytes('sheet.xml', xml))) as archive:
        assert [node.get('r') for node in workbook._iter_rows(archive, 'sheet.xml')] == ['1']


def test_nested_fake_container_does_not_release_its_metadata(monkeypatch):
    monkeypatch.setattr(xml_stream, 'MAX_XML_TEXT', 64)
    body = b'<worksheet><unexpected><sheetData>' + b'<row/>' + b' ' * 40 + b'<row/>' + b' ' * 40 + b'</sheetData></unexpected></worksheet>'
    with pytest.raises(ValueError, match='复杂'):
        list(xml_stream.parse_blocks([body], record='row', events=True))


def test_picture_capture_has_a_structural_budget(tmp_path, monkeypatch):
    from test_workbook import make_book
    rows = ''.join(f'<row r="{n}"><c r="B{n}"><f>DISPIMG("IMG_A",1)</f></c></row>' for n in (2, 3))
    source = make_book(tmp_path, rows)
    monkeypatch.setattr(workbook, 'MAX_PICTURE_REFERENCES', 1)
    with pytest.raises(ValueError, match='图片引用过多'):
        workbook.inspect_workbook(str(source), str(tmp_path / 'work'))


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le', 'utf-16-be'])
def test_normal_unicode_workbook_xml_still_parses(encoding):
    part, xml = sample('strings')
    xml = xml.replace('value', '编号HSD0001')
    bom = b'' if encoding == 'utf-8' else (b'\xff\xfe' if encoding.endswith('le') else b'\xfe\xff')
    with zipfile.ZipFile(io.BytesIO(archive_bytes(part, bom + xml.encode(encoding)))) as archive:
        assert workbook._strings(archive, {0})[0] == {0: '编号HSD0001'}


def test_retained_identifiers_have_an_aggregate_workspace_budget(monkeypatch):
    monkeypatch.setattr(workbook, 'MAX_CAPTURED_TEXT_BYTES', 8)
    part, xml = sample('rows')
    with zipfile.ZipFile(io.BytesIO(archive_bytes(part, xml.encode()))) as archive:
        with pytest.raises(ValueError, match='编号数据过多'):
            workbook._number_cells(archive, part)


def test_captured_shared_string_workspace_is_bounded(monkeypatch):
    monkeypatch.setattr(workbook, 'MAX_CAPTURED_TEXT_BYTES', 4)
    part, xml = sample('strings')
    with zipfile.ZipFile(io.BytesIO(archive_bytes(part, xml.encode()))) as archive:
        with pytest.raises(ValueError, match='编号或图片引用过多'):
            workbook._strings(archive, {0})
