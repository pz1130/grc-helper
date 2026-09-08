"""Postgres 全文检索。

语料为纯英文，用 english 配置提供词干还原；中文跨语言检索由查询侧扩展负责。
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import ClauseChunk

_CONFIG = "english"


@dataclass(frozen=True)
class RankedChunk:
    chunk_id: int
    rank: int
    score: float


async def search(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 50,
    document_id: int | None = None,
) -> list[RankedChunk]:
    if not query.strip():
        return []

    tsquery = func.websearch_to_tsquery(_CONFIG, query)
    score = func.ts_rank(ClauseChunk.tsv, tsquery)
    stmt = (
        select(ClauseChunk.id, score.label("score"))
        .where(ClauseChunk.tsv.op("@@")(tsquery))
        .order_by(score.desc(), ClauseChunk.id)
        .limit(limit)
    )
    if document_id is not None:
        stmt = stmt.where(ClauseChunk.document_id == document_id)

    rows = (await session.execute(stmt)).all()
    return [
        RankedChunk(chunk_id=row.id, rank=position, score=float(row.score))
        for position, row in enumerate(rows, start=1)
    ]
