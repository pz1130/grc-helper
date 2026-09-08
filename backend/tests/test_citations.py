"""Pure tests: the SQL session is mocked; no database fixtures."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.extraction.citations import ClauseCitationValidator, normalize


def payload(cid=1, quote="Two approvers"):
    return {"controls": [{"citations": [{"clause_id": cid, "quote": quote}]}]}


def validator(**kwargs):
    session = SimpleNamespace(scalars=AsyncMock(return_value=[
        SimpleNamespace(id=1, document_id=10, text="Two  approvers\nare required."),
        SimpleNamespace(id=2, document_id=11, text="Two approvers"),
        SimpleNamespace(id=3, document_id=10, text="Two approvers"),
    ]))
    return ClauseCitationValidator(session, **kwargs)


def test_normalize_only_whitespace():
    assert normalize("  Two\n Approvers,\tplease. ") == "Two Approvers, please."


@pytest.mark.parametrize("quote", ["Two approvers", "approvers are required."])
async def test_literal_quote_passes(quote):
    assert await validator(document_id=10, clause_ids={1}).check(payload(quote=quote)) is None


@pytest.mark.parametrize("cid,quote", [
    (999, "Two approvers"), (True, "Two approvers"), ("1", "Two approvers"),
    ([], "Two approvers"), (1, " "), (1, None), (1, 42),
    (1, "two approvers"), (1, "Two approvers are required" + "!"),
    (1, "Dual approval"), (2, "Two approvers"), (3, "Two approvers"),
])
async def test_invalid_or_out_of_scope_citation_rejected(cid, quote):
    assert await validator(document_id=10, clause_ids={1}).check(payload(cid, quote))


@pytest.mark.parametrize("data", [
    {}, {"controls": []}, {"controls": [None]}, {"controls": [{}]},
    {"controls": [{"citations": []}]}, {"controls": [{"citations": [None]}]},
    {**payload(), "insufficient_evidence": True},
])
async def test_no_empty_or_malformed_sources(data):
    assert await validator().check(data)


async def test_explicit_insufficient_evidence():
    assert await validator().check({"controls": [], "insufficient_evidence": True}) is None


async def test_all_citations_checked():
    data = payload()
    data["controls"][0]["citations"].append({"clause_id": 1, "quote": "fabricated"})
    assert await validator().check(data)


async def test_cross_document_relations_and_empty_scope():
    data = {"relations": payload(2)["controls"]}
    assert await validator(item_key="relations").check(data) is None
    assert await validator(item_key="relations", clause_ids=set()).check(data)
