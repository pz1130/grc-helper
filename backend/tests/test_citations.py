"""Pure tests: the SQL session is mocked; no database fixtures."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.extraction.citations import ClauseCitationValidator, normalize


def payload(cid=1, quote="Two approvers"):
    return {"controls": [{"citations": [{"clause_id": cid, "quote": quote}]}]}


def validator(**kwargs):
    session = SimpleNamespace(scalars=AsyncMock(return_value=[
        SimpleNamespace(id=1, document_id=10, heading="Approval",
                        text="Two  approvers\nare required."),
        SimpleNamespace(id=2, document_id=11, heading="Approval", text="Two approvers"),
        SimpleNamespace(id=3, document_id=10, heading="Approval", text="Two approvers"),
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
            "• Where operationally practical users must use the vendor’s approved\n"
            "key vault service.\n"
            "• Set the incident to the “closed” status.\n"
            "Contractual third-\nparty availability applies – see Annex."
        )),
    ]))
    return ClauseCitationValidator(session, document_id=10, clause_ids={1})


@pytest.mark.parametrize("quote", [
    pytest.param("the vendor's approved key vault service.",
                 id="curly-apostrophe-folded"),
    pytest.param('Set the incident to the "closed" status.', id="curly-double-quotes-folded"),
    pytest.param("Contractual third-party availability applies", id="hyphen-linewrap-rejoined"),
    pytest.param("availability applies - see Annex.", id="en-dash-folded"),
    pytest.param(
        "Where operationally practical users must use the vendor's approved key vault "
        "service. Set the incident to the \"closed\" status.",
        id="quote-spanning-bullets",
    ),
])
async def test_typographic_artifacts_do_not_reject_a_verbatim_quote(quote):
    assert await artifact_validator().check(payload(quote=quote)) is None


@pytest.mark.parametrize("quote", [
    pytest.param("users must use an externally hosted vault.", id="fabricated-sentence"),
    pytest.param("the vendor's rejected key vault service.", id="one-word-swapped"),
    pytest.param("where operationally practical", id="case-still-significant"),
    pytest.param("Where practical users must use", id="words-dropped-from-the-middle"),
])
async def test_folding_does_not_let_fabricated_wording_through(quote):
    assert await artifact_validator().check(payload(quote=quote))



# ── 一句话被劈成 heading + text 两半 ──────────────────────────
# 段落级编号的文档（HKMA SPM 的 `2.2` 就是一个段落，没有标题）里，解析器把
# 编号那一行当标题、剩下的当正文，于是**每个段落都在第一行处被劈开**：
#
#   heading = "Under this policy, AIs are required to develop robust technology"
#   text    = "and cyber risk management frameworks that are proportionate…"
#
# 而送进模型的提示词里这两行是**相连**的（batching.render 先写标题行再写正文），
# 模型引一句完整的话理所当然。闸 4 只拿 text 对，就把一条本来正确的抽取拒掉了——
# 实测 HKMA TM-C-1 七批里有两批栽在这里，而那两批恰恰是全文仅有的、真正
# 对银行提要求的段落。


def _split_sentence_validator():
    session = SimpleNamespace(scalars=AsyncMock(return_value=[
        SimpleNamespace(
            id=1,
            document_id=10,
            heading="Under this policy, AIs are required to develop robust technology",
            text="and cyber risk management frameworks that are proportionate.",
        ),
    ]))
    return ClauseCitationValidator(session, document_id=10, clause_ids={1})


async def test_a_quote_spanning_the_heading_and_the_body_is_accepted():
    quote = (
        "Under this policy, AIs are required to develop robust technology "
        "and cyber risk management frameworks"
    )
    assert await _split_sentence_validator().check(payload(quote=quote)) is None


async def test_a_quote_from_the_heading_alone_is_accepted():
    assert await _split_sentence_validator().check(
        payload(quote="AIs are required to develop robust technology")
    ) is None


async def test_widening_to_the_heading_does_not_let_fabrication_through():
    """放宽的只是"这条条款的全部文字"，不是"随便什么文字"。"""
    assert await _split_sentence_validator().check(
        payload(quote="AIs are required to appoint an external auditor")
    )
