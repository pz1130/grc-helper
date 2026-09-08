from pathlib import Path

import pytest
from docx import Document as DocxDocument

from app.parsing.contract import ParseError
from app.parsing.docx_parser import DocxParser


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    doc = DocxDocument()
    doc.add_paragraph("INTERNAL")
    doc.add_paragraph("Acme Bank")
    doc.add_paragraph("IT Guideline")
    doc.add_paragraph("IT Incident Management")
    doc.add_paragraph("Version: \t\t1.0")
    doc.add_paragraph("Owner: \t\tIT Department")
    doc.add_paragraph("Approver: \t\tChief Risk Officer")
    doc.add_paragraph("Effective Date: \t01/06/2025")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Term"
    table.cell(0, 1).text = "Definition"
    table.cell(1, 0).text = "IT Incident"
    table.cell(1, 1).text = "An unplanned interruption to an IT service."

    doc.add_heading("Introduction", level=1)
    doc.add_paragraph("The purpose of this Guideline is to define incident handling.")
    doc.add_heading("Purpose and Objective", level=2)
    doc.add_paragraph("Defines objectives.")
    doc.add_heading("", level=2)
    doc.add_heading("Periodic Review", level=2)
    doc.add_paragraph("Reviewed annually.")
    doc.add_heading("Roles and Responsibilities", level=1)
    doc.add_heading("IT Department", level=2)
    doc.add_paragraph("Responsible for drafting.")

    path = tmp_path / "guideline.docx"
    doc.save(path)
    return path


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.children)


def test_headings_have_no_numbers(sample_docx: Path):
    parsed = DocxParser().parse(sample_docx)
    sections = [node for node in parsed.clauses if node.kind == "section"]
    assert sections
    assert all(node.number is None for node in sections)


def test_hierarchy_comes_from_heading_styles(sample_docx: Path):
    parsed = DocxParser().parse(sample_docx)
    tops = [node for node in parsed.clauses if node.kind == "section"]

    assert [node.heading for node in tops] == ["Introduction", "Roles and Responsibilities"]
    assert [child.heading for child in tops[0].children] == [
        "Purpose and Objective",
        "Periodic Review",
    ]
    assert [child.heading for child in tops[1].children] == ["IT Department"]


def test_empty_headings_do_not_become_clauses(sample_docx: Path):
    parsed = DocxParser().parse(sample_docx)
    assert all(node.heading.strip() for node in _walk(parsed.clauses))


def test_body_text_is_attached_to_its_heading(sample_docx: Path):
    parsed = DocxParser().parse(sample_docx)
    intro = next(node for node in parsed.clauses if node.heading == "Introduction")
    assert "define incident handling" in intro.text
    assert "Reviewed annually" in intro.children[1].text


def test_tables_become_clauses(sample_docx: Path):
    parsed = DocxParser().parse(sample_docx)
    tables = [node for node in parsed.clauses if node.kind == "table"]

    assert len(tables) == 1
    assert "IT Incident" in tables[0].text
    assert "unplanned interruption" in tables[0].text


def test_cover_metadata_is_extracted(sample_docx: Path):
    from datetime import date

    meta = DocxParser().parse(sample_docx).meta
    assert meta.version == "1.0"
    assert meta.owner == "IT Department"
    assert meta.approver == "Chief Risk Officer"
    assert meta.effective_date == date(2025, 6, 1)


def test_doc_type_is_inferred_from_cover(sample_docx: Path):
    assert DocxParser().parse(sample_docx).meta.doc_type == "guideline"


def test_corrupt_file_raises_a_readable_parse_error(tmp_path: Path):
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"not a docx at all")

    with pytest.raises(ParseError) as exc:
        DocxParser().parse(broken)
    assert "docx" in exc.value.reason.lower()


def test_document_without_headings_warns_instead_of_silently_returning_nothing(tmp_path: Path):
    doc = DocxDocument()
    doc.add_paragraph("just a flat paragraph")
    path = tmp_path / "flat.docx"
    doc.save(path)

    parsed = DocxParser().parse(path)
    assert parsed.clauses == [] or all(node.kind == "table" for node in parsed.clauses)
    assert any("标题" in warning for warning in parsed.warnings)
