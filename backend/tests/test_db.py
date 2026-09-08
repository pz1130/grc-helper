import pytest
from sqlalchemy import text

from app.db import engine


def test_module_engine_targets_test_database():
    """app.db.engine is created at import; conftest must retarget it before collection."""
    assert engine.url.database == "grc_test"


@pytest.mark.asyncio
async def test_pgvector_extension_is_installed(db_session):
    result = await db_session.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    )
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_session_can_query(db_session):
    result = await db_session.execute(text("SELECT 42"))
    assert result.scalar() == 42
