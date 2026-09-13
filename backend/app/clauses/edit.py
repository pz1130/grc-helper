"""条款拆/合。不删行，每次改动写审计。"""

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.controls.models import ControlSource
from app.errors import AppError, NotFound
from app.iam.audit import record
from app.iam.models import User
from app.indexing.service import rebuild_chunks
from app.parsing.flatten import PATH_SEPARATOR, build_citation_label


async def _lock(session: AsyncSession, document_id: int) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(734005, :doc)"), {"doc": document_id}
    )


def _heading_path_for_sibling(sibling: Clause, heading: str) -> str:
    parent = PATH_SEPARATOR.join(sibling.heading_path.split(PATH_SEPARATOR)[:-1])
    return PATH_SEPARATOR.join([part for part in (parent, heading) if part])


async def split_clause(
    session: AsyncSession, clause_id: int, *, at: int, actor: User
) -> Clause:
    clause = await session.get(Clause, clause_id)
    if clause is None or clause.status == "merged":
        raise NotFound("条款不存在")
    body = clause.text or ""
    if at <= 0 or at >= len(body):
        raise AppError("切开位置必须落在正文中间")
    await _lock(session, clause.document_id)

    left, right = body[:at].rstrip(), body[at:].lstrip()
    if not left or not right:
        raise AppError("切开位置必须落在正文中间")

    before = {"text": clause.text}
    clause.text = left
    first_line = right.split("\n", 1)[0].strip()
    heading = first_line[:80] if first_line else f"{clause.heading} (continued)"
    heading_path = _heading_path_for_sibling(clause, heading)

    await session.execute(
        update(Clause)
        .where(Clause.document_id == clause.document_id, Clause.order_index > clause.order_index)
        .values(order_index=Clause.order_index + 1)
    )
    created = Clause(
        document_id=clause.document_id,
        parent_id=clause.parent_id,
        number=None,
        heading=heading,
        heading_path=heading_path,
        citation_label=build_citation_label(None, heading_path),
        text=right,
        order_index=clause.order_index + 1,
        level=clause.level,
        page_ref=clause.page_ref,
        kind=clause.kind,
        language=clause.language,
        status="active",
    )
    session.add(created)
    await session.flush()
    await rebuild_chunks(session, document_id=clause.document_id)
    await record(
        session,
        user=actor,
        action="clause.split",
        entity_type="Clause",
        entity_id=clause.id,
        before=before,
        after={"text": clause.text, "created_id": created.id},
    )
    return created


async def merge_clauses(
    session: AsyncSession, *, winner_id: int, loser_id: int, actor: User
) -> Clause:
    if winner_id == loser_id:
        raise AppError("不能与自己合并")
    winner = await session.get(Clause, winner_id)
    loser = await session.get(Clause, loser_id)
    if winner is None or loser is None or "merged" in {winner.status, loser.status}:
        raise NotFound("条款不存在")
    if winner.document_id != loser.document_id:
        raise AppError("只能合并同一份文档里的条款")
    await _lock(session, winner.document_id)

    winner.text = f"{winner.text.rstrip()}\n\n{loser.text.lstrip()}".strip()
    children = list(await session.scalars(select(Clause).where(Clause.parent_id == loser.id)))
    for child in children:
        child.parent_id = winner.id

    occupied = set(
        await session.scalars(
            select(ControlSource.control_id).where(ControlSource.clause_id == winner.id)
        )
    )
    sources = list(await session.scalars(select(ControlSource).where(ControlSource.clause_id == loser.id)))
    for source in sources:
        if source.control_id in occupied:
            continue
        source.clause_id = winner.id
        occupied.add(source.control_id)

    loser.status = "merged"
    loser.merged_into_id = winner.id
    await session.flush()
    await rebuild_chunks(session, document_id=winner.document_id)
    await record(
        session,
        user=actor,
        action="clause.merge",
        entity_type="Clause",
        entity_id=loser.id,
        before={"text": loser.text, "heading": loser.heading},
        after={"merged_into": winner.id},
    )
    return winner
