import asyncio
import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 测试必须指向独立的库，避免污染开发数据。
# 不继承应用的 DATABASE_URL：pytest 若加载 .env 的 /grc，DROP 会毁掉开发库。
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://grc:grc@db:5432/grc_test"
)

# 必须在任何 test 模块被导入前生效：app.db 在 import 时就用 get_settings()
# 建了模块级 engine，晚一步就会绑到开发库上。
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production-use")
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session")
async def _schema() -> AsyncGenerator[None, None]:
    """整个测试会话建一次表结构。"""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    admin_engine = create_async_engine(
        TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres",
        isolation_level="AUTOCOMMIT",
    )
    db_name = TEST_DATABASE_URL.rsplit("/", 1)[1]
    async with admin_engine.connect() as conn:
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{db_name}"')
        await conn.exec_driver_sql(f'CREATE DATABASE "{db_name}"')
    await admin_engine.dispose()

    await asyncio.to_thread(command.upgrade, cfg, "head")
    yield


@pytest_asyncio.fixture
async def db_session(_schema) -> AsyncGenerator[AsyncSession, None]:
    """每个测试跑在一个事务里，结束回滚，测试之间互不影响。"""
    engine = create_async_engine(TEST_DATABASE_URL)
    connection = await engine.connect()
    transaction = await connection.begin()
    # create_savepoint：让被测代码里的 commit()/rollback() 只作用在 SAVEPOINT 上，
    # 外层事务原封不动。没有它，路由里一次 session.rollback() 就会把整个
    # 测试事务连同种子数据一起掀掉。
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.db import get_session
    from app.main import app

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
