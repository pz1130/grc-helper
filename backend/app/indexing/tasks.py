"""ARQ tasks for building and embedding the retrieval index."""

from typing import Any

from app.db import session_factory
from app.indexing.embedder import embed_pending
from app.indexing.service import rebuild_chunks


async def index_document(ctx: dict[str, Any], document_id: int) -> dict[str, Any]:
    async with session_factory() as session:
        chunks = await rebuild_chunks(session, document_id=document_id)
        await session.commit()
        result = await embed_pending(session)
        return {"chunks": chunks, **result}


async def reindex_all(ctx: dict[str, Any]) -> dict[str, Any]:
    """换 embedding 模型后的全量重建。"""
    async with session_factory() as session:
        total = 0
        while True:
            result = await embed_pending(session, limit=500)
            total += int(result["embedded"])
            if not result["embedded"] or not result["remaining"]:
                return {"embedded": total, "model": result["model"]}
