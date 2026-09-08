"""条款树到 Clause 行，并生成可审计的引用锚点。"""

from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.parsing.contract import ClauseNode

PATH_SEPARATOR = " › "


def build_citation_label(number: str | None, heading_path: str) -> str:
    return number if number else heading_path


def flatten(
    nodes: list[ClauseNode], *, document_id: int, language: str = "en"
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def walk(node: ClauseNode, ancestors: list[str], parent_key: int | None) -> None:
        path = [*ancestors, node.heading]
        heading_path = PATH_SEPARATOR.join(path)
        key = len(rows)
        rows.append(
            {
                "_parent_key": parent_key,
                "document_id": document_id,
                "number": node.number,
                "heading": node.heading,
                "heading_path": heading_path,
                "citation_label": build_citation_label(node.number, heading_path),
                "text": node.text,
                "order_index": key,
                "level": node.level,
                "page_ref": node.page_ref,
                "kind": node.kind,
                "language": language,
            }
        )
        for child in node.children:
            walk(child, path, key)

    for root in nodes:
        walk(root, [], None)
    return rows


async def persist(
    session: AsyncSession,
    nodes: list[ClauseNode],
    *,
    document_id: int,
    language: str = "en",
) -> int:
    await session.execute(delete(Clause).where(Clause.document_id == document_id))

    rows = flatten(nodes, document_id=document_id, language=language)
    id_by_key: dict[int, int] = {}
    for key, row in enumerate(rows):
        parent_key = row.pop("_parent_key")
        clause = Clause(
            **row,
            parent_id=id_by_key[parent_key] if parent_key is not None else None,
        )
        session.add(clause)
        await session.flush()
        id_by_key[key] = clause.id

    return len(rows)
