"""检索质量验收（M3 风险闸门）。

需要真实语料 + 可用的 embedding provider，会产生 API 费用，所以默认跳过。
本地手动运行：make retrieval
"""

import json
import os
from pathlib import Path

import pytest

from app.search.service import search

CORPUS = Path(os.environ.get("CORPUS_DIR", "/samples"))
GOLD = Path(__file__).parent / "fixtures" / "gold_queries.json"

pytestmark = pytest.mark.skipif(
    not CORPUS.is_dir() or os.environ.get("RUN_RETRIEVAL_EVAL") != "1",
    reason="需要真实语料且显式开启（会产生 API 费用），见 make retrieval",
)

TARGET_RECALL_AT_5 = 0.75


def _gold() -> list[dict]:
    return json.loads(GOLD.read_text(encoding="utf-8"))


def _matches(hit, case: dict) -> bool:
    return (
        case["expect_document"].casefold() in hit.document_title.casefold()
        and hit.citation_label.casefold().startswith(case["expect_citation_prefix"].casefold())
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _gold(), ids=lambda case: case["query"][:30])
async def test_gold_query_is_answered_in_top_five(db_session, case):
    response = await search(db_session, case["query"], limit=5)
    assert response.hits, f"{case['query']}：一条都没召回"
    assert any(_matches(hit, case) for hit in response.hits), (
        f"{case['query']}：前 5 条里没有 {case['expect_document']} "
        f"{case['expect_citation_prefix']}；实际命中 "
        f"{[(hit.document_title[:20], hit.citation_label) for hit in response.hits]}"
    )


@pytest.mark.asyncio
async def test_chinese_queries_reach_english_clauses(db_session):
    chinese = [case for case in _gold() if any("一" <= ch <= "鿿" for ch in case["query"])]
    assert chinese, "黄金集里必须有中文查询"
    for case in chinese:
        response = await search(db_session, case["query"], limit=5)
        assert response.vector_used or len(response.expanded_terms) > 1, (
            f"{case['query']}：既没走向量也没扩展词，等于没做跨语言"
        )
        assert response.hits, f"{case['query']}：一条都没召回"


@pytest.mark.asyncio
async def test_print_quality_report(db_session, capsys):
    cases = _gold()
    reciprocal_ranks: list[float] = []
    recalled = 0

    with capsys.disabled():
        print(f"\n{'R@5':>5} {'MRR':>6}  查询")
        for case in cases:
            response = await search(db_session, case["query"], limit=5)
            position = next(
                (index for index, hit in enumerate(response.hits, start=1) if _matches(hit, case)),
                None,
            )
            if position:
                recalled += 1
                reciprocal_ranks.append(1.0 / position)
            else:
                reciprocal_ranks.append(0.0)
            print(
                f"{'✅' if position else '❌':>5} {reciprocal_ranks[-1]:>6.2f}  "
                f"{case['query'][:52]}"
            )

        recall = recalled / len(cases)
        mrr = sum(reciprocal_ranks) / len(cases)
        print(f"\n  Recall@5 = {recall:.2f}   MRR = {mrr:.2f}   （目标 R@5 ≥ {TARGET_RECALL_AT_5}）")

    assert recall >= TARGET_RECALL_AT_5, (
        f"Recall@5 {recall:.2f} 低于目标 {TARGET_RECALL_AT_5}——检索质量不达标，不要开 M4"
    )
