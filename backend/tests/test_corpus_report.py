"""真实语料验收（默认跳过，见 make corpus）。"""

import os
import re
from pathlib import Path

import pytest

from app.parsing.contract import ClauseNode
from app.parsing.registry import SUPPORTED_EXTENSIONS, get_parser

CORPUS = Path(os.environ.get("CORPUS_DIR", "/samples"))

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


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.name[:40])
def test_house_style_anchors_are_present(path: Path):
    """这批文件都以 Introduction 或 Role/Roles and Responsibility 起头。

    锚点缺失意味着解析漏掉了文档开头——正是首版塌树时的症状。
    """
    parsed = get_parser(path).parse(path)
    headings = {n.heading.strip().casefold() for n in _walk(parsed.clauses)}
    anchors = {
        "introduction",
        "role and responsibility",
        "roles and responsibilities",
        "roles & responsibilities",
    }
    assert headings & anchors, f"{path.name}: 一个 house style 锚点都没找到"
