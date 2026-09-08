from pydantic import BaseModel


class SearchHit(BaseModel):
    chunk_id: int
    clause_id: int
    document_id: int
    document_title: str
    citation_label: str
    heading_path: str
    text: str
    score: float
    rank_fulltext: int | None
    rank_vector: int | None


class SearchResponse(BaseModel):
    query: str
    expanded_terms: list[str]
    hits: list[SearchHit]
    vector_used: bool
