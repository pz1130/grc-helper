from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.clauses.models import EMBEDDING_DIM
from app.controls.models import Control
from app.relations.indexing import embed_pending, render_control
from app.relations.models import ControlEmbedding


def _vectors(count: int):
    return ([[0.02] * EMBEDDING_DIM for _ in range(count)], count)


async def _controls(db_session, how_many: int) -> list[Control]:
    rows = [
        Control(code=f"C-{n:04d}", title=f"Control {n}", statement=f"Statement {n}.")
        for n in range(1, how_many + 1)
    ]
    db_session.add_all(rows)
    await db_session.flush()
    return rows


def test_render_control_carries_code_title_and_statement():
    from types import SimpleNamespace

    text = render_control(SimpleNamespace(
        code="C-0009", title="Dual approval", statement="Two approvers required."))
    assert "C-0009" in text and "Dual approval" in text and "Two approvers required." in text


@pytest.mark.asyncio
async def test_embedding_backfills_every_control_without_one(db_session):
    await _controls(db_session, 3)
    with patch("app.relations.indexing.embed", new=AsyncMock(return_value=_vectors(3))), \
         patch("app.relations.indexing.current_model", new=AsyncMock(return_value="embo-01")):
        result = await embed_pending(db_session)

    assert result["embedded"] == 3
    rows = list(await db_session.scalars(select(ControlEmbedding)))
    assert len(rows) == 3
    assert all(len(r.embedding) == EMBEDDING_DIM for r in rows)
    assert all(r.embedding_model == "embo-01" for r in rows)


@pytest.mark.asyncio
async def test_a_second_run_is_a_no_op(db_session):
    await _controls(db_session, 2)
    with patch("app.relations.indexing.embed", new=AsyncMock(return_value=_vectors(2))), \
         patch("app.relations.indexing.current_model", new=AsyncMock(return_value="embo-01")):
        await embed_pending(db_session)
        again = await embed_pending(db_session)
    assert again["embedded"] == 0


@pytest.mark.asyncio
async def test_changing_the_model_reembeds_everything(db_session):
    await _controls(db_session, 2)
    with patch("app.relations.indexing.embed", new=AsyncMock(return_value=_vectors(2))), \
         patch("app.relations.indexing.current_model", new=AsyncMock(return_value="embo-01")):
        await embed_pending(db_session)
    with patch("app.relations.indexing.embed", new=AsyncMock(return_value=_vectors(2))), \
         patch("app.relations.indexing.current_model", new=AsyncMock(return_value="embo-02")):
        result = await embed_pending(db_session)

    assert result["embedded"] == 2
    rows = list(await db_session.scalars(select(ControlEmbedding)))
    assert len(rows) == 2, "换模型是重算，不是新增行"
    assert all(r.embedding_model == "embo-02" for r in rows)


@pytest.mark.asyncio
async def test_an_empty_library_reports_nothing_to_do(db_session):
    with patch("app.relations.indexing.current_model", new=AsyncMock(return_value="embo-01")):
        result = await embed_pending(db_session)
    assert result["embedded"] == 0 and result["pending"] == 0
