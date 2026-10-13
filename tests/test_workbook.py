from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image
import pytest

from hsd_tool.workbook import inspect_workbook, write_numbered_workbook

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
DRAW = "http://schemas.openxmlformats.org/drawingml/2006/main"


def png_bytes(color="red"):
    stream = BytesIO()
    Image.new("RGB", (16, 12), color).save(stream, "PNG")
    return stream.getvalue()


def make_book(tmp_path, rows=None, *, image_data=None, second_sheet=False, drawing=None):
    if rows is None:
        rows = '<row r="2"><c r="A2" s="1"/><c r="B2" t="str"><f>_xlfn.DISPIMG(&quot;IMG_A&quot;,1)</f><v>#VALUE!</v></c></row>'
    sheet2 = '<sheet name="隐藏表" sheetId="2" state="hidden" r:id="rId2"/>' if second_sheet else ""
    rel2 = f'<Relationship Id="rId2" Type="{REL}/worksheet" Target="worksheets/sheet2.xml"/>' if second_sheet else ""
    parts = {
        "xl/workbook.xml": f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets><sheet name="恒尚达" sheetId="1" r:id="rId1"/>{sheet2}</sheets></workbook>'.encode(),
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>{rel2}<Relationship Id="rId3" Type="http://www.wps.cn/officeDocument/2020/cellImage" Target="cellimages.xml"/></Relationships>'.encode(),
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN}" xmlns:r="{REL}"><dimension ref="A1:B500000"/><sheetData>{rows}</sheetData><extLst><ext uri="preserve-me"/></extLst></worksheet>'.encode(),
        "xl/sharedStrings.xml": f'<sst xmlns="{MAIN}"><si><t>00007</t></si><si><t></t></si><si><r><t>HSD</t></r><r><t>0009</t></r></si><si><t>=DISPIMG(&quot;IMG_A&quot;,1)</t></si></sst>'.encode(),
        "xl/styles.xml": f'<styleSheet xmlns="{MAIN}"><numFmts count="2"><numFmt numFmtId="164" formatCode="00000"/><numFmt numFmtId="165" formatCode="&quot;HSD&quot;0000"/></numFmts><cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="165"/></cellXfs></styleSheet>'.encode(),
        "xl/cellimages.xml": f'<cellImages xmlns="http://www.wps.cn/officeDocument/2017/etCustomData" xmlns:xdr="{XDR}" xmlns:a="{DRAW}" xmlns:r="{REL}"><cellImage><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="IMG_A"/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="img1"/></xdr:blipFill></xdr:pic></cellImage></cellImages>'.encode(),
        "xl/_rels/cellimages.xml.rels": f'<Relationships xmlns="{PKG}"><Relationship Id="img1" Type="{REL}/image" Target="media/image1.png"/></Relationships>'.encode(),
        "xl/media/image1.png": png_bytes() if image_data is None else image_data,
        "docProps/custom.xml": b'<custom preserve="exact bytes">\r\nunchanged</custom>',
    }
    if second_sheet:
        parts["xl/worksheets/sheet2.xml"] = f'<worksheet xmlns="{MAIN}"><sheetData><row r="8"><c r="A8" t="inlineStr"><is><t>HIDDEN001</t></is></c><c r="B8" t="str"><f>DISPIMG(&quot;IMG_A&quot;,1)</f></c></row></sheetData></worksheet>'.encode()
    if drawing:
        parts["xl/worksheets/_rels/sheet1.xml.rels"] = f'<Relationships xmlns="{PKG}"><Relationship Id="dr1" Type="{REL}/drawing" Target="../drawings/drawing1.xml"/></Relationships>'.encode()
        parts["xl/drawings/drawing1.xml"] = f'<xdr:wsDr xmlns:xdr="{XDR}" xmlns:a="{DRAW}" xmlns:r="{REL}">{drawing}</xdr:wsDr>'.encode()
        parts["xl/drawings/_rels/drawing1.xml.rels"] = f'<Relationships xmlns="{PKG}"><Relationship Id="img1" Type="{REL}/image" Target="../media/image1.png"/></Relationships>'.encode()
    target = tmp_path / "input.xlsx"
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.comment = b"keep archive comment"
        for name, data in parts.items():
            archive.writestr(name, data)
    return target


def image_cell(row, identifier="IMG_A"):
    return f'<c r="B{row}" t="str"><f>_xlfn.DISPIMG(&quot;{identifier}&quot;,1)</f></c>'


