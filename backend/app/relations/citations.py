"""关系提案的闸 3 与闸 4。

两个控制点都是库中既有数据，没有内容可编造；闸 4 在这里防的是判断错——
要求从两端各自的 statement 里逐字引出支撑这条关系的词句。只引一端
等于没说清楚这两者之间到底是什么关系。
"""

import math
from collections.abc import Collection
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls.models import Control
from app.llm.validation import normalize

_ENDS = (("from_control_id", "from_quote"), ("to_control_id", "to_quote"))


class RelationCitationValidator:
    def __init__(
        self,
        session: AsyncSession,
        *,
        control_ids: Collection[int],
        item_key: str = "relations",
    ) -> None:
        self._session = session
        self._control_ids = frozenset(control_ids)
        self._item_key = item_key

    async def check(self, payload: dict[str, Any]) -> str | None:
        items = payload.get(self._item_key)
        if not isinstance(items, list):
            return f"{self._item_key} must be a list"
        if not items:
            return None if payload.get("insufficient_evidence") is True else "没有给出任何关系"
        if payload.get("insufficient_evidence") is True:
            return "insufficient_evidence 不能与关系并存"

        for entry in items:
            if not isinstance(entry, dict):
                return "关系格式无效"
            for id_field, quote_field in _ENDS:
                control_id = entry.get(id_field)
                if type(control_id) is not int or control_id <= 0:
                    return f"无效的 {id_field}: {control_id!r}"
                if control_id not in self._control_ids:
                    return f"控制点 {control_id} 不属于本批次"
                quote = entry.get(quote_field)
                if not isinstance(quote, str) or not normalize(quote):
                    return f"控制点 {control_id} 一侧没有给出引文"
            if entry["from_control_id"] == entry["to_control_id"]:
                return "关系的两端不能是同一个控制点"
            confidence = entry.get("confidence")
            if (
                type(confidence) not in (int, float)
                or isinstance(confidence, bool)
                or not math.isfinite(confidence)
                or not 0 <= confidence <= 1
            ):
                return f"无效的 confidence: {confidence!r}"

        wanted = {entry[field] for entry in items for field, _ in _ENDS}
        statements = {
            row.id: row.statement or ""
            for row in await self._session.scalars(
                select(Control).where(Control.id.in_(wanted))
            )
        }
        for entry in items:
            for id_field, quote_field in _ENDS:
                control_id = entry[id_field]
                if control_id not in statements:
                    return f"控制点 {control_id} 在库中不存在"
                if normalize(entry[quote_field]) not in normalize(statements[control_id]):
                    return f"引文在控制点 {control_id} 的正文中找不到"
        return None
