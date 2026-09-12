"""The sole module that materializes reviewed controls and applies human edits."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.controls.merge import MergePlan
from app.controls.models import (
    Control,
    ControlRelation,
    ControlSource,
    RelationType,
    SourceRelation,
    active_controls,
)
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
    framework_item_quote: TextValue
    rationale: Annotated[str, Field(strict=True, min_length=1, max_length=2000)]
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None = None


# M6 只推断这两种：conflicts_with 属 M10 的冲突检测，implements/refines 语义
# 相邻、模型容易混，人工抽查也难给出一致标准。
_M6_RELATIONS = (RelationType.DUPLICATES, RelationType.DEPENDS_ON)


class RelationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    from_control_id: Annotated[int, Field(strict=True, gt=0)]
    to_control_id: Annotated[int, Field(strict=True, gt=0)]
    relation_type: RelationType
    from_quote: TextValue
    to_quote: TextValue
    rationale: Annotated[str, Field(strict=True, min_length=1, max_length=2000)]
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None = None


async def _materialize_relation(
    session: AsyncSession, proposal: Proposal, data: dict[str, Any], *, actor_id: int | None
) -> None:
    from app.relations.citations import RelationCitationValidator

    try:
        validated = RelationPayload.model_validate(data)
    except ValidationError as exc:
        raise AppError(f"关系内容无效：{exc}") from exc
    if validated.relation_type not in _M6_RELATIONS:
        raise AppError(f"本里程碑不支持关系类型 {validated.relation_type.value}")
    if validated.from_control_id == validated.to_control_id:
        raise AppError("关系的两端不能是同一个控制点")

    ends = {validated.from_control_id, validated.to_control_id}
    reason = await RelationCitationValidator(session, control_ids=ends).check(
        {"relations": [data]}
    )
    if reason:
        raise AppError(f"引用校验失败：{reason}")

    start, end = validated.from_control_id, validated.to_control_id
    # duplicates 对称：不规范化就会存下 A→B 与 B→A 两条互为镜像的记录，
    # (from, to, relation_type) 的唯一约束对它们无能为力。
    if validated.relation_type is RelationType.DUPLICATES and start > end:
        start, end = end, start

    await lock_control_writes(session)
    existing = await session.scalar(
        select(ControlRelation).where(
            ControlRelation.from_control_id == start,
            ControlRelation.to_control_id == end,
            ControlRelation.relation_type == validated.relation_type,
        )
    )
    if existing is not None:
        raise Conflict("这两个控制点之间已有同类型的确认关系")

    session.add(ControlRelation(
        from_control_id=start,
        to_control_id=end,
        relation_type=validated.relation_type,
        rationale=validated.rationale,
        confidence=proposal.confidence,
        confirmed_by=actor_id,
        confirmed_at=datetime.now(UTC),
    ))
    await session.flush()


async def _materialize_conflict(
    session: AsyncSession, proposal: Proposal, data: dict[str, Any], *, actor_id: int | None
) -> None:
    from app.conflicts.citations import ConflictCitationValidator
    from app.conflicts.models import PolicyConflict, normalise_pair
    from app.conflicts.schemas import ConflictPayload

    try:
        validated = ConflictPayload.model_validate(data)
    except ValidationError as exc:
        raise AppError(f"冲突内容无效：{exc}") from exc
    if validated.clause_a_id == validated.clause_b_id:
        raise AppError("冲突的两端不能是同一条条款")

    ends = {validated.clause_a_id, validated.clause_b_id}
    reason = await ConflictCitationValidator(session, clause_ids=ends).check(
        {"conflicts": [data]}
    )
    if reason:
        raise AppError(f"引用校验失败：{reason}")

    # 冲突无方向：不规范化就会存下互为镜像的两行，唯一约束对它们无能为力。
    low, high = normalise_pair(validated.clause_a_id, validated.clause_b_id)
    topic = validated.topic.strip()

    existing = await session.scalar(
        select(PolicyConflict).where(
            PolicyConflict.clause_a_id == low,
            PolicyConflict.clause_b_id == high,
            PolicyConflict.topic == topic,
        )
    )
    if existing is not None:
        # 同一处冲突被两条提案各确认一次是正常的（两个批次都报了），不当错误。
        return

    session.add(
        PolicyConflict(
            clause_a_id=low,
            clause_b_id=high,
            topic=topic,
            difference=validated.difference,
            confidence=validated.confidence,
            confirmed_by=actor_id,
            confirmed_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def _materialize_mapping(
    session: AsyncSession, proposal: Proposal, data: dict[str, Any], *, actor_id: int | None
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
        quote=validated.framework_item_quote,
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


def normalise_statement(statement: str) -> str:
    """判重用的正文归一化：折叠空白 + 转小写。

    用 `lower()` 而不是 `casefold()`，是为了和 `sql_normalised_statement()` 逐字对齐——
    过滤在 SQL 里做、比对在 Python 里做，两边规则一旦分叉，后果是**静默的**：
    队列该标的没标，页面看起来一切正常。tests/test_review_duplicates.py 守着这一致性。
    """
    return " ".join((statement or "").split()).lower()


def sql_normalised_statement() -> ColumnElement[str]:
    """`normalise_statement` 的 SQL 版本，用来把比对压进一次查询。"""
    return func.lower(func.btrim(func.regexp_replace(Control.statement, r"\s+", " ", "g")))


async def find_statement_duplicate(session: AsyncSession, statement: str) -> Control | None:
    """返回正文与之逐字相同的**已生效**控制点。

    这是个**可证的事实**，不是判断——所以摆给审核者看，而不是替他们并掉。
    """
    normalised = normalise_statement(statement)
    if not normalised:
        return None
    return await session.scalar(
        select(Control)
        .where(sql_normalised_statement() == normalised, Control.status == "active")
        .order_by(Control.id)
        .limit(1)
    )


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
    session: AsyncSession,
    proposal: Proposal,
    data: dict[str, Any],
    *,
    actor_id: int | None,
    merge_into_control_id: int | None = None,
) -> None:
    if not isinstance(data, dict):
        raise AppError("提案内容必须是对象")
    if merge_into_control_id is not None and proposal.kind != ProposalKind.CONTROL_EXTRACT:
        raise AppError("只有控制点提案可以并入已有控制点")
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
    if proposal.kind == ProposalKind.RELATION:
        await _materialize_relation(session, proposal, data, actor_id=actor_id)
        return
    if proposal.kind == ProposalKind.CONFLICT:
        await _materialize_conflict(session, proposal, data, actor_id=actor_id)
        return
    if proposal.kind == ProposalKind.ANSWER:
        from app.audit.citations import AnswerCitationValidator
        from app.audit.models import AnswerDraft, AuditQuestion, QuestionStatus
        from app.audit.schemas import AnswerProposalPayload
        from app.clauses.models import Clause
        from app.evidence.models import EvidenceItem

        try:
            validated = AnswerProposalPayload.model_validate(data)
        except ValidationError as exc:
            raise AppError(f"审计答复内容无效：{exc}") from exc
        question = await session.get(AuditQuestion, validated.question_id)
        if question is None:
            raise NotFound("审计问题不存在")
        if await session.scalar(
            select(AnswerDraft.id).where(AnswerDraft.question_id == question.id)
        ) is not None:
            raise Conflict("该问题已有答复草稿")
        clause_ids = {citation.clause_id for citation in validated.citations}
        known_clauses = set(
            await session.scalars(select(Clause.id).where(Clause.id.in_(clause_ids)))
        )
        known_controls = set(
            await session.scalars(
                select(Control.id).where(Control.id.in_(validated.cited_control_ids))
            )
        )
        known_evidence = set(
            await session.scalars(
                select(EvidenceItem.id).where(
                    EvidenceItem.id.in_(validated.suggested_evidence_ids)
                )
            )
        )
        if clause_ids != known_clauses:
            raise AppError("答复引用了不存在的条款")
        if set(validated.cited_control_ids) != known_controls:
            raise AppError("答复引用了不存在的控制点")
        if set(validated.suggested_evidence_ids) != known_evidence:
            raise AppError("答复引用了不存在的证据")
        reason = await AnswerCitationValidator(
            session,
            allowed_clause_ids=clause_ids,
            allowed_control_ids=known_controls,
            allowed_evidence_ids=known_evidence,
        ).check(data)
        if reason:
            raise AppError(f"引用校验失败：{reason}")
        session.add(AnswerDraft(
            question_id=question.id,
            body=validated.body,
            language=validated.language,
            cited_clause_ids=sorted(clause_ids),
            cited_control_ids=validated.cited_control_ids,
            suggested_evidence_ids=validated.suggested_evidence_ids,
            gap_notes=validated.gap_notes,
            confidence=proposal.confidence,
            generated_by_llm_call_id=proposal.llm_call_id,
            reviewed_by=actor_id,
        ))
        question.status = QuestionStatus.DRAFTED
        await session.flush()
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
    if merge_into_control_id is not None:
        if matrix:
            raise AppError("Excel 导入的控制点不走合并")
        await _merge_into(
            session, merge_into_control_id, validated, proposal, actor_id=actor_id
        )
        return

    # 判重只看生效行：命中已合并的会把新提案挂到一条死控制点上。
    live = list(await session.scalars(active_controls().order_by(Control.id)))
    if matrix:
        control = next((c for c in live if c.code == validated.code), None)
        if control is not None and (
            _normalise_title(control.title) != _normalise_title(validated.title)
            or control.statement != validated.statement
            or control.category != validated.category
        ):
            raise Conflict("已有控制点编号对应不同内容")
    else:
        control = next(
            (c for c in live if _normalise_title(c.title) == _normalise_title(validated.title)),
            None,
        )
    if control is None:
        # 编号分配看全部行，含已合并的——否则 C-0002 会被发第二次。
        allocated = list(await session.scalars(select(Control).order_by(Control.id)))
        maximum = max(
            (int(c.code[2:]) for c in allocated if re.fullmatch(r"C-\d+", c.code)),
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

    await _attach_sources(session, control, validated, proposal, actor_id=actor_id)


async def _attach_sources(
    session: AsyncSession,
    control: Control,
    validated: Any,
    proposal: Proposal,
    *,
    actor_id: int | None,
) -> None:
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


async def _merge_into(
    session: AsyncSession,
    control_id: int,
    validated: Any,
    proposal: Proposal,
    *,
    actor_id: int | None,
) -> None:
    """审核者选择「并入已有控制点」：只把引用挂过去，不改那条控制点的正文。

    队列可能是几分钟前渲染的，那条控制点这期间可能已被人编辑过——所以这里
    **再验一次正文相同**，而不是信前端送来的 id。赢家保留自己的标题与正文，
    与既有的「标题相同则并入」一条路走法一致。
    """
    control = await session.get(Control, control_id)
    if control is None:
        raise NotFound("要并入的控制点不存在")
    if control.status != "active":
        raise AppError("要并入的控制点已不再生效")
    if normalise_statement(control.statement) != normalise_statement(validated.statement):
        raise AppError(f"{control.code} 的正文已与本提案不同，无法并入；请刷新确认队列")
    await _attach_sources(session, control, validated, proposal, actor_id=actor_id)


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


async def merge_controls(
    session: AsyncSession, *, loser_id: int, winner_id: int, actor: User
) -> MergePlan:
    """把输家的关联转挂到赢家；输家留行，只改标记。不改赢家的标题/正文/分类/负责人。"""
    from dataclasses import asdict

    from app.controls.merge import plan_merge
    from app.environment.models import Implementation
    from app.evidence.models import EvidenceItem
    from app.iam.audit import record
    from app.iam.permissions import Permission
    from app.relations.models import ControlEmbedding
    from app.review.service import require_actor
    from app.risk.models import RiskEntry

    require_actor(actor, Permission.CONTROL_WRITE)
    await lock_control_writes(session)
    # 预览与执行之间库可能已经变了，必须重算，不信客户端送来的计划。
    plan = await plan_merge(session, loser_id=loser_id, winner_id=winner_id)
    if plan.blockers:
        raise AppError("；".join(plan.blockers))

    loser = await session.get(Control, loser_id)
    winner = await session.get(Control, winner_id)
    if loser is None or winner is None:
        raise AppError("控制点不存在")

    before = {
        "code": loser.code,
        "title": loser.title,
        "statement": loser.statement,
        "status": loser.status,
    }

    discard_models = {
        "control_embeddings": ControlEmbedding,
        "control_relations": ControlRelation,
        "control_sources": ControlSource,
        "evidence_items": EvidenceItem,
        "implementations": Implementation,
        "mappings": Mapping,
        "risk_entries": RiskEntry,
    }
    # 先删重复行再转挂，否则 mappings / control_sources 等唯一约束会先炸。
    for discarded in plan.discards:
        row = await session.get(discard_models[discarded.table], discarded.id)
        if row is not None:
            await session.delete(row)
    await session.flush()

    for model in (
        ControlEmbedding,
        ControlSource,
        EvidenceItem,
        Implementation,
        Mapping,
        RiskEntry,
    ):
        for row in list(await session.scalars(select(model).where(model.control_id == loser.id))):
            row.control_id = winner.id

    for row in list(
        await session.scalars(
            select(ControlRelation).where(
                or_(
                    ControlRelation.from_control_id == loser.id,
                    ControlRelation.to_control_id == loser.id,
                )
            )
        )
    ):
        if row.from_control_id == loser.id:
            row.from_control_id = winner.id
        if row.to_control_id == loser.id:
            row.to_control_id = winner.id

    loser.status = "merged"
    loser.merged_into_id = winner.id

    await record(
        session,
        user=actor,
        action="control.merge",
        entity_type="Control",
        entity_id=loser.id,
        before=before,
        after={
            "merged_into": winner.code,
            "moves": plan.moves,
            "discards": [asdict(item) for item in plan.discards],
        },
    )
    await session.flush()
    return plan
