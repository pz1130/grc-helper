from pydantic import BaseModel, ConfigDict, Field


class ClauseTreeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str | None
    heading: str
    heading_path: str
    citation_label: str
    text: str
    level: int
    page_ref: int | None
    kind: str
    children: list["ClauseTreeOut"] = Field(default_factory=list)
