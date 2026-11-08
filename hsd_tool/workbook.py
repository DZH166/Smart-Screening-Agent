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
from .archive_io import member_blocks, check_directory_size
from .cancellation import check
from .xml_stream import parse_blocks
from .image_budget import IMAGE_BUDGET
from .image_headers import image_header

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
# Compatibility names: bytes are limited by available resources, not fixed caps.
MAX_PART_BYTES = None
MAX_ARCHIVE_BYTES = None
MAX_IMAGE_BYTES = None
MAX_IMAGE_PIXELS = 40_000_000
IO_CHUNK_BYTES = 1024 * 1024
SPOOL_MEMORY_BYTES = 8 * 1024 * 1024
MAX_CAPTURED_CELLS = 500_000
MAX_CAPTURED_TEXT_BYTES = 32 * 1024 * 1024
MAX_PICTURE_REFERENCES = 10_000
WORKBOOK_IMAGE_FORMATS = ("PNG", "JPEG", "WEBP", "BMP", "GIF", "TIFF")
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
    return next(parse_blocks(member_blocks(archive, archive.getinfo(part))))


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
    parent = None
    ancestors = []
    for event, node in parse_blocks(member_blocks(archive, archive.getinfo(part)), record='row', events=True):
        name = _local(node.tag)
        if event == 'start':
            ancestors.append(node)
            if name == 'sheetData' and len(ancestors) == 2 and _local(ancestors[0].tag) == 'worksheet':
                parent = node
        else:
            if name == "row" and len(ancestors) >= 2 and ancestors[-2] is parent:
                check()
                yield node
                node.clear()
                parent.clear()
            ancestors.pop()


def _strings(archive: ZipFile, wanted: set[int]) -> tuple[dict[int, str], dict[int, str]]:
    selected, pictures = {}, {}
    if "xl/sharedStrings.xml" not in archive.namelist():
        return selected, pictures
    index, captured = 0, 0
    root = None
    ancestors = []
    for event, node in parse_blocks(member_blocks(archive, archive.getinfo("xl/sharedStrings.xml")), record='si', events=True):
        if root is None:
            root = node
        if event == 'start':
            ancestors.append(node)
            continue
        if _local(node.tag) == "si" and len(ancestors) == 2 and ancestors[0] is root:
            check()
            value = _rich_text(node)
            if index in wanted or "DISPIMG" in value.upper():
                captured += len(value.encode('utf-8'))
                if captured > MAX_CAPTURED_TEXT_BYTES or len(selected) + len(pictures) >= MAX_CAPTURED_CELLS:
                    raise ValueError("表格编号或图片引用过多，无法安全读取，请整理模板后重试。")
                if index in wanted:
                    selected[index] = value
                if "DISPIMG" in value.upper():
                    if len(pictures) >= MAX_PICTURE_REFERENCES:
                        raise ValueError("表格图片引用过多，请整理模板后分批处理。")
                    pictures[index] = value
            node.clear()
            root.clear()
            index += 1
        ancestors.pop()
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
    captured = 0
    for row in _iter_rows(archive, part):
        for cell in row:
            ref = CELL_REF.fullmatch(cell.get("r", ""))
            if ref and ref[1] == "A":
                coordinate = int(ref[2])
                if coordinate in numbers:
                    raise ValueError(f"A{coordinate} 在表格中重复出现，无法安全读取。")
                encoded = ET.tostring(cell)
                captured += len(encoded)
                if len(numbers) >= MAX_CAPTURED_CELLS or captured > MAX_CAPTURED_TEXT_BYTES:
                    raise ValueError("表格编号数据过多，无法安全读取，请整理模板后重试。")
                numbers[coordinate] = ET.fromstring(encoded)
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
                if name not in result and len(result) >= MAX_PICTURE_REFERENCES:
                    raise ValueError("表格图片引用过多，请整理模板后分批处理。")
                target = rels.get(rid, {}).get("part")
                # Conflicting image IDs must never pick an arbitrary source.
                result[name] = None if name in result and result[name] != target else target
    return result


