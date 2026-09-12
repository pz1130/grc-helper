"""ARQ worker。

用 ARQ 而非 Celery：它是 async 原生的，与 async SQLAlchemy 共用同一套并发
模型，不必在同步/异步之间反复搭桥。M2 起解析、OCR、向量化、AI 批量任务
都注册在这里。
"""

from typing import Any, ClassVar

from arq import create_pool, cron
from arq.connections import RedisSettings
from arq.worker import func

import app.models  # noqa: F401  — 注册全部模型，跨模块外键才解析得了
from app.audit.tasks import generate_engagement_answers
from app.config import get_settings
from app.conflicts.tasks import detect_conflicts
from app.extraction.tasks import extract_controls
from app.indexing.tasks import index_document, reindex_all
from app.ingest.staging import purge_staging
from app.ingest.tasks import parse_document
from app.mapping.tasks import map_framework
from app.relations.indexing import embed_controls
from app.relations.tasks import infer_relations


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


# ARQ 读的是 Function.timeout_s——裸 coroutine 只吃得到下面的 job_timeout。
# 逐批调 provider 的任务全都远超 15 分钟（M5 记录过一次映射跑了 51 分钟），
# 裸注册等于每 15 分钟被杀一次，max_tries 用完就永远跑不完。它们都带检查点，
# 所以真被杀了能续，但别让「能续」替「跑得完」背书。
LONG_JOB_TIMEOUT = 7200


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        ping,
        parse_document,
        index_document,
        func(reindex_all, timeout=LONG_JOB_TIMEOUT),
        func(extract_controls, timeout=LONG_JOB_TIMEOUT),
        func(map_framework, timeout=LONG_JOB_TIMEOUT),
        func(infer_relations, timeout=LONG_JOB_TIMEOUT),
        func(embed_controls, timeout=LONG_JOB_TIMEOUT),
        func(generate_engagement_answers, timeout=LONG_JOB_TIMEOUT),
        func(detect_conflicts, timeout=LONG_JOB_TIMEOUT),
    ]
    # 暂存卷的唯一出口。挑凌晨是因为它会删文件，别和白天的上传挤在一起。
    cron_jobs: ClassVar[list[Any]] = [cron(purge_staging, hour=3, minute=17)]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 900  # 15 分钟：够一份大 PDF 走完 OCR + 抽取
    keep_result = 3600
    max_tries = 3  # 幂等任务的自动重试（spec §9）
