import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.citations import AnswerCitationValidator, ground_answer_citations
from app.audit.history import similar_history
from app.audit.models import AnswerDraft, AuditEngagement, AuditQuestion, QuestionStatus
from app.audit.prompts import ANSWER_SCHEMA, ANSWER_SYSTEM, ANSWER_TASK_KEY
from app.controls.models import Control, ControlSource
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.evidence.models import EvidenceItem
from app.frameworks.models import Framework
from app.iam.audit import record
from app.iam.models import User
from app.llm.runner import run
from app.review import service as review_service
from app.review.models import Proposal, ProposalKind, ProposalStatus
from app.search.service import search


def require_engagement_scope(actor: User, engagement_id: int) -> None:
    if actor.engagement_scope_id is not None and actor.engagement_scope_id != engagement_id:
        raise NotFound("审计项目不存在")


async def require_question_scope(
    session: AsyncSession, actor: User, question_id: int
) -> AuditQuestion:
    question = await session.get(AuditQuestion, question_id)
    if question is None:
        raise NotFound("审计问题不存在")
    require_engagement_scope(actor, question.engagement_id)
    return question


async def create_engagement(session: AsyncSession, data: dict, *, actor: User) -> AuditEngagement:
    if actor.engagement_scope_id is not None:
        raise Forbidden("限范围账号不能创建审计项目")
    framework_id = data.get("framework_id")
    if framework_id is not None and await session.get(Framework, framework_id) is None:
        raise NotFound("框架不存在")
    engagement = AuditEngagement(**data, created_by=actor.id)
    session.add(engagement)
    await session.flush()
    await record(
        session,
        user=actor,
        action="audit_engagement.create",
        entity_type="AuditEngagement",
        entity_id=engagement.id,
        after=data,
    )
    return engagement


async def import_questions(
    session: AsyncSession, engagement_id: int, text: str, language: str, *, actor: User
) -> list[AuditQuestion]:
    questions = [
        (line.strip().lstrip("-• ").strip(), language) for line in text.splitlines() if line.strip()
    ]
    return await import_question_rows(
        session, engagement_id, questions, actor=actor, source="paste"
    )


async def import_question_rows(
    session: AsyncSession,
    engagement_id: int,
    questions: list[tuple[str, str]],
    *,
    actor: User,
    source: str,
) -> list[AuditQuestion]:
    require_engagement_scope(actor, engagement_id)
    if await session.get(AuditEngagement, engagement_id) is None:
        raise NotFound("审计项目不存在")
    if not questions:
        raise AppError("至少输入一个审计问题")
    if len(questions) > 200:
        raise AppError("一次最多导入 200 个问题")
    if any(not question or language not in {"zh", "en"} for question, language in questions):
        raise AppError("审计问题或语言无效")
    start = await session.scalar(
        select(func.coalesce(func.max(AuditQuestion.seq), 0)).where(
            AuditQuestion.engagement_id == engagement_id
        )
    )
    rows = [
        AuditQuestion(
            engagement_id=engagement_id,
            seq=start + index,
            question_text=question,
            language=language,
            status=QuestionStatus.PENDING,
        )
        for index, (question, language) in enumerate(questions, 1)
    ]
    session.add_all(rows)
    await session.flush()
    await record(
        session,
        user=actor,
        action="audit_questions.import",
        entity_type="AuditEngagement",
        entity_id=engagement_id,
        after={"count": len(rows), "question_ids": [row.id for row in rows], "source": source},
    )
    return rows


