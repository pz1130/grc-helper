"""按批映射并原子提交，骨架沿用 M4 的 extraction/tasks.py。"""

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls.models import Control
from app.db import session_factory
from app.errors import AppError, NotFound
from app.frameworks.models import Framework, FrameworkItem
from app.llm.models import LLMCall
from app.llm.runner import run
from app.llm.validation import ValidationFailure
from app.mapping.batching import build_batches, render_controls, render_items
from app.mapping.citations import MappingCitationValidator
from app.mapping.prompts import MAPPING_SCHEMA, MAPPING_SYSTEM, MAPPING_TASK_KEY
from app.review import service as review_service
from app.review.models import ProposalKind

logger = logging.getLogger(__name__)
CHECKPOINT_KEY = "_framework_mapping"


def fingerprint(framework_id: int, prompt: str, run_key: str | None) -> str:
    encoded = json.dumps(
        ["v1", run_key, framework_id, MAPPING_SYSTEM, MAPPING_SCHEMA, prompt],
        sort_keys=True,
        ensure_ascii=False,
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
            LLMCall.task_key == MAPPING_TASK_KEY,
            LLMCall.status == "ok",
            LLMCall.redaction_hits.contains({CHECKPOINT_KEY: {"fingerprint": key}}),
        )
        .order_by(LLMCall.id.desc())
        .limit(1)
    )


async def run_mapping(
    session: AsyncSession, framework_id: int, *, run_key: str | None = None
) -> dict[str, Any]:
    framework = await session.get(Framework, framework_id)
    if framework is None:
        raise NotFound("框架不存在")

    controls = list(await session.scalars(select(Control).order_by(Control.id)))
    if not controls:
        raise AppError("控制点库为空，无法映射；请先在确认队列中确认控制点")
    controls_text = render_controls(controls)

    items = list(await session.scalars(
        select(FrameworkItem)
        .where(FrameworkItem.framework_id == framework_id)
        .order_by(FrameworkItem.order_index, FrameworkItem.id)
    ))
    batches = [
        (render_items(batch), [item.id for item in batch.items])
        for batch in build_batches(items)
    ]
    summary: dict[str, Any] = {
        "batches": len(batches),
        "proposals": 0,
        "rejected": 0,
        "completed_batches": 0,
        "skipped_batches": 0,
        "attempted_batches": 0,
        "proposal_ids": [],
        "llm_call_ids": [],
        "resumed_proposal_ids": [],
    }

    for items_text, item_ids in batches:
        prompt = (
            "# Framework items to assess\n"
            + items_text
            + "\n# All available controls\n"
            + controls_text
            + "\nOutput JSON Schema:\n"
            + json.dumps(MAPPING_SCHEMA)
        )
        key = fingerprint(framework_id, prompt, run_key)
        cached = await _checkpoint(session, key)
        if cached is not None:
            summary["skipped_batches"] += 1
            summary["resumed_proposal_ids"].extend(
                cached.redaction_hits[CHECKPOINT_KEY]["proposal_ids"]
            )
            await session.commit()
            continue

        validator = MappingCitationValidator(session, item_ids=item_ids)
        summary["attempted_batches"] += 1
        try:
            result = await run(
                session,
                task_key=MAPPING_TASK_KEY,
                system=MAPPING_SYSTEM,
                prompt=prompt,
                schema=MAPPING_SCHEMA,
                citation_validator=validator,
            )
        except ValidationFailure as failure:
            logger.warning("Framework %s mapping rejected: %s", framework_id, failure.reason)
            summary["rejected"] += 1
            await session.commit()
            continue
        except Exception:
            await session.commit()
            raise

        call = await session.get(LLMCall, result.llm_call_id)
        if call is None:
            raise RuntimeError("Mapping runner did not persist its LLMCall")
        ids: list[int] = []
        try:
            async with session.begin_nested():
                for entry in result.payload["mappings"]:
                    proposal = await review_service.create(
                        session,
                        kind=ProposalKind.MAPPING,
                        payload=entry,
                        citations=[{
                            "framework_item_id": entry["framework_item_id"],
                            "quote": entry["quote"],
                        }],
                        confidence=entry["confidence"],
                        llm_call_id=result.llm_call_id,
                        document_id=None,
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


async def map_framework(ctx: dict[str, Any], framework_id: int) -> dict[str, Any]:
    async with session_factory() as session:
        return await run_mapping(session, framework_id, run_key=ctx.get("job_id"))
