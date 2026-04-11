# External Integrations

**Analysis Date:** 2026-04-11

## APIs & External Services

**Embedding (primary):**
- Google Gemini Embedding API — generates 768-dim vectors for all chunks
  - Model: `models/gemini-embedding-001`
  - SDK: `google-generativeai==0.7.2` via `langchain-google-genai==1.0.7`
  - Client: `GoogleGenerativeAIEmbeddings` in `ingestion/indexer.py`
  - Auth: `GOOGLE_API_KEY` env var
  - Rate limit: 100 RPM on free tier; indexer retries with 60s backoff (up to 4 attempts) — see `ingestion/indexer.py` lines 58–115

**LLM Generation:**
- Groq API — narrative answer generation (free tier)
  - Model: not yet selected in code (chain not yet implemented)
  - SDK: `groq==0.9.0` via `langchain-groq==0.1.6`
  - Auth: `GROQ_API_KEY` env var
  - Usage: answer generation only — never for scoring, retrieval, or citation extraction

**Web Scraping Target:**
- RBI website (`rbi.org.in`) — the only external data source
  - Index URL: `https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx`
  - PDF host: `rbidocs.rbi.org.in/rdocs/.../*.PDF`
  - Auth: none (public); requires browser User-Agent + `Referer` header to avoid bot blocking
  - Fetched with `requests.Session` + retry logic in `scraper/rbi_scraper.py`
  - Polite delay: 0.5s between detail pages, 1.0s between PDF downloads

## Data Storage

**Databases:**

- PostgreSQL 16 (Alpine) — audit log only
  - Connection: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` env vars
  - Client: SQLAlchemy 2.0 + psycopg2-binary driver
  - Migrations: Alembic (`db/`)
  - Container: `ria_postgres` via `docker-compose.yml`, volume `postgres_data`
  - Table: `query_audit_log` — append-only, no UPDATE/DELETE ever
  - Schema:
    ```sql
    CREATE TABLE query_audit_log (
      query_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      query_text           TEXT NOT NULL,
      retrieved_chunk_ids  TEXT[],
      confidence_score     FLOAT,
      llm_response         TEXT,
      citations            JSONB,
      gate_fired           BOOLEAN DEFAULT FALSE,
      created_at           TIMESTAMPTZ DEFAULT NOW()
    );
    ```

**Vector Stores:**

- Chroma (local dev) — in-process, file-backed
  - Persistence: `CHROMA_PERSIST_DIR` (default `./data/chroma`, gitignored)
  - Collection: `rbi_circulars`
  - Client: `langchain-chroma==0.1.2`
  - Instantiated in `ingestion/indexer.py::get_chroma_store()`
  - Known issue: no dedup across pipeline re-runs — wipe `data/chroma` before Phase 2

- Pinecone (demo/prod) — free tier
  - Auth: `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT` env vars
  - Index: `PINECONE_INDEX_NAME` (default `rbi_circulars`)
  - SDK: `pinecone-client==3.2.2` via `langchain-community` Pinecone wrapper
  - Instantiated in `ingestion/indexer.py::get_pinecone_store()`
  - Switching is manual (pass store instance to `index_documents()`)

**File Storage:**
- Local filesystem only — PDFs downloaded to `./data/pdfs/` (gitignored)
- No cloud object storage in v1

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- None — no user authentication in v1 (explicitly out of scope per CLAUDE.md)

## Monitoring & Observability

**Metrics:**
- prometheus-client 0.20.0 — metrics exposition; `monitoring/` directory is empty (Phase 5)
- Planned metrics: query count, gate fire rate, avg confidence score
- Grafana dashboards planned (Phase 5), not yet configured

**Error Tracking:**
- None (no Sentry or equivalent)

**Logs:**
- structlog 24.2.0 — structured JSON-style logs throughout all modules
- No `print()` permitted anywhere; all log calls use `logger = structlog.get_logger(__name__)`
- Log events use snake_case keys (e.g. `batch_indexed`, `pdf_download_failed`, `extraction_complete`)

## CI/CD & Deployment

**Hosting:**
- No deployment config present; local Docker Compose only

**CI Pipeline:**
- None configured

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Scheduling

**Freshness Scheduler:**
- APScheduler 3.10.4 — nightly delta re-index
- Schedule: `SCHEDULER_HOUR:SCHEDULER_MINUTE` in `SCHEDULER_TIMEZONE` (default 02:00 IST)
- `scheduler/` directory is empty — Phase 4 work
- Behavior contract: diff against `scraped_at`, never full re-index; log and skip on failure, never swallow errors silently

## Environment Configuration

**Required env vars (all sourced from `.env`):**
- `GOOGLE_API_KEY` — Gemini API
- `GROQ_API_KEY` — Groq API
- `PINECONE_API_KEY` — Pinecone (demo/prod only)
- `PINECONE_ENVIRONMENT` — Pinecone region
- `PINECONE_INDEX_NAME` — Pinecone index (default `rbi_circulars`)
- `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD`
- `CHROMA_PERSIST_DIR` — local vector store path
- `CONFIDENCE_THRESHOLD` — gate threshold (default `0.72`)
- `SCHEDULER_HOUR` / `SCHEDULER_MINUTE` / `SCHEDULER_TIMEZONE`
- `ENV` — environment selector (`local` | `demo` | `prod`)

**Secrets location:**
- `.env` file at project root (gitignored); `.env.example` is committed as template

---

*Integration audit: 2026-04-11*