async def generate_answer(session: AsyncSession, question_id: int, language: str, *, actor: User):
    question = await require_question_scope(session, actor, question_id)
    existing = await session.scalar(
        select(AnswerDraft.id).where(AnswerDraft.question_id == question_id)
    )
    if existing is not None:
        raise Conflict("该问题已有答复草稿")
    pending = await session.scalars(
        select(Proposal).where(
            Proposal.kind == ProposalKind.ANSWER,
            Proposal.status == ProposalStatus.PENDING,
        )
    )
    if any(proposal.payload.get("question_id") == question_id for proposal in pending):
        raise Conflict("该问题已有待审核的答复提案")
    result_set = await search(session, question.question_text, limit=8)
    if not result_set.hits:
        raise AppError("没有检索到可引用的内部条款，无法生成可靠答复")
    clause_ids = {hit.clause_id for hit in result_set.hits}
    controls = list(
        await session.scalars(
            select(Control)
            .join(ControlSource)
            .where(ControlSource.clause_id.in_(clause_ids))
            .distinct()
        )
    )
    control_ids = {control.id for control in controls}
    evidence = (
        list(
            await session.scalars(
                select(EvidenceItem).where(EvidenceItem.control_id.in_(control_ids))
            )
        )
        if control_ids
        else []
    )
    sources = [
        {
            "clause_id": hit.clause_id,
            "document": hit.document_title,
            "label": hit.citation_label,
            "text": hit.text,
        }
        for hit in result_set.hits
    ]
    history = await similar_history(
        session, question.question_text, exclude_question_id=question.id, limit=3
    )
    prompt = json.dumps(
        {
            "question": question.question_text,
            "requested_language": language,
            "sources": sources,
            "controls": [
                {"id": row.id, "code": row.code, "statement": row.statement} for row in controls
            ],
            "evidence": [
                {
                    "id": row.id,
                    "control_id": row.control_id,
                    "title": row.title,
                    "status": row.status.value,
                    "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                }
                for row in evidence
            ],
            "similar_finalized_answers": [
                {
                    "question": row.question_text,
                    "answer": row.answer[:4000],
                    "language": row.language,
                    "similarity": row.similarity,
                }
                for row in history
            ],
            "schema": ANSWER_SCHEMA,
        },
        ensure_ascii=False,
    )
    # Do not keep a read transaction open while waiting for the external model.
    await session.commit()
    result = await run(
        session,
        task_key=ANSWER_TASK_KEY,
        system=ANSWER_SYSTEM,
        prompt=prompt,
        schema=ANSWER_SCHEMA,
        interactive=True,
        citation_validator=AnswerCitationValidator(
            session,
            allowed_clause_ids=clause_ids,
            allowed_control_ids=control_ids,
            allowed_evidence_ids={row.id for row in evidence},
            require_quotes=False,
        ),
    )
    if result.payload["language"] != language:
        raise AppError("模型返回的答复语言与请求不一致，请重试")
    result.payload["citations"] = await ground_answer_citations(session, result.payload)
    if not result.payload["citations"]:
        raise AppError("模型没有选择可用的内部条款，请重试")
    payload = {"question_id": question.id, **result.payload}
    proposal = await review_service.create(
        session,
        kind=ProposalKind.ANSWER,
        payload=payload,
        citations=result.payload["citations"],
        confidence=result.confidence,
        llm_call_id=result.llm_call_id,
        actor=actor,
    )
    await session.flush()
    return proposal


async def update_answer(
    session: AsyncSession, answer: AnswerDraft, body: str, *, actor: User
) -> AnswerDraft:
    await require_question_scope(session, actor, answer.question_id)
    if answer.finalized_at is not None:
        raise Conflict("已定稿答复不能再编辑")
    before = {"body": answer.body}
    answer.body = body
    answer.reviewed_by = actor.id
    await record(
        session,
        user=actor,
        action="answer.update",
        entity_type="AnswerDraft",
        entity_id=answer.id,
        before=before,
        after={"body": body},
    )
    await session.flush()
    return answer


async def finalize_answer(
    session: AsyncSession, answer: AnswerDraft, *, actor: User
) -> AnswerDraft:
    question = await require_question_scope(session, actor, answer.question_id)
    if answer.finalized_at is not None:
        raise Conflict("答复已经定稿")
    answer.final_body = answer.body
    answer.finalized_at = datetime.now(UTC)
    answer.reviewed_by = actor.id
    question.status = QuestionStatus.FINALIZED
    await record(
        session,
        user=actor,
        action="answer.finalize",
        entity_type="AnswerDraft",
        entity_id=answer.id,
        after={"question_id": answer.question_id},
    )
    await session.flush()
    return answer
