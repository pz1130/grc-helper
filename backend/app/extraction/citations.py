"""Literal citation validation against clause bodies."""

from collections.abc import Collection
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.llm.validation import clause_source, normalize

__all__ = ["ClauseCitationValidator", "clause_source", "normalize"]


class ClauseCitationValidator:
    def __init__(
        self, session: AsyncSession, *, document_id: int | None = None,
        clause_ids: Collection[int] | None = None, item_key: str = "controls",
    ) -> None:
        self._session = session
        self._document_id = document_id
        self._clause_ids = frozenset(clause_ids) if clause_ids is not None else None
        self._item_key = item_key

    async def check(self, payload: dict[str, Any]) -> str | None:
        items = payload.get(self._item_key)
        if not isinstance(items, list):
            return f"{self._item_key} must be a list"
        if not items:
            return None if payload.get("insufficient_evidence") is True else "No evidence supplied"
        if payload.get("insufficient_evidence") is True:
            return "insufficient_evidence cannot accompany proposals"
        citations: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                return "Invalid proposal"
            sources = item.get("citations")
            if not isinstance(sources, list) or not sources:
                return "提案没有给出引用"
            for source in sources:
                if not isinstance(source, dict):
                    return "Invalid citation"
                cid, quote = source.get("clause_id"), source.get("quote")
                if type(cid) is not int or cid <= 0:
                    return f"Invalid clause_id: {cid!r}"
                if not isinstance(quote, str) or not normalize(quote):
                    return f"条款 {cid} 的引用没有给出引文"
                citations.append(source)
        wanted = {c["clause_id"] for c in citations}
        clauses = {
            c.id: c for c in await self._session.scalars(
                select(Clause).where(Clause.id.in_(wanted))
            )
        }
        for source in citations:
            cid = source["clause_id"]
            clause = clauses.get(cid)
            if clause is None:
                return f"引用的条款 {cid} 在库中不存在"
            if self._document_id is not None and clause.document_id != self._document_id:
                return f"引用的条款 {cid} 不属于本次抽取的文档"
            if self._clause_ids is not None and cid not in self._clause_ids:
                return f"引用的条款 {cid} 不属于本次批次"
            if normalize(source["quote"]) not in normalize(clause_source(clause)):
                return f"引文在条款 {cid} 的原文中找不到"
        return None
