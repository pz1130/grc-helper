from copy import deepcopy
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Integer, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.iam.audit import record
from app.iam.models import User
from app.iam.permissions import Permission, has_permission
from app.ingest.models import Document
from app.review import thresholds as thresholds_module
from app.review.materialize import ControlPayload, lock_control_writes, materialize
from app.review.models import Proposal, ProposalKind, ProposalStatus

# 模型在 rationale 里自己写了否定表述，却仍把强度标成 full/partial 的那批。
# 实测 281 条 partial 里 101 条命中，其中 25 条置信度仍在 0.75 以上——是最可能
# 标错的一批。这是**关键词启发式**，不是判定：有些 does not 出现在无害的从句里。
# 界面上必须如实标成「启发式」，别让人当成结论。
RATIONALE_DOUBT = r"does not|doesn't|not specifically|no explicit|not address|lacks|absent"


class Decision(StrEnum):
    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"


_STATUS = {
    Decision.ACCEPT: ProposalStatus.ACCEPTED,
    Decision.MODIFY: ProposalStatus.MODIFIED,
    Decision.REJECT: ProposalStatus.REJECTED,
}


async def create(
    session: AsyncSession,
    *,
    kind: ProposalKind,
    payload: dict[str, Any],
    citations: list[dict[str, Any]],
    confidence: float | None = None,
    llm_call_id: int | None = None,
    document_id: int | None = None,
    actor: User | None = None,
) -> Proposal:
    """Audited proposal creation; caller owns the transaction and worker authentication."""
    import math

    if not isinstance(payload, dict) or not isinstance(citations, list):
        raise AppError("提案内容及引用格式无效")
    if confidence is not None and (
        type(confidence) not in (int, float)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise AppError("置信度必须在 0 到 1 之间")
    if kind == ProposalKind.CONTROL_EXTRACT:
        try:
            ControlPayload.model_validate(payload)
        except ValidationError as exc:
            raise AppError(f"控制点提案无效：{exc}") from exc
        if payload.get("citations") != citations:
            raise AppError("提案引用与内容不一致")
        from app.extraction.citations import ClauseCitationValidator

        reason = await ClauseCitationValidator(session, document_id=document_id).check(
            {"controls": [payload]}
        )
        if reason:
            raise AppError(f"引用校验失败：{reason}")
    elif kind == ProposalKind.MAPPING:
        from app.mapping.citations import MappingCitationValidator

        item_id = payload.get("framework_item_id")
        if type(item_id) is not int:
            raise AppError("映射提案缺少 framework_item_id")
        reason = await MappingCitationValidator(session, item_ids={item_id}).check(
            {"mappings": [payload]}
        )
        if reason:
            raise AppError(f"引用校验失败：{reason}")
    elif kind == ProposalKind.RELATION:
        from app.relations.citations import RelationCitationValidator

        ends = (payload.get("from_control_id"), payload.get("to_control_id"))
        if any(type(value) is not int for value in ends):
            raise AppError("关系提案缺少控制点编号")
        reason = await RelationCitationValidator(session, control_ids=set(ends)).check(
            {"relations": [payload]}
        )
        if reason:
            raise AppError(f"引用校验失败：{reason}")
    proposal = Proposal(
        kind=kind,
        payload=deepcopy(payload),
        citations=deepcopy(citations),
        confidence=confidence,
        llm_call_id=llm_call_id,
        document_id=document_id,
        status=ProposalStatus.PENDING,
    )
    session.add(proposal)
    await session.flush()
    await record(
        session,
        user=actor,
        action="proposal.create",
        entity_type="Proposal",
        entity_id=proposal.id,
        after={"kind": kind.value, "llm_call_id": llm_call_id, "document_id": document_id},
    )
    await session.flush()
    return proposal


def require_actor(actor: User, permission: Permission = Permission.REVIEW_DECIDE) -> None:
    if (
        not actor.is_active
        or not has_permission(actor.role, permission)
        or (actor.expires_at is not None and actor.expires_at <= datetime.now(UTC))
    ):
        raise Forbidden(f"当前账号无权执行该操作（需要 {permission.value}）")


def validate_decision(
    decision: Decision, payload: dict[str, Any] | None, reason: str | None
) -> None:
    if decision == Decision.MODIFY:
        if not isinstance(payload, dict) or not payload:
            raise AppError("修改后接受必须给出改后的内容")
    elif payload is not None:
        raise AppError("仅修改后接受允许提供内容")
    if decision == Decision.REJECT:
        if not isinstance(reason, str) or not reason.strip():
            raise AppError("拒绝必须给出原因")
    elif reason is not None:
        raise AppError("仅拒绝允许提供原因")


async def pending(
    session: AsyncSession,
    *,
    kind: ProposalKind | None = None,
    document_id: int | None = None,
    strength: list[str] | None = None,
    framework: str | None = None,
    doubtful_rationale: bool = False,
    limit: int = 50,
) -> list[Proposal]:
    if not 1 <= limit <= 200:
        raise AppError("limit 必须在 1 到 200 之间")
    stmt = (
        select(Proposal)
        .where(Proposal.status == ProposalStatus.PENDING)
        .order_by(Proposal.confidence.asc().nullsfirst(), Proposal.id)
        .limit(limit)
    )
    if kind is not None:
        stmt = stmt.where(Proposal.kind == kind)
    if document_id is not None:
        stmt = stmt.where(Proposal.document_id == document_id)
    if strength:
        # 映射提案里只有 full/partial 影响覆盖度，supporting 不消除差距——
        # 审核 400 多条时，能只看影响结论的那些是刚需。
        stmt = stmt.where(Proposal.payload["strength"].astext.in_(strength))
    if framework:
        # 按框架筛：CSF 106 个要求项 vs 800-53 的 1014 个，两者的审阅回报差一个量级，
        # 能只看一个框架是把 400 多条切成可做的量的最有效一刀。
        from app.frameworks.models import Framework, FrameworkItem

        stmt = stmt.where(
            Proposal.payload["framework_item_id"].astext.cast(Integer).in_(
                select(FrameworkItem.id)
                .join(Framework, Framework.id == FrameworkItem.framework_id)
                .where(Framework.key == framework)
            )
        )
    if doubtful_rationale:
        stmt = stmt.where(Proposal.payload["rationale"].astext.op("~*")(RATIONALE_DOUBT))
    return list(await session.scalars(stmt))


async def locked_proposal(session: AsyncSession, proposal_id: int) -> Proposal | None:
    # Refresh cached identities after the lock: another transaction may have decided it.
    return await session.scalar(
        select(Proposal)
        .where(Proposal.id == proposal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def citation_clause_ids(proposal: Proposal) -> set[int]:
    ids: set[int] = set()
    for citations in (proposal.citations, proposal.payload.get("citations", [])):
        if isinstance(citations, list):
            ids.update(
                c["clause_id"]
                for c in citations
                if isinstance(c, dict) and type(c.get("clause_id")) is int
            )
    return ids


async def ocr_flag(session: AsyncSession, proposal: Proposal) -> bool:
    stmt = (
        select(Document.id)
        .where(
            Document.ocr_quality_flag.is_(True),
            or_(
                Document.id == proposal.document_id,
                Document.id.in_(
                    select(Clause.document_id).where(
                        Clause.id.in_(citation_clause_ids(proposal))
                    )
                ),
            ),
        )
        .limit(1)
    )
    return await session.scalar(stmt) is not None


async def ocr_flags(
    session: AsyncSession, proposals: list[Proposal]
) -> frozenset[int]:
    """整页两次查完 OCR 存疑标记，返回命中的提案 id。

    逐条查时 412 条映射提案就是 412 次往返。这里先把所有引用条款一次映射到
    文档，再一次查出其中哪些文档存疑，剩下的判断在内存里做。
    """
    if not proposals:
        return frozenset()
    wanted_clauses = {cid for p in proposals for cid in citation_clause_ids(p)}
    clause_document: dict[int, int] = {}
    if wanted_clauses:
        rows = await session.execute(
            select(Clause.id, Clause.document_id).where(Clause.id.in_(wanted_clauses))
        )
        clause_document = dict(rows.all())

    documents = {p.document_id for p in proposals if p.document_id is not None}
    documents.update(clause_document.values())
    if not documents:
        return frozenset()
    flagged = set(
        await session.scalars(
            select(Document.id).where(
                Document.id.in_(documents), Document.ocr_quality_flag.is_(True)
            )
        )
    )
    if not flagged:
        return frozenset()

    hit = set()
    for proposal in proposals:
        touched = {clause_document[cid]
                   for cid in citation_clause_ids(proposal) if cid in clause_document}
        if proposal.document_id is not None:
            touched.add(proposal.document_id)
        if touched & flagged:
            hit.add(proposal.id)
    return frozenset(hit)


def eligible(
    proposal: Proposal, limits: thresholds_module.Thresholds, *, ocr_flag: bool
) -> bool:
    """纯函数：给定 OCR 标记，这条提案能否批量接受。

    拆出来是为了让整页判定可以先批量查标记、再在内存里逐条判，
    不必每条提案都往库里跑一次。
    """
    return (
        proposal.status == ProposalStatus.PENDING
        and proposal.kind == ProposalKind.CONTROL_EXTRACT
        and proposal.payload.get("origin") != "matrix"
        and thresholds_module.bulk_acceptable(proposal, limits, ocr_flag=ocr_flag)
    )


async def eligibility(
    session: AsyncSession, proposal: Proposal, limits: thresholds_module.Thresholds
) -> tuple[bool, bool]:
    flag = await ocr_flag(session, proposal)
    return eligible(proposal, limits, ocr_flag=flag), flag


async def decide(
    session: AsyncSession,
    proposal_id: int,
    *,
    actor: User,
    decision: Decision,
    payload: dict[str, Any] | None = None,
    reason: str | None = None,
) -> Proposal:
    require_actor(actor)
    try:
        decision = Decision(decision)
    except (ValueError, TypeError) as exc:
        raise AppError("无效的裁定操作") from exc
    try:
        async with session.begin_nested():
            await lock_control_writes(session)
            proposal = await locked_proposal(session, proposal_id)
            if proposal is None:
                raise NotFound("提案不存在")
            if proposal.status != ProposalStatus.PENDING:
                raise Conflict(f"该提案已被裁定为 {proposal.status.value}，不能重复裁定")
            validate_decision(decision, payload, reason)
            before = {"status": proposal.status.value}
            if decision != Decision.REJECT:
                data = deepcopy(payload if decision == Decision.MODIFY else proposal.payload)
                await materialize(session, proposal, data, actor_id=actor.id)
                # Snapshot precisely what was approved; raw AI payload stays immutable.
                proposal.decided_payload = data
            proposal.status = _STATUS[decision]
            proposal.decided_by = actor.id
            proposal.decided_at = datetime.now(UTC)
            proposal.reject_reason = reason.strip() if decision == Decision.REJECT else None
            await record(
                session,
                user=actor,
                action=f"proposal.{decision.value}",
                entity_type="Proposal",
                entity_id=proposal.id,
                before=before,
                after={
                    "kind": proposal.kind.value,
                    "status": proposal.status.value,
                    "decided_payload": proposal.decided_payload,
                    "reject_reason": proposal.reject_reason,
                },
            )
            await session.flush()
        return proposal
    except IntegrityError as exc:
        raise Conflict("确认内容与现有数据冲突，请刷新后重试") from exc


async def bulk_accept(
    session: AsyncSession, proposal_ids: list[int], *, actor: User
) -> dict[str, int]:
    require_actor(actor)
    if (
        not proposal_ids
        or len(proposal_ids) > 200
        or any(type(value) is not int or value <= 0 for value in proposal_ids)
        or len(set(proposal_ids)) != len(proposal_ids)
    ):
        raise AppError("提案编号必须为 1 到 200 个不同的正整数")
    limits = await thresholds_module.load(session)
    accepted = skipped = 0
    # All-or-nothing on invalid content, while ineligible/missing rows are counted skips.
    # Deterministic row lock order prevents deadlocks between overlapping batches.
    async with session.begin_nested():
        await lock_control_writes(session)
        for proposal_id in sorted(proposal_ids):
            proposal = await locked_proposal(session, proposal_id)
            if proposal is None:
                skipped += 1
                continue
            acceptable, _ = await eligibility(session, proposal, limits)
            if not acceptable:
                skipped += 1
                continue
            await decide(session, proposal_id, actor=actor, decision=Decision.ACCEPT)
            accepted += 1
    return {"accepted": accepted, "skipped": skipped}
