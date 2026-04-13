"""
Chunker: RecursiveCharacterTextSplitter with metadata propagation.

Every chunk must carry complete ChunkMetadata. Chunks from documents
with incomplete metadata are quarantined — never indexed.
"""

from datetime import datetime

import structlog
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

from models.chunk import ChunkMetadata, RawCircularMetadata
from scraper.pdf_extractor import ExtractedDocument

logger = structlog.get_logger(__name__)

CHUNK_SIZE = 500       # tokens (approximated as chars / 4 — tiktoken not required here)
CHUNK_OVERLAP = 50
SEPARATORS = ["\n\n", "\n", r"\d+\.", r"\(\w+\)"]


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE * 4,   # chars ≈ tokens * 4
        chunk_overlap=CHUNK_OVERLAP * 4,
        separators=SEPARATORS,
        is_separator_regex=True,
    )


def chunk_document(
    extracted: ExtractedDocument,
    raw_meta: RawCircularMetadata,
) -> list[Document]:
    """
    Split extracted text blocks into LangChain Documents with full metadata.

    Returns empty list and logs an error if the extracted document
    is marked as failed (caller should quarantine).

    Each returned Document has metadata matching ChunkMetadata fields.
    """
    if extracted.extraction_failed:
        logger.error(
            "chunking_skipped_failed_extraction",
            circular_id=extracted.circular_id,
            reason=extracted.failure_reason,
        )
        return []

    splitter = _splitter()
    chunks: list[Document] = []
    chunk_index = 0

    for block in extracted.blocks:
        sub_chunks = splitter.split_text(block.text)
        for sub in sub_chunks:
            if not sub.strip():
                continue

            # Build validated metadata — reject chunk if validation fails
            try:
                meta = ChunkMetadata(
                    source="RBI",
                    circular_id=raw_meta.circular_id,
                    circular_title=raw_meta.circular_title,
                    effective_date=raw_meta.effective_date,
                    clause_ref=block.clause_ref or "unclassified",
                    chunk_index=chunk_index,
                    scraped_at=raw_meta.scraped_at,
                )
            except Exception as exc:
                logger.error(
                    "metadata_validation_failed",
                    circular_id=raw_meta.circular_id,
                    chunk_index=chunk_index,
                    error=str(exc),
                )
                continue

            chunks.append(
                Document(
                    page_content=sub,
                    metadata=meta.model_dump(mode="json"),
                )
            )
            chunk_index += 1

    logger.info(
        "chunking_complete",
        circular_id=raw_meta.circular_id,
        chunks=len(chunks),
        blocks=len(extracted.blocks),
    )
    return chunks
