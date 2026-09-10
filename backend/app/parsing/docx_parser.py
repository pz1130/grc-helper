"""DOCX parser based on Heading styles, tables, and cover metadata."""

import re
from datetime import date, datetime
from pathlib import Path

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsing.contract import ClauseNode, DocumentMeta, ParsedDocument, ParseError

_HEADING = re.compile(r"^Heading (\d+)$")
_META = re.compile(
    r"^\s*(Version|Owner|Approver|Approved Date|Effective Date)\s*:\s*(.+?)\s*$"
)
_DOC_TYPE = re.compile(r"\bIT\s+(Policy|Standard|Procedure|Guideline)\b", re.IGNORECASE)
_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%B %d, %Y")


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXT = f"{_W}t"
_DELETED = f"{_W}del"


def _element_text(element) -> str:
    """收集段落/单元格里的 w:t，跳过 w:del 下的内容。

    不能用 python-docx 的 Paragraph.text：它只拼接 w:p 的**直接** w:r 子节点，
    嵌在 w:ins（修订插入）里的 run 会被静默丢弃。实测一份带修订痕迹的真实
    文档丢了 96% 的插入片段（约 4700 字符），句子中间凭空少词。

    下游没有任何闸门能察觉这件事：引文确实逐字存在于（已残缺的）条款正文里，
    模型却会自行补上一个看似合理的主语，读起来像有据可依。

    w:del 的正文放在 w:delText，本来就取不到；这里显式跳过是防个别写法把
    w:t 塞进 w:del——修订删除的文字不该出现在正文中。
    """
    parts: list[str] = []

    def walk(node) -> None:
        for child in node:
            if child.tag == _DELETED:
                continue
            if child.tag == _TEXT:
                parts.append(child.text or "")
            else:
                walk(child)

    walk(element)
    return "".join(parts)


def _paragraph_text(paragraph: Paragraph) -> str:
    return _element_text(paragraph._element)


def _heading_level(paragraph: Paragraph) -> int | None:
    match = _HEADING.match(paragraph.style.name or "")
    return int(match.group(1)) if match else None


def _parse_date(raw: str) -> date | None:
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), date_format).date()
        except ValueError:
            continue
    return None


def _table_text(table: Table) -> str:
    rows: list[str] = []
    for row in table.rows:
        cells = [
            "\n".join(_paragraph_text(p) for p in cell.paragraphs).strip()
            for cell in row.cells
        ]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


class DocxParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            document = DocxDocument(str(path))
        except Exception as exc:
            raise ParseError(f"无法打开 docx 文件：{type(exc).__name__}") from exc

        warnings: list[str] = []
        roots: list[ClauseNode] = []
        stack: list[ClauseNode] = []
        meta_fields: dict[str, str] = {}
        doc_type: str | None = None
        empty_headings = 0

        def attach(node: ClauseNode, level: int) -> None:
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)

        for paragraph in document.paragraphs:
            text = _paragraph_text(paragraph).strip()
            level = _heading_level(paragraph)

            if level is not None:
                if not text:
                    empty_headings += 1
                    continue
                node = ClauseNode(heading=text, text="", level=level)
                attach(node, level)
                stack.append(node)
                continue

            if not text:
                continue

            if match := _META.match(text):
                meta_fields.setdefault(match.group(1), match.group(2).strip())
            if doc_type is None and (match := _DOC_TYPE.search(text)):
                doc_type = match.group(1).lower()

            if stack:
                stack[-1].text = f"{stack[-1].text}\n{text}".strip()

        for index, table in enumerate(document.tables, start=1):
            body = _table_text(table)
            if not body:
                continue
            roots.append(ClauseNode(heading=f"Table {index}", text=body, level=1, kind="table"))

        if empty_headings:
            warnings.append(f"已跳过 {empty_headings} 个空标题")
        if not any(node.kind == "section" for node in roots):
            warnings.append("未找到任何标题样式，该文档可能不是标准 house style")

        meta = DocumentMeta(
            title=None,
            version=meta_fields.get("Version"),
            owner=meta_fields.get("Owner"),
            approver=meta_fields.get("Approver"),
            approved_date=_parse_date(meta_fields.get("Approved Date", "")),
            effective_date=_parse_date(meta_fields.get("Effective Date", "")),
            doc_type=doc_type,
        )
        return ParsedDocument(meta=meta, clauses=roots, warnings=warnings)
