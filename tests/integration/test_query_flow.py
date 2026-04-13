"""
Integration test for the full query flow (retrieval → gate → chain → response).

Uses mocked vectorstore and LLM — no network calls, no quota consumption.
Tests both the happy path (gate passes, answer returned) and gate-fired path.
"""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from models.response import GateFiredResponse, QueryResponse

client = TestClient(app)


def _make_doc(
    circular_id: str = "RBI/2024-25/87",
    title: str = "Amendment to KYC Direction",
    effective_date: str = "2024-06-01",
    clause_ref: str = "Section 3",
    chunk_index: int = 0,
    content: str = "KYC requirements for full-KYC PPI above Rs 10,000.",
) -> MagicMock:
    doc = MagicMock()
    doc.page_content = content
    doc.metadata = {
        "circular_id": circular_id,
        "circular_title": title,
        "effective_date": effective_date,
        "clause_ref": clause_ref,
        "chunk_index": chunk_index,
        "source": "RBI",
    }
    return doc


@pytest.fixture
def high_confidence_docs():
    """Docs that score above the 0.72 gate threshold."""
    doc = _make_doc()
    return [(doc, 0.85), (_make_doc(chunk_index=1, content="Additional KYC details."), 0.78)]


@pytest.fixture
def low_confidence_docs():
    """Docs that score below the 0.72 gate threshold (SEBI out-of-scope)."""
    doc = _make_doc(
        circular_id="RBI/2024-25/01",
        title="Unrelated Circular",
        content="This circular is about treasury bonds.",
    )
    return [(doc, 0.55), (_make_doc(chunk_index=1, content="More bonds."), 0.50)]


class TestQueryEndpointGatePasses:
    def test_returns_answer_and_citations(self, high_confidence_docs, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")

        with (
            patch("api.routes.retrieve_with_scores", return_value=high_confidence_docs),
            patch("api.routes.run_chain") as mock_chain,
            patch("api.routes.write_audit_record"),
        ):
            mock_chain.return_value = QueryResponse(
                answer="KYC requires full-KYC for PPIs above Rs 10,000.",
                citations=[],
                confidence_score=0.85,
                query_id=uuid.uuid4(),
            )
            resp = client.post("/api/v1/query", json={"query": "What are KYC requirements for PPI above Rs 10000?"})

        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert data["confidence_score"] == pytest.approx(0.85)
        assert "gate_fired" not in data or data.get("gate_fired") is False

    def test_audit_record_written_on_success(self, high_confidence_docs, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")

        with (
            patch("api.routes.retrieve_with_scores", return_value=high_confidence_docs),
            patch("api.routes.run_chain") as mock_chain,
            patch("api.routes.write_audit_record") as mock_audit,
        ):
            mock_chain.return_value = QueryResponse(
                answer="Answer text.",
                citations=[],
                confidence_score=0.85,
                query_id=uuid.uuid4(),
            )
            client.post("/api/v1/query", json={"query": "What are KYC requirements for PPI above Rs 10000?"})

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["gate_fired"] is False
        assert call_kwargs["llm_response"] == "Answer text."


class TestQueryEndpointGateFires:
    def test_returns_fallback_message(self, low_confidence_docs, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")

        with (
            patch("api.routes.retrieve_with_scores", return_value=low_confidence_docs),
            patch("api.routes.write_audit_record"),
        ):
            resp = client.post("/api/v1/query", json={"query": "What are SEBI disclosure norms?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["gate_fired"] is True
        assert "rbi.org.in" in data["answer"]
        assert data["citations"] == []

    def test_llm_not_called_when_gate_fires(self, low_confidence_docs, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")

        with (
            patch("api.routes.retrieve_with_scores", return_value=low_confidence_docs),
            patch("api.routes.run_chain") as mock_chain,
            patch("api.routes.write_audit_record"),
        ):
            client.post("/api/v1/query", json={"query": "What are SEBI disclosure norms?"})

        mock_chain.assert_not_called()

    def test_audit_logged_when_gate_fires(self, low_confidence_docs, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.72")

        with (
            patch("api.routes.retrieve_with_scores", return_value=low_confidence_docs),
            patch("api.routes.write_audit_record") as mock_audit,
        ):
            client.post("/api/v1/query", json={"query": "What are SEBI disclosure norms?"})

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["gate_fired"] is True
        assert call_kwargs["llm_response"] is None


class TestQueryEndpointValidation:
    def test_empty_query_rejected(self):
        resp = client.post("/api/v1/query", json={"query": "hi"})
        assert resp.status_code == 422  # min_length=5

    def test_missing_query_rejected(self):
        resp = client.post("/api/v1/query", json={})
        assert resp.status_code == 422

    def test_health_endpoint(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
