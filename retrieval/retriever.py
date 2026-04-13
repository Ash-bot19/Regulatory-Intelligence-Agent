"""
MMR retriever over the rbi_circulars Chroma collection.

k=6, lambda_mult=0.3 — diversity-first to avoid 6 chunks from one doc.
"""

import os

import structlog
from langchain_core.documents import Document

logger = structlog.get_logger(__name__)

_MMR_K = 6
_MMR_LAMBDA = 0.3
_FETCH_K = 20  # candidate pool for MMR diversification


def get_retriever(store=None):
    """
    Return an MMR retriever backed by the Chroma store.

    Pass a store explicitly in tests; defaults to the local Chroma instance.
    """
    if store is None:
        from ingestion.indexer import get_chroma_store
        store = get_chroma_store()

    return store.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": _MMR_K,
            "fetch_k": _FETCH_K,
            "lambda_mult": _MMR_LAMBDA,
        },
    )


def retrieve_with_scores(query: str, store=None) -> list[tuple[Document, float]]:
    """
    Return (document, similarity_score) pairs for top-k results.

    Used by the confidence gate to check the top score before calling the LLM.
    Similarity score is cosine similarity in [0, 1] range.
    """
    if store is None:
        from ingestion.indexer import get_chroma_store
        store = get_chroma_store()

    results = store.similarity_search_with_relevance_scores(
        query,
        k=_MMR_K,
        score_threshold=0.0,
    )
    logger.info(
        "retrieval_scores",
        query_preview=query[:60],
        scores=[round(s, 4) for _, s in results],
    )
    return results
