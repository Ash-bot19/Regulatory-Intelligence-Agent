"""Unit tests for the chunker — no PDF/network required."""

from datetime import date, datetime

import pytest

from models.chunk import RawCircularMetadata
from scraper.pdf_extractor import ExtractedDocument, TextBlock
from ingestion.chunker import chunk_document


SAMPLE_META = RawCircularMetadata(
    circular_id="RBI/2024-25/67",
    circular_title="Test Circular",
    effective_date=date(2024, 9, 1),
    pdf_url="https://example.com/test.pdf",
    scraped_at=datetime(2024, 10, 1, 12, 0, 0),
)


def _make_extracted(text: str, failed: bool = False) -> ExtractedDocument:
    doc = ExtractedDocument(circular_id="RBI/2024-25/67")
    if failed:
        doc.extraction_failed = True
        doc.failure_reason = "test_failure"
    else:
        doc.blocks = [TextBlock(text=text, page_number=1, clause_ref="4.2", block_index=0)]
    return doc


class TestChunkDocument:
    def test_returns_empty_on_failed_extraction(self):
        doc = _make_extracted("", failed=True)
        result = chunk_document(doc, SAMPLE_META)
        assert result == []

    def test_chunk_has_required_metadata_fields(self):
        long_text = "This is a test regulatory sentence. " * 50
        doc = _make_extracted(long_text)
        chunks = chunk_document(doc, SAMPLE_META)
        assert len(chunks) > 0

        meta = chunks[0].metadata
        assert meta["source"] == "RBI"
        assert meta["circular_id"] == "RBI/2024-25/67"
        assert meta["circular_title"] == "Test Circular"
        assert "effective_date" in meta
        assert "clause_ref" in meta
        assert "chunk_index" in meta
        assert "scraped_at" in meta

    def test_chunk_indices_are_sequential(self):
        long_text = "Regulatory content. " * 200
        doc = _make_extracted(long_text)
        chunks = chunk_document(doc, SAMPLE_META)
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_block_text_returns_empty(self):
        doc = ExtractedDocument(circular_id="RBI/2024-25/67")
        doc.blocks = [TextBlock(text="   ", page_number=1, block_index=0)]
        result = chunk_document(doc, SAMPLE_META)
        assert result == []
