from pathlib import Path

import pytest

from app.parsing.contract import ParseError
from app.parsing.ocr import ocr_pdf
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
                "IT Procedure - Change Management Procedure",
                "Version: 2.01",
                "Procedure Owners: IT Department",
                "Approver: Chief Risk Officer",
                "Approved Date: 1 December 2022",
                "Effective Date: 1 December 2022",
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


def test_cover_metadata_is_extracted(sample_pdf: Path):
    from datetime import date

    meta = PdfParser().parse(sample_pdf).meta
    assert meta.title == "IT Procedure - Change Management Procedure"
    assert meta.version == "2.01"
    assert meta.owner == "IT Department"
    assert meta.approver == "Chief Risk Officer"
    assert meta.approved_date == date(2022, 12, 1)
    assert meta.effective_date == date(2022, 12, 1)
    assert meta.doc_type == "procedure"


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


# ── 扫描件（没有文本层）── OQ-18 ────────────────────────────────────
#
# 手上 21 份 PDF（15 份外部 + 6 份样本）**全部有文本层**，所以这条路一直是空白。
# 合成一份没有文本层的 PDF 就能把它从"未知"变成"已知"：把文字画成位图再存成
# PDF，等价于扫描件的形态（真实扫描件还有噪点、倾斜、印章，那是第二轮的事）。
#
# 钉死的结论：**"OCR 兜底"目前并不存在**。文本层不够时解析器只加一条警告、
# 返回空文档，`ocr_pdf()` 在 app/ 下没有任何调用者，镜像里也没有
# tesseract/poppler。下面三条就是这个事实的可执行版本——谁要接上 OCR，
# 它们会红，那时候改它们才是对的。


def _write_scanned_pdf(path: Path, pages: list[list[str]]) -> Path:
    """把文字画成位图再存成 PDF——产物没有文本层，形态等价于扫描件。"""
    from PIL import Image, ImageDraw

    images = []
    for lines in pages:
        image = Image.new("RGB", (1240, 1754), "white")  # A4 @150dpi
        draw = ImageDraw.Draw(image)
        y = 80
        for line in lines:
            draw.text((80, y), line, fill="black")
            y += 28
        images.append(image)
    images[0].save(str(path), save_all=True, append_images=images[1:])
    return path


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    return _write_scanned_pdf(
        tmp_path / "scanned.pdf",
        [
            [
                "IT Procedure - Access Control Procedure",
                "Version: 1.0",
                "1 Roles and Responsibilities",
                "The IT Division owns this procedure and reviews it annually.",
            ],
            [
                "2 Access Provisioning",
                "2.1 All privileged accounts shall be approved by two approvers.",
                "2.2 Access reviews shall be performed quarterly.",
            ],
        ],
    )


def test_scanned_pdf_really_has_no_text_layer(scanned_pdf: Path):
    """先证明这份合成件确实是扫描件的形态，否则下面两条测的是别的东西。"""
    lines, _ = extract_lines(scanned_pdf)
    assert sum(len(line) for line in lines) < TEXT_LAYER_MIN_CHARS


def test_scanned_pdf_yields_an_empty_document_with_a_warning(scanned_pdf: Path):
    """扫描件进来的结果是**空文档 + 一条警告**，不是 OCR 出来的条款。"""
    parsed = PdfParser().parse(scanned_pdf)
    assert parsed.clauses == []
    assert any("文本层" in warning for warning in parsed.warnings)


def test_scan_warning_points_at_the_fallback_that_actually_exists(scanned_pdf: Path):
    """那条警告不能承诺一个不存在的兜底。

    原文写的是"需要 OCR 兜底"——而 OCR 并没有接进解析路径（见本文件上方说明）。
    用户读完会以为系统接下来会 OCR，或者以为装个依赖就好了。
    真正**存在**的兜底是"手动粘贴纯文本"（`POST /api/documents/{id}/plain-text`），
    警告就该指向它。
    """
    warning = next(w for w in PdfParser().parse(scanned_pdf).warnings if "文本层" in w)
    assert "OCR 兜底" not in warning
    assert "粘贴" in warning


def test_scanned_pdf_does_not_set_ocr_used(scanned_pdf: Path):
    """`ocr_used` 恒为 False——`Document.ocr_quality_flag` 由它赋值，

    所以扫描件在库里不会被标成"OCR 质量存疑"，而是看起来像一份正常但空的文档。
    这正是这条路最危险的地方：没有任何下游信号说"这份没解析出来是因为它是扫描件"。
    """
    parsed = PdfParser().parse(scanned_pdf)
    assert parsed.ocr_used is False


def test_ocr_module_explains_what_is_missing_instead_of_crashing():
    """真去调 ocr_pdf 会拿到一条能照着做的报错，而不是 ImportError 堆栈。

    镜像里没有 tesseract/poppler，所以这是当前**必然**走到的分支。
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name in {"pytesseract", "pdf2image"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        with pytest.raises(ParseError) as exc:
            ocr_pdf(Path("whatever.pdf"))
    finally:
        builtins.__import__ = real_import
    assert "tesseract" in str(exc.value)
