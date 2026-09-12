import hashlib
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Integer, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.controls.models import Control, ControlSource
from app.errors import AppError, Conflict, Forbidden, NotFound
from app.frameworks.models import FrameworkItem
from app.iam.audit import record
from app.iam.models import User
from app.iam.permissions import Permission, has_permission
from app.ingest.models import Document
from app.review import thresholds as thresholds_module
from app.review.materialize import (
    ControlPayload,
    find_statement_duplicate,
    lock_control_writes,
    materialize,
)
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


class ReviewTier(StrEnum):
    AUTO = "auto"
    SAMPLE = "sample"
    MANUAL = "manual"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class ReviewAssessment:
    tier: ReviewTier
    reasons: tuple[str, ...]


def _sampled(proposal: Proposal, rate: float) -> bool:
    """Stable sampling: repeated page loads never change the review set."""
    if not math.isfinite(rate) or rate <= 0:
        return False
    if rate >= 1:
        return True
    key = f"{proposal.kind.value}:{proposal.id}".encode()
    bucket = int.from_bytes(hashlib.sha256(key).digest()[:8], "big") / 2**64
    return bucket < rate


def assess(
    proposal: Proposal,
    limits: thresholds_module.Thresholds,
    *,
    ocr_flag: bool,
    context_complete: bool = True,
    exact_duplicate: bool = False,
) -> ReviewAssessment:
    """Classify an AI proposal while keeping uncertain output out of formal data."""
    if proposal.status != ProposalStatus.PENDING:
        return ReviewAssessment(ReviewTier.MANUAL, ("already_decided",))
    if proposal.kind not in (ProposalKind.MAPPING, ProposalKind.RELATION):
        return ReviewAssessment(ReviewTier.MANUAL, ("unsupported_kind",))
    if not context_complete:
        return ReviewAssessment(ReviewTier.MANUAL, ("missing_context",))
    if ocr_flag:
        return ReviewAssessment(ReviewTier.MANUAL, ("ocr_suspect",))

    confidence = proposal.confidence
    high_confidence = (
        type(confidence) in (int, float)
        and math.isfinite(confidence)
        and 0 <= limits.force_manual <= limits.auto_accept <= 1
        and confidence >= limits.auto_accept
    )
    reasons: list[str] = []
    eligible = False
    if proposal.kind == ProposalKind.MAPPING:
        doubtful = bool(
            re.search(RATIONALE_DOUBT, str(proposal.payload.get("rationale", "")), re.IGNORECASE)
        )
        if doubtful:
            reasons.append("hedged_rationale")
        eligible = high_confidence and not doubtful
    else:
        relation_type = proposal.payload.get("relation_type")
        eligible = high_confidence and relation_type == "duplicates" and exact_duplicate
        if relation_type == "depends_on":
            reasons.append("directional_relation")
        elif not exact_duplicate:
            reasons.append("non_exact_duplicate")

    if eligible:
        if _sampled(proposal, limits.review_sample_rate):
            return ReviewAssessment(ReviewTier.SAMPLE, ("continuous_sample",))
        return ReviewAssessment(ReviewTier.AUTO, ("validated_high_confidence",))
    if _sampled(proposal, limits.review_sample_rate):
        return ReviewAssessment(ReviewTier.SAMPLE, tuple(reasons or ["calibration_sample"]))
    if confidence is None or not high_confidence:
        reasons.append("below_auto_threshold")
    return ReviewAssessment(ReviewTier.DEFERRED, tuple(dict.fromkeys(reasons)))


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
    elif kind == ProposalKind.ANSWER:
        from app.audit.citations import AnswerCitationValidator
        from app.audit.schemas import AnswerProposalPayload

        try:
            AnswerProposalPayload.model_validate(payload)
        except ValidationError as exc:
            raise AppError(f"审计答复提案无效：{exc}") from exc
        if payload.get("citations") != citations:
            raise AppError("答复提案引用与内容不一致")
        clause_ids = {
            citation.get("clause_id")
            for citation in citations
            if isinstance(citation, dict) and type(citation.get("clause_id")) is int
        }
        reason = await AnswerCitationValidator(
            session, allowed_clause_ids=clause_ids
        ).check(payload)
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
    if not 1 <= limit <= 2000:
        raise AppError("limit 必须在 1 到 2000 之间")
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


def proposal_control_ids(proposal: Proposal) -> set[int]:
    keys = (
        ("control_id",) if proposal.kind == ProposalKind.MAPPING
        else ("from_control_id", "to_control_id")
    )
    return {
        value
        for key in keys
        if type(value := proposal.payload.get(key)) is int
    }


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
    control_ids = {cid for p in proposals for cid in proposal_control_ids(p)}
    proposal_controls = {p.id: proposal_control_ids(p) for p in proposals}
    control_clauses: dict[int, set[int]] = {}
    if control_ids:
        rows = await session.execute(
            select(ControlSource.control_id, ControlSource.clause_id).where(
                ControlSource.control_id.in_(control_ids)
            )
        )
        for control_id, clause_id in rows:
            control_clauses.setdefault(control_id, set()).add(clause_id)
            wanted_clauses.add(clause_id)
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
        for control_id in proposal_controls[proposal.id]:
            touched.update(
                clause_document[clause_id]
                for clause_id in control_clauses.get(control_id, set())
                if clause_id in clause_document
            )
        if proposal.document_id is not None:
            touched.add(proposal.document_id)
        if touched & flagged:
            hit.add(proposal.id)
    return frozenset(hit)


