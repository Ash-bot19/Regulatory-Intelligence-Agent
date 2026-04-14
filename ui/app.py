"""
Streamlit Chat UI for the Regulatory Intelligence Agent.

Usage:
    streamlit run ui/app.py

Calls the FastAPI backend at http://localhost:8000/api/v1/query.
The UI never calls retrieval or LLM directly — everything goes through the API.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")
REQUEST_TIMEOUT = 30
GATE_THRESHOLD = 0.65


# ── API helpers ──────────────────────────────────────────────────────────────


def _start_api() -> None:
    """Start the FastAPI server as a background subprocess if not already running."""
    if "api_process" in st.session_state:
        return
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000"],
        cwd=str(_PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    st.session_state["api_process"] = proc.pid


def _call_api(payload: dict) -> dict:
    """POST to /query with one automatic restart attempt on connection failure."""
    url = f"{API_BASE}/query"
    try:
        r = httpx.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except httpx.RequestError:
        _start_api()
        time.sleep(4)
        r = httpx.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()


# ── CSS injection ─────────────────────────────────────────────────────────────


def _inject_css() -> None:
    st.markdown(
        """
<style>
/* ── Scroll smoothing ───────────────────────────────────── */
html {
    scroll-behavior: smooth;
}
/* Prevent scroll-anchor jumps when Streamlit rerenders */
[data-testid="stAppViewBlockContainer"],
[data-testid="stVerticalBlock"] {
    overflow-anchor: none;
}

/* ── Page & layout ─────────────────────────────────────── */
[data-testid="stAppViewContainer"] {
    background: #0e1117;
}
[data-testid="stHeader"] {
    background: transparent;
    border-bottom: 1px solid #1a1f2e;
}
[data-testid="stToolbar"] { display: none; }
.block-container {
    padding-top: 0.5rem;
    padding-bottom: 5rem;
    max-width: 800px;
}

/* ── App header ─────────────────────────────────────────── */
.app-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 18px 0 14px 0;
    border-bottom: 1px solid #1a1f2e;
    margin-bottom: 1.25rem;
}
.app-header-icon {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
}
.app-header-text h1 {
    font-size: 16px;
    font-weight: 600;
    color: #f1f5f9;
    margin: 0;
    letter-spacing: -0.2px;
}
.app-header-text p {
    font-size: 12px;
    color: #475569;
    margin: 2px 0 0 0;
}
.status-dot {
    width: 7px;
    height: 7px;
    background: #22c55e;
    border-radius: 50%;
    display: inline-block;
    margin-right: 5px;
    box-shadow: 0 0 6px #22c55e77;
    animation: pulse 2.5s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* ── Chat messages ──────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 4px 0 !important;
}

/* ── Confidence badge (pass) ────────────────────────────── */
.conf-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #22c55e;
    background: #052e16;
    border: 1px solid #16a34a33;
    border-radius: 6px;
    padding: 3px 10px;
    margin-top: 10px;
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    letter-spacing: 0.2px;
}

/* ── Confidence badge (gate fired) ─────────────────────── */
.conf-badge-low {
    color: #f59e0b;
    background: #1c1407;
    border-color: #d9770633;
}

/* ── Gate-fired panel ───────────────────────────────────── */
.gate-panel {
    background: #1a1100;
    border: 1px solid #78350f44;
    border-left: 3px solid #f59e0b;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 10px;
}
.gate-label {
    font-size: 10.5px;
    font-weight: 700;
    color: #f59e0b;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    margin-bottom: 8px;
}
.gate-message {
    font-size: 13.5px;
    color: #cbd5e1;
    line-height: 1.65;
}

/* ── Suggestion chips label ─────────────────────────────── */
.suggestion-label {
    font-size: 11px;
    color: #475569;
    margin: 12px 0 6px 0;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    font-weight: 600;
}

/* ── Suggestion buttons ─────────────────────────────────── */
div[data-testid="stButton"] > button {
    border-radius: 18px !important;
    border: 1px solid #1e2330 !important;
    background: #0f1623 !important;
    color: #7c8ea8 !important;
    font-size: 12px !important;
    padding: 5px 14px !important;
    height: auto !important;
    white-space: normal !important;
    text-align: left !important;
    line-height: 1.4 !important;
    transition: border-color 0.15s, color 0.15s !important;
}
div[data-testid="stButton"] > button:hover {
    border-color: #2563eb !important;
    color: #60a5fa !important;
    background: #0c1525 !important;
}

/* ── Citation cards ─────────────────────────────────────── */
.citation-card {
    background: #0d1117;
    border: 1px solid #1a1f2e;
    border-left: 3px solid #2563eb;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 8px;
}
.citation-id {
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 11px;
    color: #60a5fa;
    font-weight: 600;
    letter-spacing: 0.3px;
    margin-bottom: 4px;
}
.citation-title {
    font-size: 13px;
    color: #cbd5e1;
    margin-bottom: 5px;
    line-height: 1.45;
}
.citation-meta {
    font-size: 11px;
    color: #334155;
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
}

