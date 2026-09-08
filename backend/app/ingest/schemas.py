from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.ingest.models import DocStatus, DocType


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    doc_type: DocType
    status: DocStatus
    version: str | None
    owner: str | None
    approver: str | None
    approved_date: date | None
    effective_date: date | None
    review_due_date: date | None
    original_filename: str
    parse_error: str | None
    parse_warnings: str | None
    ocr_quality_flag: bool
    supersedes_id: int | None
    created_at: datetime


class PlainTextIn(BaseModel):
    text: str = Field(min_length=1)
