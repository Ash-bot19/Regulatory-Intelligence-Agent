"""
POST /query — the single external endpoint.

Request flow:
  1. Retrieve top-k docs with scores (MMR)
  2. Confidence gate check (fires before LLM)
  3. RAG chain (LLM + citation extraction)
  4. Audit log write (always, including gate-fired)
  5. Return QueryResponse or GateFiredResponse
"""

import time
import uuid

import structlog
from fastapi import APIRouter, HTTPException

from api.schemas import QueryRequest
from audit.writer import write_audit_record
from chain.rag_chain import run_chain
from models.response import GateFiredResponse, QueryResponse
from monitoring.metrics import confidence_histogram, llm_latency_histogram, query_counter
from retrieval.confidence_gate import GateFired, check_gate
from retrieval.retriever import retrieve_with_scores

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse | GateFiredResponse,
    summary="Submit a regulatory question",
    description=(
        "Retrieves relevant RBI circular excerpts, checks confidence gate, "
        "and returns a grounded answer with citations. "
        "Returns the fallback message if confidence threshold is not met."
    ),
)
async def query(request: QueryRequest) -> QueryResponse | GateFiredResponse:
    query_id = uuid.uuid4()
    query_text = request.query.strip()

    logger.info("query_received", query_id=str(query_id), query_preview=query_text[:80])

    # Step 1: Retrieve with scores
    try:
        scored_docs = retrieve_with_scores(query_text)
    except Exception as exc:
        logger.error("retrieval_failed", query_id=str(query_id), error=str(exc))
        # Log the failed request before re-raising
        write_audit_record(
            query_id=query_id,
            query_text=query_text,
            retrieved_chunk_ids=[],
            confidence_score=0.0,
            llm_response=None,
            citations=None,
            gate_fired=False,
        )
        raise HTTPException(status_code=503, detail="Retrieval service unavailable")

    chunk_ids = [doc.metadata.get("circular_id", "") for doc, _ in scored_docs]

    # Step 2: Confidence gate
    try:
        docs, top_score = check_gate(scored_docs, query_id)
    except GateFired as gf:
        confidence_histogram.observe(gf.response.confidence_score)
        query_counter.labels(outcome="gate_fired").inc()
        write_audit_record(
            query_id=query_id,
            query_text=query_text,
            retrieved_chunk_ids=chunk_ids,
            confidence_score=gf.response.confidence_score,
            llm_response=None,
            citations=None,
            gate_fired=True,
        )
        logger.info("response_gate_fired", query_id=str(query_id))
        return gf.response

    confidence_histogram.observe(top_score)

    # Step 3: RAG chain
    llm_start = time.monotonic()
    try:
        response = run_chain(
            query=query_text,
            docs=docs,
            confidence_score=top_score,
            query_id=query_id,
        )
    except ValueError as exc:
        # Citation extraction failed — treat as gate fired
        logger.error("chain_citation_empty", query_id=str(query_id), error=str(exc))
        query_counter.labels(outcome="gate_fired").inc()
        fallback = GateFiredResponse(confidence_score=top_score, query_id=query_id)
        write_audit_record(
            query_id=query_id,
            query_text=query_text,
            retrieved_chunk_ids=chunk_ids,
            confidence_score=top_score,
            llm_response=None,
            citations=None,
            gate_fired=True,
        )
        return fallback
    except Exception as exc:
        logger.error("chain_failed", query_id=str(query_id), error=str(exc))
        query_counter.labels(outcome="error").inc()
        write_audit_record(
            query_id=query_id,
            query_text=query_text,
            retrieved_chunk_ids=chunk_ids,
            confidence_score=top_score,
            llm_response=None,
            citations=None,
            gate_fired=False,
        )
        raise HTTPException(status_code=503, detail="LLM service unavailable")

    llm_latency_histogram.observe(time.monotonic() - llm_start)
    query_counter.labels(outcome="answered").inc()

    # Step 4: Audit log
    write_audit_record(
        query_id=query_id,
        query_text=query_text,
        retrieved_chunk_ids=chunk_ids,
        confidence_score=response.confidence_score,
        llm_response=response.answer,
        citations=[c.model_dump(mode="json") for c in response.citations],
        gate_fired=False,
    )

    logger.info(
        "response_sent",
        query_id=str(query_id),
        num_citations=len(response.citations),
        confidence=round(response.confidence_score, 4),
    )
    return response
