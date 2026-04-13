from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class AuditRecord(BaseModel):
    query_id: UUID
    query_text: str
    retrieved_chunk_ids: list[str]
    confidence_score: float
    llm_response: str | None
    citations: list[dict] | None
    gate_fired: bool
    created_at: datetime
