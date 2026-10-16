"""Read the fixed WPS template and change identifiers without re-saving its images.

Only the selected worksheet XML is patched on export. All other ZIP entries are
copied as bytes, including WPS cellimages, drawings, formulas, and custom parts.
The reader streams the worksheet: a misleading 285,499-row used range must not
become 285,499 product records or a large in-memory worksheet object tree.
"""
from __future__ import annotations

from collections import defaultdict
import copy
from decimal import Decimal, InvalidOperation
import errno
import os
from pathlib import Path
import posixpath
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile, ZIP64_LIMIT

from PIL import Image
from .archive_io import member_blocks

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
# Compatibility names: bytes are limited by available resources, not fixed caps.
MAX_PART_BYTES = None
MAX_ARCHIVE_BYTES = None
MAX_IMAGE_BYTES = None
MAX_IMAGE_PIXELS = 40_000_000
IO_CHUNK_BYTES = 1024 * 1024
SPOOL_MEMORY_BYTES = 8 * 1024 * 1024
DISPIMG = re.compile(r'(?:_xlfn\.)?DISPIMG\s*\(\s*"([^"\r\n]+)"', re.I)
CELL_REF = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")
XML_NAME = rb"(?:[A-Za-z_][\w.-]*:)?"
ROW_XML = re.compile(rb"<(?P<name>" + XML_NAME + rb"row)\b(?P<attrs>[^<>]*?)(?:\s*/>|>.*?</(?P=name)\s*>)", re.S)
CELL_XML = re.compile(rb"<(?P<name>" + XML_NAME + rb"c)\b(?P<attrs>[^<>]*?)(?:\s*/>|>.*?</(?P=name)\s*>)", re.S)
ATTR_R = re.compile(rb"(?:^|\s)r\s*=\s*([\"'])(.*?)\1", re.S)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element if _local(child.tag) == name), None)


def _text(element: ET.Element | None) -> str:
    return "" if element is None else "".join(element.itertext())


def _rich_text(element: ET.Element | None) -> str:
    # Phonetic annotations are not part of the displayed identifier.
    if element is None:
        return ""
    return "".join(_text(node) for child in element if _local(child.tag) != "rPh"
                   for node in ([child] if _local(child.tag) == "t" else list(child))
                   if _local(node.tag) == "t")


def _validate_archive(archive: ZipFile) -> None:
    entries = archive.infolist()
    if len(entries) > 20_000:
        raise ValueError("表格内部文件过多，无法安全读取。")
    if len({item.filename for item in entries}) != len(entries):
        raise ValueError("表格包含重复的内部文件，无法确定数据来源。")
    for item in entries:
        if item.file_size < 0 or item.compress_size < 0:
            raise ValueError("表格内部文件长度无效。")
        if item.flag_bits & 1:
            raise ValueError("暂不支持加密表格，请先另存为未加密的 XLSX。")


def _xml(archive: ZipFile, part: str) -> ET.Element:
    parser, tail, read = ET.XMLParser(), b"", 0
    info = archive.getinfo(part)
    for block in member_blocks(archive, info):
        read += len(block)
        upper = (tail + block).upper()
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise ValueError("表格包含不支持的 XML 声明。")
        tail = upper[-16:]
        parser.feed(block)
    if read != info.file_size:
        raise ValueError("表格内部文件未完整读取。")
    return parser.close()


def _copy_member(archive: ZipFile, info, destination) -> None:
    """Consume through EOF for CRC and actual-length validation, in fixed blocks."""
    copied = 0
    for block in member_blocks(archive, info):
        copied += len(block)
        if copied > info.file_size:
            raise ValueError("表格内部文件实际长度不符。")
        destination.write(block)
    if copied != info.file_size:
        raise ValueError("表格内部文件未完整读取。")


def _target(part: str, target: str) -> str:
    if "\\" in target or ":" in target or "\x00" in target:
        raise ValueError("表格内部图片路径无效。")
    resolved = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                 else posixpath.join(posixpath.dirname(part), target))
    if resolved == ".." or resolved.startswith("../"):
        raise ValueError("表格内部图片路径越界。")
    return resolved


