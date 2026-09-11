import re
from collections.abc import Collection
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.llm.validation import normalize


class AnswerCitationValidator:
    def __init__(
        self,
        session: AsyncSession,
        *,
        allowed_clause_ids: Collection[int],
        allowed_control_ids: Collection[int] | None = None,
        allowed_evidence_ids: Collection[int] | None = None,
        require_quotes: bool = True,
    ) -> None:
        self._session = session
        self._allowed_clauses = frozenset(allowed_clause_ids)
        self._allowed_controls = (
            frozenset(allowed_control_ids) if allowed_control_ids is not None else None
        )
        self._allowed_evidence = (
            frozenset(allowed_evidence_ids) if allowed_evidence_ids is not None else None
        )
        self._require_quotes = require_quotes

    async def check(self, payload: dict[str, Any]) -> str | None:
        citations = payload.get("citations")
        if not isinstance(citations, list) or not citations:
            return "答复必须引用至少一条内部条款"
        wanted: set[int] = set()
        for citation in citations:
            if not isinstance(citation, dict):
                return "答复引用格式无效"
            clause_id, quote = citation.get("clause_id"), citation.get("quote")
            if type(clause_id) is not int or clause_id not in self._allowed_clauses:
                return f"条款 {clause_id!r} 不属于本次检索结果"
            if self._require_quotes and (not isinstance(quote, str) or not normalize(quote)):
                return f"条款 {clause_id} 缺少原文引用"
            wanted.add(clause_id)
        for field, allowed, label in (
            ("cited_control_ids", self._allowed_controls, "控制项"),
            ("suggested_evidence_ids", self._allowed_evidence, "证据"),
        ):
            values = payload.get(field)
            if allowed is None:
                continue
            if not isinstance(values, list) or any(type(value) is not int for value in values):
                return f"{label}引用格式无效"
            outside = set(values) - allowed
            if outside:
                return f"{label} {min(outside)} 不属于本次检索结果"
        if not self._require_quotes:
            return None
        clauses = {
            clause.id: clause.text
            for clause in await self._session.scalars(select(Clause).where(Clause.id.in_(wanted)))
        }
        for citation in citations:
            clause_id = citation["clause_id"]
            if clause_id not in clauses:
                return f"条款 {clause_id} 不存在"
            if normalize(citation["quote"]) not in normalize(clauses[clause_id]):
                return f"引用在条款 {clause_id} 的正文中找不到"
        return None


def _best_excerpt(text: str, context: str) -> str:
    compact = " ".join(text.split())
    parts = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", compact) if part.strip()]
    if not parts:
        return compact
    terms = {term.casefold() for term in re.findall(r"[\w-]{3,}", context)}

    def score(part: str) -> tuple[int, int]:
        words = {term.casefold() for term in re.findall(r"[\w-]{3,}", part)}
        return len(terms & words), -len(part)

    return max(parts, key=score)[:600]


async def ground_answer_citations(
    session: AsyncSession, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    ids = list(dict.fromkeys(citation["clause_id"] for citation in payload["citations"]))
    clauses = {
        clause.id: clause.text
        for clause in await session.scalars(select(Clause).where(Clause.id.in_(ids)))
    }
    return [
        {
            "clause_id": clause_id,
            "quote": _best_excerpt(clauses[clause_id], payload["body"]),
        }
        for clause_id in ids
        if clause_id in clauses
    ]
