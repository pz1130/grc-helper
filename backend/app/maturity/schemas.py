from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.maturity.models import AssessmentStatus, ScoreSource


class AssessmentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    framework_id: Annotated[int, Field(strict=True, gt=0)]
    name: Annotated[str, Field(strict=True, min_length=1, max_length=300)]
    as_of_date: date


class AssessmentOut(AssessmentCreateIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: AssessmentStatus
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class ScoreUpsertIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    framework_item_id: Annotated[int, Field(strict=True, gt=0)]
    doc_score: Annotated[int, Field(strict=True, ge=0, le=4)]
    impl_score: Annotated[int, Field(strict=True, ge=0, le=4)]
    doc_rationale: str = ""
    impl_rationale: str = ""


class ScoreOut(ScoreUpsertIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assessment_id: int
    doc_score_source: ScoreSource
    impl_score_source: ScoreSource
    scored_by: int | None
    scored_at: datetime
