"""双通道关系推断；骨架照抄 M5 硬化后的 mapping/tasks.py。

继承而来的六条，均有出处，不重新踩：检查点查完立刻提交（advisory 锁不得
跨越 LLM 调用）、ProviderError 计入 failed 并继续、引用逐条丢弃而非整批
作废、按批原子提交、schema 带 maxItems、总时限与 <think> 剥离在 runner 内。
"""

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls.models import Control, RelationType
from app.db import session_factory
from app.errors import AppError
from app.llm.models import LLMCall
from app.llm.providers.base import ProviderError
from app.llm.runner import run
from app.llm.validation import ValidationFailure
from app.relations.citations import RelationCitationValidator
from app.relations.clustering import duplicate_pairs, section_clusters
from app.relations.prompts import (
    DEPENDS_SYSTEM,
    DUPLICATE_SYSTEM,
    PAIRS_PER_BATCH,
    RELATION_SCHEMA,
    RELATION_TASK_KEY,
    render_cluster,
    render_pairs,
)
from app.review import service as review_service
from app.review.models import ProposalKind

logger = logging.getLogger(__name__)
CHECKPOINT_KEY = "_relation_inference"


def fingerprint(system: str, prompt: str, run_key: str | None) -> str:
    encoded = json.dumps(
        ["v1", run_key, system, RELATION_SCHEMA, prompt], sort_keys=True, ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


async def _checkpoint(session: AsyncSession, key: str) -> LLMCall | None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(bytes.fromhex(key)[:8], "big", signed=True)},
    )
    return await session.scalar(
        select(LLMCall)
        .where(
            LLMCall.task_key == RELATION_TASK_KEY,
            LLMCall.status == "ok",
            LLMCall.redaction_hits.contains({CHECKPOINT_KEY: {"fingerprint": key}}),
        )
        .order_by(LLMCall.id.desc())
        .limit(1)
    )


async def _build_batches(session: AsyncSession) -> list[tuple[str, str, list[int], str]]:
    """产出 (system, prompt, control_ids, relation_type) 四元组。"""
    controls = {c.id: c for c in await session.scalars(select(Control).order_by(Control.id))}
    if not controls:
        raise AppError("控制点库为空，无法推断关系；请先在确认队列中确认控制点")

    batches: list[tuple[str, str, list[int], str]] = []

    pairs = await duplicate_pairs(session)
    for start in range(0, len(pairs), PAIRS_PER_BATCH):
        window = pairs[start : start + PAIRS_PER_BATCH]
        rendered = render_pairs(
            [(controls[p.low], controls[p.high], p.similarity) for p in window]
        )
        ids = sorted({i for p in window for i in (p.low, p.high)})
        batches.append((DUPLICATE_SYSTEM, rendered, ids, RelationType.DUPLICATES.value))

    for cluster in await section_clusters(session):
        rendered = render_cluster([controls[i] for i in cluster.control_ids])
        batches.append(
            (DEPENDS_SYSTEM, rendered, list(cluster.control_ids),
             RelationType.DEPENDS_ON.value)
        )

    if not batches:
        raise AppError("没有可推断的候选：控制点缺少向量或章节内不足两条")
    return batches


async def run_inference(
    session: AsyncSession, *, run_key: str | None = None
) -> dict[str, Any]:
    batches = await _build_batches(session)
    summary: dict[str, Any] = {
        "batches": len(batches),
        "proposals": 0,
        "rejected": 0,
        "failed": 0,
        "dropped_relations": 0,
        "completed_batches": 0,
        "skipped_batches": 0,
        "attempted_batches": 0,
        "proposal_ids": [],
        "llm_call_ids": [],
        "resumed_proposal_ids": [],
    }

    for system, rendered, control_ids, relation_type in batches:
        prompt = rendered + "\nOutput JSON Schema:\n" + json.dumps(RELATION_SCHEMA)
        key = fingerprint(system, prompt, run_key)
        cached = await _checkpoint(session, key)
        resumed = (
            cached.redaction_hits[CHECKPOINT_KEY]["proposal_ids"]
            if cached is not None
            else None
        )
        # 检查点查完立刻提交：advisory 锁是事务级的，不提交就跨越整个 LLM 调用。
        await session.commit()
        if resumed is not None:
            summary["skipped_batches"] += 1
            summary["resumed_proposal_ids"].extend(resumed)
            continue

        validator = RelationCitationValidator(session, control_ids=control_ids)
        summary["attempted_batches"] += 1
        try:
            # 引用校验不进 run()：runner 只对 schema 失败做纠错重试，引用失败
            # 直接抛出，移到这里逐条判可把「一条不合格整批作废」变成「只丢那一条」。
            result = await run(
                session,
                task_key=RELATION_TASK_KEY,
                system=system,
                prompt=prompt,
                schema=RELATION_SCHEMA,
            )
        except ValidationFailure as failure:
            logger.warning("Relation batch rejected: %s", failure.reason)
            summary["rejected"] += 1
            await session.commit()
            continue
        except ProviderError as failure:
            logger.warning("Relation batch failed: %s", failure)
            summary["failed"] += 1
            await session.commit()
            continue
        except Exception:
            await session.commit()
            raise

        call = await session.get(LLMCall, result.llm_call_id)
        if call is None:
            raise RuntimeError("Relation runner did not persist its LLMCall")

        entries = result.payload["relations"]
        if entries and await validator.check(result.payload) is not None:
            kept = []
            for entry in entries:
                reason = await validator.check({"relations": [entry]})
                if reason is None:
                    kept.append(entry)
                else:
                    logger.warning("Dropped one relation: %s", reason)
                    summary["dropped_relations"] += 1
            entries = kept

        ids: list[int] = []
        try:
            async with session.begin_nested():
                for entry in entries:
                    payload = {**entry, "relation_type": relation_type}
                    proposal = await review_service.create(
                        session,
                        kind=ProposalKind.RELATION,
                        payload=payload,
                        citations=[
                            {"control_id": entry["from_control_id"],
                             "quote": entry["from_quote"]},
                            {"control_id": entry["to_control_id"],
                             "quote": entry["to_quote"]},
                        ],
                        confidence=entry["confidence"],
                        llm_call_id=result.llm_call_id,
                    )
                    await session.flush()
                    ids.append(proposal.id)
                call.redaction_hits = {
                    **(call.redaction_hits or {}),
                    CHECKPOINT_KEY: {"fingerprint": key, "proposal_ids": ids},
                }
                await session.flush()
        except Exception:
            await session.commit()
            raise

        await session.commit()
        summary["completed_batches"] += 1
        summary["proposals"] += len(ids)
        summary["proposal_ids"].extend(ids)
        summary["llm_call_ids"].append(result.llm_call_id)
    return summary


async def infer_relations(ctx: dict[str, Any]) -> dict[str, Any]:
    async with session_factory() as session:
        return await run_inference(session, run_key=ctx.get("job_id"))
