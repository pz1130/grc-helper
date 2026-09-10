"""语料盲区：你自己的制度里，有多少要求还没变成控制点。

与框架覆盖度方向相反——那个问「外部要求有没有被满足」，这个问「我们写下的要求
有没有被系统看见」。两种盲区都是静默的：不扫就没有任何地方会提示。

实测撞到过：6 份文档里 2 份从未产生任何抽取提案，而界面上毫无迹象。
"""

import pytest

from app.clauses.models import Clause
from app.controls.models import Control, ControlSource, SourceRelation
from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password
from app.ingest.coverage import document_coverage, uncovered_clauses
from app.ingest.models import DocStatus, DocType, Document
from app.review.models import Proposal, ProposalKind, ProposalStatus


async def _document(db_session, title: str, clauses: list[str]) -> Document:
    document = Document(title=title, doc_type=DocType.PROCEDURE,
                        file_hash=title.ljust(64, "0")[:64], file_path=f"/{title}.pdf",
                        original_filename=f"{title}.pdf", status=DocStatus.ACTIVE)
    db_session.add(document)
    await db_session.flush()
    for index, text in enumerate(clauses):
        db_session.add(Clause(document_id=document.id, number=str(index), heading="H",
                              heading_path=f"S › {index}", citation_label=str(index),
                              text=text, order_index=index, level=2))
    await db_session.flush()
    return document


NORM = ("Access to production systems must be approved by the service owner "
        "before the change window opens.")
PLAIN = ("This section describes the layout of the document and lists the "
         "annexes that accompany it for reference purposes only.")


async def _control_from(db_session, clause_text_index: int, document: Document) -> None:
    from sqlalchemy import select

    clause = await db_session.scalar(
        select(Clause).where(Clause.document_id == document.id,
                             Clause.order_index == clause_text_index))
    control = Control(code=f"C-{document.id}-{clause_text_index}", title="t", statement="s")
    db_session.add(control)
    await db_session.flush()
    db_session.add(ControlSource(control_id=control.id, clause_id=clause.id,
                                 relation=SourceRelation.DEFINES))
    await db_session.flush()


@pytest.mark.asyncio
async def test_a_document_that_was_never_extracted_is_called_out(db_session):
    """不是「抽了但都被拒」，是根本没跑过——这两种要分得开。"""
    await _document(db_session, "never", [NORM, NORM])
    rows = {r.title: r for r in await document_coverage(db_session)}

    row = rows["never"]
    assert row.proposals == 0
    assert row.never_extracted is True
    assert row.normative_clauses == 2 and row.controls == 0


@pytest.mark.asyncio
async def test_extracted_but_all_rejected_is_not_the_same_as_never_extracted(db_session):
    document = await _document(db_session, "rejected", [NORM])
    db_session.add(Proposal(kind=ProposalKind.CONTROL_EXTRACT, status=ProposalStatus.REJECTED,
                            document_id=document.id, payload={"title": "t", "statement": "s"},
                            citations=[], confidence=0.5, reject_reason="不成立"))
    await db_session.flush()

    row = next(r for r in await document_coverage(db_session) if r.title == "rejected")
    assert row.proposals == 1
    assert row.never_extracted is False, "跑过但被拒，和从没跑过是两回事"
    assert row.controls == 0


@pytest.mark.asyncio
async def test_normative_clauses_without_a_control_are_counted(db_session):
    document = await _document(db_session, "partial", [NORM, NORM, PLAIN])
    await _control_from(db_session, 0, document)

    row = next(r for r in await document_coverage(db_session) if r.title == "partial")
    assert row.clauses == 3
    assert row.normative_clauses == 2, "PLAIN 不含情态词，不算规范条款"
    assert row.controls == 1
    assert row.uncovered_normative == 1


@pytest.mark.asyncio
async def test_uncovered_detail_lists_the_clauses_and_flags_obligations(db_session):
    document = await _document(db_session, "detail", [
        NORM,
        "Teams should review the dashboard weekly and record any anomalies found.",
    ])
    rows = await uncovered_clauses(db_session, document.id)

    assert [r.citation_label for r in rows] == ["0", "1"]
    assert rows[0].strong is True, "must 是义务"
    assert rows[1].strong is False, "should 是建议——漏一条义务和漏一条建议不是一回事"
    assert rows[0].heading_path


@pytest.mark.asyncio
async def test_a_clause_backing_a_control_is_not_reported_as_uncovered(db_session):
    document = await _document(db_session, "covered", [NORM])
    await _control_from(db_session, 0, document)
    assert await uncovered_clauses(db_session, document.id) == []


@pytest.mark.asyncio
async def test_coverage_endpoint_is_readable_by_any_read_user(client, db_session):
    db_session.add(User(email="v@example.com", name="V", role=Role.VIEWER,
                        password_hash=hash_password("pw123456")))
    await _document(db_session, "api", [NORM])
    await db_session.flush()
    token = (await client.post("/api/auth/login",
                               json={"email": "v@example.com", "password": "pw123456"})
             ).json()["access_token"]

    body = (await client.get("/api/documents/coverage",
                             headers={"Authorization": f"Bearer {token}"})).json()
    row = next(r for r in body if r["title"] == "api")
    assert row["never_extracted"] is True and row["normative_clauses"] == 1
