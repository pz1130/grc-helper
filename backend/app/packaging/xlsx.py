"""Excel members of the audit readiness package."""

import io
from typing import Any

from openpyxl import Workbook

MAPPING_HEADERS = [
    "控制点代码",
    "控制点标题",
    "框架项代码",
    "框架项标题",
    "强度",
    "置信度",
    "理由",
]
EVIDENCE_HEADERS = ["控制点代码", "证据标题", "类型", "负责人", "采集日期", "新鲜度"]


def _save(headers: list[str], rows: list[list[Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _evidence_values(row: Any) -> list[Any]:
    if isinstance(row, (list, tuple)):
        return list(row)
    collected = row.last_collected_at
    owner_id = row.owner_user_id
    return [
        row.control_code or "",
        row.title,
        row.evidence_type_name or "",
        "" if owner_id is None else str(owner_id),
        collected.date().isoformat() if collected else "",
        row.display_status,
    ]


def build_mappings_xlsx(rows) -> bytes:
    return _save(MAPPING_HEADERS, [list(row) for row in rows])


def build_evidence_xlsx(rows) -> bytes:
    return _save(EVIDENCE_HEADERS, [_evidence_values(row) for row in rows])
