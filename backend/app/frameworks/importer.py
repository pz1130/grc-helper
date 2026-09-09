"""确定性导入：无 AI，因此不进确认队列，凭 FRAMEWORK_WRITE 直接落库。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.frameworks.models import Framework, FrameworkItem
from app.frameworks.template import parse_rows
from app.iam.audit import record
from app.iam.models import User
from app.matrix.template import Sheet, read_sheet


class FrameworkImportError(AppError):
    code = "framework_import_error"


def read_template(content: bytes) -> tuple[list[str], list[list[str]]]:
    """复用 M4 的加固 XLSX 解析（拒 DTD/公式/超限）。"""
    sheet: Sheet = read_sheet(content)
    return sheet.headers, sheet.rows


async def import_framework(
    session: AsyncSession,
    headers: list[str],
    rows: list[list[str]],
    *,
    key: str,
    name_zh: str,
    name_en: str,
    version: str,
    source: str,
    actor: User,
) -> Framework:
    """事务性导入。调用方负责权限与提交；校验不过一行都不写。"""
    parsed, report = parse_rows(headers, rows)
    if report:
        raise FrameworkImportError("；".join(report[:20]))

    existing = await session.scalar(select(Framework).where(Framework.key == key))
    if existing is not None:
        raise FrameworkImportError(f"框架标识「{key}」已存在；重新导入请使用新的 key")

    framework = Framework(
        key=key,
        name_zh=name_zh,
        name_en=name_en,
        version=version,
        source=source,
        item_count=len(parsed),
        imported_by=actor.id,
    )
    session.add(framework)
    await session.flush()

    # 两遍：先建全部节点拿到 id，再回填 parent_id。模板行序不保证父先于子。
    by_code: dict[str, FrameworkItem] = {}
    for row in parsed:
        item = FrameworkItem(
            framework_id=framework.id,
            code=row.code,
            title=row.title,
            description=row.description,
            level=row.level,
            order_index=row.order_index,
            attributes=row.attributes,
        )
        session.add(item)
        by_code[row.code] = item
    await session.flush()

    for row in parsed:
        if row.parent_code:
            by_code[row.code].parent_id = by_code[row.parent_code].id
    await session.flush()

    after: dict[str, Any] = {
        "key": key,
        "version": version,
        "item_count": len(parsed),
        "source": source,
    }
    await record(
        session,
        user=actor,
        action="framework.import",
        entity_type="Framework",
        entity_id=framework.id,
        after=after,
    )
    await session.flush()
    return framework
