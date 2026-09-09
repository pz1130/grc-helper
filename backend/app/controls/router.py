from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls import service
from app.controls.models import Control
from app.controls.schemas import ControlDetailOut, ControlOut, ControlUpdateIn
from app.db import get_session
from app.errors import NotFound
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.review.materialize import update_control as apply_control_update

router = APIRouter(prefix="/api/controls", tags=["controls"])


@router.get("", response_model=list[ControlOut])
async def list_controls(
    *,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: Annotated[User, Depends(require(Permission.READ))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Control]:
    return await service.search(session, q=q, limit=limit)


@router.get("/{control_id}", response_model=ControlDetailOut)
async def get_control(
    *,
    control_id: int,
    _: Annotated[User, Depends(require(Permission.READ))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ControlDetailOut:
    control = await session.get(Control, control_id)
    if control is None:
        raise NotFound("控制点不存在")
    return ControlDetailOut(
        **ControlOut.model_validate(control).model_dump(),
        sources=await service.sources(session, control_id),
        relations=await service.relations(session, control_id),
        mappings=await service.mappings(session, control_id),
    )


@router.patch("/{control_id}", response_model=ControlOut)
async def update_control(
    *,
    control_id: int,
    payload: ControlUpdateIn,
    actor: Annotated[User, Depends(require(Permission.CONTROL_WRITE))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Control:
    try:
        control = await apply_control_update(
            session, control_id, payload.model_dump(exclude_unset=True), actor=actor
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return control
