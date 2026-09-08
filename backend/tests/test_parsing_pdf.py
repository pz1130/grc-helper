from pathlib import Path

import pytest

from app.parsing.contract import ParseError
from app.parsing.pdf_parser import TEXT_LAYER_MIN_CHARS, PdfParser, extract_lines


def _write_pdf(path: Path, pages: list[list[str]]) -> Path:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    for lines in pages:
        pdf.add_page()
        for line in lines:
            pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    return _write_pdf(
        tmp_path / "procedure.pdf",
        [
            [
                "Change Log",
                "1.0 01/06/2021 Start version of the Procedure",
                "2.01 01/12/2022 Spelling errors fixed",
                "Table of Contents",
                "1 Role and Responsibility ........................ 2",
                "4 Change Management Process ..................... 3",
            ],
            [
                "1 Role and Responsibility",
                "The IT Division owns this procedure.",
                "4 Change Management Process",
                "4.1 Normal Change",
                "Normal changes follow the CAB cycle.",
            ],
        ],
    )


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.children)


def test_extract_lines_returns_text_and_page_map(sample_pdf: Path):
    lines, page_of = extract_lines(sample_pdf)
    assert any("Change Management Process" in line for line in lines)
    assert set(page_of.values()) == {1, 2}


def test_numbering_traps_are_filtered_end_to_end(sample_pdf: Path):
    parsed = PdfParser().parse(sample_pdf)
    numbers = [node.number for node in _walk(parsed.clauses)]
    assert numbers == ["1", "4", "4.1"]
    assert "1.0" not in numbers and "2.01" not in numbers


def test_hierarchy_comes_from_the_number(sample_pdf: Path):
    parsed = PdfParser().parse(sample_pdf)
    process = next(node for node in parsed.clauses if node.number == "4")
    assert [child.number for child in process.children] == ["4.1"]


def test_pdf_clauses_carry_real_numbers(sample_pdf: Path):
    parsed = PdfParser().parse(sample_pdf)
    assert all(node.number for node in parsed.clauses)


def test_page_reference_is_recorded(sample_pdf: Path):
    parsed = PdfParser().parse(sample_pdf)
    assert next(node for node in parsed.clauses if node.number == "1").page_ref == 2


def test_warnings_report_what_was_filtered(sample_pdf: Path):
    parsed = PdfParser().parse(sample_pdf)
    assert any("目录行" in warning or "版本历史行" in warning for warning in parsed.warnings)


def test_scanned_pdf_is_reported_not_silently_empty(tmp_path: Path):
    empty = _write_pdf(tmp_path / "scanned.pdf", [[""]])
    parsed = PdfParser().parse(empty)
    assert parsed.clauses == []
    assert any("文本层" in warning for warning in parsed.warnings)


def test_corrupt_pdf_raises_readable_error(tmp_path: Path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 truncated")

    with pytest.raises(ParseError) as exc:
        PdfParser().parse(broken)
    assert "PDF" in exc.value.reason


def test_text_layer_threshold_matches_measured_corpus():
    assert TEXT_LAYER_MIN_CHARS == 200
