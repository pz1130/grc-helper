import pytest
from sqlalchemy import select

from app.clauses.models import Clause
from app.controls.models import Control
from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password
from app.ingest.models import DocStatus, DocType, Document
from app.review.models import Proposal, ProposalKind


async def _seed(db_session, role: Role, email: str) -> User:
    user = User(email=email, name=email, role=role, password_hash=hash_password("pw123456"))
    db_session.add(user)
    await db_session.flush()
    return user


async def _auth(client, email: str) -> dict[str, str]:
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _proposal(db_session, *, confidence: float = 0.9) -> Proposal:
    from uuid import uuid4

    doc = Document(
        title="P",
        doc_type=DocType.PROCEDURE,
        file_hash=uuid4().hex * 2,
        file_path="/x.pdf",
        original_filename="x.pdf",
        status=DocStatus.ACTIVE,
    )
    db_session.add(doc)
    await db_session.flush()
    clause = Clause(
        document_id=doc.id,
        number="4.1",
        heading="H",
        heading_path="D › H",
        citation_label="4.1",
        text="Two approvers are required.",
        order_index=0,
        level=1,
    )
    db_session.add(clause)
    await db_session.flush()
    proposal = Proposal(
        kind=ProposalKind.CONTROL_EXTRACT,
        payload={
            "title": "Dual approval",
            "statement": "Two approvers.",
            "citations": [{"clause_id": clause.id, "quote": "Two approvers"}],
        },
        citations=[{"clause_id": clause.id, "quote": "Two approvers"}],
        confidence=confidence,
        document_id=doc.id,
    )
    db_session.add(proposal)
    await db_session.flush()
    return proposal


@pytest.mark.asyncio
async def test_viewer_can_read_the_queue(client, db_session):
    await _seed(db_session, Role.VIEWER, "v@example.com")
    await _proposal(db_session)
    headers = await _auth(client, "v@example.com")

    resp = await client.get("/api/proposals", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["payload"]["title"] == "Dual approval"


@pytest.mark.asyncio
async def test_contributor_cannot_decide(client, db_session):
    """spec D12：确认权只给 GRC Lead 及以上，这是数据质量的守门权。"""
    await _seed(db_session, Role.CONTRIBUTOR, "c@example.com")
    proposal = await _proposal(db_session)
    headers = await _auth(client, "c@example.com")

    resp = await client.post(
        f"/api/proposals/{proposal.id}/decide", json={"decision": "accept"}, headers=headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_grc_lead_can_accept(client, db_session):
    await _seed(db_session, Role.GRC_LEAD, "l@example.com")
    proposal = await _proposal(db_session)
    headers = await _auth(client, "l@example.com")

    resp = await client.post(
        f"/api/proposals/{proposal.id}/decide", json={"decision": "accept"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert await db_session.scalar(select(Control)) is not None


@pytest.mark.asyncio
async def test_modify_requires_a_payload(client, db_session):
    await _seed(db_session, Role.GRC_LEAD, "l@example.com")
    proposal = await _proposal(db_session)
    headers = await _auth(client, "l@example.com")

    resp = await client.post(
        f"/api/proposals/{proposal.id}/decide", json={"decision": "modify"}, headers=headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reject_requires_a_reason(client, db_session):
    """拒绝原因会回流用于改进 prompt，不能省。"""
    await _seed(db_session, Role.GRC_LEAD, "l@example.com")
    proposal = await _proposal(db_session)
    headers = await _auth(client, "l@example.com")

    resp = await client.post(
        f"/api/proposals/{proposal.id}/decide", json={"decision": "reject"}, headers=headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_accept_reports_how_many_were_skipped(client, db_session):
    await _seed(db_session, Role.GRC_LEAD, "l@example.com")
    high = await _proposal(db_session, confidence=0.95)
    low = await _proposal(db_session, confidence=0.40)
    headers = await _auth(client, "l@example.com")

    resp = await client.post(
        "/api/proposals/bulk-accept", json={"ids": [high.id, low.id]}, headers=headers
    )
    assert resp.json() == {"accepted": 1, "skipped": 1}


@pytest.mark.asyncio
async def test_stats_report_pending_counts_by_kind(client, db_session):
    await _seed(db_session, Role.VIEWER, "v@example.com")
    await _proposal(db_session)
    headers = await _auth(client, "v@example.com")

    body = (await client.get("/api/proposals/stats", headers=headers)).json()
    assert body["pending"] == 1
    assert body["by_kind"]["control_extract"] == 1


@pytest.mark.asyncio
async def test_queue_exposes_server_eligibility_and_ocr(client, db_session):
    await _seed(db_session, Role.VIEWER, "v@example.com")
    proposal = await _proposal(db_session, confidence=0.99)
    doc = await db_session.get(Document, proposal.document_id)
    doc.ocr_quality_flag = True
    await db_session.flush()
    headers = await _auth(client, "v@example.com")
    response = await client.get("/api/proposals", headers=headers)
    assert response.json()[0]["ocr_quality_flag"] is True
    assert response.json()[0]["bulk_acceptable"] is False


@pytest.mark.asyncio
async def test_contributor_cannot_bulk_decide(client, db_session):
    await _seed(db_session, Role.CONTRIBUTOR, "c@example.com")
    headers = await _auth(client, "c@example.com")
    response = await client.post("/api/proposals/bulk-accept", json={"ids": [1]}, headers=headers)
    assert response.status_code == 403
