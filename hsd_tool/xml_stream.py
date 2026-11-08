"""Bound in-memory XML structure while streaming arbitrarily long row lists.

These are parser workspace limits, not file/upload byte limits. Completed rows
or shared-string records may be released independently; metadata outside those
records remains bounded. DTDs are forbidden by the parser for every encoding.
"""
from collections import deque
import xml.etree.ElementTree as ET

from .cancellation import check

MAX_XML_DEPTH = 128
MAX_XML_NODES = 100_000
MAX_XML_TEXT = 8 * 1024 * 1024
MAX_XML_TOKEN_BYTES = 8 * 1024 * 1024
_COMPLEX = '表格内部结构或文字过于复杂，无法安全读取，请使用编号模板重新另存。'


class GuardedBuilder(ET.TreeBuilder):
    def __init__(self, record=None, events=False):
        super().__init__()
        self.record, self.events = record, deque() if events else None
        self.depth = self.serial = self.token_text = 0
        self.record_depth = None
        self.record_nodes = self.record_text = 0
        self.metadata_nodes = self.metadata_text = 0
        self.tags = []
        self.last_closed = None

    def _text(self, size):
        if self.record_depth is not None:
            self.record_text += size
            total = self.record_text
        else:
            self.metadata_text += size
            total = self.metadata_text
        if total > MAX_XML_TEXT:
            raise ValueError(_COMPLEX)

    def start(self, tag, attrs):
        self.serial += 1
        self.token_text = 0
        self.depth += 1
        self.tags.append(tag.rsplit('}', 1)[-1])
        self.last_closed = None
        if self.depth > MAX_XML_DEPTH:
            raise ValueError(_COMPLEX)
        record_path = {'row': ['worksheet', 'sheetData', 'row'], 'si': ['sst', 'si']}.get(self.record)
        if self.record_depth is None and self.tags == record_path:
            self.record_depth = self.depth
            self.record_nodes = self.record_text = 0
        if self.record_depth is not None:
            self.record_nodes += 1
            count = self.record_nodes
        else:
            self.metadata_nodes += 1
            count = self.metadata_nodes
        if count > MAX_XML_NODES:
            raise ValueError(_COMPLEX)
        self._text(len(tag) + sum(len(k) + len(v) for k, v in attrs.items()))
        node = super().start(tag, attrs)
        if self.events is not None:
            self.events.append(('start', node))
        return node

    def data(self, data):
        self.serial += 1
        self.token_text += len(data)
        if self.token_text > MAX_XML_TEXT:
            raise ValueError(_COMPLEX)
        # Only indentation attached to a released record (or its cleared
        # container's initial text) may be excluded. Metadata trees retain
        # whitespace too; excluding all of it would bypass the total budget.
        container_path = {'row': ['worksheet', 'sheetData'], 'si': ['sst']}.get(self.record)
        released_indent = (container_path is not None and self.record_depth is None
                           and self.tags == container_path
                           and self.last_closed in (None, self.record) and data.isspace())
        if not released_indent:
            self._text(len(data))
        super().data(data)

    def end(self, tag):
        self.serial += 1
        self.token_text = 0
        node = super().end(tag)
        if self.events is not None:
            self.events.append(('end', node))
        if self.record_depth == self.depth:
            self.record_depth = None
        self.tags.pop()
        self.last_closed = tag.rsplit('}', 1)[-1]
        self.depth -= 1
        return node

    def doctype(self, name, pubid, system):
        raise ValueError('表格包含不支持的 XML 声明。')


def parse_blocks(blocks, *, record=None, events=False):
    """Yield real parser events; returns a root only for non-stream callers."""
    builder = GuardedBuilder(record=record, events=events)
    parser = ET.XMLParser(target=builder)
    pending, tail = 0, b''
    for block in blocks:
        check()
        # Keep the prior rejection of declarations even inside comments. NUL
        # removal additionally recognizes UTF-16/32 ASCII declaration tokens;
        # the doctype callback above remains the encoding-independent guard.
        sample = (tail + block).replace(b'\0', b'').upper()
        if b'<!DOCTYPE' in sample or b'<!ENTITY' in sample:
            raise ValueError('表格包含不支持的 XML 声明。')
        tail = (tail + block)[-64:]
        pending += len(block)
        if pending > MAX_XML_TOKEN_BYTES:
            raise ValueError(_COMPLEX)
        serial = builder.serial
        parser.feed(block)
        if builder.serial != serial:
            pending = 0
        if events:
            while builder.events:
                yield builder.events.popleft()
    check()
    root = parser.close()
    if events:
        while builder.events:
            yield builder.events.popleft()
    else:
        yield root