def _relationships(archive: ZipFile, part: str) -> dict[str, dict]:
    rel_part = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if rel_part not in archive.namelist():
        return {}
    return {node.get("Id", ""): {"part": _target(part, node.get("Target", "")),
                                     "type": node.get("Type", "")}
            for node in _xml(archive, rel_part)
            if node.get("TargetMode", "").lower() != "external"}


def _sheets(archive: ZipFile) -> list[dict]:
    rels = _relationships(archive, "xl/workbook.xml")
    result = []
    for node in _xml(archive, "xl/workbook.xml").iter():
        if _local(node.tag) != "sheet":
            continue
        rid = next((value for key, value in node.attrib.items() if _local(key) == "id"), "")
        if rid not in rels:
            raise ValueError("表格工作表关系损坏。")
        result.append({"name": node.get("name", ""), "hidden": node.get("state", "visible") != "visible",
                       "part": rels[rid]["part"]})
    if not result:
        raise ValueError("表格中没有工作表。")
    return result


def _select_sheet(sheets: list[dict], sheet_name: str | None) -> dict:
    selected = next((sheet for sheet in sheets if sheet["name"] == sheet_name), None) if sheet_name is not None else next((sheet for sheet in sheets if not sheet["hidden"]), None)
    if selected is None:
        raise ValueError("找不到指定工作表。" if sheet_name is not None else "表格中没有可见工作表。")
    return selected


def _iter_rows(archive: ZipFile, part: str):
    with archive.open(part) as stream:
        parent = None
        for event, node in ET.iterparse(stream, events=("start", "end")):
            name = _local(node.tag)
            if event == "start" and name == "sheetData":
                parent = node
            elif event == "end" and name == "row":
                yield node
                node.clear()
                if parent is not None:
                    parent.clear()


def _strings(archive: ZipFile, wanted: set[int]) -> tuple[dict[int, str], dict[int, str]]:
    selected, pictures = {}, {}
    if "xl/sharedStrings.xml" not in archive.namelist():
        return selected, pictures
    with archive.open("xl/sharedStrings.xml") as stream:
        index = 0
        root = None
        for event, node in ET.iterparse(stream, events=("start", "end")):
            if root is None:
                root = node
            if event == "end" and _local(node.tag) == "si":
                value = _rich_text(node)
                if index in wanted:
                    selected[index] = value
                if "DISPIMG" in value.upper():
                    pictures[index] = value
                node.clear()
                root.clear()
                index += 1
    return selected, pictures


def _styles(archive: ZipFile) -> list[str]:
    if "xl/styles.xml" not in archive.namelist():
        return []
    root = _xml(archive, "xl/styles.xml")
    custom = {int(node.get("numFmtId", "0")): node.get("formatCode", "")
              for node in root.iter() if _local(node.tag) == "numFmt"}
    cell_xfs = _child(root, "cellXfs")
    return [custom.get(int(node.get("numFmtId", "0")), "") for node in cell_xfs] if cell_xfs is not None else []


def _display_numeric(value: str, fmt: str) -> str:
    """Handle identifier formats such as 00000 and \"HSD\"0000, not dates."""
    try:
        number = Decimal(value)
    except InvalidOperation:
        return value
    if not number.is_finite():
        return value
    if number == number.to_integral():
        plain = str(int(number))
        section = fmt.split(";", 1)[0]
        token = re.fullmatch(r'(?P<prefix>(?:"[^"]*"|\\.|[^0#?.,%Ee@;\[\]0-9])*)(?P<zeros>0+)(?P<suffix>(?:"[^"]*"|\\.|[^0#?.,%Ee@;\[\]0-9])*)', section)
        if token and number >= 0:
            literal = lambda text: re.sub(r'"([^"]*)"|\\(.)', lambda match: match.group(1) if match.group(1) is not None else match.group(2), text)
            return literal(token["prefix"]) + plain.zfill(len(token["zeros"])) + literal(token["suffix"])
        return plain
    return format(number, "f").rstrip("0").rstrip(".") if "." in format(number, "f") else format(number, "f")


def _cell_value(cell: ET.Element | None, strings: dict[int, str], styles: list[str]) -> str:
    if cell is None:
        return ""
    kind = cell.get("t", "n")
    value = _text(_child(cell, "v"))
    if kind == "s":
        if not value:
            return ""
        try:
            return strings[int(value)]
        except (ValueError, KeyError) as exc:
            raise ValueError(f"{cell.get('r', '')} 的文字索引损坏。") from exc
    if kind == "inlineStr":
        return _rich_text(_child(cell, "is"))
    if kind in {"str", "e", "b", "d"} or not value:
        return value
    try:
        style = int(cell.get("s", "0"))
        fmt = styles[style] if 0 <= style < len(styles) else ""
    except ValueError:
        fmt = ""
    return _display_numeric(value, fmt)


