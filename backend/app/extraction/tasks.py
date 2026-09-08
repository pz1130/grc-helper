"""Extract proposals through review; commit each completed batch atomically.

The existing LLMCall.redaction_hits JSON holds a namespaced checkpoint alongside
redaction counters. No source text is added there. Checkpoints include the run,
document, rendered batch and prompt/schema version, including empty successes.
An advisory transaction lock serialises duplicate deliveries of the same batch.
Core callers must use a dedicated session: this function commits batch work.
"""

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.db import session_factory
from app.errors import Conflict, NotFound
from app.extraction.batching import build_batches, render
from app.extraction.citations import ClauseCitationValidator
from app.extraction.prompts import EXTRACT_SCHEMA, EXTRACT_SYSTEM, EXTRACT_TASK_KEY
from app.ingest.models import DocStatus, Document
from app.llm.models import LLMCall
from app.llm.runner import run
from app.llm.validation import ValidationFailure
from app.review import service as review_service
from app.review.models import ProposalKind

logger = logging.getLogger(__name__)
CHECKPOINT_KEY = "_control_extraction"


def fingerprint(document_id: int, prompt: str, run_key: str | None) -> str:
    encoded = json.dumps(
        ["v1", run_key, document_id, EXTRACT_SYSTEM, EXTRACT_SCHEMA, prompt],
        sort_keys=True, ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


async def _checkpoint(session: AsyncSession, key: str) -> LLMCall | None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(bytes.fromhex(key)[:8], "big", signed=True)},
    )
    return await session.scalar(select(LLMCall).where(
        LLMCall.task_key == EXTRACT_TASK_KEY,
        LLMCall.status == "ok",
        LLMCall.redaction_hits.contains({CHECKPOINT_KEY: {"fingerprint": key}}),
    ).order_by(LLMCall.id.desc()).limit(1))


async def run_extraction(
    session: AsyncSession, document_id: int, *, run_key: str | None = None,
) -> dict[str, Any]:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFound("文档不存在")
    if document.status != DocStatus.ACTIVE:
        raise Conflict("只有 active 文档可以抽取控制点")
    clauses = list(await session.scalars(
        select(Clause).where(Clause.document_id == document_id)
        .order_by(Clause.order_index, Clause.id)
    ))
    # Render up front so per-batch commits cannot expire the next batch's ORM data.
    batches = [(render(b), [c.id for c in b.clauses]) for b in build_batches(clauses)]
    summary: dict[str, Any] = {
        "batches": len(batches), "proposals": 0, "rejected": 0,
        "completed_batches": 0, "skipped_batches": 0, "attempted_batches": 0,
        "proposal_ids": [], "llm_call_ids": [], "resumed_proposal_ids": [],
        "resumed_llm_call_ids": [],
    }
    for prompt, clause_ids in batches:
        key = fingerprint(document_id, prompt, run_key)
        cached = await _checkpoint(session, key)
        if cached is not None:
            summary["skipped_batches"] += 1
            summary["resumed_proposal_ids"].extend(
                cached.redaction_hits[CHECKPOINT_KEY]["proposal_ids"]
            )
            summary["resumed_llm_call_ids"].append(cached.id)
            await session.commit()  # release the transaction lock
            continue
        validator = ClauseCitationValidator(
            session, document_id=document_id, clause_ids=clause_ids,
        )
        summary["attempted_batches"] += 1
        try:
            result = await run(
                session, task_key=EXTRACT_TASK_KEY, system=EXTRACT_SYSTEM,
                prompt=prompt + "\nOutput JSON Schema:\n" + json.dumps(EXTRACT_SCHEMA),
                schema=EXTRACT_SCHEMA, citation_validator=validator,
            )
        except ValidationFailure as failure:
            logger.warning("Document %s extraction rejected: %s", document_id, failure.reason)
            summary["rejected"] += 1
            # The runner has flushed an error LLMCall. Preserve it, but do not cache failure.
            await session.commit()
            continue
        except Exception:
            # Preserve the runner's failure trace; proposal creation has not started.
            await session.commit()
            raise
        call = await session.get(LLMCall, result.llm_call_id)
        if call is None:
            raise RuntimeError("Extraction runner did not persist its LLMCall")
        ids: list[int] = []
        try:
            async with session.begin_nested():
                for item in result.payload["controls"]:
                    proposal = await review_service.create(
                        session, kind=ProposalKind.CONTROL_EXTRACT, payload=item,
                        citations=item["citations"], confidence=item["confidence"],
                        llm_call_id=result.llm_call_id, document_id=document_id,
                    )
                    await session.flush()
                    ids.append(proposal.id)
                call.redaction_hits = {
                    **(call.redaction_hits or {}),
                    CHECKPOINT_KEY: {"fingerprint": key, "proposal_ids": ids},
                }
                await session.flush()
        except Exception:
            # Savepoint removes every proposal in the failed batch, retaining the LLM trace.
            await session.commit()
            raise
        await session.commit()
        summary["completed_batches"] += 1
        summary["proposals"] += len(ids)
        summary["proposal_ids"].extend(ids)
        summary["llm_call_ids"].append(result.llm_call_id)
    return summary


async def extract_controls(ctx: dict[str, Any], document_id: int) -> dict[str, Any]:
    async with session_factory() as session:
        return await run_extraction(session, document_id, run_key=ctx.get("job_id"))
