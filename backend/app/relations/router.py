from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import Conflict
from app.iam.audit import record
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.relations.indexing import embed_pending
from app.worker import enqueue

router = APIRouter(prefix="/api/relations", tags=["relations"])
Writer = Annotated[User, Depends(require(Permission.CONTROL_WRITE))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/embed")
async def embed(actor: Writer, session: Session) -> dict[str, Any]:
    result = await embed_pending(session)
    await record(
        session, user=actor, action="relations.embed", entity_type="Control",
        entity_id=0, after=result,
    )
    await session.commit()
    return result


@router.post("/infer")
async def infer(actor: Writer, session: Session) -> dict[str, str]:
    job_id = await enqueue("infer_relations")
    if not job_id:
        raise Conflict("关系推断任务未能进入队列")
    await record(
        session, user=actor, action="relations.enqueue", entity_type="Control",
        entity_id=0, after={"job_id": job_id},
    )
    await session.commit()
    return {"job_id": job_id}
