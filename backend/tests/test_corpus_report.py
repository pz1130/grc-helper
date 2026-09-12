"""真实语料验收（默认跳过，见 make corpus）。"""

import os
import re
from pathlib import Path

import pytest

from app.parsing.contract import ClauseNode
from app.parsing.registry import SUPPORTED_EXTENSIONS, get_parser

CORPUS = Path(os.environ.get("CORPUS_DIR", "/samples"))

# 锚点是 **house style** 的东西，不是解析器的：换一家机构就该换一套，
# 拿本仓库这套去量别人的文档，失败的是「文风不同」而不是「解析漏了开头」。
# 换一套：CORPUS_ANCHORS="引言,职责分工"；不知道该填什么就 CORPUS_ANCHORS=none 跳过。
_ANCHORS = os.environ.get("CORPUS_ANCHORS")
ANCHORS = (
    {piece.strip().casefold() for piece in _ANCHORS.split(",") if piece.strip()}
    if _ANCHORS and _ANCHORS != "none"
    else set()
    if _ANCHORS == "none"
    else {
        "introduction",
        "role and responsibility",
        "roles and responsibilities",
        "roles & responsibilities",
    }
)

pytestmark = pytest.mark.skipif(
    not CORPUS.is_dir(), reason="未挂载真实语料目录，跳过（见 make corpus）"
)


def _files() -> list[Path]:
    if not CORPUS.is_dir():
        return []
    return sorted(path for path in CORPUS.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS)


def _walk(nodes: list[ClauseNode]):
    for node in nodes:
        yield node
        yield from _walk(node.children)


@pytest.mark.parametrize("path", _files(), ids=lambda path: path.name[:40])
def test_every_real_document_parses_into_clauses(path: Path):
    parsed = get_parser(path).parse(path)
    clauses = list(_walk(parsed.clauses))
    assert clauses, f"{path.name} 一条条款都没解析出来"


@pytest.mark.parametrize("path", _files(), ids=lambda path: path.name[:40])
def test_no_ghost_clauses_from_toc_or_version_rows(path: Path):
    parsed = get_parser(path).parse(path)
    for node in _walk(parsed.clauses):
        assert "...." not in node.heading, f"{path.name}: 目录行漏进来了 → {node.heading!r}"
        assert not re.match(r"^\d{2}/\d{2}/\d{4}", node.heading), (
            f"{path.name}: 版本历史行漏进来了 → {node.heading!r}"
        )


@pytest.mark.parametrize("path", _files(), ids=lambda path: path.name[:40])
def test_no_empty_headings(path: Path):
    parsed = get_parser(path).parse(path)
    for node in _walk(parsed.clauses):
        assert node.heading.strip(), f"{path.name}: 出现空标题条款"


def test_docx_tables_are_captured():
    docx_files = [path for path in _files() if path.suffix.lower() == ".docx"]
    if not docx_files:
        pytest.skip("语料里没有 docx")

    parsed = get_parser(docx_files[0]).parse(docx_files[0])
    assert any(node.kind == "table" for node in _walk(parsed.clauses)), "表格一张都没进来"


def test_print_corpus_report(capsys):
    files = _files()
    if not files:
        pytest.skip("语料目录为空")

    with capsys.disabled():
        print(f"\n{'条款':>6} {'表格':>5} {'告警':>5}  文件")
        for path in files:
            parsed = get_parser(path).parse(path)
            nodes = list(_walk(parsed.clauses))
            tables = sum(1 for node in nodes if node.kind == "table")
            print(f"{len(nodes):>6} {tables:>5} {len(parsed.warnings):>5}  {path.name[:52]}")
            for warning in parsed.warnings:
                print(f"{'':>18}⚠️  {warning}")


# ── 结构性断言 ──────────────────────────────────────────────
# 首版的语料测试只断言"不是已知的三类噪声"，从没断言"条款是不是真的条款"，
# 结果 4/6 份文件的树塌了还全绿。下面三条断言的是**结构本身**。


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name[:40])
def test_top_level_clauses_are_top_level_numbers(path: Path):
    """顶层条款的编号必须是单段的。

    实测事故：噪声顶掉父节点后，1.1 / 1.2 / 2.1 全被打到顶层，
    一份文件冒出 18 个"顶层"条款。
    """
    parsed = get_parser(path).parse(path)
    offenders = [
        n.number
        for n in parsed.clauses
        if n.kind == "section" and n.number and "." in n.number
    ]
    assert not offenders, f"{path.name}: 这些子条款被打到了顶层 → {offenders}"


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name[:40])
def test_child_number_extends_its_parent(path: Path):
    """树的完整性：子条款编号必须是父条款编号的延长。"""
    parsed = get_parser(path).parse(path)

    def check(parent: ClauseNode) -> None:
        for child in parent.children:
            if parent.number and child.number:
                assert child.number.startswith(f"{parent.number}."), (
                    f"{path.name}: {child.number} 挂在了 {parent.number} 下面"
                )
            check(child)

    for root in parsed.clauses:
        check(root)


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name[:40])
def test_no_page_footer_or_list_item_became_a_clause(path: Path):
    """页脚与操作步骤不得成为条款（实测各 17 / 41 条）。"""
    import re

    parsed = get_parser(path).parse(path)
    for node in _walk(parsed.clauses):
        assert not re.match(r"^\|?\s*P\s*a\s*g\s*e", node.heading), (
            f"{path.name}: 页脚漏进来了 → {node.heading!r}"
        )


