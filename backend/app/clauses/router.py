from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.clauses.schemas import ClauseOut
from app.db import get_session
from app.errors import NotFound
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.ingest.models import Document

router = APIRouter(prefix="/api/clauses", tags=["clauses"])


@router.get("/{clause_id}", response_model=ClauseOut)
async def get_clause(
    *,
    clause_id: int,
    _: Annotated[User, Depends(require(Permission.READ))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClauseOut:
    row = (
        await session.execute(
            select(Clause, Document.title)
            .join(Document, Document.id == Clause.document_id)
            .where(Clause.id == clause_id)
        )
    ).first()
    if row is None:
        raise NotFound("条款不存在")
    clause, document_title = row
    return ClauseOut(
        id=clause.id,
        document_id=clause.document_id,
        document_title=document_title,
        number=clause.number,
        heading=clause.heading,
        heading_path=clause.heading_path,
        citation_label=clause.citation_label,
        text=clause.text,
        level=clause.level,
        page_ref=clause.page_ref,
    )
