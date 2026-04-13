"""
Confidence gate — fires BEFORE the LLM is called.

Threshold: 0.72 (set in CONFIDENCE_THRESHOLD env var, default matches locked contract).
If the top retrieved chunk similarity score is below threshold, the gate fires and
the LLM is never called.
"""

import os
import uuid

import structlog
from langchain_core.documents import Document

from models.response import GateFiredResponse, QueryResponse

logger = structlog.get_logger(__name__)

_DEFAULT_THRESHOLD = 0.72


def get_threshold() -> float:
    return float(os.environ.get("CONFIDENCE_THRESHOLD", _DEFAULT_THRESHOLD))


class GateFired(Exception):
    """Raised when confidence gate fires. Carries the pre-built fallback response."""

    def __init__(self, response: GateFiredResponse):
        self.response = response
        super().__init__(f"Gate fired — confidence {response.confidence_score:.4f} < threshold")


def check_gate(
    scored_docs: list[tuple[Document, float]],
    query_id: uuid.UUID,
) -> tuple[list[Document], float]:
    """
    Evaluate the confidence gate against the top similarity score.

    Args:
        scored_docs: (document, score) pairs from retrieve_with_scores, ordered desc by score.
        query_id: UUID for this request (included in fallback response for audit linkage).

    Returns:
        (docs, top_score) if gate passes.

    Raises:
        GateFired: if top score < threshold or scored_docs is empty.
    """
    threshold = get_threshold()

    if not scored_docs:
        logger.warning("gate_no_results", query_id=str(query_id))
        raise GateFired(
            GateFiredResponse(confidence_score=0.0, query_id=query_id)
        )

    top_score = scored_docs[0][1]
    docs = [doc for doc, _ in scored_docs]

    logger.info(
        "gate_check",
        query_id=str(query_id),
        top_score=round(top_score, 4),
        threshold=threshold,
    )

    if top_score < threshold:
        logger.info(
            "gate_fired",
            query_id=str(query_id),
            top_score=round(top_score, 4),
            threshold=threshold,
        )
        raise GateFired(
            GateFiredResponse(confidence_score=top_score, query_id=query_id)
        )

    logger.info("gate_passed", query_id=str(query_id), top_score=round(top_score, 4))
    return docs, top_score
