"""执行合并：把输家的关联转挂到赢家，输家留行。"""

import pytest
from sqlalchemy import func, or_, select

from app.controls.models import Control, ControlRelation, ControlSource, RelationType
from app.environment.models import (
    HowEnforced,
    Implementation,
    ImplementationStatus,
    TechAsset,
    TechAssetCategory,
    TechAssetEnvironment,
    TechAssetStatus,
)
from app.errors import AppError, Forbidden
from app.evidence.models import EvidenceCadence, EvidenceItem, EvidenceStatus, EvidenceType
from app.frameworks.models import Mapping, MappingStrength
from app.iam.models import AuditLog, User
from app.iam.permissions import Role
from app.iam.security import hash_password
from app.relations.models import ControlEmbedding
from app.review.materialize import merge_controls
from app.risk.models import RiskEntry, RiskSource, RiskStatus
from tests.test_control_merge_plan import (
    _clause,
    _control,
    _framework_item,
    _mapping,
    _relation,
    _snapshot,
    _source,
)

_FK_MODELS = (
    ControlEmbedding,
    ControlSource,
    EvidenceItem,
    Implementation,
    Mapping,
    RiskEntry,
)


async def _user(db_session, role: Role, email: str) -> User:
    user = User(email=email, name=email, role=role, password_hash=hash_password("pw123456"))
    db_session.add(user)
    await db_session.flush()
    return user


