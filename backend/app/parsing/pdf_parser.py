"""PDF text-layer parser.

Scanned PDFs are reported explicitly and handled by the OCR fallback layer.
"""

from pathlib import Path

import pdfplumber

from app.parsing.contract import DocumentMeta, ParseError, ParsedDocument
from app.parsing.numbering import assemble_tree, extract_headings

TEXT_LAYER_MIN_CHARS = 200


def extract_lines(path: Path) -> tuple[list[str], dict[int, int]]:
    """Return all extracted lines and a zero-based line-to-one-based-page map."""
    lines: list[str] = []
    page_of: dict[int, int] = {}
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for line in (page.extract_text() or "").splitlines():
                    page_of[len(lines)] = page_number
                    lines.append(line)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"无法读取 PDF：{type(exc).__name__}") from exc
    return lines, page_of


def _empty_meta() -> DocumentMeta:
    return DocumentMeta(
        title=None,
        version=None,
        owner=None,
        approver=None,
        approved_date=None,
        effective_date=None,
        doc_type=None,
    )


class PdfParser:
    def parse(self, path: Path) -> ParsedDocument:
        lines, page_of = extract_lines(path)
        warnings: list[str] = []

        if sum(len(line) for line in lines) < TEXT_LAYER_MIN_CHARS:
            warnings.append("该 PDF 没有可用的文本层（疑似扫描件），需要 OCR 兜底")
            return ParsedDocument(meta=_empty_meta(), clauses=[], warnings=warnings)

        headings, filter_warnings = extract_headings(lines)
        warnings.extend(filter_warnings)
        if not headings:
            warnings.append("未识别出任何编号条款，该 PDF 可能不是标准 house style")

        return ParsedDocument(
            meta=_empty_meta(),
            clauses=assemble_tree(headings, lines, page_of=page_of),
            warnings=warnings,
        )
