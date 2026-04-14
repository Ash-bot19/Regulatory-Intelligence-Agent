from datetime import date
from uuid import UUID
from pydantic import BaseModel


class CitationRecord(BaseModel):
    circular_id: str
    circular_title: str
    effective_date: date
    clause_ref: str
    chunk_index: int


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationRecord]
    confidence_score: float
    query_id: UUID


class GateFiredResponse(BaseModel):
    answer: str = (
        "Insufficient regulatory basis found in indexed circulars. "
        "Please consult your compliance team or refer directly to RBI circulars at rbi.org.in."
    )
    citations: list[CitationRecord] = []
    confidence_score: float
    query_id: UUID
    gate_fired: bool = True
    suggestions: list[str] = []