def _floating_images(archive: ZipFile, sheet_part: str) -> dict[int, list[str | None]]:
    rows = defaultdict(list)
    count = 0
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
                count += 1
                if count > MAX_PICTURE_REFERENCES:
                    raise ValueError("表格图片引用过多，请整理模板后分批处理。")
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
            # Reserve before opening a legacy decoder too: the input spool
            # may contain WebP (whose plugin reads all encoded bytes) or TIFF
            # metadata. No state/database lock is held while waiting.
            with IMAGE_BUDGET.reserve(check_cancel=check):
                image_header(staged, max_pixels=MAX_IMAGE_PIXELS, formats=WORKBOOK_IMAGE_FORMATS, check_cancel=check)
                with Image.open(staged, formats=list(WORKBOOK_IMAGE_FORMATS)) as preview:
                    preview.load()
                    # Normalize only the preview. Source workbook bytes and
                    # design colours/alpha in its original image stay intact.
                    with preview.convert("RGBA") as rgba, Image.new("RGBA", preview.size, "white") as background:
                        background.alpha_composite(rgba)
                        with background.convert("RGB") as rgb:
                            rgb.save(destination, "PNG")
        return str(destination.resolve()), None
    except (OSError, ValueError, Image.DecompressionBombError, BadZipFile):
        return None, "表格图片无法解码，需人工处理。"


def inspect_workbook(path: str, work_dir: str, sheet_name: str | None = None) -> dict:
    """Return image-bearing B rows and displayed A identifiers from one sheet."""
    destination = Path(work_dir).resolve() / "workbook_images"
    destination.mkdir(parents=True, exist_ok=True)
    try:
        check_directory_size(path, max_entries=20_000, too_many="表格内部文件过多，无法安全读取。")
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
            reference_count = sum(len(values) for values in pictures.values())
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
                    reference_count += 1
                    if reference_count > MAX_PICTURE_REFERENCES:
                        raise ValueError("表格图片引用过多，请整理模板后分批处理。")
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


def _tag_end(raw: bytes, start: int) -> int:
    """End of one real XML tag, including quoted > characters."""
    quote = None
    for index in range(start, len(raw)):
        value = raw[index]
        if quote is not None:
            if value == quote:
                quote = None
        elif value in (34, 39):
            quote = value
        elif value == 62:
            return index + 1
    raise ValueError("表格行标签不完整，无法安全回填。")


def _patch_row(raw: bytes, row_number: int, value: str) -> bytes:
    """Change only A in one bounded UTF-8 row; comments/CDATA are not cells."""
    from xml.parsers import expat
    parser = expat.ParserCreate()
    depth, row_name, found, current = 0, None, None, None

    def start(name, attrs):
        nonlocal depth, row_name, current
        depth += 1
        if depth == 1:
            row_name = name.encode("utf-8")
        elif depth == 2 and name.rsplit(":", 1)[-1] == "c" and attrs.get("r") == f"A{row_number}":
            if found is not None or current is not None:
                raise ValueError(f"A{row_number} 在表格中重复出现，无法安全回填。")
            offset = parser.CurrentByteIndex
            end = _tag_end(raw, offset)
            encoded_name = name.encode("utf-8")
            current = (offset, encoded_name, raw[offset + 1 + len(encoded_name):end - 1],
                       raw[offset:end].rstrip().endswith(b"/>"))

    def end(name):
        nonlocal depth, current, found
        if depth == 2 and current is not None and current[1] == name.encode("utf-8"):
            stop = parser.CurrentByteIndex if current[3] else _tag_end(raw, parser.CurrentByteIndex)
            found = (*current[:3], stop)
            current = None
        depth -= 1

    parser.StartElementHandler, parser.EndElementHandler = start, end
    try:
        parser.Parse(raw, True)
    except expat.ExpatError as exc:
        raise ValueError("表格编号行无法安全回填。") from exc
    if found is not None:
        offset, name, attrs, stop = found
        return raw[:offset] + _new_cell(name, attrs, value) + raw[stop:]
    if row_name is None:
        raise ValueError("目标编号行无法读取。")
    cell = _new_cell(row_name[:-3] + b"c", b' r="' + f"A{row_number}".encode() + b'"', value)
    start_end = _tag_end(raw, 0)
    if raw[:start_end].rstrip().endswith(b"/>"):
        return raw[:start_end - 2].rstrip() + b">" + cell + b"</" + row_name + b">"
    return raw[:start_end] + cell + raw[start_end:]


