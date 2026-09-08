"""ARQ worker。

用 ARQ 而非 Celery：它是 async 原生的，与 async SQLAlchemy 共用同一套并发
模型，不必在同步/异步之间反复搭桥。M2 起解析、OCR、向量化、AI 批量任务
都注册在这里。
"""

from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

import app.models  # noqa: F401  — 注册全部模型，跨模块外键才解析得了
from app.config import get_settings
from app.indexing.tasks import index_document, reindex_all
from app.ingest.tasks import parse_document


async def ping(ctx: dict[str, Any]) -> str:
    """冒烟任务：验证 API 能投递、worker 能执行。"""
    return "pong"


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def enqueue(function: str, *args: Any) -> str:
    """API 侧投递任务。返回 job id，前端据此轮询进度。"""
    pool = await create_pool(_redis_settings())
    try:
        job = await pool.enqueue_job(function, *args)
        return job.job_id if job else ""
    finally:
        await pool.close()


class WorkerSettings:
    functions = [ping, parse_document, index_document, reindex_all]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 900          # 15 分钟：够一份大 PDF 走完 OCR + 抽取
    keep_result = 3600
    max_tries = 3              # 幂等任务的自动重试（spec §9）
