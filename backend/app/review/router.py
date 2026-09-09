from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.controls.models import Control
from app.db import get_session
from app.frameworks.models import FrameworkItem, MappingStrength
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


async def present(
    session: AsyncSession,
    proposal: Proposal,
    limits: Thresholds,
    context: dict[int, dict[str, Any]] | None = None,
) -> ProposalOut:
    acceptable, flag = await service.eligibility(session, proposal, limits)
    mapping: dict[str, Any] | None = None
    if proposal.kind == ProposalKind.MAPPING:
        item_id = proposal.payload.get("framework_item_id")
        control_id = proposal.payload.get("control_id")
        if type(item_id) is int and type(control_id) is int:
            item = await session.get(FrameworkItem, item_id)
            control = await session.get(Control, control_id)
            if item is not None and control is not None:
                mapping = {
                    "framework_item": {
                        "id": item.id,
                        "code": item.code,
                        "title": item.title,
                        "description": item.description,
                    },
                    "control": {
                        "id": control.id,
                        "code": control.code,
                        "title": control.title,
                        "statement": control.statement,
                    },
                }
    relation: dict[str, Any] | None = None
    if proposal.kind == ProposalKind.RELATION:
        start = proposal.payload.get("from_control_id")
        end = proposal.payload.get("to_control_id")
        if type(start) is int and type(end) is int:
            left = await session.get(Control, start)
            right = await session.get(Control, end)
            if left is not None and right is not None:
                relation = {
                    "relation_type": proposal.payload.get("relation_type"),
                    "from": {"id": left.id, "code": left.code, "title": left.title,
                             "statement": left.statement},
                    "to": {"id": right.id, "code": right.code, "title": right.title,
                           "statement": right.statement},
                }
    return ProposalOut.model_validate(proposal).model_copy(
        update={
            "bulk_acceptable": acceptable,
            "ocr_quality_flag": flag,
            "mapping_context": mapping,
            "relation_context": relation,
            "citations": _enrich(proposal.citations, context or {}),
        }
    )


@router.get("", response_model=list[ProposalOut])
async def list_pending(
    *,
    kind: ProposalKind | None = None,
    document_id: int | None = Query(default=None, gt=0),
    strength: Annotated[list[MappingStrength] | None, Query()] = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: Annotated[User, Depends(require(Permission.READ))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProposalOut]:
    rows = await service.pending(
        session,
        kind=kind,
        document_id=document_id,
        strength=[value.value for value in strength] if strength else None,
        limit=limit,
    )
    limits = await load(session)
    context = await clause_context(session, rows)
    return [await present(session, row, limits, context) for row in rows]


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
        output = await present(
            session, proposal, await load(session),
            await clause_context(session, [proposal]),
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return output
