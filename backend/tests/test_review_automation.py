import pytest
from sqlalchemy import select

from app.clauses.models import Clause
from app.controls.models import Control, ControlSource, SourceRelation
from app.frameworks.models import Framework, FrameworkItem, Mapping
from app.iam.models import AuditLog, User
from app.iam.permissions import Role
from app.iam.security import create_access_token, hash_password
from app.ingest.models import DocStatus, DocType, Document
from app.llm.models import AppSetting
from app.review.models import Proposal, ProposalKind, ProposalStatus
from app.review.service import ReviewTier, assess, auto_process
from app.review.thresholds import Thresholds


def _proposal(kind, payload, *, confidence=0.95, proposal_id=10):
    return Proposal(
        id=proposal_id,
        kind=kind,
        payload=payload,
        citations=[],
        confidence=confidence,
        status=ProposalStatus.PENDING,
    )


def test_clean_high_confidence_mapping_is_auto_eligible():
    proposal = _proposal(ProposalKind.MAPPING, {"rationale": "Direct coverage."})

    result = assess(
        proposal, Thresholds(0.9, 0.6, 0), ocr_flag=False
    )

    assert result.tier is ReviewTier.AUTO


def test_hedged_mapping_is_not_auto_accepted():
    proposal = _proposal(
        ProposalKind.MAPPING,
        {"rationale": "The control does not specifically address this requirement."},
    )

    result = assess(
        proposal, Thresholds(0.9, 0.6, 0), ocr_flag=False
    )

    assert result.tier is ReviewTier.DEFERRED
    assert "hedged_rationale" in result.reasons


def test_only_exact_statement_duplicate_relations_can_auto_accept():
    proposal = _proposal(
        ProposalKind.RELATION,
        {"relation_type": "duplicates"},
    )

    exact = assess(
        proposal, Thresholds(0.9, 0.6, 0), ocr_flag=False, exact_duplicate=True
    )
    similar = assess(
        proposal, Thresholds(0.9, 0.6, 0), ocr_flag=False, exact_duplicate=False
    )

    assert exact.tier is ReviewTier.AUTO
    assert similar.tier is ReviewTier.DEFERRED


async def _seed_mapping(db_session, *, ocr=False, confidence=0.95):
    actor = User(
        email=f"lead-{confidence}-{ocr}@example.com",
        name="Lead",
        role=Role.GRC_LEAD,
        password_hash=hash_password("pw"),
    )
    document = Document(
        title="Policy",
        doc_type=DocType.POLICY,
        file_hash=("b" if ocr else "a") * 64,
        file_path="/policy.pdf",
        original_filename="policy.pdf",
        status=DocStatus.ACTIVE,
        ocr_quality_flag=ocr,
    )
    framework = Framework(
        key=f"framework-{confidence}-{ocr}",
        name_zh="框架",
        name_en="Framework",
        version="1",
        source="test",
        item_count=1,
    )
    db_session.add_all([actor, document, framework])
    await db_session.flush()
    clause = Clause(
        document_id=document.id,
        number="1",
        heading="Access",
        heading_path="Access",
        citation_label="1",
        text="Access must be reviewed.",
        order_index=0,
        level=1,
    )
    control = Control(code=f"C-{int(confidence * 1000)}-{int(ocr)}", title="Access", statement="Review access.")
    item = FrameworkItem(
        framework_id=framework.id,
        code="AC-1",
        title="Access",
        description="Review access periodically.",
        level=1,
        order_index=0,
    )
    db_session.add_all([clause, control, item])
    await db_session.flush()
    db_session.add(
        ControlSource(
            control_id=control.id,
            clause_id=clause.id,
            relation=SourceRelation.DEFINES,
        )
    )
    proposal = Proposal(
        kind=ProposalKind.MAPPING,
        payload={
            "framework_item_id": item.id,
            "control_id": control.id,
            "strength": "full",
            "framework_item_quote": "Review access periodically.",
            "rationale": "Direct coverage.",
            "confidence": confidence,
        },
        citations=[],
        confidence=confidence,
    )
    db_session.add(proposal)
    await db_session.flush()
    return actor, proposal


@pytest.mark.asyncio
async def test_auto_process_materializes_without_impersonating_a_human(db_session):
    actor, proposal = await _seed_mapping(db_session)
    setting = await db_session.get(AppSetting, "review_sample_rate")
    setting.value = {"value": 0}
    await db_session.flush()

    result = await auto_process(db_session, actor=actor)

    assert result["accepted"] == 1
    assert proposal.status is ProposalStatus.ACCEPTED
    assert proposal.decided_by is None
    assert await db_session.scalar(select(Mapping)) is not None
    system_log = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "proposal.auto_accept")
    )
    batch_log = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "proposal.auto_process")
    )
    assert system_log.user_id is None
    assert batch_log.user_id == actor.id


@pytest.mark.asyncio
async def test_ocr_source_forces_mapping_into_manual_review(db_session):
    actor, proposal = await _seed_mapping(db_session, ocr=True)
    setting = await db_session.get(AppSetting, "review_sample_rate")
    setting.value = {"value": 0}
    await db_session.flush()

    result = await auto_process(db_session, actor=actor)

    assert result["accepted"] == 0
    assert result["manual"] == 1
    assert proposal.status is ProposalStatus.PENDING
    assert await db_session.scalar(select(Mapping)) is None


@pytest.mark.asyncio
async def test_actionable_queue_hides_auto_and_deferred_items(client, db_session):
    actor, proposal = await _seed_mapping(db_session)
    setting = await db_session.get(AppSetting, "review_sample_rate")
    setting.value = {"value": 0}
    await db_session.flush()
    headers = {
        "Authorization": f"Bearer {create_access_token(actor.id, actor.role)}"
    }

    all_items = (await client.get("/api/proposals", headers=headers)).json()
    actionable = (
        await client.get("/api/proposals?actionable_only=true", headers=headers)
    ).json()

    assert next(item for item in all_items if item["id"] == proposal.id)["review_tier"] == "auto"
    assert actionable == []


@pytest.mark.asyncio
async def test_automation_preview_is_read_only_and_shows_impact(client, db_session):
    actor, proposal = await _seed_mapping(db_session)
    setting = await db_session.get(AppSetting, "review_sample_rate")
    setting.value = {"value": 0}
    await db_session.flush()
    headers = {
        "Authorization": f"Bearer {create_access_token(actor.id, actor.role)}"
    }

    response = await client.get(
        "/api/proposals/auto-process/preview", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["by_tier"]["auto"] == 1
    assert body["estimated_changes"] == {"mappings": 1, "relations": 0}
    assert body["auto_items"][0]["id"] == proposal.id
    assert proposal.status is ProposalStatus.PENDING
    assert await db_session.scalar(select(Mapping)) is None
    assert await db_session.scalar(
        select(AuditLog).where(AuditLog.action.like("proposal.auto%"))
    ) is None
