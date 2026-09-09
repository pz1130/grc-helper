"""The sole module that materializes reviewed controls and applies human edits."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.controls.models import Control, ControlSource, SourceRelation
from app.errors import AppError, Conflict, NotFound
from app.frameworks.models import FrameworkItem, Mapping, MappingStrength
from app.iam.models import AuditLog, User
from app.review.models import Proposal, ProposalKind, ProposalStatus

TextValue = Annotated[str, Field(strict=True, min_length=1)]
_PROVENANCE = ("origin", "matrix_mapping_proposal_id", "source_sha256", "row_number")


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    clause_id: Annotated[int, Field(strict=True, gt=0)]
    quote: TextValue
    relation: SourceRelation = SourceRelation.DEFINES


class ControlPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: Annotated[str, Field(strict=True, min_length=1, max_length=500)]
    statement: TextValue
    category: Annotated[str, Field(strict=True, max_length=100)] | None = None
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None = None
    citations: list[Citation]


class MatrixControlPayload(ControlPayload):
    code: Annotated[str, Field(strict=True, max_length=64)] | None = None
    owner: str | None = None
    framework_refs: str | None = None
    note: str | None = None
    origin: str
    matrix_mapping_proposal_id: Annotated[int, Field(strict=True, gt=0)]
    source_sha256: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
    row_number: Annotated[int, Field(strict=True, ge=1)]


class MappingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    framework_item_id: Annotated[int, Field(strict=True, gt=0)]
    control_id: Annotated[int, Field(strict=True, gt=0)]
    strength: MappingStrength
    quote: TextValue
    rationale: Annotated[str, Field(strict=True, min_length=1, max_length=2000)]
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None = None


async def _materialize_mapping(
    session: AsyncSession, proposal: Proposal, data: dict[str, Any], *, actor_id: int
) -> None:
    from app.mapping.citations import MappingCitationValidator

    try:
        validated = MappingPayload.model_validate(data)
    except ValidationError as exc:
        raise AppError(f"映射内容无效：{exc}") from exc

    item = await session.get(FrameworkItem, validated.framework_item_id)
    if item is None:
        raise AppError("框架项不存在")
    reason = await MappingCitationValidator(
        session, item_ids={validated.framework_item_id}
    ).check({"mappings": [data]})
    if reason:
        raise AppError(f"引用校验失败：{reason}")

    await lock_control_writes(session)
    existing = await session.scalar(
        select(Mapping).where(
            Mapping.control_id == validated.control_id,
            Mapping.framework_item_id == validated.framework_item_id,
        )
    )
    if existing is not None:
        raise Conflict("该控制点与框架项之间已有确认过的映射")

    session.add(Mapping(
        control_id=validated.control_id,
        framework_item_id=validated.framework_item_id,
        strength=validated.strength,
        rationale=validated.rationale,
        quote=validated.quote,
        confidence=proposal.confidence,
        proposed_by_llm_call_id=proposal.llm_call_id,
        confirmed_by=actor_id,
        confirmed_at=datetime.now(UTC),
    ))
    await session.flush()


async def lock_control_writes(session: AsyncSession) -> None:
    # Serialize deduplication/code allocation, including human edits, across processes.
    # A transaction advisory lock survives the helper and is released by commit/rollback.
    await session.execute(text("SELECT pg_advisory_xact_lock(734004, 1)"))


def _normalise_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


async def _matrix_origin(session: AsyncSession, proposal: Proposal, data: dict[str, Any]) -> bool:
    original = proposal.payload
    if original.get("origin") != "matrix":
        if any(key in data for key in _PROVENANCE):
            raise AppError("不能将普通抽取改为 Excel 来源")
        return False
    if any(data.get(key) != original.get(key) for key in _PROVENANCE):
        raise AppError("Excel 来源信息不可修改")
    mapping_id = original.get("matrix_mapping_proposal_id")
    if type(mapping_id) is not int:
        raise AppError("无效的列映射来源")
    mapping = await session.get(Proposal, mapping_id)
    if (
        mapping is None
        or mapping.kind != ProposalKind.MATRIX_MAPPING
        or mapping.status not in (ProposalStatus.ACCEPTED, ProposalStatus.MODIFIED)
        or mapping.payload.get("source_sha256") != original.get("source_sha256")
        or proposal.document_id is not None
        or proposal.llm_call_id is not None
    ):
        raise AppError("Excel 来源未经过确认")
    row_number = original.get("row_number")
    source_rows = mapping.payload.get("source_rows")
    if (
        type(row_number) is not int
        or type(source_rows) is not int
        or not 1 <= row_number <= source_rows
    ):
        raise AppError("Excel 行号无效")
    imported = await session.scalar(
        select(AuditLog)
        .where(
            AuditLog.action == "matrix.import",
            AuditLog.entity_type == "Proposal",
            AuditLog.entity_id == str(mapping_id),
        )
        .limit(1)
    )
    if imported is None or proposal.id not in (imported.after or {}).get("proposal_ids", []):
        raise AppError("缺少 Excel 导入记录")
    return True


async def materialize(
    session: AsyncSession, proposal: Proposal, data: dict[str, Any], *, actor_id: int
) -> None:
    if not isinstance(data, dict):
        raise AppError("提案内容必须是对象")
    if proposal.kind == ProposalKind.MATRIX_MAPPING:
        from app.matrix.importer import validate_mapping_proposal

        try:
            validate_mapping_proposal(proposal, data)
        except ValueError as exc:
            raise AppError(str(exc)) from exc
        for key in ("source_sha256", "source_headers", "source_rows"):
            data[key] = proposal.payload[key]
        return
    if proposal.kind == ProposalKind.MAPPING:
        await _materialize_mapping(session, proposal, data, actor_id=actor_id)
        return
    if proposal.kind != ProposalKind.CONTROL_EXTRACT:
        raise AppError(f"尚不支持确认 {proposal.kind.value} 提案")

    matrix = await _matrix_origin(session, proposal, data)
    try:
        validated = (MatrixControlPayload if matrix else ControlPayload).model_validate(data)
    except ValidationError as exc:
        raise AppError(f"控制点内容无效：{exc}") from exc
    if matrix:
        if validated.citations:
            raise AppError("Excel 行不得声明条款引用")
    else:
        from app.extraction.citations import ClauseCitationValidator

        if not validated.citations:
            raise AppError("控制点必须提供条款引用")
        reason = await ClauseCitationValidator(session, document_id=proposal.document_id).check(
            {"controls": [data]}
        )
        if reason:
            raise AppError(f"引用校验失败：{reason}")

    await lock_control_writes(session)
    controls = list(await session.scalars(select(Control).order_by(Control.id)))
    if matrix:
        control = next((c for c in controls if c.code == validated.code), None)
        if control is not None and (
            _normalise_title(control.title) != _normalise_title(validated.title)
            or control.statement != validated.statement
            or control.category != validated.category
        ):
            raise Conflict("已有控制点编号对应不同内容")
    else:
        control = next(
            (c for c in controls if _normalise_title(c.title) == _normalise_title(validated.title)),
            None,
        )
    if control is None:
        # max numeric suffix, rather than row count, handles deletions and imported codes.
        maximum = max(
            (int(c.code[2:]) for c in controls if re.fullmatch(r"C-\d+", c.code)),
            default=0,
        )
        control = Control(
            code=(validated.code if matrix else None) or f"C-{maximum + 1:04d}",
            title=validated.title,
            statement=validated.statement,
            category=validated.category,
        )
        session.add(control)
        await session.flush()

    existing = set(
        await session.scalars(
            select(ControlSource.clause_id).where(ControlSource.control_id == control.id)
        )
    )
    for citation in validated.citations:
        if citation.clause_id in existing:
            continue
        session.add(
            ControlSource(
                control_id=control.id,
                clause_id=citation.clause_id,
                relation=citation.relation,
                confidence=proposal.confidence,
                proposed_by_llm_call_id=proposal.llm_call_id,
                confirmed_by=actor_id,
                confirmed_at=datetime.now(UTC),
            )
        )
        existing.add(citation.clause_id)
    await session.flush()


async def update_control(
    session: AsyncSession, control_id: int, changes: dict[str, Any], *, actor: User
) -> Control:
    """Explicit human PATCH; audited, with all formal writes kept in this module."""
    from app.controls.schemas import ControlUpdateIn
    from app.iam.audit import record
    from app.iam.permissions import Permission
    from app.review.service import require_actor

    require_actor(actor, Permission.CONTROL_WRITE)
    try:
        changes = ControlUpdateIn.model_validate(changes).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise AppError(f"控制点修改无效：{exc}") from exc
    await lock_control_writes(session)
    control = await session.scalar(
        select(Control)
        .where(Control.id == control_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if control is None:
        raise NotFound("控制点不存在")
    if changes.get("owner_user_id") is not None:
        owner = await session.get(User, changes["owner_user_id"])
        if owner is None:
            raise AppError("负责人不存在")
    before = {field: getattr(control, field) for field in changes}
    for field, value in changes.items():
        setattr(control, field, value)
    await session.flush()
    await record(
        session,
        user=actor,
        action="control.update",
        entity_type="Control",
        entity_id=control.id,
        before=before,
        after={field: getattr(control, field) for field in changes},
    )
    await session.flush()
    return control
