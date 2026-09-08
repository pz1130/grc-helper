"""Confirmed mappings produce pending proposals, never formal controls."""

import hashlib
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Conflict, NotFound
from app.iam.models import AuditLog, User
from app.matrix.template import MAX_COLUMNS, MAX_ROWS, Sheet, validate
from app.review.models import Proposal, ProposalKind, ProposalStatus

_SOURCE_KEYS = ("source_sha256", "source_headers", "source_rows")


def validate_mapping_proposal(proposal: Proposal, data: dict[str, Any]) -> dict[str, str]:
    """Review hook: verify mapping structure and immutable original upload binding.

    Full row validation happens on re-upload before any import writes. A reviewer
    may provide only mapping/notes, or echo the unchanged source metadata.
    """
    if proposal.kind != ProposalKind.MATRIX_MAPPING:
        raise ValueError("不是 Excel 列映射提案")
    original = proposal.payload
    if not isinstance(original, dict) or not isinstance(data, dict):
        raise ValueError("映射提案内容无效")  # noqa: TRY004 -- domain validation, not caller typing
    digest = original.get("source_sha256")
    headers = original.get("source_headers")
    count = original.get("source_rows")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("映射缺少原始文件摘要，请重新上传")
    if (not isinstance(headers, list) or not 1 <= len(headers) <= MAX_COLUMNS
            or not all(isinstance(h, str) and h for h in headers)
            or len(set(headers)) != len(headers)):
        raise ValueError("映射原始表头无效")
    if type(count) is not int or not 1 <= count <= MAX_ROWS:
        raise ValueError("映射原始行数无效")
    for key in _SOURCE_KEYS:
        if key in data and data[key] != original[key]:
            raise ValueError(f"不能修改原始文件绑定 {key}")
    if set(data) - {"mapping", "notes", "confidence", *_SOURCE_KEYS}:
        raise ValueError("映射包含不支持的字段")
    mapping = data.get("mapping")
    # A placeholder row exercises mapping shape without re-reading source data.
    report = validate(Sheet(headers, [["sample"] * len(headers)]), mapping)
    if report:
        raise ValueError("；".join(report))
    return dict(mapping)


async def import_rows(
    session: AsyncSession, sheet: Sheet, mapping: dict[str, str], *, actor_id: int,
    mapping_proposal_id: int, source_sha256: str,
) -> dict[str, Any]:
    """Internal deterministic conversion; caller owns authorization and transaction."""
    report = validate(sheet, mapping)
    if report:
        raise ValueError("；".join(report))
    index = {field: sheet.headers.index(column) for field, column in mapping.items()}
    proposals: list[Proposal] = []
    for ordinal, row in enumerate(sheet.rows, start=1):
        payload = {
            field: row[position].strip() if position < len(row) else ""
            for field, position in index.items()
        }
        payload.update(
            origin="matrix", matrix_mapping_proposal_id=mapping_proposal_id,
            source_sha256=source_sha256, row_number=ordinal, citations=[],
        )
        proposal = Proposal(
            kind=ProposalKind.CONTROL_EXTRACT, status=ProposalStatus.PENDING,
            payload=payload, citations=[], confidence=None, llm_call_id=None,
        )
        session.add(proposal)
        proposals.append(proposal)
    await session.flush()
    result = {"imported": len(proposals), "proposal_ids": [p.id for p in proposals],
              "mapping_proposal_id": mapping_proposal_id}
    session.add(AuditLog(
        user_id=actor_id, action="matrix.import", entity_type="Proposal",
        entity_id=str(mapping_proposal_id), after=result,
    ))
    await session.flush()
    return result


async def import_confirmed(
    session: AsyncSession, sheet: Sheet, content: bytes, *, proposal_id: int,
    actor: User, mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    proposal = await session.scalar(
        select(Proposal).where(Proposal.id == proposal_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if proposal is None:
        raise NotFound("列映射提案不存在")
    if proposal.kind != ProposalKind.MATRIX_MAPPING or proposal.status not in {
        ProposalStatus.ACCEPTED, ProposalStatus.MODIFIED,
    }:
        raise Conflict("只能导入已确认的 Excel 列映射提案")
    data = (proposal.decided_payload if proposal.status == ProposalStatus.MODIFIED
            else proposal.payload)
    confirmed = validate_mapping_proposal(proposal, data)
    if mapping is not None and mapping != confirmed:
        raise Conflict("导入映射必须与已确认的映射完全一致")
    digest = hashlib.sha256(content).hexdigest()
    original = proposal.payload
    if (digest != original["source_sha256"] or sheet.headers != original["source_headers"]
            or len(sheet.rows) != original["source_rows"]):
        raise Conflict("上传文件与列映射提案的原始文件不一致")
    report = validate(sheet, confirmed)
    if report:
        raise ValueError("；".join(report))
    # Locking the parent serializes retries, and the audit commits atomically with
    # its child proposals. Preserve both original and decided payloads unchanged.
    previous = await session.scalar(select(AuditLog).where(
        AuditLog.action == "matrix.import", AuditLog.entity_type == "Proposal",
        AuditLog.entity_id == str(proposal.id),
    ).order_by(AuditLog.id).limit(1))
    if previous is not None:
        return dict(previous.after)
    return await import_rows(
        session, sheet, confirmed, actor_id=actor.id,
        mapping_proposal_id=proposal.id, source_sha256=digest,
    )
