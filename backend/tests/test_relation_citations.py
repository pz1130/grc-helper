from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.relations.citations import RelationCitationValidator

FROM_TEXT = "Every change must be approved by the CAB before implementation."
TO_TEXT = "The implementer shall follow the approved implementation plan."


def relation(**overrides):
    return {
        "from_control_id": 1,
        "to_control_id": 2,
        "from_quote": "approved by the CAB",
        "to_quote": "follow the approved implementation plan",
        "rationale": "implementation depends on prior approval",
        "confidence": 0.8,
        **overrides,
    }


def validator(control_ids=frozenset({1, 2})):
    session = SimpleNamespace(scalars=AsyncMock(return_value=[
        SimpleNamespace(id=1, statement=FROM_TEXT),
        SimpleNamespace(id=2, statement=TO_TEXT),
    ]))
    return RelationCitationValidator(session, control_ids=control_ids)


async def test_a_literal_quote_at_both_ends_passes():
    assert await validator().check({"relations": [relation()]}) is None


async def test_typographic_variants_are_folded():
    payload = {"relations": [relation(from_quote="approved by the CAB")]}
    assert await validator().check(payload) is None


@pytest.mark.parametrize("kwargs", [
    pytest.param({"from_control_id": 999}, id="gate3-from-not-in-batch"),
    pytest.param({"to_control_id": 999}, id="gate3-to-not-in-batch"),
    pytest.param({"from_control_id": 2, "to_control_id": 2}, id="self-relation"),
    pytest.param({"from_quote": "rejected by the CAB"}, id="gate4-from-fabricated"),
    pytest.param({"to_quote": "ignore the plan"}, id="gate4-to-fabricated"),
    pytest.param({"from_quote": "follow the approved implementation plan"},
                 id="gate4-quotes-swapped"),
    pytest.param({"from_quote": "   "}, id="blank-quote"),
    pytest.param({"from_control_id": True}, id="bool-is-not-an-id"),
    pytest.param({"confidence": 1.5}, id="confidence-out-of-range"),
])
async def test_invalid_relations_rejected(kwargs):
    assert await validator().check({"relations": [relation(**kwargs)]})


async def test_empty_list_requires_the_abstention_flag():
    assert await validator().check({"relations": []})
    assert await validator().check(
        {"relations": [], "insufficient_evidence": True}) is None


async def test_abstention_cannot_accompany_relations():
    assert await validator().check(
        {"relations": [relation()], "insufficient_evidence": True})


async def test_every_relation_is_checked_not_just_the_first():
    payload = {"relations": [relation(), relation(from_quote="fabricated")]}
    assert await validator().check(payload)