def eligible(
    proposal: Proposal,
    limits: thresholds_module.Thresholds,
    *,
    ocr_flag: bool,
    statement_duplicate: bool = False,
) -> bool:
    """纯函数：给定 OCR 标记，这条提案能否批量接受。

    拆出来是为了让整页判定可以先批量查标记、再在内存里逐条判，
    不必每条提案都往库里跑一次。

    正文与已有控制点逐字相同的，一律禁止批量——理由与 OCR 存疑那条相同：
    它需要一个逐条的选择（并入还是另建），批量按钮给不了。
    """
    return (
        not statement_duplicate
        and proposal.status == ProposalStatus.PENDING
        and proposal.kind == ProposalKind.CONTROL_EXTRACT
        and proposal.payload.get("origin") != "matrix"
        and thresholds_module.bulk_acceptable(proposal, limits, ocr_flag=ocr_flag)
    )


async def eligibility(
    session: AsyncSession, proposal: Proposal, limits: thresholds_module.Thresholds
) -> tuple[bool, bool]:
    flag = await ocr_flag(session, proposal)
    duplicate = None
    if proposal.kind == ProposalKind.CONTROL_EXTRACT:
        duplicate = await find_statement_duplicate(
            session, str((proposal.payload or {}).get("statement") or "")
        )
    return (
        eligible(proposal, limits, ocr_flag=flag, statement_duplicate=duplicate is not None),
        flag,
    )


async def decide(
    session: AsyncSession,
    proposal_id: int,
    *,
    actor: User,
    decision: Decision,
    payload: dict[str, Any] | None = None,
    reason: str | None = None,
    merge_into_control_id: int | None = None,
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
                await materialize(
                    session,
                    proposal,
                    data,
                    actor_id=actor.id,
                    merge_into_control_id=merge_into_control_id,
                )
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
                    "merged_into_control_id": merge_into_control_id,
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


async def auto_process(
    session: AsyncSession, *, actor: User, limit: int = 200
) -> dict[str, int]:
    """Materialize only the narrow, deterministic auto tier.

    The initiating user is logged on the batch action. Individual decisions are
    attributed to the system (decided_by NULL) so an automated result is never
    presented as a human approval.
    """
    require_actor(actor)
    if not 1 <= limit <= 200:
        raise AppError("limit 必须在 1 到 200 之间")
    proposals = list(
        await session.scalars(
            select(Proposal)
            .where(
                Proposal.status == ProposalStatus.PENDING,
                Proposal.kind.in_((ProposalKind.MAPPING, ProposalKind.RELATION)),
            )
            .order_by(Proposal.id)
            .limit(5000)
        )
    )
    limits = await thresholds_module.load(session)
    flagged = await ocr_flags(session, proposals)

    control_ids = {value for p in proposals for value in proposal_control_ids(p)}
    controls = {
        control.id: control
        for control in (
            await session.scalars(select(Control).where(Control.id.in_(control_ids)))
            if control_ids else []
        )
    }
    item_ids = {
        value
        for p in proposals
        if p.kind == ProposalKind.MAPPING
        if type(value := p.payload.get("framework_item_id")) is int
    }
    existing_items = set(
        await session.scalars(
            select(FrameworkItem.id).where(FrameworkItem.id.in_(item_ids))
        )
    ) if item_ids else set()

    assessments: dict[int, ReviewAssessment] = {}
    for proposal in proposals:
        ids = proposal_control_ids(proposal)
        context_complete = ids <= controls.keys()
        exact_duplicate = False
        if proposal.kind == ProposalKind.MAPPING:
            context_complete = context_complete and proposal.payload.get("framework_item_id") in existing_items
        elif len(ids) == 2 and context_complete:
            left = controls[proposal.payload["from_control_id"]].statement
            right = controls[proposal.payload["to_control_id"]].statement
            exact_duplicate = " ".join(left.split()).casefold() == " ".join(right.split()).casefold()
        assessments[proposal.id] = assess(
            proposal,
            limits,
            ocr_flag=proposal.id in flagged,
            context_complete=context_complete,
            exact_duplicate=exact_duplicate,
        )

    counts = {tier.value: 0 for tier in ReviewTier}
    for assessment in assessments.values():
        counts[assessment.tier.value] += 1
    accepted = skipped = 0
    for proposal in proposals:
        assessment = assessments[proposal.id]
        if assessment.tier != ReviewTier.AUTO or accepted >= limit:
            continue
        try:
            async with session.begin_nested():
                await lock_control_writes(session)
                locked = await locked_proposal(session, proposal.id)
                if locked is None or locked.status != ProposalStatus.PENDING:
                    skipped += 1
                    continue
                data = deepcopy(locked.payload)
                await materialize(session, locked, data, actor_id=None)
                locked.status = ProposalStatus.ACCEPTED
                locked.decided_by = None
                locked.decided_at = datetime.now(UTC)
                locked.decided_payload = data
                await record(
                    session,
                    user=None,
                    action="proposal.auto_accept",
                    entity_type="Proposal",
                    entity_id=locked.id,
                    before={"status": ProposalStatus.PENDING.value},
                    after={
                        "status": ProposalStatus.ACCEPTED.value,
                        "policy": "validated_high_confidence_v1",
                        "reasons": list(assessment.reasons),
                    },
                )
                await session.flush()
            accepted += 1
        except (AppError, IntegrityError):
            skipped += 1

    await record(
        session,
        user=actor,
        action="proposal.auto_process",
        entity_type="ProposalBatch",
        entity_id="mapping-relation",
        after={"scanned": len(proposals), "accepted": accepted, "skipped": skipped, **counts},
    )
    await session.flush()
    return {"scanned": len(proposals), "accepted": accepted, "skipped": skipped, **counts}
