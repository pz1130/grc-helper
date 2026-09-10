from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.controls.models import Control, ControlSource
from app.db import get_session
from app.frameworks.coverage import CLOSING
from app.frameworks.models import FrameworkItem, Mapping, MappingStrength
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.ingest.models import Document
from app.review import service
from app.review.models import Proposal, ProposalKind, ProposalStatus
from app.review.schemas import BulkAcceptIn, DecideIn, ProposalOut
from app.review.thresholds import Thresholds, load

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


def _clause_ids(proposals: list[Proposal]) -> set[int]:
    return {
        citation["clause_id"]
        for proposal in proposals
        for citation in (proposal.citations or [])
        if isinstance(citation, dict) and type(citation.get("clause_id")) is int
    }


async def clause_context(
    session: AsyncSession, proposals: list[Proposal]
) -> dict[int, dict[str, Any]]:
    """整页一次查完条款来源，不按提案逐条查。

    citations 存的是模型原始产出，只有 {clause_id, quote}；审核人拿到裸数字
    既看不出出自哪份规章，也无从判断引文有没有被断章取义。
    """
    wanted = _clause_ids(proposals)
    if not wanted:
        return {}
    rows = await session.execute(
        select(Clause, Document)
        .join(Document, Document.id == Clause.document_id)
        .where(Clause.id.in_(wanted))
    )
    return {
        clause.id: {
            "document_id": document.id,
            "document_title": document.title,
            "citation_label": clause.citation_label,
            "heading_path": clause.heading_path,
        }
        for clause, document in rows
    }


@dataclass(frozen=True)
class PageContext:
    """一页提案渲染所需的全部旁路数据，一次性查好。

    此前每条提案要单独查 3 次（OCR 标记 + 框架项 + 控制点），412 条映射提案
    就是 1200 多次往返。这里按页批量查，往返数与提案条数无关。
    """

    clauses: dict[int, dict[str, Any]] = field(default_factory=dict)
    items: dict[int, FrameworkItem] = field(default_factory=dict)
    controls: dict[int, Control] = field(default_factory=dict)
    ocr_flagged: frozenset[int] = frozenset()
    # 框架项 → 已确认映射 [(控制点编号, 强度)]。审 supporting 时最要紧的一条
    # 上下文：目标项若已被 full/partial 关掉，这条确认了也不会改变任何结论。
    item_mappings: dict[int, list[tuple[str, str]]] = field(default_factory=dict)
    # 控制点 → 它出自哪几条内部条款。控制点是抽取产物，审核者要能回到原文：
    # OQ-5 记着有 28 条已接受的控制点建立在残缺文本上，看不到出处就发现不了。
    control_sources: dict[int, list[dict[str, Any]]] = field(default_factory=dict)


def _int(value: Any) -> int | None:
    return value if type(value) is int else None


async def page_context(session: AsyncSession, proposals: list[Proposal]) -> PageContext:
    item_ids: set[int] = set()
    control_ids: set[int] = set()
    for proposal in proposals:
        payload = proposal.payload or {}
        if proposal.kind == ProposalKind.MAPPING:
            if (value := _int(payload.get("framework_item_id"))) is not None:
                item_ids.add(value)
            if (value := _int(payload.get("control_id"))) is not None:
                control_ids.add(value)
        elif proposal.kind == ProposalKind.RELATION:
            for key in ("from_control_id", "to_control_id"):
                if (value := _int(payload.get(key))) is not None:
                    control_ids.add(value)

    items = {
        item.id: item
        for item in (
            await session.scalars(select(FrameworkItem).where(FrameworkItem.id.in_(item_ids)))
            if item_ids else []
        )
    }
    controls = {
        control.id: control
        for control in (
            await session.scalars(select(Control).where(Control.id.in_(control_ids)))
            if control_ids else []
        )
    }
    item_mappings: dict[int, list[tuple[str, str]]] = {}
    if item_ids:
        rows = await session.execute(
            select(Mapping.framework_item_id, Control.code, Mapping.strength)
            .join(Control, Control.id == Mapping.control_id)
            .where(Mapping.framework_item_id.in_(item_ids))
            .order_by(Control.code)
        )
        for item_id, code, strength in rows:
            item_mappings.setdefault(item_id, []).append(
                (code, strength.value if hasattr(strength, "value") else str(strength))
            )

    control_sources: dict[int, list[dict[str, Any]]] = {}
    if control_ids:
        rows = await session.execute(
            select(
                ControlSource.control_id,
                Clause.id,
                Clause.citation_label,
                Clause.heading_path,
                Document.id,
                Document.title,
            )
            .join(Clause, Clause.id == ControlSource.clause_id)
            .join(Document, Document.id == Clause.document_id)
            .where(ControlSource.control_id.in_(control_ids))
            .order_by(ControlSource.control_id, Clause.order_index)
        )
        for control_id, clause_id, label, path, document_id, title in rows:
            control_sources.setdefault(control_id, []).append({
                "clause_id": clause_id,
                "citation_label": label,
                "heading_path": path,
                "document_id": document_id,
                "document_title": title,
            })

    return PageContext(
        clauses=await clause_context(session, proposals),
        items=items,
        controls=controls,
        ocr_flagged=await service.ocr_flags(session, proposals),
        item_mappings=item_mappings,
        control_sources=control_sources,
    )