def _patch_sheet_blocks(blocks, destination, assignments: dict[int, str]) -> None:
    """Copy arbitrary-length XML through disk; hold only a target row in RAM."""
    import codecs
    from xml.parsers import expat
    from . import xml_stream

    parser = expat.ParserCreate()
    stack, pending = [], set(assignments)
    active, cursor, serial, unfinished = None, 0, 0, 0
    declared_encoding = None
    # This is a single-record workspace bound, not an XML/file byte cap.
    row_workspace = 8 * xml_stream.MAX_XML_TEXT + 64 * xml_stream.MAX_XML_NODES

    with tempfile.TemporaryFile(mode="w+b") as source:
        def read_range(start, stop):
            source.seek(start)
            while start < stop:
                check()
                block = source.read(min(IO_CHUNK_BYTES, stop - start))
                if not block:
                    raise ValueError("表格内部文件未完整读取。")
                yield block
                start += len(block)

        def codec():
            source.seek(0)
            prefix = source.read(4)
            if prefix.startswith(b"\xff\xfe") or prefix[:4] in (b"<\0?\0", b"<\0w\0"):
                return "utf-16-le"
            if prefix.startswith(b"\xfe\xff") or prefix[:4] in (b"\0<\0?", b"\0<\0w"):
                return "utf-16-be"
            encoding = declared_encoding or "utf-8"
            if codecs.lookup(encoding).name == "utf-16":
                raise ValueError("表格 XML 编码无法确认，请重新另存 XLSX。")
            return encoding

        def tag_stop(start):
            # Closing tags have no quoted attributes. The parser has already
            # consumed the complete tag before invoking its end callback.
            source.seek(start)
            encoding = codec()
            source.seek(start)
            marker = ">".encode(encoding)
            tail, offset = b"", start
            while True:
                block = source.read(min(65536, row_workspace))
                if not block:
                    raise ValueError("表格行结尾不完整。")
                sample = tail + block
                index = sample.find(marker)
                if index >= 0:
                    return offset - len(tail) + index + len(marker)
                offset += len(block)
                if offset - start > row_workspace:
                    raise ValueError("单行表格数据过于复杂，无法安全回填。")
                tail = sample[-len(marker):]

        def empty_row(begin):
            # Expat's end offset for <row/> may already point to </sheetData>.
            # Inspect the actual opening tag rather than consuming that parent.
            encoding = codec()
            decoder = codecs.getincrementaldecoder(encoding)()
            source.seek(begin)
            sample, read = b"", 0
            while read <= xml_stream.MAX_XML_TOKEN_BYTES:
                check()
                block = source.read(65536)
                if not block:
                    raise ValueError("表格行标签不完整，无法安全回填。")
                read += len(block)
                sample += decoder.decode(block, final=False).encode("utf-8")
                try:
                    stop = _tag_end(sample, 0)
                except ValueError:
                    continue
                return sample[:stop].rstrip().endswith(b"/>")
            raise ValueError("表格行标签过于复杂，无法安全回填。")

        def start(name, attrs):
            nonlocal active, serial
            serial += 1
            stack.append(name)
            if len(stack) > xml_stream.MAX_XML_DEPTH:
                raise ValueError("表格内部结构过于复杂，无法安全回填。")
            if (len(stack) == 3 and stack[0].rsplit(":", 1)[-1] == "worksheet"
                    and stack[-2].rsplit(":", 1)[-1] == "sheetData"
                    and name.rsplit(":", 1)[-1] == "row"):
                reference = attrs.get("r", "")
                if reference.isdigit() and int(reference) in assignments:
                    number = int(reference)
                    if number not in pending:
                        raise ValueError(f"A{number} 对应行重复，无法安全回填。")
                    active = (number, parser.CurrentByteIndex, len(stack))

        def end(name):
            nonlocal active, cursor, serial
            serial += 1
            if active is not None and len(stack) == active[2]:
                number, begin, _ = active
                stop = parser.CurrentByteIndex
                # For <row/>, Expat points just after />; for a normal end it
                # points to the start of </row>. Inspect only the nearby bytes.
                encoding = codec()
                if not empty_row(begin):
                    stop = tag_stop(stop)
                if stop - begin > row_workspace:
                    raise ValueError("单行表格数据过于复杂，无法安全回填。")
                for block in read_range(cursor, begin):
                    destination.write(block)
                source.seek(begin)
                raw = source.read(stop - begin)
                patched = _patch_row(raw.decode(encoding).encode("utf-8"), number, assignments[number])
                destination.write(patched.decode("utf-8").encode(encoding, errors="xmlcharrefreplace"))
                pending.remove(number)
                cursor, active = stop, None
            stack.pop()

        def data(value):
            nonlocal serial
            serial += 1

        def declaration(version, encoding, standalone):
            nonlocal declared_encoding
            declared_encoding = encoding

        def doctype(*args):
            raise ValueError("表格包含不支持的 XML 声明。")

        parser.StartElementHandler, parser.EndElementHandler = start, end
        parser.CharacterDataHandler, parser.XmlDeclHandler = data, declaration
        parser.StartDoctypeDeclHandler = doctype
        for block in blocks:
            check()
            source.seek(0, 2)
            source.write(block)
            unfinished += len(block)
            if unfinished > xml_stream.MAX_XML_TOKEN_BYTES:
                raise ValueError("表格 XML 标签过于复杂，无法安全回填。")
            previous = serial
            try:
                parser.Parse(block, False)
            except expat.ExpatError as exc:
                raise ValueError("表格内部结构无法安全回填。") from exc
            if serial != previous:
                unfinished = 0
        try:
            parser.Parse(b"", True)
        except expat.ExpatError as exc:
            raise ValueError("表格内部结构无法安全回填。") from exc
        if pending:
            raise ValueError("目标编号行不存在：" + "、".join(f"A{row}" for row in sorted(pending)))
        source.seek(0, 2)
        for block in read_range(cursor, source.tell()):
            destination.write(block)


