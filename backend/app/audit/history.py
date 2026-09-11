"""Deterministic retrieval of similar finalized audit answers."""

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AnswerDraft, AuditEngagement, AuditQuestion, QuestionStatus

_WORDS = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "do",
        "does",
        "how",
        "is",
        "of",
        "the",
        "what",
        "which",
        "如何",
        "什么",
        "是否",
    }
)


@dataclass(frozen=True)
class SimilarAnswer:
    answer_id: int
    question_id: int
    question_text: str
    engagement_name: str
    answer: str
    language: str
    finalized_at: datetime
    similarity: float


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for value in _WORDS.findall(text.casefold()):
        if value in _STOP_WORDS:
            continue
        if re.fullmatch(r"[\u3400-\u9fff]+", value):
            tokens.update(value)
            tokens.update(value[index : index + 2] for index in range(len(value) - 1))
        else:
            tokens.add(value)
    return tokens


def similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


async def similar_history(
    session: AsyncSession,
    question_text: str,
    *,
    exclude_question_id: int | None = None,
    limit: int = 3,
) -> list[SimilarAnswer]:
    statement = (
        select(AnswerDraft, AuditQuestion, AuditEngagement.name)
        .join(AuditQuestion, AuditQuestion.id == AnswerDraft.question_id)
        .join(AuditEngagement, AuditEngagement.id == AuditQuestion.engagement_id)
        .where(
            AnswerDraft.finalized_at.is_not(None),
            AuditQuestion.status == QuestionStatus.FINALIZED,
        )
    )
    if exclude_question_id is not None:
        statement = statement.where(AuditQuestion.id != exclude_question_id)
    candidates = []
    for answer, question, engagement_name in await session.execute(statement):
        score = similarity(question_text, question.question_text)
        if score <= 0:
            continue
        candidates.append(
            SimilarAnswer(
                answer_id=answer.id,
                question_id=question.id,
                question_text=question.question_text,
                engagement_name=engagement_name,
                answer=answer.final_body or answer.body,
                language=answer.language,
                finalized_at=answer.finalized_at,
                similarity=round(score, 4),
            )
        )
    candidates.sort(key=lambda item: (-item.similarity, -item.answer_id))
    return candidates[:limit]