def _number_cells(archive: ZipFile, part: str) -> tuple[dict[int, ET.Element], set[int]]:
    numbers, wanted = {}, set()
    for row in _iter_rows(archive, part):
        for cell in row:
            ref = CELL_REF.fullmatch(cell.get("r", ""))
            if ref and ref[1] == "A":
                coordinate = int(ref[2])
                if coordinate in numbers:
                    raise ValueError(f"A{coordinate} 在表格中重复出现，无法安全读取。")
                numbers[coordinate] = ET.fromstring(ET.tostring(cell))
                value = _text(_child(cell, "v"))
                if cell.get("t") == "s" and value:
                    try:
                        wanted.add(int(value))
                    except ValueError as exc:
                        raise ValueError(f"{cell.get('r')} 的文字索引损坏。") from exc
    return numbers, wanted


def _cell_images(archive: ZipFile) -> dict[str, str | None]:
    result = {}
    parts = [rel["part"] for rel in _relationships(archive, "xl/workbook.xml").values()
             if rel["type"].lower().endswith("/cellimage")]
    if not parts and "xl/cellimages.xml" in archive.namelist():
        parts = ["xl/cellimages.xml"]
    for part in parts:
        rels = _relationships(archive, part)
        for picture in _xml(archive, part).iter():
            if _local(picture.tag) != "pic":
                continue
            name = next((node.get("name") for node in picture.iter() if _local(node.tag) == "cNvPr"), None)
            rid = next((value for node in picture.iter() if _local(node.tag) == "blip"
                        for key, value in node.attrib.items() if _local(key) == "embed"), None)
            if name:
                target = rels.get(rid, {}).get("part")
                # Conflicting image IDs must never pick an arbitrary source.
                result[name] = None if name in result and result[name] != target else target
    return result


def _floating_images(archive: ZipFile, sheet_part: str) -> dict[int, list[str | None]]:
    rows = defaultdict(list)
    for relation in _relationships(archive, sheet_part).values():
        if not relation["type"].endswith("/drawing"):
            continue
        part = relation["part"]
        rels = _relationships(archive, part)
        for anchor in _xml(archive, part):
            if _local(anchor.tag) not in {"oneCellAnchor", "twoCellAnchor"}:
                continue
            origin = _child(anchor, "from")
            if origin is None or _text(_child(origin, "col")) != "1":
                continue
            try:
                row = int(_text(_child(origin, "row"))) + 1
            except ValueError:
                continue
            for picture in anchor:
                if _local(picture.tag) != "pic":
                    continue
                if any(node.get("hidden") in {"1", "true"} for node in picture.iter() if _local(node.tag) == "cNvPr"):
                    continue
                rid = next((value for node in picture.iter() if _local(node.tag) == "blip"
                            for key, value in node.attrib.items() if _local(key) == "embed"), None)
                rows[row].append(rels.get(rid, {}).get("part"))
    return rows


def _extract_image(archive: ZipFile, part: str | None, destination: Path) -> tuple[str | None, str | None]:
    if not part or part not in archive.namelist():
        return None, "表格图片引用失效或图片不存在。"
    try:
        info = archive.getinfo(part)
        if info.file_size > SPOOL_MEMORY_BYTES and info.file_size > shutil.disk_usage(destination.parent).free:
            return None, "主机磁盘空间不足，无法暂存表格图片，请清理后重试。"
        # Seekable spooling avoids repeated ZIP decompression during image
        # decoding and prevents encoded-image memory growing with file bytes.
        with tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES, dir=destination.parent) as staged:
            _copy_member(archive, info, staged)
            staged.seek(0)
            with Image.open(staged) as preview:
                if preview.width * preview.height > MAX_IMAGE_PIXELS:
                    return None, "表格图片像素过大，需人工处理。"
                preview.load()
                # Normalize the preview only; the original XLSX bytes stay intact.
                rgba = preview.convert("RGBA")
                background = Image.new("RGBA", rgba.size, "white")
                background.alpha_composite(rgba)
                background.convert("RGB").save(destination, "PNG")
        return str(destination.resolve()), None
    except (OSError, ValueError, Image.DecompressionBombError, BadZipFile):
        return None, "表格图片无法解码，需人工处理。"


