"""
Unit tests for the confidence gate.

No network calls — uses mock scored_docs to validate gate logic.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from retrieval.confidence_gate import GateFired, check_gate, get_threshold


def _make_doc(circular_id: str = "RBI/2024-25/67") -> MagicMock:
    doc = MagicMock()
    doc.metadata = {"circular_id": circular_id}
    return doc


class TestGateThreshold:
    def test_default_threshold_is_072(self, monkeypatch):
        monkeypatch.delenv("CONFIDENCE_THRESHOLD", raising=False)
        assert get_threshold() == 0.72

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.85")
        assert get_threshold() == 0.85


class TestGatePasses:
    def test_passes_at_threshold(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")
        docs = [(_make_doc(), 0.72), (_make_doc(), 0.65)]
        result_docs, top_score = check_gate(docs, uuid.uuid4())
        assert top_score == 0.72
        assert len(result_docs) == 2

    def test_passes_above_threshold(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")
        docs = [(_make_doc(), 0.95), (_make_doc(), 0.88)]
        result_docs, top_score = check_gate(docs, uuid.uuid4())
        assert top_score == 0.95


class TestGateFires:
    def test_fires_below_threshold(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")
        docs = [(_make_doc(), 0.71), (_make_doc(), 0.60)]
        with pytest.raises(GateFired) as exc_info:
            check_gate(docs, uuid.uuid4())
        assert exc_info.value.response.gate_fired is True
        assert exc_info.value.response.confidence_score == pytest.approx(0.71)

    def test_fires_on_empty_results(self):
        with pytest.raises(GateFired) as exc_info:
            check_gate([], uuid.uuid4())
        assert exc_info.value.response.confidence_score == 0.0

    def test_fallback_message_unchanged(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")
        docs = [(_make_doc(), 0.50)]
        with pytest.raises(GateFired) as exc_info:
            check_gate(docs, uuid.uuid4())
        expected = (
            "Insufficient regulatory basis found in indexed circulars. "
            "Please consult your compliance team or refer directly to RBI circulars at rbi.org.in."
        )
        assert exc_info.value.response.answer == expected

    def test_query_id_propagated(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")
        query_id = uuid.uuid4()
        docs = [(_make_doc(), 0.50)]
        with pytest.raises(GateFired) as exc_info:
            check_gate(docs, query_id)
        assert exc_info.value.response.query_id == query_id
