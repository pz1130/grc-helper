from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.controls.models import RelationType, SourceRelation


class ControlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    title: str
    statement: str
    category: str | None
    owner_user_id: int | None
    status: str
    created_at: datetime


class SourceOut(BaseModel):
    clause_id: int
    document_id: int
    document_title: str
    citation_label: str
    heading_path: str
    relation: SourceRelation


class RelationOut(BaseModel):
    from_control_id: int
    to_control_id: int
    relation_type: RelationType
    rationale: str


class ControlDetailOut(ControlOut):
    sources: list[SourceOut]
    relations: list[RelationOut]


class ControlUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Annotated[str, Field(strict=True, min_length=1, max_length=500)] | None = None
    statement: Annotated[str, Field(strict=True, min_length=1)] | None = None
    category: Annotated[str, Field(strict=True, max_length=100)] | None = None
    owner_user_id: Annotated[int, Field(strict=True, gt=0)] | None = None

    @model_validator(mode="after")
    def valid_patch(self) -> "ControlUpdateIn":
        if not self.model_fields_set:
            raise ValueError("必须提供修改字段")
        for field in ("title", "statement"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} 不能为空")
        return self
