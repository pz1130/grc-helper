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


def artifact_validator():
    """条款正文带 PDF 抽取产物：弯引号、项目符号、连字符断行。"""
    session = SimpleNamespace(scalars=AsyncMock(return_value=[
        SimpleNamespace(id=1, document_id=10, text=(
            "• Where operationally practical users must use the Acme’s approved\n"
            "key vault service.\n"
            "• Set the incident to the “closed” status.\n"
            "Contractual third-\nparty availability applies – see Annex."
        )),
    ]))
    return ClauseCitationValidator(session, document_id=10, clause_ids={1})


@pytest.mark.parametrize("quote", [
    pytest.param("the Acme's approved key vault service.",
                 id="curly-apostrophe-folded"),
    pytest.param('Set the incident to the "closed" status.', id="curly-double-quotes-folded"),
    pytest.param("Contractual third-party availability applies", id="hyphen-linewrap-rejoined"),
    pytest.param("availability applies - see Annex.", id="en-dash-folded"),
    pytest.param(
        "Where operationally practical users must use the Acme's approved privileged access "
        "management system. Set the incident to the \"closed\" status.",
        id="quote-spanning-bullets",
    ),
])
async def test_typographic_artifacts_do_not_reject_a_verbatim_quote(quote):
    assert await artifact_validator().check(payload(quote=quote)) is None


@pytest.mark.parametrize("quote", [
    pytest.param("users must use an externally hosted vault.", id="fabricated-sentence"),
    pytest.param("the Acme's rejected key vault service.", id="one-word-swapped"),
    pytest.param("where technically feasible", id="case-still-significant"),
    pytest.param("Where feasible users must use", id="words-dropped-from-the-middle"),
])
async def test_folding_does_not_let_fabricated_wording_through(quote):
    assert await artifact_validator().check(payload(quote=quote))


def test_normalize_folds_presentation_but_preserves_wording():
    assert normalize("  Two\n Approvers,\tplease. ") == "Two Approvers, please."
    assert normalize("Acme’s “closed” – x") == "Acme's \"closed\" - x"
    assert normalize("third-\nparty") == "third-party"
    assert normalize("• a\n• b") == "a b"
