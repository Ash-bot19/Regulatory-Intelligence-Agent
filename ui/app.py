"""
Streamlit UI for the Regulatory Intelligence Agent.

Usage:
    streamlit run ui/app.py

Calls the FastAPI backend at http://localhost:8000/api/v1/query.
The UI never calls retrieval or LLM directly — everything goes through the API.
"""

import os
from datetime import date

import httpx
import streamlit as st

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")
REQUEST_TIMEOUT = 30

st.set_page_config(
    page_title="Regulatory Intelligence Agent",
    page_icon="📋",
    layout="centered",
)

st.title("Regulatory Intelligence Agent")
st.caption("Answers grounded in RBI circulars · No hallucinations · Sources always cited")

st.divider()

query = st.text_area(
    "Ask a regulatory question",
    placeholder="e.g. What are the KYC requirements for a full-KYC PPI above ₹10,000?",
    height=100,
)

submit = st.button("Ask", type="primary", disabled=not query.strip())

if submit and query.strip():
    with st.spinner("Searching RBI circulars..."):
        try:
            response = httpx.post(
                f"{API_BASE}/query",
                json={"query": query.strip()},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            st.error("Request timed out. The API may be starting up — try again.")
            st.stop()
        except httpx.HTTPStatusError as exc:
            st.error(f"API error {exc.response.status_code}: {exc.response.text}")
            st.stop()
        except httpx.RequestError as exc:
            st.error(f"Could not reach the API at {API_BASE}. Is the server running?\n\n`{exc}`")
            st.stop()

    gate_fired = data.get("gate_fired", False)
    confidence = data.get("confidence_score", 0.0)

    if gate_fired:
        # Gate fired — show fallback, no citations
        st.warning("**Insufficient regulatory basis found**")
        st.write(data["answer"])
        st.caption(f"Confidence score: {confidence:.2f} (below threshold of 0.72)")
        st.info(
            "The system only answers questions grounded in indexed RBI circulars. "
            "For SEBI, IRDAI, or NPCI queries, refer to those regulators directly."
        )
    else:
        # Gate passed — show answer + citations
        st.success("**Answer**")
        st.write(data["answer"])

        col1, col2 = st.columns([1, 1])
        col1.metric("Confidence", f"{confidence:.2f}")
        col2.metric("Sources cited", len(data.get("citations", [])))

        citations = data.get("citations", [])
        if citations:
            st.divider()
            st.subheader("Sources")
            for i, citation in enumerate(citations, 1):
                with st.expander(
                    f"{i}. {citation['circular_id']} — {citation['circular_title'][:60]}"
                ):
                    effective = citation.get("effective_date", "")
                    clause = citation.get("clause_ref", "")
                    st.markdown(f"**Effective date:** {effective}")
                    if clause:
                        st.markdown(f"**Clause:** {clause}")
                    st.markdown(
                        f"[View on RBI website](https://www.rbi.org.in)",
                        unsafe_allow_html=False,
                    )

        query_id = data.get("query_id", "")
        if query_id:
            st.caption(f"Query ID: `{query_id}`")

st.divider()
st.caption(
    "This system answers questions based solely on indexed RBI circulars. "
    "It does not provide legal advice. For authoritative guidance, refer to rbi.org.in."
)
