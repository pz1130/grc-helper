from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.clauses.models import Clause, ClauseChunk
from app.indexing.tasks import index_document
from app.ingest.models import DocType, Document
from app.llm.routing import RoutingError


async def _document(db_session) -> Document:
    doc = Document(
        title="P", doc_type=DocType.PROCEDURE, file_hash="a" * 64,
        file_path="/x.pdf", original_filename="x.pdf",
    )
    db_session.add(doc)
    await db_session.flush()
    db_session.add(
        Clause(
            document_id=doc.id, number="1", heading="Scope", heading_path="Doc › Scope",
            citation_label="1", text="Applies to all systems.", order_index=0, level=1,
        )
    )
    await db_session.flush()
    await db_session.commit()
    return doc


@pytest.mark.asyncio
async def test_missing_embedding_provider_is_not_a_failure(db_session):
    """没配 provider 是预期状态，不是故障。

    当成失败会触发三次重试、刷屏，还会掩盖真正的上游故障。
    """
    doc = await _document(db_session)

    with patch("app.indexing.tasks.session_factory") as factory:
        factory.return_value.__aenter__.return_value = db_session
        with patch(
            "app.indexing.tasks.embed_pending",
            new=AsyncMock(side_effect=RoutingError("任务 embedding 尚未配置 provider")),
        ):
            result = await index_document({}, doc.id)

    assert result["chunks"] >= 1
    assert result["embedded"] == 0
    assert "skipped" in result


@pytest.mark.asyncio
async def test_chunks_survive_when_embedding_is_unavailable(db_session):
    """切块必须先落库：否则没配 provider 时连关键词检索都没得用。"""
    doc = await _document(db_session)

    with patch("app.indexing.tasks.session_factory") as factory:
        factory.return_value.__aenter__.return_value = db_session
        with patch(
            "app.indexing.tasks.embed_pending",
            new=AsyncMock(side_effect=RoutingError("未配置")),
        ):
            await index_document({}, doc.id)

    assert await db_session.scalar(select(ClauseChunk)) is not None


@pytest.mark.asyncio
async def test_real_upstream_failure_still_propagates(db_session):
    """上游 500 是真故障，必须抛出去让 ARQ 重试——不能和"没配"混为一谈。"""
    from app.llm.providers.base import ProviderError

    doc = await _document(db_session)

    with patch("app.indexing.tasks.session_factory") as factory:
        factory.return_value.__aenter__.return_value = db_session
        with patch(
            "app.indexing.tasks.embed_pending",
            new=AsyncMock(side_effect=ProviderError("上游返回 500", retryable=True)),
        ):
            with pytest.raises(ProviderError):
                await index_document({}, doc.id)
