import pytest

from app.controls.models import Control
from app.frameworks.coverage import gaps, is_requirement, summarize
from app.frameworks.models import Framework, FrameworkItem, Mapping, MappingStrength
from app.review.models import Proposal, ProposalKind, ProposalStatus


def _item(**kwargs):
    from types import SimpleNamespace
    return SimpleNamespace(**{"attributes": None, **kwargs})


def test_a_leaf_is_a_requirement_by_default():
    assert is_requirement(_item(), has_children=False) is True


def test_a_container_is_not_a_requirement_by_default():
    assert is_requirement(_item(), has_children=True) is False


def test_an_explicit_flag_overrides_the_leaf_rule_in_both_directions():
    assert is_requirement(_item(attributes={"is_requirement": True}), has_children=True) is True
    assert is_requirement(_item(attributes={"is_requirement": False}), has_children=False) is False


async def _corpus(db_session):
    fw = Framework(key="k", name_zh="z", name_en="e", version="1", source="s", item_count=0)
    control = Control(code="C-0001", title="t", statement="s")
    db_session.add_all([fw, control])
    await db_session.flush()

    root = FrameworkItem(framework_id=fw.id, code="AC", title="Access Control",
                         description="", level=1, order_index=0)
    db_session.add(root)
    await db_session.flush()
    covered = FrameworkItem(
        framework_id=fw.id, parent_id=root.id, code="AC-1", title="Policy",
        description="d", level=2, order_index=1,
        attributes={"baselines": ["low", "moderate"]})
    supported_only = FrameworkItem(
        framework_id=fw.id, parent_id=root.id, code="AC-2", title="Accounts",
        description="d", level=2, order_index=2,
        attributes={"baselines": ["moderate"]})
    untouched = FrameworkItem(
        framework_id=fw.id, parent_id=root.id, code="AC-3", title="Enforcement",
        description="d", level=2, order_index=3,
        attributes={"baselines": ["high"]})
    db_session.add_all([covered, supported_only, untouched])
    await db_session.flush()

    db_session.add(Mapping(control_id=control.id, framework_item_id=covered.id,
                           strength=MappingStrength.PARTIAL, rationale="r", quote="d"))
    db_session.add(Mapping(control_id=control.id, framework_item_id=supported_only.id,
                           strength=MappingStrength.SUPPORTING, rationale="r", quote="d"))
    await db_session.flush()
    return fw, control, covered, supported_only, untouched


@pytest.mark.asyncio
async def test_supporting_alone_does_not_close_a_gap(db_session):
    fw, _, _, _supported_only, _untouched = await _corpus(db_session)
    rows = await gaps(db_session, fw.id)
    codes = {row.code for row in rows}
    assert codes == {"AC-2", "AC-3"}
    assert next(row for row in rows if row.code == "AC-2").has_supporting is True
    assert next(row for row in rows if row.code == "AC-3").has_supporting is False


@pytest.mark.asyncio
async def test_containers_are_excluded_from_the_denominator(db_session):
    fw, *_ = await _corpus(db_session)
    rows = await summarize(db_session, fw.id)
    root = next(row for row in rows if row.code == "AC")
    assert root.requirements == 3
    assert root.covered == 1


@pytest.mark.asyncio
async def test_baseline_filters_the_denominator(db_session):
    fw, *_ = await _corpus(db_session)
    rows = await summarize(db_session, fw.id, baseline="moderate")
    root = next(row for row in rows if row.code == "AC")
    assert root.requirements == 2
    assert root.covered == 1
    assert {row.code for row in await gaps(db_session, fw.id, baseline="moderate")} == {"AC-2"}


@pytest.mark.asyncio
async def test_pending_proposals_never_affect_coverage(db_session):
    fw, control, _, _, untouched = await _corpus(db_session)
    db_session.add(Proposal(
        kind=ProposalKind.MAPPING, status=ProposalStatus.PENDING,
        payload={"framework_item_id": untouched.id, "control_id": control.id,
                 "strength": "full", "quote": "d", "rationale": "r", "confidence": 0.99},
        citations=[], confidence=0.99,
    ))
    await db_session.flush()
    assert "AC-3" in {row.code for row in await gaps(db_session, fw.id)}


@pytest.mark.asyncio
async def test_an_empty_framework_has_no_requirements(db_session):
    fw = Framework(key="empty", name_zh="z", name_en="e", version="1", source="s", item_count=0)
    db_session.add(fw)
    await db_session.flush()
    assert await summarize(db_session, fw.id) == []
    assert await gaps(db_session, fw.id) == []
