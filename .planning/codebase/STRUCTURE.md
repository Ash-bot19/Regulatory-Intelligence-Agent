# Codebase Structure

**Analysis Date:** 2026-04-11

## Directory Layout

```
regulatory-intelligence-agent/
├── scraper/                # RBI HTTP scraper, PDF downloader, PyMuPDF extractor
│   ├── __init__.py
│   ├── rbi_scraper.py      # scrape_index(), download_all(), download_pdf()
│   └── pdf_extractor.py    # extract_text() → ExtractedDocument/TextBlock
├── ingestion/              # Pipeline orchestrator, chunker, indexer, quarantine
│   ├── __init__.py
│   ├── pipeline.py         # run_pipeline() — CLI entry point
│   ├── chunker.py          # chunk_document() — RecursiveCharacterTextSplitter
│   ├── indexer.py          # index_documents(), get_chroma_store(), get_pinecone_store()
│   └── quarantine.py       # quarantine(), list_quarantined() — JSONL failure log
├── models/                 # Pydantic schemas only — no business logic
│   ├── __init__.py
│   ├── chunk.py            # ChunkMetadata, RawCircularMetadata
│   ├── response.py         # QueryResponse, CitationRecord, GateFiredResponse
│   └── audit.py            # AuditRecord
├── retrieval/              # MMR retriever + confidence gate (Phase 2 — stub)
├── chain/                  # LCEL RAG chain, citation mapper (Phase 2 — stub)
├── api/                    # FastAPI app, routes, middleware (Phase 3 — stub)
├── audit/                  # PostgreSQL audit log writer (Phase 3 — stub)
├── scheduler/              # APScheduler freshness job (Phase 4 — stub)
├── ui/                     # Streamlit app (Phase 4 — stub)
├── db/                     # Alembic migrations (Phase 3 — stub)
├── monitoring/             # Prometheus config, Grafana dashboards (Phase 5 — stub)
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── test_chunker.py           # Chunker metadata contract tests
│   │   └── test_scraper_parsing.py   # _parse_date, _normalize_circular_id tests
│   ├── integration/                  # Empty — Phase 2+
│   └── e2e/                          # Empty — Phase 4+
├── scripts/                # Utility scripts (empty)
├── data/                   # Runtime data — gitignored
│   ├── chroma/             # Chroma vector store persistence
│   ├── pdfs/               # Downloaded RBI PDFs (named {id_underscored}.pdf)
│   └── quarantine.jsonl    # Failed document records (append-only)
├── .env                    # Local secrets — gitignored
├── .env.example            # Template for required env vars
├── .gitignore
├── docker-compose.yml      # PostgreSQL 16 service only (Chroma runs in-process)
├── requirements.txt        # Pinned Python dependencies
└── CLAUDE.md               # Project build tracking and locked contracts
```

## Directory Purposes

**`scraper/`:**
- Purpose: All code that touches the network or reads PDFs
- Contains: HTTP session management, HTML parsing (BeautifulSoup), PDF block extraction (PyMuPDF), date/ID normalization helpers
- Key files: `scraper/rbi_scraper.py`, `scraper/pdf_extractor.py`
- Note: Internal dataclasses (`TextBlock`, `ExtractedDocument`) stay inside this module — not imported by layers beyond `ingestion/`

**`ingestion/`:**
- Purpose: Pipeline orchestration and data transformation from raw download to indexed vector chunks
- Contains: Pipeline entry point, LangChain text splitter wrapper, Chroma/Pinecone indexer with rate-limit retry, JSONL quarantine writer
- Key files: `ingestion/pipeline.py`, `ingestion/chunker.py`, `ingestion/indexer.py`, `ingestion/quarantine.py`

**`models/`:**
- Purpose: Single source of truth for all data contracts between layers — import from here, never define inline schemas in routes or services
- Contains: Three Pydantic v2 model files covering the full data lifecycle (raw scrape → chunk → API response → audit)
- Key files: `models/chunk.py`, `models/response.py`, `models/audit.py`

**`retrieval/` (Phase 2):**
- Purpose: MMR retriever wrapping Chroma/Pinecone store; will expose a function returning top-k chunks with similarity scores
- Planned: `retrieval/mmr_retriever.py`, `retrieval/confidence_gate.py`

**`chain/` (Phase 2):**
- Purpose: LCEL RAG chain — takes retrieved chunks, calls LLM, builds `QueryResponse` with citations from metadata
- Planned: `chain/rag_chain.py`, `chain/citation_mapper.py`, `chain/response_builder.py`

**`api/` (Phase 3):**
- Purpose: FastAPI application with confidence gate middleware and POST /query route
- Planned: `api/main.py`, `api/routes/query.py`, `api/middleware/confidence_gate.py`

**`audit/` (Phase 3):**
- Purpose: Append-only PostgreSQL writer for `query_audit_log`; every request including gate-fired ones must be logged
- Planned: `audit/writer.py`, `audit/schema.py`

**`db/` (Phase 3):**
- Purpose: Alembic migration files for the audit log table
- Planned: `db/alembic.ini`, `db/migrations/`

**`scheduler/` (Phase 4):**
- Purpose: APScheduler nightly delta re-index job; must not do full corpus re-index
- Planned: `scheduler/freshness_job.py`