@pytest.mark.skipif(not ANCHORS, reason="CORPUS_ANCHORS=none：这批文档的 house style 锚点未知")
@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name[:40])
def test_house_style_anchors_are_present(path: Path):
    """这批文件都以 Introduction 或 Role/Roles and Responsibility 起头。

    锚点缺失意味着解析漏掉了文档开头——正是首版塌树时的症状。
    """
    parsed = get_parser(path).parse(path)
    headings = {n.heading.strip().casefold() for n in _walk(parsed.clauses)}
    assert headings & ANCHORS, f"{path.name}: 一个 house style 锚点都没找到"


# ── 塌树检测 ────────────────────────────────────────────────
# 上面的断言问的都是「已有的条款是不是真条款」，没有一条问「条款是不是太少了」。
# 实测：KBC 的 43 页公司治理宪章切出 **4 条**、其中一条装下 70% 的正文，
# HKMA 的 10 页模块切出 **1 条**装下全部——八条断言全绿。
#
# 下面两条问的是**形状**，不是文风。一份文件被压成一坨，不论出自哪家机构都是错的；
# 反过来 6 页切出 97 条也是错的。这正是换语料时最先该知道的事。
#
# 阈值取自 22 份实测（15 份外部机构 PDF + 6 份样本 + 1 份新 docx）：
#   最大块占比   正常 7–33%；样本里最高 56%（一份 2.4k 字的短文件）
#                塌掉的是 70% / 84% / 100% / 100%
#   条/千字      PDF 正常 0.29–0.43，docx 正常 1.31–3.73
#                塌掉的 0.03 / 0.04 / 0.10，过切的 13.34
MIN_CHARS_TO_JUDGE = 3000
MAX_SINGLE_CLAUSE_SHARE = 0.60
MIN_CLAUSES_PER_1K = 0.15
MAX_CLAUSES_PER_1K = 8.0


def _shape(path: Path) -> tuple[int, int, int]:
    """返回（条款数, 正文总字数, 最大单条字数）。"""
    nodes = list(_walk(get_parser(path).parse(path).clauses))
    sizes = [len(node.text or "") for node in nodes]
    return len(nodes), sum(sizes), max(sizes, default=0)


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name[:40])
def test_no_single_clause_swallows_the_document(path: Path):
    """一条条款装下大半篇正文，等于条款树没切开。

    下游全靠条款定位：引用指向哪一条、变更影响按条款配对、控制点出处回到哪一段。
    一坨装下全文时这些仍然「能跑」，只是全部指向同一个地方。
    """
    count, total, biggest = _shape(path)
    if total < MIN_CHARS_TO_JUDGE:
        pytest.skip(f"{path.name}: 正文不足 {MIN_CHARS_TO_JUDGE} 字，形状判据不适用")
    share = biggest / total
    assert share <= MAX_SINGLE_CLAUSE_SHARE, (
        f"{path.name}: 最大一条装下 {share:.0%} 的正文（共 {count} 条）——条款树没切开"
    )


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name[:40])
def test_clause_count_is_proportionate_to_the_text(path: Path):
    """条款数与文本量要相称：太少是塌树，太多是把正文行当成了条款。"""
    count, total, _ = _shape(path)
    if total < MIN_CHARS_TO_JUDGE:
        pytest.skip(f"{path.name}: 正文不足 {MIN_CHARS_TO_JUDGE} 字，形状判据不适用")
    per_k = count / (total / 1000)
    assert per_k >= MIN_CLAUSES_PER_1K, (
        f"{path.name}: 每千字只有 {per_k:.2f} 条（共 {count} 条 / {total} 字）——疑似塌树"
    )
    assert per_k <= MAX_CLAUSES_PER_1K, (
        f"{path.name}: 每千字 {per_k:.2f} 条（共 {count} 条 / {total} 字）——疑似把正文行当成了条款"
    )