/* ── Expander ────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #0d1117 !important;
    border: 1px solid #1a1f2e !important;
    border-radius: 8px !important;
    margin-top: 10px !important;
}
[data-testid="stExpander"] summary {
    font-size: 12.5px !important;
    color: #64748b !important;
}

/* ── Chat input ─────────────────────────────────────────── */
[data-testid="stChatInput"] textarea {
    background: #0d1117 !important;
    border: 1px solid #1a1f2e !important;
    border-radius: 12px !important;
    color: #e2e8f0 !important;
    font-size: 14px !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px #1d4ed810 !important;
}

/* ── Footer ─────────────────────────────────────────────── */
.footer {
    text-align: center;
    font-size: 11px;
    color: #1e293b;
    padding-top: 10px;
    margin-top: 0.5rem;
}
</style>
""",
        unsafe_allow_html=True,
    )


# ── Render helpers ────────────────────────────────────────────────────────────


def _render_assistant_response(data: dict, show_suggestions: bool = True) -> None:
    """Render an assistant chat bubble: gate-fired fallback or grounded answer."""
    gate_fired = data.get("gate_fired", False)
    confidence = data.get("confidence_score", 0.0)
    answer = data.get("answer", "")
    citations = data.get("citations", [])
    suggestions = data.get("suggestions", [])
    query_id = data.get("query_id", "")

    if gate_fired:
        st.markdown(
            f"""<div class="gate-panel">
<div class="gate-label">⚠ Insufficient regulatory basis</div>
<div class="gate-message">{answer}</div>
</div>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="conf-badge conf-badge-low">'
            f'confidence {confidence:.2f} · below {GATE_THRESHOLD} threshold'
            f'</div>',
            unsafe_allow_html=True,
        )
        if show_suggestions and suggestions:
            st.markdown(
                '<div class="suggestion-label">Try an RBI-scoped query</div>',
                unsafe_allow_html=True,
            )
            for suggestion in suggestions:
                def _set_pending(s: str = suggestion) -> None:
                    st.session_state["_pending_query"] = s
                st.button(
                    suggestion,
                    key=f"sug_{hash(suggestion)}_{query_id}",
                    on_click=_set_pending,
                )
    else:
        st.write(answer)
        n = len(citations)
        st.markdown(
            f'<div class="conf-badge">'
            f'✓ &nbsp;confidence {confidence:.2f} · {n} source{"s" if n != 1 else ""} cited'
            f'</div>',
            unsafe_allow_html=True,
        )
        if citations:
            with st.expander(f"Sources ({n})"):
                for c in citations:
                    clause = c.get("clause_ref", "")
                    meta = f"Effective: {c.get('effective_date', 'N/A')}"
                    if clause:
                        meta += f" · {clause}"
                    st.markdown(
                        f"""<div class="citation-card">
<div class="citation-id">{c.get('circular_id', '')}</div>
<div class="citation-title">{c.get('circular_title', '')}</div>
<div class="citation-meta">{meta}</div>
</div>""",
                        unsafe_allow_html=True,
                    )
        if query_id:
            st.caption(f"`{query_id}`")


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Regulatory Intelligence Agent",
    page_icon="📋",
    layout="centered",
)

_inject_css()

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(
    """
<div class="app-header">
    <div class="app-header-icon">📋</div>
    <div class="app-header-text">
        <h1>Regulatory Intelligence Agent</h1>
        <p><span class="status-dot"></span>RBI circulars · grounded answers · sources always cited</p>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Consume pending query from suggestion click ───────────────────────────────

_pending = st.session_state.pop("_pending_query", None)

# ── Chat input (always at bottom, outside container) ─────────────────────────

prompt = st.chat_input("Ask a regulatory question…")

query_text = _pending or prompt

# ── Fixed-height chat container (eliminates page-level scroll jitter) ─────────

chat_container = st.container(height=560)

with chat_container:
    # Replay history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.write(msg["content"])
            else:
                _render_assistant_response(msg["data"], show_suggestions=False)

    # Handle new query inside the same container so it appears inline
    if query_text:
        st.session_state.messages.append({"role": "user", "content": query_text})
        with st.chat_message("user"):
            st.write(query_text)

        with st.chat_message("assistant"):
            with st.spinner("Searching RBI circulars…"):
                try:
                    data = _call_api({"query": query_text})
                except httpx.TimeoutException:
                    st.error("Request timed out. The API may still be starting — try again in a few seconds.")
                    st.stop()
                except httpx.HTTPStatusError as exc:
                    st.error(f"API error {exc.response.status_code}: {exc.response.text}")
                    st.stop()
                except httpx.RequestError as exc:
                    st.error(f"Could not reach the API at {API_BASE} after restart attempt.\n\n`{exc}`")
                    st.stop()

            _render_assistant_response(data, show_suggestions=True)

        st.session_state.messages.append({"role": "assistant", "data": data})

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown(
    '<div class="footer">Answers grounded in indexed RBI circulars only · Not legal advice · rbi.org.in</div>',
    unsafe_allow_html=True,
)
