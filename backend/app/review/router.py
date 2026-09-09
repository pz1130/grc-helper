from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls.models import Control
from app.db import get_session
from app.frameworks.models import FrameworkItem
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.review import service
from app.review.models import Proposal, ProposalKind, ProposalStatus
from app.review.schemas import BulkAcceptIn, DecideIn, ProposalOut
from app.review.thresholds import Thresholds, load

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


async def present(session: AsyncSession, proposal: Proposal, limits: Thresholds) -> ProposalOut:
    acceptable, flag = await service.eligibility(session, proposal, limits)
    context: dict[str, Any] | None = None
    if proposal.kind == ProposalKind.MAPPING:
        item_id = proposal.payload.get("framework_item_id")
        control_id = proposal.payload.get("control_id")
        if type(item_id) is int and type(control_id) is int:
            item = await session.get(FrameworkItem, item_id)
            control = await session.get(Control, control_id)
            if item is not None and control is not None:
                context = {
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
    return ProposalOut.model_validate(proposal).model_copy(
        update={
            "bulk_acceptable": acceptable,
            "ocr_quality_flag": flag,
            "mapping_context": context,
        }
    )


@router.get("", response_model=list[ProposalOut])
async def list_pending(
    *,
    kind: ProposalKind | None = None,
    document_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=200),
    _: Annotated[User, Depends(require(Permission.READ))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProposalOut]:
    rows = await service.pending(session, kind=kind, document_id=document_id, limit=limit)
    limits = await load(session)
    return [await present(session, row, limits) for row in rows]


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
        output = await present(session, proposal, await load(session))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return output
