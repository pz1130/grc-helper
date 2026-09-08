"""ARQ tasks for building and embedding the retrieval index."""

from typing import Any

import logging

from app.db import session_factory
from app.indexing.embedder import embed_pending
from app.indexing.service import rebuild_chunks
from app.llm.routing import RoutingError

logger = logging.getLogger(__name__)


async def index_document(ctx: dict[str, Any], document_id: int) -> dict[str, Any]:
    async with session_factory() as session:
        chunks = await rebuild_chunks(session, document_id=document_id)
        await session.commit()
        try:
            result = await embed_pending(session)
        except RoutingError as exc:
            # 没配 embedding provider 是**预期状态**，不是故障：切块已经落库，
            # 检索会降级成纯关键词。当成失败重试三次只会刷屏，且掩盖真故障。
            logger.info("跳过向量化：%s", exc)
            return {"chunks": chunks, "embedded": 0, "remaining": chunks, "skipped": str(exc)}
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