async def _fk_counts(db_session, control_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in _FK_MODELS:
        n = await db_session.scalar(
            select(func.count()).select_from(model).where(model.control_id == control_id)
        )
        counts[model.__tablename__] = int(n or 0)
    n = await db_session.scalar(
        select(func.count())
        .select_from(ControlRelation)
        .where(
            or_(
                ControlRelation.from_control_id == control_id,
                ControlRelation.to_control_id == control_id,
            )
        )
    )
    counts["control_relations"] = int(n or 0)
    return counts


async def _seed_moving_refs(db_session, winner: Control, loser: Control) -> dict:
    """七张表各布一条会转挂的（向量是丢弃，赢家那条不动）。"""
    other = await _control(db_session, "C-0003")
    shared = await _framework_item(db_session, "PR.AA-00")
    unique = await _framework_item(db_session, "PR.AA-01")
    await _mapping(db_session, winner.id, shared.id, MappingStrength.FULL)
    await _mapping(db_session, loser.id, shared.id, MappingStrength.PARTIAL)
    mapping = await _mapping(db_session, loser.id, unique.id, MappingStrength.FULL)
    clause = await _clause(db_session)
    source = await _source(db_session, loser.id, clause.id)
    relation = await _relation(db_session, loser, other, RelationType.DEPENDS_ON)
    winner_emb = ControlEmbedding(control_id=winner.id)
    loser_emb = ControlEmbedding(control_id=loser.id)
    evidence_type = EvidenceType(
        name_zh="证",
        name_en="Ev",
        format="pdf",
        cadence=EvidenceCadence.ANNUAL,
    )
    asset = TechAsset(
        name="PAM-exec",
        category=TechAssetCategory.PAM,
        vendor="V",
        environment=TechAssetEnvironment.PROD,
        status=TechAssetStatus.ACTIVE,
    )
    db_session.add_all([winner_emb, loser_emb, evidence_type, asset])
    await db_session.flush()
    evidence = EvidenceItem(
        evidence_type_id=evidence_type.id,
        control_id=loser.id,
        title="E",
        status=EvidenceStatus.PLANNED,
    )
    implementation = Implementation(
        control_id=loser.id,
        tech_asset_id=asset.id,
        description="d",
        how_enforced=HowEnforced.MANUAL,
        status=ImplementationStatus.IMPLEMENTED,
    )
    risk = RiskEntry(
        title="R",
        source=RiskSource.MANUAL,
        source_ref={},
        control_id=loser.id,
        likelihood=2,
        impact=3,
        inherent_score=6,
        status=RiskStatus.OPEN,
    )
    db_session.add_all([evidence, implementation, risk])
    await db_session.flush()
    return {
        "other": other,
        "mapping": mapping,
        "source": source,
        "relation": relation,
        "winner_emb": winner_emb,
        "loser_emb": loser_emb,
        "evidence": evidence,
        "implementation": implementation,
        "risk": risk,
    }


async def test_every_reference_ends_up_on_the_winner(db_session):
    lead = await _user(db_session, Role.GRC_LEAD, "lead@example.com")
    winner = await _control(db_session, "C-0001")
    loser = await _control(db_session, "C-0002")
    refs = await _seed_moving_refs(db_session, winner, loser)
    winner_id, loser_id = winner.id, loser.id
    other_id = refs["other"].id
    mapping_id = refs["mapping"].id
    source_id = refs["source"].id
    relation_id = refs["relation"].id
    winner_emb_id = refs["winner_emb"].id
    loser_emb_id = refs["loser_emb"].id
    evidence_id = refs["evidence"].id
    implementation_id = refs["implementation"].id
    risk_id = refs["risk"].id

    await merge_controls(db_session, loser_id=loser_id, winner_id=winner_id, actor=lead)
    db_session.expire_all()

    assert await _fk_counts(db_session, loser_id) == {
        "control_embeddings": 0,
        "control_sources": 0,
        "evidence_items": 0,
        "implementations": 0,
        "mappings": 0,
        "risk_entries": 0,
        "control_relations": 0,
    }
    assert (await db_session.get(Mapping, mapping_id)).control_id == winner_id
    assert (await db_session.get(ControlSource, source_id)).control_id == winner_id
    assert (await db_session.get(EvidenceItem, evidence_id)).control_id == winner_id
    assert (await db_session.get(Implementation, implementation_id)).control_id == winner_id
    assert (await db_session.get(RiskEntry, risk_id)).control_id == winner_id
    moved = await db_session.get(ControlRelation, relation_id)
    assert moved.from_control_id == winner_id
    assert moved.to_control_id == other_id
    assert await db_session.get(ControlEmbedding, loser_emb_id) is None
    kept = await db_session.get(ControlEmbedding, winner_emb_id)
    assert kept is not None and kept.control_id == winner_id


async def test_the_loser_is_kept_and_points_at_the_winner(db_session):
    lead = await _user(db_session, Role.GRC_LEAD, "lead@example.com")
    winner = await _control(db_session, "C-0001")
    loser = await _control(db_session, "C-0002")
    winner_id, loser_id = winner.id, loser.id

    await merge_controls(db_session, loser_id=loser_id, winner_id=winner_id, actor=lead)
    db_session.expire_all()

    kept = await db_session.get(Control, loser_id)
    assert kept is not None
    assert kept.status == "merged" and kept.merged_into_id == winner_id


async def test_the_winner_s_own_wording_is_untouched(db_session):
    lead = await _user(db_session, Role.GRC_LEAD, "lead@example.com")
    winner = await _control(db_session, "C-0001", statement="Keep this statement")
    winner.title = "Winner title"
    winner.category = "Access"
    winner.owner_user_id = lead.id
    loser = await _control(db_session, "C-0002", statement="Loser statement")
    await db_session.flush()
    winner_id, loser_id = winner.id, loser.id
    before = (winner.title, winner.statement, winner.category, winner.owner_user_id)

    await merge_controls(db_session, loser_id=loser_id, winner_id=winner_id, actor=lead)
    db_session.expire_all()

    kept = await db_session.get(Control, winner_id)
    assert (kept.title, kept.statement, kept.category, kept.owner_user_id) == before
    assert kept.status == "active"
    assert kept.merged_into_id is None


async def test_the_audit_entry_says_what_moved_and_what_was_dropped(db_session):
    lead = await _user(db_session, Role.GRC_LEAD, "lead@example.com")
    winner = await _control(db_session, "C-0001")
    loser = await _control(db_session, "C-0002")
    await _seed_moving_refs(db_session, winner, loser)

    await merge_controls(db_session, loser_id=loser.id, winner_id=winner.id, actor=lead)

    entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "control.merge"))
    assert entry.before["code"] == "C-0002"
    assert entry.after["merged_into"] == "C-0001"
    assert entry.after["moves"]["mappings"] == 1
    assert entry.after["discards"][0]["detail"]


async def test_a_blocked_plan_changes_nothing(db_session):
    lead = await _user(db_session, Role.GRC_LEAD, "lead@example.com")
    c = await _control(db_session, "C-0001")
    other = await _control(db_session, "C-0002")
    await _seed_moving_refs(db_session, c, other)
    before = await _snapshot(db_session)

    with pytest.raises(AppError, match="不能把控制点并入它自己"):
        await merge_controls(db_session, loser_id=c.id, winner_id=c.id, actor=lead)

    assert await _snapshot(db_session) == before


async def test_a_contributor_cannot_merge(db_session):
    contributor = await _user(db_session, Role.CONTRIBUTOR, "c@example.com")
    winner = await _control(db_session, "C-0001")
    loser = await _control(db_session, "C-0002")

    with pytest.raises(Forbidden):
        await merge_controls(
            db_session, loser_id=loser.id, winner_id=winner.id, actor=contributor
        )
