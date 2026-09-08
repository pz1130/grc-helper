"""Database integration tests READY for the coordinator; not run by extraction owner."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.clauses.models import Clause
from app.extraction import tasks
from app.ingest.models import DocStatus, DocType, Document
from app.llm.models import LLMCall, RulesetName
from app.llm.runner import ValidatedResult
from app.llm.validation import ValidationFailure
from app.review.models import Proposal


@pytest.fixture
async def extraction_document(db_session):
    document = Document(title="Approval", doc_type=DocType.PROCEDURE,
                        file_hash="9" * 64, file_path="/approval.pdf",
                        original_filename="approval.pdf", status=DocStatus.ACTIVE,
                        ocr_quality_flag=True)
    db_session.add(document)
    await db_session.flush()
    clause = Clause(document_id=document.id, number="1", heading="Approval",
                    heading_path="Approval", citation_label="1", level=1, order_index=0,
                    text="Two approvers are required.")
    db_session.add(clause)
    await db_session.flush()
    return document, clause


def fake_runner(monkeypatch, *, empty=False, invalid=False):
    async def run(session, **kwargs):
        clause = await session.scalar(select(Clause).order_by(Clause.id))
        data = {"controls": []} if empty else {"controls": [{
            "title": "Dual approval", "statement": "Two approvers are required.",
            "confidence": 0.95, "citations": [{
                "clause_id": clause.id,
                "quote": "fabricated" if invalid else "Two approvers",
            }],
        }]}
        if empty:
            data["insufficient_evidence"] = True
        reason = await kwargs["citation_validator"].check(data)
        call = LLMCall(task_key="control_extract", model="test", prompt_hash="a" * 64,
                       ruleset=RulesetName.GENERATION, status="error" if reason else "ok",
                       error=reason, redaction_hits={"dictionary": 1})
        session.add(call)
        await session.flush()
        if reason:
            raise ValidationFailure(reason)
        return ValidatedResult(data, None, call.id)

    runner = AsyncMock(side_effect=run)
    monkeypatch.setattr(tasks, "run", runner)
    return runner


async def test_db_extraction_resume_and_fresh_evaluation(db_session, extraction_document, monkeypatch):
    doc, _ = extraction_document
    runner = fake_runner(monkeypatch)
    first = await tasks.run_extraction(db_session, doc.id, run_key="job")
    assert first["proposals"] == 1
    proposal = await db_session.get(Proposal, first["proposal_ids"][0])
    assert proposal.document_id == doc.id
    assert proposal.llm_call_id == first["llm_call_ids"][0]
    second = await tasks.run_extraction(db_session, doc.id, run_key="job")
    assert second["skipped_batches"] == 1
    assert second["proposal_ids"] == []
    assert second["resumed_proposal_ids"] == first["proposal_ids"]
    third = await tasks.run_extraction(db_session, doc.id, run_key="fresh-evaluation")
    assert third["completed_batches"] == 1
    assert third["proposal_ids"] != first["proposal_ids"]
    assert runner.await_count == 2


async def test_db_empty_batch_resumes(db_session, extraction_document, monkeypatch):
    doc, _ = extraction_document
    runner = fake_runner(monkeypatch, empty=True)
    first = await tasks.run_extraction(db_session, doc.id)
    second = await tasks.run_extraction(db_session, doc.id)
    assert first["completed_batches"] == second["skipped_batches"] == 1
    assert first["proposal_ids"] == second["proposal_ids"] == []
    runner.assert_awaited_once()


async def test_db_rejection_keeps_error_trace(db_session, extraction_document, monkeypatch):
    doc, _ = extraction_document
    fake_runner(monkeypatch, invalid=True)
    result = await tasks.run_extraction(db_session, doc.id)
    assert result["rejected"] == 1
    assert await db_session.scalar(select(func.count()).select_from(Proposal)) == 0
    call = await db_session.scalar(select(LLMCall))
    assert call.status == "error" and call.error
    assert tasks.CHECKPOINT_KEY not in call.redaction_hits


async def test_db_failed_proposal_flush_leaves_no_partial_batch(
    db_session, extraction_document, monkeypatch,
):
    doc, _ = extraction_document
    fake_runner(monkeypatch)
    real_create = tasks.review_service.create

    async def fail_after_create(*args, **kwargs):
        await real_create(*args, **kwargs)
        raise RuntimeError("review failure after write")

    monkeypatch.setattr(tasks.review_service, "create", fail_after_create)
    with pytest.raises(RuntimeError, match="review failure"):
        await tasks.run_extraction(db_session, doc.id)
    assert await db_session.scalar(select(func.count()).select_from(Proposal)) == 0
    call = await db_session.scalar(select(LLMCall))
    assert call is not None
    assert tasks.CHECKPOINT_KEY not in (call.redaction_hits or {})
