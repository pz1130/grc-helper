from pydantic import BaseModel


class PreviousDocumentOut(BaseModel):
    id: int
    title: str
    version: str | None


class ClauseChangeOut(BaseModel):
    clause_id: int
    citation_label: str
    text: str


class MatchedClauseOut(BaseModel):
    old_clause_id: int
    new_clause_id: int
    citation_label: str
    text: str


class AffectedControlOut(BaseModel):
    id: int
    code: str
    title: str


class AffectedMappingOut(BaseModel):
    id: int
    control_id: int
    framework_item_code: str


class AffectedEvidenceOut(BaseModel):
    id: int
    control_id: int
    title: str


class ImpactOut(BaseModel):
    previous_document: PreviousDocumentOut
    added: list[ClauseChangeOut]
    removed: list[ClauseChangeOut]
    matched: list[MatchedClauseOut]
    affected_controls: list[AffectedControlOut]
    affected_mappings: list[AffectedMappingOut]
    affected_evidence: list[AffectedEvidenceOut]
