"""合并计划：只查不写。算出会转挂什么、会丢弃什么，供人决定后再执行。"""

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.controls.models import Control, ControlRelation, ControlSource
from app.environment.models import Implementation, TechAsset
from app.evidence.models import EvidenceItem
from app.frameworks.models import FrameworkItem, Mapping
from app.relations.models import ControlEmbedding
from app.risk.models import RiskEntry


@dataclass(frozen=True)
class Discard:
    table: str
    id: int
    detail: str


@dataclass(frozen=True)
class MergePlan:
    loser_code: str
    winner_code: str
    moves: dict[str, int]
    discards: list[Discard]
    blockers: list[str]


def _add_moves(moves: dict[str, int], table: str, n: int) -> None:
    if n:
        moves[table] = n


async def _load_and_blockers(
    session: AsyncSession, loser_id: int, winner_id: int
) -> tuple[Control | None, Control | None, list[str]]:
    if loser_id == winner_id:
        control = await session.get(Control, loser_id)
        if control is None:
            return None, None, ["控制点不存在"]
        blockers = ["不能把控制点并入它自己"]
        if control.status == "merged":
            blockers.append("已经合并的控制点不能再合并")
        return control, control, blockers

    loser = await session.get(Control, loser_id)
    winner = await session.get(Control, winner_id)
    blockers: list[str] = []
    if loser is None or winner is None:
        blockers.append("控制点不存在")
    if (loser is not None and loser.status == "merged") or (
        winner is not None and winner.status == "merged"
    ):
        blockers.append("已经合并的控制点不能再合并")
    return loser, winner, blockers


async def _count_on_loser(session: AsyncSession, model: type, loser_id: int) -> int:
    n = await session.scalar(
        select(func.count()).select_from(model).where(model.control_id == loser_id)
    )
    return int(n or 0)


async def _plan_embeddings(session: AsyncSession, loser_id: int) -> list[Discard]:
    # 一条控制点一行向量；赢家的留着，输家的整行丢掉。
    rows = list(
        await session.scalars(
            select(ControlEmbedding)
            .where(ControlEmbedding.control_id == loser_id)
            .order_by(ControlEmbedding.id)
        )
    )
    return [
        Discard(table="control_embeddings", id=row.id, detail="输家向量丢弃，保留赢家的")
        for row in rows
    ]


async def _plan_relations(
    session: AsyncSession, loser: Control, winner: Control
) -> tuple[int, list[Discard]]:
    occupied = {
        (row.from_control_id, row.to_control_id, row.relation_type)
        for row in await session.scalars(
            select(ControlRelation).where(
                ControlRelation.from_control_id != loser.id,
                ControlRelation.to_control_id != loser.id,
            )
        )
    }
    rows = list(
        await session.scalars(
            select(ControlRelation)
            .where(
                or_(
                    ControlRelation.from_control_id == loser.id,
                    ControlRelation.to_control_id == loser.id,
                )
            )
            .order_by(ControlRelation.id)
        )
    )
    moved = 0
    discards: list[Discard] = []
    for row in rows:
        new_from = winner.id if row.from_control_id == loser.id else row.from_control_id
        new_to = winner.id if row.to_control_id == loser.id else row.to_control_id
        key = (new_from, new_to, row.relation_type)
        if new_from == new_to:
            discards.append(
                Discard(
                    table="control_relations",
                    id=row.id,
                    detail=f"{row.relation_type.value}：合并后会自环",
                )
            )
        elif key in occupied:
            discards.append(
                Discard(
                    table="control_relations",
                    id=row.id,
                    detail=f"{row.relation_type.value}：转挂后与已有关系重复",
                )
            )
        else:
            occupied.add(key)
            moved += 1
    return moved, discards


async def _plan_sources(
    session: AsyncSession, loser_id: int, winner_id: int
) -> tuple[int, list[Discard]]:
    winner_clauses = set(
        await session.scalars(
            select(ControlSource.clause_id).where(ControlSource.control_id == winner_id)
        )
    )
    rows = (
        await session.execute(
            select(ControlSource, Clause)
            .join(Clause, Clause.id == ControlSource.clause_id)
            .where(ControlSource.control_id == loser_id)
            .order_by(ControlSource.id)
        )
    ).all()
    moved = 0
    discards: list[Discard] = []
    for source, clause in rows:
        if source.clause_id in winner_clauses:
            discards.append(
                Discard(
                    table="control_sources",
                    id=source.id,
                    detail=f"条款 {clause.citation_label}：赢家已有",
                )
            )
        else:
            moved += 1
    return moved, discards


