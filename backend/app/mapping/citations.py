"""映射提案的闸 3 与闸 4。"""

from collections.abc import Collection
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls.models import Control
from app.frameworks.models import FrameworkItem, MappingStrength
from app.llm.validation import normalize

_STRENGTHS = {strength.value for strength in MappingStrength}


class MappingCitationValidator:
    def __init__(
        self,
        session: AsyncSession,
        *,
        item_ids: Collection[int],
        item_key: str = "mappings",
    ) -> None:
        self._session = session
        self._item_ids = frozenset(item_ids)
        self._item_key = item_key

    async def check(self, payload: dict[str, Any]) -> str | None:
        items = payload.get(self._item_key)
        if not isinstance(items, list):
            return f"{self._item_key} must be a list"
        if not items:
            return None if payload.get("insufficient_evidence") is True else "没有给出任何映射"
        if payload.get("insufficient_evidence") is True:
            return "insufficient_evidence 不能与映射并存"

        for entry in items:
            if not isinstance(entry, dict):
                return "映射格式无效"
            item_id, control_id = entry.get("framework_item_id"), entry.get("control_id")
            if type(item_id) is not int or item_id <= 0:
                return f"无效的 framework_item_id: {item_id!r}"
            if type(control_id) is not int or control_id <= 0:
                return f"无效的 control_id: {control_id!r}"
            if item_id not in self._item_ids:
                return f"框架项 {item_id} 不属于本批次"
            if entry.get("strength") not in _STRENGTHS:
                return f"无效的 strength: {entry.get('strength')!r}"
            quote = entry.get("quote")
            if not isinstance(quote, str) or not normalize(quote):
                return f"框架项 {item_id} 的映射没有给出引文"

        wanted_items = {entry["framework_item_id"] for entry in items}
        wanted_controls = {entry["control_id"] for entry in items}
        descriptions = {
            row.id: row.description or ""
            for row in await self._session.scalars(
                select(FrameworkItem).where(FrameworkItem.id.in_(wanted_items))
            )
        }
        known_controls = {
            row.id
            for row in await self._session.scalars(
                select(Control).where(Control.id.in_(wanted_controls))
            )
        }

        for entry in items:
            item_id, control_id = entry["framework_item_id"], entry["control_id"]
            if item_id not in descriptions:
                return f"框架项 {item_id} 在库中不存在"
            if control_id not in known_controls:
                return f"控制点 {control_id} 在库中不存在"
            if normalize(entry["quote"]) not in normalize(descriptions[item_id]):
                return f"引文在框架项 {item_id} 的正文中找不到"
        return None
