"""已合并的控制点从枚举路径消失，按 id 取的路径仍能解析去向。"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.clauses.models import EMBEDDING_DIM, Clause
from app.controls.models import Control
from app.errors import AppError
from app.frameworks.models import Framework, FrameworkItem, Mapping, MappingStrength
from app.iam.models import User
from app.iam.permissions import Role
from app.iam.security import hash_password
from app.ingest.models import DocStatus, DocType, Document
from app.review.models import Proposal, ProposalKind
from app.review.service import Decision, decide


async def _user(db_session, role: Role = Role.VIEWER, email: str = "v@example.com") -> User:
    user = User(email=email, name=email, role=role, password_hash=hash_password("pw123456"))
    db_session.add(user)
    await db_session.flush()
    return user


async def _auth(client, email: str = "v@example.com") -> dict[str, str]:
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _control(
    db_session, code: str, *, title: str | None = None, statement: str | None = None
) -> Control:
    control = Control(
        code=code,
        title=title or f"Title {code}",
        statement=statement or f"{code} statement.",
    )
    db_session.add(control)
    await db_session.flush()
    return control


async def _merged_pair(db_session, *, loser_title: str | None = None) -> tuple[Control, Control]:
    """赢家 + 已合并的输家。不走 merge_controls：本文件测的是枚举，不是执行。"""
    winner = await _control(db_session, "C-0001", title="Live control")
    loser = await _control(db_session, "C-0002", title=loser_title or "Merged control")
    loser.status = "merged"
    loser.merged_into_id = winner.id
    await db_session.flush()
    return winner, loser


async def _review_setup(db_session):
    actor = User(
        email="lead@example.com", name="L", role=Role.GRC_LEAD, password_hash=hash_password("pw")
    )
    doc = Document(
        title="P",
        doc_type=DocType.PROCEDURE,
        file_hash="a" * 64,
        file_path="/x.pdf",
        original_filename="x.pdf",
        status=DocStatus.ACTIVE,
    )
    db_session.add_all([actor, doc])
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
    return actor, doc, clause


async def _extract_proposal(db_session, doc, clause, *, title: str):
    proposal = Proposal(
        kind=ProposalKind.CONTROL_EXTRACT,
        payload={
            "title": title,
            "statement": "Two approvers.",
            "confidence": 0.9,
            "citations": [{"clause_id": clause.id, "quote": "Two approvers"}],
        },
        citations=[{"clause_id": clause.id, "quote": "Two approvers"}],
        confidence=0.9,
        document_id=doc.id,
    )
    db_session.add(proposal)
    await db_session.flush()
    return proposal


async def _framework(db_session) -> tuple[Framework, FrameworkItem]:
    framework = Framework(
        key="nist-csf-2.0", name_zh="框架", name_en="Framework", version="2.0", source="nist.gov"
    )
    db_session.add(framework)
    await db_session.flush()
    item = FrameworkItem(
        framework_id=framework.id,
        parent_id=None,
        code="GV.PO-01",
        title="Policy",
        level=1,
        order_index=0,
    )
    db_session.add(item)
    await db_session.flush()
    return framework, item


def _vectors(count: int):
    return ([[0.02] * EMBEDDING_DIM for _ in range(count)], count)


@pytest.mark.asyncio
async def test_the_control_list_hides_a_merged_control(client, db_session):
    await _user(db_session)
    winner, loser = await _merged_pair(db_session)
    headers = await _auth(client)

    body = (await client.get("/api/controls", headers=headers)).json()
    codes = [row["code"] for row in body]
    assert winner.code in codes
    assert loser.code not in codes
    assert [row["id"] for row in body] == [winner.id]


@pytest.mark.asyncio
async def test_the_graph_has_no_node_for_a_merged_control(db_session):
    from app.graph.service import relation_graph

    winner, loser = await _merged_pair(db_session)
    graph = await relation_graph(db_session)
    codes = [node.code for node in graph.nodes]
    assert winner.code in codes
    assert loser.code not in codes


@pytest.mark.asyncio
async def test_embed_pending_skips_a_merged_control(db_session):
    from app.relations.indexing import embed_pending
    from app.relations.models import ControlEmbedding

    winner, loser = await _merged_pair(db_session)
    with patch(
        "app.relations.indexing.embed",
        new=AsyncMock(side_effect=lambda session, *, texts: _vectors(len(texts))),
    ), patch(
        "app.relations.indexing.current_model", new=AsyncMock(return_value="embo-01")
    ):
        result = await embed_pending(db_session)

    assert result["embedded"] == 1
    ids = list(await db_session.scalars(select(ControlEmbedding.control_id)))
    assert ids == [winner.id]
    assert loser.id not in ids


@pytest.mark.asyncio
async def test_relation_candidates_skip_a_merged_control(db_session):
    from app.relations.tasks import _build_batches

    winner, _loser = await _merged_pair(db_session)
    # 只剩已合并的行时，枚举应视为空库，而不是带着输家去凑候选。
    winner.status = "merged"
    await db_session.flush()
    with pytest.raises(AppError, match="控制点库为空"):
        await _build_batches(db_session)


@pytest.mark.asyncio
async def test_mapping_candidates_skip_a_merged_control(db_session, monkeypatch):
    from app.mapping import tasks

    winner, loser = await _merged_pair(db_session)
    # 只要框架、不要要求项：render_controls 在分批之前就会跑，避免真打模型。
    framework = Framework(
        key="nist-csf-2.0", name_zh="框架", name_en="Framework", version="2.0", source="nist.gov"
    )
    db_session.add(framework)
    await db_session.flush()
    seen: list[str] = []
    real = tasks.render_controls

    def capturing(controls):
        seen.extend(c.code for c in controls)
        return real(controls)

    monkeypatch.setattr(tasks, "render_controls", capturing)
    await tasks.run_mapping(db_session, framework.id)

    assert winner.code in seen
    assert loser.code not in seen


@pytest.mark.asyncio
async def test_the_readiness_package_skips_a_merged_control(db_session):
    from app.packaging.service import mapping_rows

    winner, loser = await _merged_pair(db_session)
    framework, item = await _framework(db_session)
    db_session.add_all(
        [
            Mapping(
                control_id=winner.id,
                framework_item_id=item.id,
                strength=MappingStrength.FULL,
            ),
            Mapping(
                control_id=loser.id,
                framework_item_id=item.id,
                strength=MappingStrength.PARTIAL,
            ),
        ]
    )
    await db_session.flush()

    codes = [row[0] for row in await mapping_rows(db_session, framework.id)]
    assert winner.code in codes
    assert loser.code not in codes


@pytest.mark.asyncio
async def test_the_detail_page_still_answers_for_a_merged_control(client, db_session):
    await _user(db_session)
    winner, loser = await _merged_pair(db_session)
    headers = await _auth(client)

    body = (await client.get(f"/api/controls/{loser.id}", headers=headers)).json()
    assert body["status"] == "merged" and body["merged_into_id"] == winner.id


@pytest.mark.asyncio
async def test_title_deduplication_ignores_a_merged_control(db_session):
    actor, doc, clause = await _review_setup(db_session)
    winner, loser = await _merged_pair(db_session, loser_title="Dual approval")
    proposal = await _extract_proposal(db_session, doc, clause, title="Dual approval")

    await decide(db_session, proposal.id, actor=actor, decision=Decision.ACCEPT)

    live = list(
        await db_session.scalars(select(Control).where(Control.status != "merged"))
    )
    created = [c for c in live if c.id != winner.id]
    assert len(created) == 1
    assert created[0].id != loser.id
    assert created[0].title == "Dual approval"
    assert created[0].status == "active"


@pytest.mark.asyncio
async def test_a_merged_code_is_never_handed_out_again(db_session):
    actor, doc, clause = await _review_setup(db_session)
    await _merged_pair(db_session)
    proposal = await _extract_proposal(db_session, doc, clause, title="Brand new control")

    await decide(db_session, proposal.id, actor=actor, decision=Decision.ACCEPT)

    created = await db_session.scalar(
        select(Control).where(Control.title == "Brand new control")
    )
    assert created is not None
    assert created.code == "C-0003"
