from pathlib import Path

import pytest

from app.parsing.contract import ParseError
from app.parsing.headings import continues_the_heading
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


# ── 段落级编号的外部文档 ── OQ-20 ──────────────────────────────────
#
# HKMA SPM TM-C-1 那一类：`2.2` 本身就是一个段落，没有标题行。解析器把编号那
# 一行当标题、剩下的当正文，一句话被劈成两半：
#
#   heading = "Under this policy, AIs are required to develop robust technology"
#   text    = "and cyber risk management frameworks that are proportionate…"
#
# 下面两条把 2026-09-13 那次改造的效果固定住，免得日后悄悄退回去。


@pytest.fixture
def paragraph_numbered_pdf(tmp_path: Path) -> Path:
    """段落级编号：编号后面直接是正文，没有标题，且会跨行断开。"""
    return _write_pdf(
        tmp_path / "hkma-like.pdf",
        [
            [
                "Supervisory Policy Manual",
                "TM-C-1 Cyber Risk Management",
                "2.2 Under this policy, AIs are required to develop robust technology",
                "and cyber risk management frameworks that are proportionate to their",
                "size and the complexity of their operations.",
                "2.3 The Monetary Authority expects senior management to review the",
                "framework at least annually and after any material incident.",
            ],
        ],
    )


def test_paragraph_number_does_not_leave_half_a_sentence_as_the_heading(
    paragraph_numbered_pdf: Path,
):
    """标题要么是真标题，要么是编号——不能是半句话。

    审核者在确认队列里看到的就是这个 heading，`heading_path` 由它拼成，
    chunk 的上下文前缀也是它。半句话会一路污染到检索和引用可读性。
    """
    parsed = PdfParser().parse(paragraph_numbered_pdf)
    flat: list = []

    def walk(nodes):
        for node in nodes:
            flat.append(node)
            walk(node.children)

    walk(parsed.clauses)
    numbered = [node for node in flat if (node.number or "").strip()]
    assert numbered, "这份文档应当切出带编号的条款"
    for node in numbered:
        assert not continues_the_heading(node.text or ""), (
            f"条款 {node.number} 的正文以小写开头，说明 heading 仍是半句话："
            f"heading={node.heading!r} text={node.text!r}"
        )


def test_sample_house_style_anchors_do_not_fire_on_an_outside_document(
    paragraph_numbered_pdf: Path,
):
    """别拿样本那批文档的文风去量别家机构的文档。

    「Introduction / Roles and Responsibilities」是样本那 6 份的文风，不是解析器
    的性质。写死它会对每一份外部文档误报「解析可能不完整」，而它们解析得好好的。
    """
    from app.parsing.validate import check_completeness

    parsed = PdfParser().parse(paragraph_numbered_pdf)
    assert check_completeness(parsed) == []
    assert not any("应有的章节" in warning for warning in parsed.warnings)


def test_known_limit_uppercase_continuation_still_leaves_a_fragment(tmp_path: Path):
    """已知缺口，**刻意不修**：续行以大写词开头时，heading 仍是半句话。

    `continues_the_heading` 用"正文以小写字母开头"代理"这是同一句话的后半截"。
    续行以缩写开头就漏判——而 IT / GRC 制度里这恰恰极常见（IT、AIs、API、
    MFA、VPN、HKMA…）。下面这条就是实测出来的形状：

        heading = "AIs should ensure that their cyber resilience frameworks cover"
        text    = "IT assets across all environments and third-party connections."

    为什么不顺手补一条规则：改标题判据需要一把可信的尺子，而手上只有 6 份样本
    （外部那 29 份不在仓库里）。本项目在这件事上栽过——通用自洽度分在真实文档上
    "救 3 份坏 3 份"，教训是不要照着手上的语料调标题判据（见 OQ-19）。

    这条测试**描述现状而不是认可现状**。谁要补上这个缺口，它会红：那时候请先
    用 `make corpus CORPUS_DIR=...` 在一批真实文档上量过再改。
    """
    pdf = _write_pdf(
        tmp_path / "uppercase-continuation.pdf",
        [
            [
                "Supervisory Policy Manual",
                "2.2 AIs should ensure that their cyber resilience frameworks cover",
                "IT assets across all environments and third-party connections.",
                # 单独一条带编号的会被当成孤儿编号跳过，凑一对才是真实的文档形状
                "2.3 The Monetary Authority expects senior management to review the",
                "framework at least annually and after any material incident.",
            ],
        ],
    )
    flat: list = []

    def walk(nodes):
        for node in nodes:
            flat.append(node)
            walk(node.children)

    walk(PdfParser().parse(pdf).clauses)
    fragment = next(node for node in flat if node.number == "2.2")
    assert fragment.heading.startswith("AIs should ensure"), (
        "如果这条断言不成立，说明缺口被补上了——请更新本测试与 OQ-20"
    )