def inspect_workbook(path: str, work_dir: str, sheet_name: str | None = None) -> dict:
    """Return image-bearing B rows and displayed A identifiers from one sheet."""
    destination = Path(work_dir).resolve() / "workbook_images"
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with ZipFile(path) as archive:
            _validate_archive(archive)
            sheets = _sheets(archive)
            sheet = _select_sheet(sheets, sheet_name)
            cells, wanted = _number_cells(archive, sheet["part"])
            strings, string_images = _strings(archive, wanted)
            styles = _styles(archive)
            numbers = {row: _cell_value(cell, strings, styles) for row, cell in cells.items()}
            image_ids = _cell_images(archive)
            pictures = _floating_images(archive, sheet["part"])
            issues = {}
            for row in _iter_rows(archive, sheet["part"]):
                for cell in row:
                    ref = CELL_REF.fullmatch(cell.get("r", ""))
                    if not ref or ref[1] != "B":
                        continue
                    formula = _text(_child(cell, "f"))
                    if cell.get("t") == "s":
                        value = _text(_child(cell, "v"))
                        try:
                            text = string_images.get(int(value), "") if value else ""
                        except ValueError:
                            text = ""
                    else:
                        text = _rich_text(_child(cell, "is")) or _text(_child(cell, "v"))
                    formula = formula or text
                    if "DISPIMG" not in formula.upper():
                        continue
                    row_number = int(ref[2])
                    match = DISPIMG.search(formula)
                    pictures[row_number].append(image_ids.get(match[1]) if match else None)
                    if not match:
                        issues[row_number] = "无法解析此行的 DISPIMG 图片引用。"
            result_rows = []
            for row_number, parts in sorted(pictures.items()):
                issue = issues.get(row_number)
                # A repeated relationship to the exact same image is harmless.
                unique = list(dict.fromkeys(parts))
                image_path, image_issue = _extract_image(archive, unique[0], destination / f"r{row_number}.png")
                if len(unique) > 1:
                    issue = "此行有多张不同图片，需人工确认。"
                if not issue:
                    issue = image_issue
                if row_number in cells and _child(cells[row_number], "f") is not None and not numbers.get(row_number):
                    issue = "编号单元格含公式且没有可用结果，请在副本中确认后重试。"
                if row_number in cells and cells[row_number].get("t") == "e":
                    issue = "编号单元格为表格错误值，请在副本中修正后重试。"
                result_rows.append({"id": f"r{row_number}", "row_number": row_number,
                                    "number": numbers.get(row_number, ""), "image_path": image_path, "issue": issue})
            return {"sheets": [{"name": s["name"], "hidden": s["hidden"]} for s in sheets],
                    "sheet_name": sheet["name"], "rows": result_rows,
                    "reserved_numbers": list(dict.fromkeys(value for value in numbers.values() if value != ""))}
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError("无法读取表格，请确认这是完整、未加密的 XLSX 文件。") from exc


def _attribute_r(attributes: bytes) -> bytes | None:
    match = ATTR_R.search(attributes)
    return match[2] if match else None


def _new_cell(name: bytes, attributes: bytes, value: str) -> bytes:
    attributes = re.sub(rb"\s+t\s*=\s*([\"']).*?\1", b"", attributes, flags=re.S)
    attributes = attributes.rstrip().rstrip(b"/").rstrip()
    prefix = name[:-1]
    return (b"<" + name + attributes + b' t="inlineStr"><' + prefix + b'is><' + prefix
            + b't xml:space="preserve">' + escape(value).encode("utf-8") + b"</" + prefix
            + b"t></" + prefix + b"is></" + name + b">")


