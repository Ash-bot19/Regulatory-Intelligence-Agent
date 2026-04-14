"""
LCEL RAG chain — retrieved chunks → GPT-4o-mini → structured response.

The LLM is only called after the confidence gate passes (handled in the API layer).
The chain itself is stateless: caller passes in pre-retrieved docs and query.
"""

import os
import uuid

import structlog
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from chain.citation_mapper import extract_citations
from models.response import QueryResponse

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a regulatory compliance assistant specialising in Reserve Bank of India (RBI) regulations.

You will be given excerpts from official RBI circulars. Your job is to extract and present every piece of relevant regulatory information from the context — even if coverage is partial.

Step 1: Read all provided excerpts carefully.
Step 2: Identify every excerpt that relates — directly or indirectly — to the user's question.
Step 3: Synthesise those excerpts into a structured answer.
Step 4: If coverage is partial, answer with what is available and note the gap at the end (one sentence).

Hard rules:
- Use ONLY information present in the provided context. Do not draw on outside knowledge.
- Never refuse to answer solely because the context lacks a specific detail. Extract what is there.
- If the context contains KYC, compliance, or related prudential requirements, include them even if they do not mention the exact product or entity in the query.
- Do not fabricate circular references, dates, or regulatory requirements not present in the context.
- Write in plain English. Use numbered lists for multi-part requirements.
- Do not add legal disclaimers or recommend consulting a lawyer.

Context from RBI circulars:
{context}
"""

_HUMAN_PROMPT = "{question}"


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=os.environ["OPENAI_API_KEY"],
        temperature=0,
        max_tokens=1024,
    )


def _format_context(docs: list[Document]) -> str:
    """Concatenate chunk page_content with source attribution headers."""
    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        header = (
            f"[{i}] {meta.get('circular_id', 'Unknown')} — "
            f"{meta.get('circular_title', '')} "
            f"(effective {meta.get('effective_date', 'unknown')})"
        )
        parts.append(f"{header}\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def run_chain(
    query: str,
    docs: list[Document],
    confidence_score: float,
    query_id: uuid.UUID | None = None,
) -> QueryResponse:
    """
    Execute the RAG chain given pre-retrieved documents.

    Args:
        query: the user's question
        docs: retrieved documents from the MMR retriever
        confidence_score: top similarity score from retrieval (already passed gate)
        query_id: optional UUID; generated if not supplied

    Returns:
        QueryResponse with answer, citations, confidence_score, query_id.

    Raises:
        ValueError: if citation extraction produces an empty list (no grounded answer
                    possible — caller should fire the fallback).
    """
    if query_id is None:
        query_id = uuid.uuid4()

    citations = extract_citations(docs)
    if not citations:
        logger.error(
            "chain_no_citations",
            query_id=str(query_id),
            num_docs=len(docs),
        )
        raise ValueError("Citation extraction returned empty list — cannot produce grounded answer")

    context = _format_context(docs)
    llm = _build_llm()
    prompt = ChatPromptTemplate.from_messages(
        [("system", _SYSTEM_PROMPT), ("human", _HUMAN_PROMPT)]
    )
    chain = prompt | llm | StrOutputParser()

    logger.info("llm_call_start", query_id=str(query_id), num_docs=len(docs))
    answer = chain.invoke({"context": context, "question": query})
    logger.info("llm_call_complete", query_id=str(query_id), answer_len=len(answer))

    return QueryResponse(
        answer=answer,
        citations=citations,
        confidence_score=confidence_score,
        query_id=query_id,
    )
