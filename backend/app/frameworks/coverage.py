"""覆盖度与差距。"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.frameworks.models import FrameworkItem, Mapping, MappingStrength

CLOSING = (MappingStrength.FULL, MappingStrength.PARTIAL)


@dataclass(frozen=True)
class CoverageRow:
    item_id: int
    code: str
    title: str
    level: int
    parent_id: int | None
    requirements: int
    covered: int


@dataclass(frozen=True)
class GapRow:
    item_id: int
    code: str
    title: str
    has_supporting: bool


def is_requirement(item: Any, has_children: bool) -> bool:
    """默认「叶子即要求」，允许 attributes.is_requirement 双向覆盖。"""
    explicit = (item.attributes or {}).get("is_requirement")
    if isinstance(explicit, bool):
        return explicit
    return not has_children


def _in_baseline(item: Any, baseline: str | None) -> bool:
    if baseline is None:
        return True
    baselines = (item.attributes or {}).get("baselines")
    return isinstance(baselines, list) and baseline in baselines


async def _load(
    session: AsyncSession, framework_id: int, baseline: str | None
) -> tuple[list[Any], dict[int, set[str]], set[int]]:
    items = list(await session.scalars(
        select(FrameworkItem)
        .where(FrameworkItem.framework_id == framework_id)
        .order_by(FrameworkItem.order_index, FrameworkItem.id)
    ))
    with_children = {item.parent_id for item in items if item.parent_id is not None}

    rows = await session.execute(
        select(Mapping.framework_item_id, Mapping.strength)
        .join(FrameworkItem, FrameworkItem.id == Mapping.framework_item_id)
        .where(FrameworkItem.framework_id == framework_id)
    )
    strengths: dict[int, set[str]] = {}
    for item_id, strength in rows:
        strengths.setdefault(item_id, set()).add(
            strength.value if hasattr(strength, "value") else str(strength)
        )

    requirements = {
        item.id
        for item in items
        if is_requirement(item, item.id in with_children) and _in_baseline(item, baseline)
    }
    return items, strengths, requirements


def _closed(strengths: dict[int, set[str]], item_id: int) -> bool:
    return bool(strengths.get(item_id, set()) & {strength.value for strength in CLOSING})


async def summarize(
    session: AsyncSession, framework_id: int, *, baseline: str | None = None
) -> list[CoverageRow]:
    """每个节点汇总其子树内的已覆盖要求数 / 要求总数。"""
    items, strengths, requirements = await _load(session, framework_id, baseline)
    if not items:
        return []

    children: dict[int | None, list[Any]] = {}
    for item in items:
        children.setdefault(item.parent_id, []).append(item)

    totals: dict[int, tuple[int, int]] = {}

    def walk(item: Any) -> tuple[int, int]:
        total = 1 if item.id in requirements else 0
        covered = 1 if item.id in requirements and _closed(strengths, item.id) else 0
        for child in children.get(item.id, []):
            child_total, child_covered = walk(child)
            total += child_total
            covered += child_covered
        totals[item.id] = (total, covered)
        return total, covered

    for root in children.get(None, []):
        walk(root)

    return [
        CoverageRow(
            item_id=item.id,
            code=item.code,
            title=item.title,
            level=item.level,
            parent_id=item.parent_id,
            requirements=totals[item.id][0],
            covered=totals[item.id][1],
        )
        for item in items
    ]


async def gaps(
    session: AsyncSession, framework_id: int, *, baseline: str | None = None
) -> list[GapRow]:
    """无任何 full/partial 映射的要求项。仅有 supporting 不消差距。"""
    items, strengths, requirements = await _load(session, framework_id, baseline)
    return [
        GapRow(
            item_id=item.id,
            code=item.code,
            title=item.title,
            has_supporting=MappingStrength.SUPPORTING.value in strengths.get(item.id, set()),
        )
        for item in items
        if item.id in requirements and not _closed(strengths, item.id)
    ]
