from datetime import date, datetime
from pydantic import BaseModel, field_validator


class ChunkMetadata(BaseModel):
    source: str = "RBI"
    circular_id: str
    circular_title: str
    effective_date: date
    clause_ref: str
    chunk_index: int
    scraped_at: datetime

    @field_validator("circular_id")
    @classmethod
    def validate_circular_id(cls, v: str) -> str:
        if not v.startswith("RBI/"):
            raise ValueError(f"circular_id must start with 'RBI/', got: {v}")
        return v


class RawCircularMetadata(BaseModel):
    """Metadata extracted from the RBI listing page before PDF parsing."""
    circular_id: str
    circular_title: str
    effective_date: date
    pdf_url: str
    scraped_at: datetime
