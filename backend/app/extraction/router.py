from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import Conflict, NotFound
from app.iam.audit import record
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.ingest.models import DocStatus, Document
from app.worker import enqueue

router = APIRouter(prefix="/api/extraction", tags=["extraction"])


@router.post("/documents/{document_id}")
async def extract(
    document_id: Annotated[int, Path(gt=0)],
    actor: Annotated[User, Depends(require(Permission.CONTROL_WRITE))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFound("文档不存在")
    if document.status != DocStatus.ACTIVE:
        raise Conflict("只有 active 文档可以抽取控制点")
    job_id = await enqueue("extract_controls", document_id)
    if not job_id:
        raise Conflict("抽取任务未能进入队列")
    await record(
        session, user=actor, action="extraction.enqueue", entity_type="Document",
        entity_id=document_id, after={"job_id": job_id},
    )
    await session.commit()
    return {"job_id": job_id}
