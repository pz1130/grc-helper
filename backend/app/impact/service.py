"""变更影响分析——不用 AI，不写库（spec §1 决定④）。

条款配对只用 (number, heading_path) 精确匹配。用向量相似度做模糊配对会更
"聪明"，但影响报告的价值在于可核对：一条「这两条是同一条」的判断若来自
相似度，读报告的人没法验证它对不对。宁可列出"未配对"让人自己看。
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clauses.models import Clause
from app.controls.models import Control, ControlSource
from app.errors import BadRequest, NotFound
from app.evidence.models import EvidenceItem
from app.frameworks.models import FrameworkItem, Mapping
from app.impact.schemas import (
    AffectedControlOut,
    AffectedEvidenceOut,
    AffectedMappingOut,
    ClauseChangeOut,
    ImpactOut,
    MatchedClauseOut,
    PreviousDocumentOut,
)
from app.ingest.models import Document


@dataclass(frozen=True)
class ClausePairing:
    matched: list[tuple[int, int]]   # (旧条款 id, 新条款 id)
    removed: list[int]               # 只在旧版里
    added: list[int]                 # 只在新版里


def _key(clause: Any) -> tuple[str, str]:
    return ((clause.number or "").strip(), (clause.heading_path or "").strip())


def pair_clauses(old: list[Any], new: list[Any]) -> ClausePairing:
    """按 (number, heading_path) 配对；同键重复出现时按 id 升序一一对应。"""
    old_by_key: dict[tuple[str, str], list[Any]] = {}
    for clause in sorted(old, key=lambda c: c.id):
        old_by_key.setdefault(_key(clause), []).append(clause)
    new_by_key: dict[tuple[str, str], list[Any]] = {}
    for clause in sorted(new, key=lambda c: c.id):
        new_by_key.setdefault(_key(clause), []).append(clause)

    matched: list[tuple[int, int]] = []
    removed: list[int] = []
    added: list[int] = []

    for key in sorted(old_by_key.keys() | new_by_key.keys()):
        lefts = old_by_key.get(key, [])
        rights = new_by_key.get(key, [])
        paired = min(len(lefts), len(rights))
        matched.extend((lefts[i].id, rights[i].id) for i in range(paired))
        removed.extend(clause.id for clause in lefts[paired:])
        added.extend(clause.id for clause in rights[paired:])

    return ClausePairing(sorted(matched), sorted(removed), sorted(added))


def _clause_out(clause: Clause) -> ClauseChangeOut:
    return ClauseChangeOut(
        clause_id=clause.id,
        citation_label=clause.citation_label,
        text=clause.text,
    )


async def change_impact(session: AsyncSession, document_id: int) -> ImpactOut:
    document = await session.get(Document, document_id)
    if document is None:
        raise NotFound("文档不存在")
    if document.supersedes_id is None:
        raise BadRequest("该文档没有上一版本")

    previous = await session.get(Document, document.supersedes_id)
    if previous is None:
        raise NotFound("上一版本文档不存在")

    old_clauses = list(
        await session.scalars(
            select(Clause).where(Clause.document_id == previous.id).order_by(Clause.id)
        )
    )
    new_clauses = list(
        await session.scalars(
            select(Clause).where(Clause.document_id == document.id).order_by(Clause.id)
        )
    )
    pairing = pair_clauses(old_clauses, new_clauses)
    by_id = {clause.id: clause for clause in (*old_clauses, *new_clauses)}

    added = [_clause_out(by_id[clause_id]) for clause_id in pairing.added]
    removed = [_clause_out(by_id[clause_id]) for clause_id in pairing.removed]
    matched = [
        MatchedClauseOut(
            old_clause_id=old_id,
            new_clause_id=new_id,
            citation_label=by_id[new_id].citation_label,
            text=by_id[new_id].text,
        )
        for old_id, new_id in pairing.matched
    ]

    affected_controls: list[AffectedControlOut] = []
    affected_mappings: list[AffectedMappingOut] = []
    affected_evidence: list[AffectedEvidenceOut] = []
    if pairing.removed:
        controls = list(
            await session.scalars(
                select(Control)
                .where(
                    Control.id.in_(
                        select(ControlSource.control_id).where(
                            ControlSource.clause_id.in_(pairing.removed)
                        )
                    )
                )
                .order_by(Control.id)
            )
        )
        affected_controls = [
            AffectedControlOut(id=control.id, code=control.code, title=control.title)
            for control in controls
        ]
        codes = {control.id: control.code for control in controls}
        control_ids = list(codes)
        if control_ids:
            mapping_rows = await session.execute(
                select(Mapping, FrameworkItem)
                .join(FrameworkItem, FrameworkItem.id == Mapping.framework_item_id)
                .where(Mapping.control_id.in_(control_ids))
                .order_by(Mapping.id)
            )
            affected_mappings = [
                AffectedMappingOut(
                    id=mapping.id,
                    control_id=mapping.control_id,
                    control_code=codes[mapping.control_id],
                    framework_item_code=item.code,
                )
                for mapping, item in mapping_rows
            ]
            evidence_rows = list(
                await session.scalars(
                    select(EvidenceItem)
                    .where(EvidenceItem.control_id.in_(control_ids))
                    .order_by(EvidenceItem.id)
                )
            )
            affected_evidence = [
                AffectedEvidenceOut(
                    id=item.id,
                    control_id=item.control_id,
                    control_code=codes[item.control_id],
                    title=item.title,
                )
                for item in evidence_rows
            ]

    return ImpactOut(
        previous_document=PreviousDocumentOut(
            id=previous.id, title=previous.title, version=previous.version
        ),
        added=added,
        removed=removed,
        matched=matched,
        affected_controls=affected_controls,
        affected_mappings=affected_mappings,
        affected_evidence=affected_evidence,
    )
