# Regulatory Intelligence Agent

A RAG-based query engine for RBI circulars. Ask a compliance question, get an answer grounded in the actual regulatory text — with traceable citations and a confidence gate that refuses to guess.

---

## The Problem

RBI compliance research is manual. A typical question — "What are the KYC requirements for a full-KYC PPI above ₹10,000?" — requires searching across dozens of circulars, cross-referencing dates, and trusting that nothing was missed. LLMs make this faster but introduce a worse problem: confident-sounding answers with no grounding.

## The Solution

This system retrieves the relevant circular excerpts first, checks whether the retrieval quality is sufficient to support an answer, and only then calls the LLM — to explain what the circulars say, nothing more.

If the question is outside the indexed corpus (e.g. a SEBI question), the system says so explicitly and never calls the LLM.

**The story:** The system never guesses. If it can't ground an answer in indexed RBI circulars, it tells you.

---

## Demo

**Query 1 — gate passes:**
```
prepaid payment instrument KYC norms customer due diligence
```
Returns: answer with 2–5 cited RBI circulars, effective dates, confidence score.

**Query 2 — gate fires:**
```
What penalties does SEBI impose for insider trading violations?
```
Returns: fallback message, no LLM call, `gate_fired: true` in the audit log.

---

## Architecture

```
RBI circulars (rbi.org.in)
    │
    ▼
Scraper (requests + BeautifulSoup)
    │  two-step: index page → detail page → rbidocs PDF URL
    ▼
PyMuPDF extractor → metadata tagging (circular_id, title, effective_date, clause_ref)
    │
    ▼
RecursiveCharacterTextSplitter (500 tokens / 50 overlap, clause-aware separators)
    │  quarantine on metadata failure — never blocks pipeline
    ▼
OpenAI text-embedding-3-small (1536-dim, cosine space)
    │
    ▼
Chroma (local dev) / Pinecone free tier (demo)
    │
    ▼
POST /query (FastAPI)
    │
    ├─ MMR retriever (k=6, λ=0.3) — diversity across circulars
    │
    ├─ Confidence gate (threshold 0.65)
    │   ├─ BELOW: hardcoded fallback, LLM never called, audit row written
    │   └─ ABOVE: proceed
    │
    ├─ LCEL chain → GPT-4o-mini → narrative answer
    │   └─ Citations derived from chunk metadata (LLM never produces citations)
    │
    └─ Append-only audit log (PostgreSQL query_audit_log)

Streamlit UI → FastAPI → above
APScheduler → nightly delta re-index (02:00 IST, diff on circular_id)
Prometheus + Grafana → query count, gate fire rate, confidence distribution
```

### Key design decisions

| Decision | Why |
|---|---|
| Gate fires before LLM, not after | Prevents wasted LLM calls and catches low-quality retrievals before they become hallucinations |
| Citations from chunk metadata, not LLM | Eliminates hallucinated citations entirely — deterministic and auditable |
| MMR retrieval (k=6, λ=0.3) | Regulatory answers often span multiple circulars; pure similarity returns 6 chunks from the same doc |
| Confidence threshold 0.65 | Calibrated to OpenAI cosine scores: relevant RBI queries score 0.65–0.73, out-of-scope score 0.45–0.52 |
| Append-only audit log | Every request logged, including gate-fired ones where LLM was never called |
| Delta re-index only | Nightly freshness without re-embedding the full corpus |

---

## Stack

| Layer | Technology |
|---|---|
| Scraper | Python · requests · BeautifulSoup |
| PDF extraction | PyMuPDF |
| Chunking | LangChain RecursiveCharacterTextSplitter |
| Embeddings | OpenAI text-embedding-3-small |
| Vector store | Chroma (local) · Pinecone free tier (demo) |
| LLM | GPT-4o-mini |
| API | FastAPI |
| Audit log | PostgreSQL (append-only) |
| Scheduler | APScheduler |
| UI | Streamlit |
| Observability | Prometheus · Grafana |

---

## Running the Project

### Services

| Service | Port | URL |
|---|---|---|
| PostgreSQL | 5432 | — |
| FastAPI | 8000 | http://localhost:8000/docs |
| Streamlit UI | 8501 | http://localhost:8501 |
| Prometheus | 9090 | http://localhost:9090 |
| Grafana | 3000 | http://localhost:3000 |

### One-command startup

```bash
cp .env.example .env          # fill in OPENAI_API_KEY and POSTGRES_PASSWORD
docker compose up -d
python scripts/start.py
```

`scripts/start.py` health-checks all infra services, runs Alembic migrations if not applied, starts FastAPI and Streamlit as supervised subprocesses, and prints a startup summary. Safe to re-run.

### Individual service commands

```bash
# PostgreSQL (via Docker only)
docker compose up -d postgres

# FastAPI
python -m uvicorn api.main:app --reload --port 8000

# Streamlit UI
streamlit run ui/app.py --server.port 8501

# Freshness scheduler (standalone)
python -m scheduler.freshness
```

### Build the corpus (first run only)

```bash
# Index 2024 RBI circulars — ~139 docs, 31k chunks, ~$0.20 one-time cost
python scripts/index_corpus.py
```

### Demo

```bash
python scripts/demo.py
```

Runs both demo queries and prints expected vs actual outcomes.

### Tests

```bash
pytest tests/unit/
pytest tests/integration/   # requires Docker services running
```

---

## Corpus

- **Source:** RBI circulars only — `rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx`
- **Coverage:** 2024 calendar year — 139 circulars, 31,000 chunks, 0 quarantined
- **Freshness:** APScheduler runs a delta re-index nightly at 02:00 IST — only new circulars are embedded

Scope is RBI payments and banking regulation only. No SEBI, NPCI, or IRDAI. No user document uploads.

---

## Cost

| Item | Cost |
|---|---|
| Full corpus indexing (139 circulars) | ~$0.20 one-time |
| Per query (embedding + GPT-4o-mini) | ~$0.00071 |
| 500 dev/test queries | ~$0.35 |
| **Total build cost** | **< $1** |

---

## What It Does Not Do

- Provide legal advice — the fallback message is explicit about this
- Cover SEBI, NPCI, IRDAI, or any non-RBI regulator
- Allow citations from LLM output — citations are always derived deterministically from chunk metadata
- Call the LLM if retrieval confidence is below threshold
- Support user document uploads
