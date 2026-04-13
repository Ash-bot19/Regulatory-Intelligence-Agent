"""
Unit tests for the citation mapper.

Validates that citations are extracted from chunk metadata (not LLM output),
deduplicated correctly, and that missing metadata triggers a skip (not an error).
"""

from datetime import date
from unittest.mock import MagicMock

from chain.citation_mapper import extract_citations


def _make_doc(
    circular_id: str = "RBI/2024-25/67",
    circular_title: str = "Test Circular",
    effective_date="2024-09-01",
    clause_ref: str = "Section 4.2",
    chunk_index: int = 0,
) -> MagicMock:
    doc = MagicMock()
    doc.metadata = {
        "circular_id": circular_id,
        "circular_title": circular_title,
        "effective_date": effective_date,
        "clause_ref": clause_ref,
        "chunk_index": chunk_index,
    }
    return doc


class TestExtractCitations:
    def test_basic_extraction(self):
        docs = [_make_doc()]
        citations = extract_citations(docs)
        assert len(citations) == 1
        assert citations[0].circular_id == "RBI/2024-25/67"
        assert citations[0].clause_ref == "Section 4.2"
        assert citations[0].effective_date == date(2024, 9, 1)

    def test_deduplication_same_circular_same_clause(self):
        docs = [_make_doc(chunk_index=0), _make_doc(chunk_index=1)]
        citations = extract_citations(docs)
        assert len(citations) == 1

    def test_no_dedup_different_clause(self):
        docs = [
            _make_doc(clause_ref="Section 4.2"),
            _make_doc(clause_ref="Section 5.1"),
        ]
        citations = extract_citations(docs)
        assert len(citations) == 2

    def test_no_dedup_different_circular(self):
        docs = [
            _make_doc(circular_id="RBI/2024-25/67"),
            _make_doc(circular_id="RBI/2024-25/89"),
        ]
        citations = extract_citations(docs)
        assert len(citations) == 2

    def test_missing_circular_id_skipped(self):
        doc = MagicMock()
        doc.metadata = {"circular_title": "Orphan", "effective_date": "2024-01-01"}
        citations = extract_citations([doc])
        assert citations == []

    def test_empty_docs_returns_empty(self):
        assert extract_citations([]) == []

    def test_date_as_date_object(self):
        docs = [_make_doc(effective_date=date(2025, 3, 15))]
        citations = extract_citations(docs)
        assert citations[0].effective_date == date(2025, 3, 15)

    def test_malformed_date_uses_fallback(self):
        docs = [_make_doc(effective_date="not-a-date")]
        citations = extract_citations(docs)
        assert citations[0].effective_date == date(1900, 1, 1)

    def test_mixed_valid_and_missing_ids(self):
        valid_doc = _make_doc(circular_id="RBI/2024-25/67")
        bad_doc = MagicMock()
        bad_doc.metadata = {}
        citations = extract_citations([valid_doc, bad_doc])
        assert len(citations) == 1
        assert citations[0].circular_id == "RBI/2024-25/67"
