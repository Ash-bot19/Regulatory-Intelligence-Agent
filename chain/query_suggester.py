"""
Query suggester — called when the confidence gate fires.

Returns up to 3 RBI-scoped reformulations of the original query
that are more likely to match indexed circulars.

LLM is used only for terminology reframing, not for regulatory content.
"""

import os

import structlog
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

logger = structlog.get_logger(__name__)

_SUGGESTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are a specialist in RBI (Reserve Bank of India) regulatory terminology. "
                "The user's query did not match any indexed RBI circulars. "
                "Rewrite the query using precise RBI terminology so it is more likely to retrieve relevant circulars. "
                "Return exactly 3 alternative phrasings, one per line, no numbering, no explanations. "
                "Each phrasing must be keyword-dense and RBI-scoped. "
                "If the query is clearly outside RBI jurisdiction (e.g. SEBI, IRDAI), "
                "still return 3 RBI-adjacent reformulations that might find related circulars."
            ),
        ),
        ("human", "{query}"),
    ]
)

_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
    api_key=os.environ.get("OPENAI_API_KEY"),
)

_chain = _SUGGESTION_PROMPT | _llm | StrOutputParser()


def get_suggestions(query: str) -> list[str]:
    """Return up to 3 RBI-scoped query reformulations. Never raises — returns [] on failure."""
    try:
        raw = _chain.invoke({"query": query})
        suggestions = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        return suggestions[:3]
    except Exception as exc:
        logger.warning("suggester_failed", error=str(exc))
        return []