def _validate_sheet_stream(stream) -> None:
    """Validate the actual complete patched XML without retaining its DOM."""
    def blocks():
        stream.seek(0)
        while block := stream.read(IO_CHUNK_BYTES):
            check()
            yield block
    stack = []
    for event, node in parse_blocks(blocks(), record="row", events=True):
        if event == "start":
            stack.append(node)
        else:
            stack.pop()
            node.clear()
            if stack:
                stack[-1].remove(node)


def _patch_sheet(xml: bytes, assignments: dict[int, str]) -> bytes:
    """Compatibility helper for small byte fixtures; exports use disk streams."""
    from io import BytesIO
    output = BytesIO()
    _patch_sheet_blocks([xml], output, assignments)
    return output.getvalue()


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
            with tempfile.TemporaryFile(mode="w+b") as patched:
                _patch_sheet_blocks(member_blocks(archive, archive.getinfo(sheet["part"])), patched, assignments)
                # Validate the complete patched stream before any destination
                # is visible. No whole-sheet bytes or ElementTree is retained.
                _validate_sheet_stream(patched)
                patched.seek(0, 2)
                patched_size = patched.tell()
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix=".hsd-workbook-", suffix=".tmp", dir=destination_path.parent)
                os.close(fd)
                with ZipFile(temporary, "w") as output:
                    output.comment = archive.comment
                    for info in archive.infolist():
                        check()
                        member = copy.copy(info)
                        if info.filename == sheet["part"]:
                            member.file_size = patched_size
                            patched.seek(0)
                            with output.open(member, "w", force_zip64=patched_size >= ZIP64_LIMIT) as stream:
                                while block := patched.read(IO_CHUNK_BYTES):
                                    check()
                                    stream.write(block)
                        else:
                            with output.open(member, "w", force_zip64=info.file_size >= ZIP64_LIMIT) as stream:
                                _copy_member(archive, info, stream)
        # Opening exclusively prevents a race from overwriting another export.
        created_destination = False
        try:
            with open(destination_path, "xb") as output:
                created_destination = True
                with open(temporary, "rb") as prepared:
                    while chunk := prepared.read(1024 * 1024):
                        check()
                        output.write(chunk)
        except BaseException:
            # Include source-open and final buffered flush/close failures. An
            # already-existing destination never belongs to this operation.
            if created_destination:
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