**`ui/` (Phase 4):**
- Purpose: Streamlit interface — must render confidence score, citations with effective dates, and the locked fallback message verbatim when gate fires
- Planned: `ui/app.py`

**`monitoring/` (Phase 5):**
- Purpose: Prometheus scrape config and Grafana dashboard definitions (query count, gate fire rate, avg confidence)
- Planned: `monitoring/prometheus.yml`, `monitoring/dashboards/`

**`tests/`:**
- Purpose: Pytest test suite organized by layer and scope
- Contains: `unit/` (no network, no disk I/O), `integration/` (real Chroma, real DB — Phase 2+), `e2e/` (full stack — Phase 4+)

**`data/`:**
- Purpose: All runtime-generated local data
- Generated: Yes
- Committed: No (gitignored) — wipe `data/chroma/` before Phase 2 to prevent duplicate retrieval

## Key File Locations

**Entry Points:**
- `ingestion/pipeline.py`: CLI pipeline runner — `python -m ingestion.pipeline --source rbi`
- `api/main.py` (planned): FastAPI app — `uvicorn api.main:app --reload --port 8000`
- `ui/app.py` (planned): Streamlit UI — `streamlit run ui/app.py`

**Configuration:**
- `.env.example`: Required env vars template — copy to `.env` before first run
- `docker-compose.yml`: PostgreSQL 16 service definition

**Core Logic:**
- `scraper/rbi_scraper.py`: `scrape_index()`, `download_all()` — two-step HTTP fetch pattern
- `scraper/pdf_extractor.py`: `extract_text()` — PyMuPDF block extraction with clause ref detection
- `ingestion/chunker.py`: `chunk_document()` — splits + validates `ChunkMetadata` per chunk
- `ingestion/indexer.py`: `index_documents()`, `get_chroma_store()`, `get_pinecone_store()`
- `ingestion/quarantine.py`: `quarantine()` — append-only JSONL failure recorder

**Data Contracts:**
- `models/chunk.py`: `ChunkMetadata` (indexed chunk contract), `RawCircularMetadata` (scraper output)
- `models/response.py`: `QueryResponse`, `GateFiredResponse`, `CitationRecord` (API contracts)
- `models/audit.py`: `AuditRecord` (audit log contract)

**Testing:**
- `tests/unit/test_chunker.py`: Chunker metadata contract and sequential index tests
- `tests/unit/test_scraper_parsing.py`: Date parsing and circular ID normalization tests

## Naming Conventions

**Files:**
- `snake_case.py` for all Python modules
- Test files: `test_{module_name}.py` pattern
- PDF downloads: `{circular_id_with_slashes_replaced_by_underscores}.pdf` (e.g., `RBI_2024-25_67.pdf`)

**Directories:**
- `snake_case/` for all package directories
- Each directory is a Python package with `__init__.py`

**Classes:**
- `PascalCase` — e.g., `ChunkMetadata`, `QueryResponse`, `GateFiredResponse`, `AuditRecord`, `TextBlock`, `ExtractedDocument`

**Functions:**
- `snake_case` — e.g., `scrape_index()`, `chunk_document()`, `index_documents()`, `get_chroma_store()`
- Private helpers prefixed with `_` — e.g., `_parse_date()`, `_normalize_circular_id()`, `_fetch_pdf_url()`, `_embeddings()`, `_splitter()`

**Environment Variables:**
- `SCREAMING_SNAKE_CASE` — e.g., `GOOGLE_API_KEY`, `CHROMA_PERSIST_DIR`, `CONFIDENCE_THRESHOLD`

**Database:**
- `snake_case` plural table names — `query_audit_log`

## Where to Add New Code

**New scraper target (additional regulator — out of scope for v1 but future):**
- Scraper: `scraper/{regulator}_scraper.py`
- Extend `RawCircularMetadata` in `models/chunk.py` if new metadata fields needed
- Add pipeline entry in `ingestion/pipeline.py` under a new `--source` argument

**New API endpoint:**
- Route: `api/routes/{resource}.py`
- Pydantic schemas: `models/{resource}.py`
- Register route in `api/main.py`

**New retrieval strategy:**
- Implementation: `retrieval/{strategy_name}_retriever.py`
- Keep the interface consistent with what `chain/` expects

**New Alembic migration:**
- Generate: `alembic revision --autogenerate -m "description"` from `db/` directory
- Migration files land in `db/migrations/versions/`

**Utility scripts:**
- One-off scripts: `scripts/{descriptive_name}.py`
- Do not import from `scripts/` in other modules

**New tests:**
- Unit (no I/O): `tests/unit/test_{module}.py`
- Integration (real Chroma/DB): `tests/integration/test_{feature}.py`
- E2E (full stack): `tests/e2e/test_{flow}.py`

## Special Directories

**`data/`:**
- Purpose: Chroma persistence, downloaded PDFs, quarantine JSONL
- Generated: Yes (at runtime)
- Committed: No (`.gitignore` excludes it)
- Action required: Wipe `data/chroma/` before Phase 2 to avoid stale duplicate embeddings

**`.planning/`:**
- Purpose: GSD workflow planning artifacts and codebase analysis documents
- Generated: Yes (by GSD tooling)
- Committed: Yes

**`.git/`:**
- Purpose: Git version control
- Generated: Yes
- Committed: N/A

---

*Structure analysis: 2026-04-11*