def test_reads_wps_images_and_preserves_displayed_leading_zeros(tmp_path):
    rows = (
        '<row r="1"><c r="A1" t="inlineStr"><is><t>HSD0100</t></is></c></row>'
        '<row r="2"><c r="A2" t="s"><v>0</v></c>' + image_cell(2) + '</row>'
        '<row r="3"><c r="A3" s="1"><v>8</v></c>' + image_cell(3) + '</row>'
        '<row r="4"><c r="A4" t="s"><v>2</v></c>' + image_cell(4) + '</row>'
        '<row r="5"><c r="A5" s="2"><v>10</v></c>' + image_cell(5) + '</row>'
        '<row r="500000"><c r="B500000" t="s"><v>0</v></c></row>'
    )
    source = make_book(tmp_path, rows, second_sheet=True)
    before = source.read_bytes()
    result = inspect_workbook(str(source), str(tmp_path / "work"))
    assert result["sheet_name"] == "恒尚达"
    assert result["sheets"] == [{"name": "恒尚达", "hidden": False}, {"name": "隐藏表", "hidden": True}]
    assert [row["number"] for row in result["rows"]] == ["00007", "00008", "HSD0009", "HSD0010"]
    assert result["reserved_numbers"] == ["HSD0100", "00007", "00008", "HSD0009", "HSD0010"]
    assert all(row["issue"] is None and Path(row["image_path"]).is_absolute() for row in result["rows"])
    assert source.read_bytes() == before
    hidden = inspect_workbook(str(source), str(tmp_path / "hidden"), "隐藏表")
    assert [row["row_number"] for row in hidden["rows"]] == [8]


def test_shared_string_picture_and_missing_reference_are_not_silently_lost(tmp_path):
    rows = ('<row r="2"><c r="B2" t="s"><v>3</v></c></row>'
            '<row r="3">' + image_cell(3, "DOES_NOT_EXIST") + '</row>')
    source = make_book(tmp_path, rows)
    result = inspect_workbook(str(source), str(tmp_path / "work"))
    assert len(result["rows"]) == 2
    assert result["rows"][0]["image_path"]
    assert result["rows"][1]["image_path"] is None
    assert "引用" in result["rows"][1]["issue"]


def test_unreadable_image_returns_issue(tmp_path):
    source = make_book(tmp_path, image_data=b"not an image")
    row = inspect_workbook(str(source), str(tmp_path / "work"))["rows"][0]
    assert row["image_path"] is None
    assert "解码" in row["issue"]


def test_only_visible_floating_images_anchored_in_column_b_are_included(tmp_path):
    def anchor(col, row, hidden=False):
        return f'<xdr:oneCellAnchor><xdr:from><xdr:col>{col}</xdr:col><xdr:row>{row - 1}</xdr:row></xdr:from><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" hidden="{int(hidden)}"/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="img1"/></xdr:blipFill></xdr:pic></xdr:oneCellAnchor>'
    source = make_book(tmp_path, '<row r="2"/><row r="3"/><row r="4"/>',
                       drawing=anchor(0, 2) + anchor(1, 3) + anchor(1, 4, True))
    result = inspect_workbook(str(source), str(tmp_path / "work"))
    assert [row["row_number"] for row in result["rows"]] == [3]


def test_surgical_export_changes_only_target_cell_and_preserves_parts(tmp_path):
    rows = ('<row r="2"><c r="A2" s="1"/><c r="B2" t="str"><f>_xlfn.DISPIMG(&quot;IMG_A&quot;,1)</f><v>#VALUE!</v></c></row>'
            '<row r="3"><c r="A3" t="s"><v>1</v></c>' + image_cell(3) + '</row>'
            '<row r="4">' + image_cell(4) + '</row>')
    source = make_book(tmp_path, rows, second_sheet=True)
    before = source.read_bytes()
    output = tmp_path / "output.xlsx"
    write_numbered_workbook(str(source), str(output), "恒尚达", {2: "HSD0001", 3: "HSD0002", 4: "HSD0003"})
    assert source.read_bytes() == before
    with ZipFile(source) as original, ZipFile(output) as updated:
        assert original.namelist() == updated.namelist()
        assert original.comment == updated.comment
        for name in original.namelist():
            if name != "xl/worksheets/sheet1.xml":
                assert original.read(name) == updated.read(name), name
        old_xml = original.read("xl/worksheets/sheet1.xml")
        new_xml = updated.read("xl/worksheets/sheet1.xml")
        # Removing the three intended A-cell edits recovers the exact source XML.
        for row in (2, 3, 4):
            pattern = rb'<c\b[^>]*r="A' + str(row).encode() + rb'"[^>]*?(?:/>|>.*?</c>)'
            old_xml = re.sub(pattern, b"", old_xml)
            new_xml = re.sub(pattern, b"", new_xml)
        assert new_xml == old_xml
    result = inspect_workbook(str(output), str(tmp_path / "readback"))
    assert [row["number"] for row in result["rows"]] == ["HSD0001", "HSD0002", "HSD0003"]


