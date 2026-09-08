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
