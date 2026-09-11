from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.review.models import ProposalKind, ProposalStatus
from app.review.service import Decision, ReviewTier


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: ProposalKind
    payload: dict[str, Any]
    citations: list[Any]
    confidence: float | None
    document_id: int | None
    status: ProposalStatus
    decided_by: int | None
    decided_at: datetime | None
    decided_payload: dict[str, Any] | None
    reject_reason: str | None
    created_at: datetime
    bulk_acceptable: bool = False
    ocr_quality_flag: bool = False
    # 正文用了 must/shall，而被引原文里一个情态词都没有——结论强于出处。
    normative_drift: bool = False
    mapping_context: dict[str, Any] | None = None
    relation_context: dict[str, Any] | None = None
    review_tier: ReviewTier = ReviewTier.MANUAL
    review_reasons: list[str] = Field(default_factory=list)


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Decision
    payload: dict[str, Any] | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "DecideIn":
        if self.decision is Decision.MODIFY and not self.payload:
            raise ValueError("修改后接受必须给出改后的内容")
        if self.decision is Decision.REJECT and not (self.reason or "").strip():
            # 拒绝原因会回流用于改进 prompt，不能省
            raise ValueError("拒绝必须给出原因")
        if self.decision is not Decision.MODIFY and self.payload is not None:
            raise ValueError("仅修改后接受允许提供内容")
        if self.decision is not Decision.REJECT and self.reason is not None:
            raise ValueError("仅拒绝允许提供原因")
        return self


class BulkAcceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_ids(self) -> "BulkAcceptIn":
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("提案编号不能重复")
        return self


class AutoProcessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 200
