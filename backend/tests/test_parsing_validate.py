from app.parsing.contract import ClauseNode, DocumentMeta, ParsedDocument
from app.parsing.ocr import OCR_CONFIDENCE_THRESHOLD
from app.parsing.validate import EXPECTED_SECTIONS, check_completeness

EMPTY_META = DocumentMeta(
    title=None,
    version=None,
    owner=None,
    approver=None,
    approved_date=None,
    effective_date=None,
    doc_type=None,
)


def _parsed(headings: list[str]) -> ParsedDocument:
    return ParsedDocument(
        meta=EMPTY_META,
        clauses=[ClauseNode(heading=heading, text="", level=1) for heading in headings],
    )


def test_complete_document_yields_no_warning():
    assert check_completeness(_parsed(list(EXPECTED_SECTIONS))) == []


def test_missing_section_is_reported():
    warnings = check_completeness(_parsed(["Introduction"]))
    assert any("Roles and Responsibilities" in warning for warning in warnings)


def test_matching_is_case_and_whitespace_insensitive():
    assert check_completeness(_parsed(["  introduction  ", "ROLES AND RESPONSIBILITIES"])) == []


def test_nested_sections_also_count():
    parsed = ParsedDocument(
        meta=EMPTY_META,
        clauses=[
            ClauseNode(
                heading="Front Matter",
                text="",
                level=1,
                children=[
                    ClauseNode(heading="Introduction", text="", level=2),
                    ClauseNode(heading="Roles and Responsibilities", text="", level=2),
                ],
            )
        ],
    )
    assert check_completeness(parsed) == []


def test_document_with_no_clauses_reports_every_expected_section():
    warnings = check_completeness(_parsed([]))
    assert len(warnings) == 1
    for section in EXPECTED_SECTIONS:
        assert section in warnings[0]


def test_ocr_threshold_is_explicit():
    assert 0 < OCR_CONFIDENCE_THRESHOLD < 1
