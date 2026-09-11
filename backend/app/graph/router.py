from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.graph import service
from app.graph.schemas import GraphOut
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission

router = APIRouter(prefix="/api/graph", tags=["graph"])

Reader = Annotated[User, Depends(require(Permission.READ))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/relations", response_model=GraphOut)
async def relation_graph(*, _: Reader, session: Session) -> GraphOut:
    return await service.relation_graph(session)
