import pytest

from app.clauses.models import Clause
from app.controls.models import (
    Control,
    ControlRelation,
    ControlSource,
    RelationType,
    SourceRelation,
)
from app.graph.service import control_key
from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password
from app.ingest.models import DocType, Document


async def _user(db_session, role: Role = Role.VIEWER, email: str = "v@example.com") -> User:
    user = User(email=email, name=email, role=role, password_hash=hash_password("pw123456"))
    db_session.add(user)
    await db_session.flush()
    return user


async def _auth(client, email: str = "v@example.com") -> dict[str, str]:
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _document(db_session, title: str, index: int) -> Document:
    doc = Document(
        title=title,
        doc_type=DocType.POLICY,
        file_hash=str(index) * 64,
        file_path=f"/{index}.pdf",
        original_filename=f"{index}.pdf",
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


async def _clause(db_session, document_id: int, number: str, order_index: int = 0) -> Clause:
    clause = Clause(
        document_id=document_id,
        number=number,
        heading="H",
        heading_path=f"H › {number}",
        citation_label=number,
        text=f"Clause {number} text.",
        order_index=order_index,
        level=1,
    )
    db_session.add(clause)
    await db_session.flush()
    return clause


async def _control(db_session, code: str, title: str = "T") -> Control:
    control = Control(code=code, title=title, statement=f"{code} statement.")
    db_session.add(control)
    await db_session.flush()
    return control


async def _relation(db_session, src: Control, dst: Control, kind: RelationType) -> ControlRelation:
    relation = ControlRelation(
        from_control_id=src.id,
        to_control_id=dst.id,
        relation_type=kind,
        rationale="because",
        confidence=0.9,
    )
    db_session.add(relation)
    await db_session.flush()
    return relation


@pytest.mark.asyncio
async def test_panorama_returns_controls_and_confirmed_relations(client, db_session):
    await _user(db_session)
    first = await _control(db_session, "C-0001")
    second = await _control(db_session, "C-0002")
    await _relation(db_session, first, second, RelationType.DEPENDS_ON)
    headers = await _auth(client)

    resp = await client.get("/api/graph/relations", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert [n["key"] for n in body["nodes"]] == ["control:%d" % first.id, "control:%d" % second.id]
    assert body["nodes"][0]["kind"] == "control"
    assert body["nodes"][0]["code"] == "C-0001"
    assert len(body["edges"]) == 1
    assert body["edges"][0]["source"] == "control:%d" % first.id
    assert body["edges"][0]["target"] == "control:%d" % second.id
    assert body["edges"][0]["kind"] == "depends_on"
    assert body["edges"][0]["status"] == "confirmed"
    assert body["edges"][0]["proposal_id"] is None
    assert body["stats"] == {"nodes": 2, "edges": 1, "pending_edges": 0, "truncated": False}


@pytest.mark.asyncio
async def test_graph_requires_a_token(client, db_session):
    await _user(db_session)
    resp = await client.get("/api/graph/relations")
    assert resp.status_code == 401


async def _chain(db_session) -> list[Control]:
    """C-0001 → C-0002 → C-0003，外加一个孤立的 C-0009。"""
    first = await _control(db_session, "C-0001")
    second = await _control(db_session, "C-0002")
    third = await _control(db_session, "C-0003")
    await _control(db_session, "C-0009")
    await _relation(db_session, first, second, RelationType.DEPENDS_ON)
    await _relation(db_session, second, third, RelationType.DEPENDS_ON)
    return [first, second, third]


@pytest.mark.asyncio
async def test_focus_on_a_control_returns_one_hop_neighbourhood(client, db_session):
    await _user(db_session)
    first, second, _third = await _chain(db_session)
    headers = await _auth(client)

    resp = await client.get(
        f"/api/graph/relations?focus=control:{first.id}&hops=1", headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert {n["key"] for n in body["nodes"]} == {control_key(first.id), control_key(second.id)}
    assert len(body["edges"]) == 1


@pytest.mark.asyncio
async def test_two_hops_reaches_further(client, db_session):
    await _user(db_session)
    first, second, third = await _chain(db_session)
    headers = await _auth(client)

    resp = await client.get(
        f"/api/graph/relations?focus=control:{first.id}&hops=2", headers=headers
    )

    body = resp.json()
    assert {n["key"] for n in body["nodes"]} == {
        control_key(first.id),
        control_key(second.id),
        control_key(third.id),
    }
    assert len(body["edges"]) == 2


@pytest.mark.asyncio
async def test_focus_on_a_document_seeds_every_control_it_defines(client, db_session):
    await _user(db_session)
    doc = await _document(db_session, "Change Management", 1)
    clause = await _clause(db_session, doc.id, "4.2")
    first = await _control(db_session, "C-0001")
    second = await _control(db_session, "C-0002")
    db_session.add(
        ControlSource(control_id=first.id, clause_id=clause.id, relation=SourceRelation.DEFINES)
    )
    await _relation(db_session, first, second, RelationType.DUPLICATES)
    await db_session.flush()
    headers = await _auth(client)

    resp = await client.get(f"/api/graph/relations?focus=document:{doc.id}&hops=1", headers=headers)

    body = resp.json()
    assert {n["key"] for n in body["nodes"]} == {control_key(first.id), control_key(second.id)}


@pytest.mark.asyncio
async def test_bad_focus_is_rejected(client, db_session):
    await _user(db_session)
    headers = await _auth(client)
    resp = await client.get("/api/graph/relations?focus=banana", headers=headers)
    assert resp.status_code == 400

