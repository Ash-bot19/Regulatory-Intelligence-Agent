"""
Citation mapper — derives citations from chunk metadata, never from LLM output.

Each retrieved Document carries metadata set at index time (ChunkMetadata fields).
This module extracts that metadata and deduplicates by (circular_id, clause_ref).
"""

from datetime import date

import structlog
from langchain_core.documents import Document

from models.response import CitationRecord

logger = structlog.get_logger(__name__)


def extract_citations(docs: list[Document]) -> list[CitationRecord]:
    """
    Build citation records from the metadata of retrieved chunks.

    Deduplicates by (circular_id, clause_ref) — same clause from multiple
    overlapping chunks only appears once.

    Returns an empty list if metadata is missing or malformed; the caller
    must reject and fire the fallback if citations come back empty.
    """
    seen: set[tuple[str, str]] = set()
    citations: list[CitationRecord] = []

    for doc in docs:
        meta = doc.metadata
        circular_id = meta.get("circular_id")
        clause_ref = meta.get("clause_ref", "")

        if not circular_id:
            logger.warning("citation_skipped_missing_id", metadata=meta)
            continue

        dedup_key = (circular_id, clause_ref)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # effective_date may be a date object or ISO string — normalise to date
        raw_date = meta.get("effective_date")
        if isinstance(raw_date, str):
            try:
                effective_date = date.fromisoformat(raw_date)
            except ValueError:
                logger.warning("citation_bad_date", circular_id=circular_id, raw=raw_date)
                effective_date = date(1900, 1, 1)
        elif isinstance(raw_date, date):
            effective_date = raw_date
        else:
            effective_date = date(1900, 1, 1)

        citations.append(
            CitationRecord(
                circular_id=circular_id,
                circular_title=meta.get("circular_title", ""),
                effective_date=effective_date,
                clause_ref=clause_ref,
                chunk_index=meta.get("chunk_index", 0),
            )
        )

    logger.info("citations_extracted", count=len(citations))
    return citations