def _enrich(citations: Any, context: dict[int, dict[str, Any]]) -> Any:
    """只做补全，绝不改写模型原始产出的字段。"""
    if not isinstance(citations, list):
        return citations
    enriched = []
    for citation in citations:
        if not isinstance(citation, dict):
            enriched.append(citation)
            continue
        # 条款可能已被删除；补不上就保留原样，不让整页 500。
        extra = context.get(citation.get("clause_id"), {})
        enriched.append({**extra, **citation})
    return enriched


def _control_view(control: Control, context: PageContext) -> dict[str, Any]:
    return {
        "id": control.id,
        "code": control.code,
        "title": control.title,
        "statement": control.statement,
        # 控制点是抽取产物，不是原文。审核者要能一眼看到它出自哪份制度、哪一条，
        # 并点回去核对——判断「这条控制点是否满足某个框架要求」的前提，是先确认
        # 这条控制点本身如实反映了原文。
        "sources": context.control_sources.get(control.id, []),
    }


def present(proposal: Proposal, limits: Thresholds, context: PageContext) -> ProposalOut:
    """纯渲染，不查库——旁路数据全部来自 PageContext。"""
    payload = proposal.payload or {}
    flag = proposal.id in context.ocr_flagged
    acceptable = service.eligible(proposal, limits, ocr_flag=flag)

    mapping: dict[str, Any] | None = None
    if proposal.kind == ProposalKind.MAPPING:
        item = context.items.get(_int(payload.get("framework_item_id")))
        control = context.controls.get(_int(payload.get("control_id")))
        if item is not None and control is not None:
            confirmed = context.item_mappings.get(item.id, [])
            closing = {strength.value for strength in CLOSING}
            mapping = {
                "framework_item": {
                    "id": item.id,
                    "code": item.code,
                    "title": item.title,
                    "description": item.description,
                },
                "control": _control_view(control, context),
                "item_coverage": {
                    # 已被 full/partial 关掉：再加一条不会改变覆盖度，
                    # 而 supporting 连差距清单上的标记都不会新增。
                    "closed": any(strength in closing for _, strength in confirmed),
                    "confirmed": [
                        {"control_code": code, "strength": strength}
                        for code, strength in confirmed
                    ],
                },
            }

    relation: dict[str, Any] | None = None
    if proposal.kind == ProposalKind.RELATION:
        left = context.controls.get(_int(payload.get("from_control_id")))
        right = context.controls.get(_int(payload.get("to_control_id")))
        if left is not None and right is not None:
            relation = {
                "relation_type": payload.get("relation_type"),
                "from": _control_view(left, context),
                "to": _control_view(right, context),
            }

    return ProposalOut.model_validate(proposal).model_copy(
        update={
            "bulk_acceptable": acceptable,
            "ocr_quality_flag": flag,
            "mapping_context": mapping,
            "relation_context": relation,
            "citations": _enrich(proposal.citations, context.clauses),
        }
    )


@router.get("", response_model=list[ProposalOut])
async def list_pending(
    *,
    kind: ProposalKind | None = None,
    document_id: int | None = Query(default=None, gt=0),
    strength: Annotated[list[MappingStrength] | None, Query()] = None,
    framework: Annotated[str | None, Query(max_length=64)] = None,
    doubtful_rationale: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    _: Annotated[User, Depends(require(Permission.READ))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProposalOut]:
    rows = await service.pending(
        session,
        kind=kind,
        document_id=document_id,
        strength=[value.value for value in strength] if strength else None,
        framework=framework,
        doubtful_rationale=doubtful_rationale,
        limit=limit,
    )
    limits = await load(session)
    context = await page_context(session, rows)
    return [present(row, limits, context) for row in rows]


@router.get("/stats")
async def stats(
    _: Annotated[User, Depends(require(Permission.READ))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    rows = await session.execute(
        select(Proposal.kind, func.count())
        .where(Proposal.status == ProposalStatus.PENDING)
        .group_by(Proposal.kind)
    )
    by_kind = {kind.value: count for kind, count in rows}
    return {"pending": sum(by_kind.values()), "by_kind": by_kind}


@router.post("/bulk-accept")
async def bulk_accept(
    payload: BulkAcceptIn,
    actor: Annotated[User, Depends(require(Permission.REVIEW_DECIDE))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, int]:
    try:
        result = await service.bulk_accept(session, payload.ids, actor=actor)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result


@router.post("/{proposal_id}/decide", response_model=ProposalOut)
async def decide(
    proposal_id: int,
    payload: DecideIn,
    actor: Annotated[User, Depends(require(Permission.REVIEW_DECIDE))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProposalOut:
    try:
        proposal = await service.decide(
            session,
            proposal_id,
            actor=actor,
            decision=payload.decision,
            payload=payload.payload,
            reason=payload.reason,
        )
        output = present(
            proposal, await load(session), await page_context(session, [proposal])
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return output