@pytest.mark.parametrize("cell", [
    '<c r="A2" t="s"><v>0</v></c>',
    '<c r="A2"><v>0</v></c>',
    '<c r="A2" t="inlineStr"><is><t> </t></is></c>',
    '<c r="A2"><f>IF(1=1,&quot;&quot;,&quot;&quot;)</f><v/></c>',
])
def test_nonblank_numbers_and_formulas_cannot_be_overwritten(tmp_path, cell):
    source = make_book(tmp_path, '<row r="2">' + cell + image_cell(2) + '</row>')
    output = tmp_path / "output.xlsx"
    with pytest.raises(ValueError, match="拒绝覆盖"):
        write_numbered_workbook(str(source), str(output), "恒尚达", {2: "HSD0001"})
    assert not output.exists()


def test_formula_blank_issue_and_cached_formula_display(tmp_path):
    source = make_book(tmp_path,
        '<row r="2"><c r="A2"><f>IF(1=1,&quot;&quot;,&quot;&quot;)</f><v/></c>' + image_cell(2) + '</row>'
        '<row r="3"><c r="A3" s="1"><f>1+7</f><v>8</v></c>' + image_cell(3) + '</row>')
    result = inspect_workbook(str(source), str(tmp_path / "work"))
    assert result["rows"][0]["number"] == ""
    assert "公式" in result["rows"][0]["issue"]
    assert result["rows"][1]["number"] == "00008"
    assert result["rows"][1]["issue"] is None


def test_number_formula_error_cannot_be_used_as_identifier(tmp_path):
    source = make_book(tmp_path, '<row r="2"><c r="A2" t="e"><f>1/0</f><v>#DIV/0!</v></c>' + image_cell(2) + '</row>')
    result = inspect_workbook(str(source), str(tmp_path / "work"))
    assert result["rows"][0]["number"] == "#DIV/0!"
    assert "错误值" in result["rows"][0]["issue"]


def test_existing_output_and_source_overwrite_blocked(tmp_path):
    source = make_book(tmp_path)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="分开保存"):
        write_numbered_workbook(str(source), str(source), "恒尚达", {2: "HSD0001"})
    output = tmp_path / "output.xlsx"
    output.write_bytes(b"DO NOT REPLACE")
    with pytest.raises(FileExistsError):
        write_numbered_workbook(str(source), str(output), "恒尚达", {2: "HSD0001"})
    assert output.read_bytes() == b"DO NOT REPLACE"
    assert source.read_bytes() == original


def test_duplicate_source_coordinates_are_rejected(tmp_path):
    source = make_book(tmp_path, '<row r="2"><c r="A2"><v>7</v></c><c r="A2"/>' + image_cell(2) + '</row>')
    with pytest.raises(ValueError, match="重复出现"):
        write_numbered_workbook(str(source), str(tmp_path / "out.xlsx"), "恒尚达", {2: "HSD0001"})


def test_real_sample_count_and_whole_package_preservation(tmp_path):
    sample = Path(__file__).resolve().parents[1] / "测试样本" / "10月表格.xlsx"
    if not sample.exists():
        pytest.skip("Repository sample not present")
    source_hash = sha256(sample.read_bytes()).hexdigest()
    result = inspect_workbook(str(sample), str(tmp_path / "work"))
    assert result["sheet_name"] == "恒尚达"
    assert len(result["rows"]) == 60
    assert [row["row_number"] for row in result["rows"]] == list(range(2, 62))
    assert [row["number"] for row in result["rows"]] == [f"{number:05}" for number in range(1, 61)]
    assert not any(row["issue"] for row in result["rows"])
    output = tmp_path / "sample_copy.xlsx"
    write_numbered_workbook(str(sample), str(output), result["sheet_name"], {})
    with ZipFile(sample) as original, ZipFile(output) as copied:
        assert original.namelist() == copied.namelist()
        assert all(original.read(name) == copied.read(name) for name in original.namelist())
    # Exercise a real WPS export with a missing number, entirely on a disposable
    # copy. All 60 images and all custom WPS parts must survive the actual edit.
    missing_number = tmp_path / "sample_missing_number.xlsx"
    with ZipFile(sample) as original, ZipFile(missing_number, "w") as modified:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                data, count = re.subn(rb'<c r="A2"[^>]*>.*?</c>', b'<c r="A2" s="12"/>', data, count=1)
                assert count == 1
            modified.writestr(info, data)
    numbered = tmp_path / "sample_numbered.xlsx"
    write_numbered_workbook(str(missing_number), str(numbered), result["sheet_name"], {2: "HSD0001"})
    with ZipFile(sample) as original, ZipFile(numbered) as final:
        for name in original.namelist():
            if name != "xl/worksheets/sheet1.xml":
                assert original.read(name) == final.read(name)
        worksheet = ET.fromstring(final.read("xl/worksheets/sheet1.xml"))
        assert worksheet.find(f".//{{{MAIN}}}c[@r='A2']/{{{MAIN}}}is/{{{MAIN}}}t").text == "HSD0001"
    assert sha256(sample.read_bytes()).hexdigest() == source_hash