async def _plan_implementations(
    session: AsyncSession, loser_id: int, winner_id: int
) -> tuple[int, list[Discard]]:
    winner_assets = set(
        await session.scalars(
            select(Implementation.tech_asset_id).where(Implementation.control_id == winner_id)
        )
    )
    rows = list(
        await session.scalars(
            select(Implementation)
            .where(Implementation.control_id == loser_id)
            .order_by(Implementation.id)
        )
    )
    asset_ids = [row.tech_asset_id for row in rows if row.tech_asset_id is not None]
    assets = {
        asset.id: asset
        for asset in (
            await session.scalars(select(TechAsset).where(TechAsset.id.in_(asset_ids)))
            if asset_ids
            else []
        )
    }
    moved = 0
    discards: list[Discard] = []
    for row in rows:
        if row.tech_asset_id in winner_assets:
            if row.tech_asset_id is None:
                detail = "无绑定资产：赢家已有"
            else:
                detail = f"资产 {assets[row.tech_asset_id].name}：赢家已有"
            discards.append(Discard(table="implementations", id=row.id, detail=detail))
        else:
            moved += 1
    return moved, discards


async def _plan_mappings(
    session: AsyncSession, loser_id: int, winner_id: int
) -> tuple[int, list[Discard]]:
    winner_by_item = {
        row.framework_item_id: row
        for row in await session.scalars(select(Mapping).where(Mapping.control_id == winner_id))
    }
    rows = (
        await session.execute(
            select(Mapping, FrameworkItem)
            .join(FrameworkItem, FrameworkItem.id == Mapping.framework_item_id)
            .where(Mapping.control_id == loser_id)
            .order_by(Mapping.id)
        )
    ).all()
    moved = 0
    discards: list[Discard] = []
    for mapping, item in rows:
        existing = winner_by_item.get(mapping.framework_item_id)
        if existing is None:
            moved += 1
            continue
        detail = f"{item.code}（{mapping.strength.value}）——赢家已有 {existing.strength.value}"
        if mapping.quote:
            detail += f"；摘录：{mapping.quote}"
        discards.append(Discard(table="mappings", id=mapping.id, detail=detail))
    return moved, discards


async def plan_merge(session: AsyncSession, *, loser_id: int, winner_id: int) -> MergePlan:
    """按表名字母序、表内 id 升序分类。本函数不得写入。"""
    loser, winner, blockers = await _load_and_blockers(session, loser_id, winner_id)
    if blockers:
        return MergePlan(
            loser_code=loser.code if loser else "",
            winner_code=winner.code if winner else "",
            moves={},
            discards=[],
            blockers=blockers,
        )
    assert loser is not None and winner is not None

    moves: dict[str, int] = {}
    discards: list[Discard] = []

    discards.extend(await _plan_embeddings(session, loser_id))

    n, dropped = await _plan_relations(session, loser, winner)
    _add_moves(moves, "control_relations", n)
    discards.extend(dropped)

    n, dropped = await _plan_sources(session, loser_id, winner_id)
    _add_moves(moves, "control_sources", n)
    discards.extend(dropped)

    _add_moves(moves, "evidence_items", await _count_on_loser(session, EvidenceItem, loser_id))

    n, dropped = await _plan_implementations(session, loser_id, winner_id)
    _add_moves(moves, "implementations", n)
    discards.extend(dropped)

    n, dropped = await _plan_mappings(session, loser_id, winner_id)
    _add_moves(moves, "mappings", n)
    discards.extend(dropped)

    _add_moves(moves, "risk_entries", await _count_on_loser(session, RiskEntry, loser_id))

    return MergePlan(
        loser_code=loser.code,
        winner_code=winner.code,
        moves=moves,
        discards=discards,
        blockers=[],
    )
