"""Generate non-business image/workbook batches for desktop workflow acceptance."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import random
import sys
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw
import pymupdf


def artwork(seed: int) -> bytes:
    rng = random.Random(seed)
    image = Image.new("RGB", (1000, 190), (248, 246, 241))
    draw = ImageDraw.Draw(image)
    for index in range(110):
        x, y = rng.randrange(5, 950), rng.randrange(5, 150)
        color = tuple(rng.randrange(15, 190) for _ in range(3))
        draw.ellipse((x, y, x + rng.randrange(8, 34), y + 29), fill=color)
        draw.text((x, y), str(index), fill=(13, 16, 20))
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def workbook(path: Path, rows: list[tuple[str, bytes | None]]) -> None:
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    drawing = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
    art = "http://schemas.openxmlformats.org/drawingml/2006/main"
    images, image_rels, sheet_rows = [], [], []
    parts = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": f'<Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets><sheet name="流程验收" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://www.wps.cn/officeDocument/2020/cellImage" Target="cellimages.xml"/></Relationships>',
    }
    for index, (number, picture) in enumerate(rows, 2):
        identity = f"IMG_{index}"
        number_cell = f'<c r="A{index}" t="inlineStr"><is><t>{escape(number)}</t></is></c>'
        sheet_rows.append(f'<row r="{index}">{number_cell}<c r="B{index}" t="str"><f>_xlfn.DISPIMG(&quot;{identity}&quot;,1)</f><v>#VALUE!</v></c></row>')
        if picture is not None:
            images.append(f'<cellImage><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{index}" name="{identity}"/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="p{index}"/></xdr:blipFill></xdr:pic></cellImage>')
            image_rels.append(f'<Relationship Id="p{index}" Type="{rel}/image" Target="media/p{index}.png"/>')
            parts[f"xl/media/p{index}.png"] = picture
    parts["xl/worksheets/sheet1.xml"] = f'<worksheet xmlns="{main}"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    parts["xl/cellimages.xml"] = f'<cellImages xmlns="http://www.wps.cn/officeDocument/2017/etCustomData" xmlns:xdr="{drawing}" xmlns:a="{art}" xmlns:r="{rel}">{"".join(images)}</cellImages>'
    parts["xl/_rels/cellimages.xml.rels"] = f'<Relationships xmlns="{pkg}">{"".join(image_rels)}</Relationships>'
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def ai_file(path: Path, picture: bytes) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=1000, height=190)
        page.insert_image(page.rect, stream=picture)
        document.save(path)


def generate(output: Path) -> dict:
    batches = {}
    a, b, c = artwork(2301), artwork(7013), artwork(9847)
    for name, rows, originals in [
        ("all_reliable", [("KEEP0001", a), ("", b), ("", c)], [a, b, c]),
        ("ambiguous", [("KEEP0001", a), ("", b), ("", b), ("MISSING0004", None)], [a, b, b]),
    ]:
        directory = output / name
        directory.mkdir(parents=True, exist_ok=True)
        sources = directory / "AI"
        sources.mkdir(exist_ok=True)
        table = directory / "input.xlsx"
        workbook(table, rows)
        for index, picture in enumerate(originals):
            ai_file(sources / f"design_{index}.ai", picture)
        batches[name] = {"workbook_path": str(table.resolve()), "source_path": str(sources.resolve()),
                         "output_root": str((directory / "export").resolve()), "start_number": 1}
    (output / "fixtures.json").write_text(json.dumps(batches, ensure_ascii=False, indent=2), "utf-8")
    return batches


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "tmp" / "v11_workflow_fixtures"
    print(json.dumps(generate(destination), ensure_ascii=False, indent=2))