def _patch_sheet(xml: bytes, assignments: dict[int, str]) -> bytes:
    pending = dict(assignments)
    changes = []
    prefix_match = re.search(rb"<(" + XML_NAME + rb")worksheet\b", xml)
    prefix = prefix_match[1] if prefix_match else b""
    for row_match in ROW_XML.finditer(xml):
        reference = _attribute_r(row_match["attrs"])
        if reference is None or not reference.isdigit():
            continue
        row_number = int(reference)
        if row_number not in pending:
            continue
        value = pending.pop(row_number)
        row_xml = row_match[0]
        cell_ref = f"A{row_number}".encode("ascii")
        found = None
        for cell in CELL_XML.finditer(row_xml):
            if _attribute_r(cell["attrs"]) == cell_ref:
                if found is not None:
                    raise ValueError(f"A{row_number} 在表格中重复出现，无法安全回填。")
                found = cell
        if found is not None:
            new_cell = _new_cell(found["name"], found["attrs"], value)
            updated = row_xml[:found.start()] + new_cell + row_xml[found.end():]
        else:
            new_cell = _new_cell(prefix + b"c", b' r="' + cell_ref + b'"', value)
            start_end = row_xml.find(b">") + 1
            if row_xml[:start_end].rstrip().endswith(b"/>"):
                updated = row_xml[:start_end - 2].rstrip() + b">" + new_cell + b"</" + row_match["name"] + b">"
            else:
                updated = row_xml[:start_end] + new_cell + row_xml[start_end:]
        changes.append((row_match.start(), row_match.end(), updated))
    if pending:
        # Fixed-template rows must already exist; do not change dimensions or
        # invent layout for a floating image anchored outside the used range.
        raise ValueError("目标编号行不存在：" + "、".join(f"A{row}" for row in sorted(pending)))
    fragments, cursor = [], 0
    for start, end, replacement in changes:
        fragments.extend((xml[cursor:start], replacement))
        cursor = end
    fragments.append(xml[cursor:])
    return b"".join(fragments)


def write_numbered_workbook(source: str, destination: str, sheet_name: str, assignments: dict[int, str]) -> None:
    """Fill blank A cells only, refusing replacement or an existing output file."""
    source_path, destination_path = Path(source).resolve(), Path(destination).resolve()
    if source_path == destination_path:
        raise ValueError("输出表格必须与原表格分开保存。")
    if destination_path.exists():
        raise FileExistsError("输出表格已存在，请选择新的输出位置。")
    for row, number in assignments.items():
        if isinstance(row, bool) or not isinstance(row, int) or not 1 <= row <= 1_048_576:
            raise ValueError("编号行必须是有效的 Excel 行号。")
        if not isinstance(number, str) or not number.strip() or len(number) > 32767 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", number):
            raise ValueError("写入的编号必须是有效的非空文字。")
    temporary = None
    try:
        with ZipFile(source_path) as archive:
            _validate_archive(archive)
            sheet = _select_sheet(_sheets(archive), sheet_name)
            cells, wanted = _number_cells(archive, sheet["part"])
            strings, _ = _strings(archive, wanted)
            styles = _styles(archive)
            for row in assignments:
                cell = cells.get(row)
                if cell is not None and (_child(cell, "f") is not None or _cell_value(cell, strings, styles) != ""):
                    raise ValueError(f"A{row} 已有编号或公式，拒绝覆盖原有内容。")
            patched = _patch_sheet(archive.read(sheet["part"]), assignments)
            # Validate before creating any destination; byte patch errors must
            # not produce an apparently successful corrupt workbook.
            ET.fromstring(patched)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".hsd-workbook-", suffix=".tmp", dir=destination_path.parent)
            os.close(fd)
            with ZipFile(temporary, "w") as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    member = copy.copy(info)
                    if info.filename == sheet["part"]:
                        output.writestr(member, patched)
                    else:
                        with output.open(member, "w", force_zip64=info.file_size >= ZIP64_LIMIT) as stream:
                            _copy_member(archive, info, stream)
        # Opening exclusively prevents a race from overwriting another export.
        with open(destination_path, "xb") as output, open(temporary, "rb") as prepared:
            try:
                while chunk := prepared.read(1024 * 1024):
                    output.write(chunk)
            except BaseException:
                output.close()
                destination_path.unlink(missing_ok=True)
                raise
    except OSError as exc:
        if exc.errno in {errno.ENOSPC, getattr(errno, 'EDQUOT', errno.ENOSPC)}:
            raise ValueError("主机磁盘空间不足，无法导出表格，请清理后重试。") from exc
        raise
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError("无法导出表格，原文件未被更改。") from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
