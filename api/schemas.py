"""FastAPI request/response schemas for the query endpoint."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=2000, description="Regulatory question")
