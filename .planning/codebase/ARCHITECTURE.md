# Architecture

**Analysis Date:** 2026-04-11

## Pattern Overview

**Overall:** Sequential pipeline with confidence-gated RAG chain

**Key Characteristics:**
- Strict unidirectional pipeline: scrape → extract → chunk → embed → index
- Confidence gate (threshold 0.72) sits between retrieval and LLM — LLM is never called if gate fires
- All citations derived deterministically from chunk metadata; LLM produces only narrative text
- Append-only audit log for every request, including gate-fired ones where LLM is never invoked
- Two vector store backends (Chroma local, Pinecone prod) behind the same `index_documents` / `get_*_store` interface

## Layers

**Scraping Layer:**
- Purpose: Fetch RBI circular index, resolve detail pages, download PDFs, produce metadata
- Location: `scraper/`
- Contains: `rbi_scraper.py` (HTTP + HTML parsing), `pdf_extractor.py` (PyMuPDF block extraction)
- Depends on: `models/chunk.py` (RawCircularMetadata)
- Used by: `ingestion/pipeline.py`

**Ingestion / Pipeline Layer:**
- Purpose: Orchestrate the full scrape → extract → chunk → index pipeline; quarantine failures
- Location: `ingestion/`
- Contains: `pipeline.py` (entry point), `chunker.py` (RecursiveCharacterTextSplitter), `indexer.py` (Chroma/Pinecone), `quarantine.py` (JSONL failure log)
- Depends on: `scraper/`, `models/`
- Used by: CLI (`python -m ingestion.pipeline`) and the freshness scheduler (not yet built)

**Models Layer:**
- Purpose: Pydantic schema definitions shared across all layers — no business logic
- Location: `models/`
- Contains: `chunk.py` (ChunkMetadata, RawCircularMetadata), `response.py` (QueryResponse, CitationRecord, GateFiredResponse), `audit.py` (AuditRecord)
- Depends on: nothing (pure Pydantic)
- Used by: all layers

**Retrieval Layer (stub — Phase 2):**
- Purpose: MMR retriever (k=6, lambda=0.3) over indexed vector store; returns top-k chunks with similarity scores
- Location: `retrieval/` (empty — not yet implemented)
- Planned depends on: `ingestion/indexer.py` (store access), `models/`

**Chain Layer (stub — Phase 2):**
- Purpose: LCEL RAG chain — passes retrieved chunks to LLM, maps chunk metadata to citations, builds QueryResponse
- Location: `chain/` (empty — not yet implemented)
- Planned depends on: `retrieval/`, `models/`

**API Layer (stub — Phase 3):**
- Purpose: FastAPI POST /query endpoint, confidence gate middleware, request routing
- Location: `api/` (empty — not yet implemented)
- Planned depends on: `chain/`, `audit/`, `models/`

**Audit Layer (stub — Phase 3):**
- Purpose: Append-only write to PostgreSQL `query_audit_log` for every request
- Location: `audit/` (empty — not yet implemented)
- Planned depends on: `models/audit.py`, PostgreSQL via SQLAlchemy

**Scheduler Layer (stub — Phase 4):**
- Purpose: APScheduler nightly delta re-index at 02:00 IST — diffs scraped_at, skips already-indexed circulars
- Location: `scheduler/` (empty — not yet implemented)
- Planned depends on: `ingestion/pipeline.py`

**UI Layer (stub — Phase 4):**
- Purpose: Streamlit front-end — query input, answer + citations display, fallback message rendering
- Location: `ui/` (empty — not yet implemented)

## Data Flow

**Ingestion Pipeline (implemented):**

1. `python -m ingestion.pipeline --source rbi` invokes `run_pipeline()` in `ingestion/pipeline.py`
2. `scraper.rbi_scraper.scrape_index()` fetches RBI index page, resolves each circular's detail page, returns `list[RawCircularMetadata]`
3. `scraper.rbi_scraper.download_all()` downloads PDFs to `data/pdfs/` (named `{circular_id_underscored}.pdf`)
4. For each PDF: `scraper.pdf_extractor.extract_text()` produces `ExtractedDocument` with `list[TextBlock]`; on failure, `ingestion.quarantine.quarantine()` writes to `data/quarantine.jsonl`
5. `ingestion.chunker.chunk_document()` runs `RecursiveCharacterTextSplitter` over each text block; each sub-chunk is validated as `ChunkMetadata` — validation failure skips that chunk only (does not quarantine the document)
6. `ingestion.indexer.index_documents()` batches all `LangChain Document` objects into Chroma (local) or Pinecone (prod) in batches of 100 with 429-rate-limit retry (60s base backoff)

**Query Path (planned — Phases 2–3):**

1. Client sends POST /query to FastAPI (`api/`)
2. Confidence gate middleware computes top-chunk similarity score from MMR retrieval (`retrieval/`)
3. If score < 0.72: audit log written with `gate_fired=True`, `GateFiredResponse` returned, LLM never called
4. If score >= 0.72: LCEL chain (`chain/`) calls LLM with retrieved chunk text; citation mapper reads chunk metadata (not LLM output) to build `CitationRecord` list; `QueryResponse` returned
5. Audit log written with full response, chunk IDs, score, and LLM output

**State Management:**
- Vector index state: persisted in `data/chroma/` (Chroma local) or Pinecone index (prod)
- Quarantine state: append-only JSONL at `data/quarantine.jsonl`
- Audit state: append-only PostgreSQL table `query_audit_log`
- No in-memory global state; pipeline is stateless between runs

## Key Abstractions

**RawCircularMetadata:**
- Purpose: Carries scraper-stage metadata (id, title, date, pdf_url, scraped_at) before PDF parsing
- File: `models/chunk.py`
- Pattern: Pydantic BaseModel, produced by `scraper/rbi_scraper.py`, consumed by `ingestion/chunker.py`

**ChunkMetadata:**
- Purpose: The complete metadata contract every indexed chunk must satisfy — enforced by Pydantic validator (`circular_id` must start with "RBI/")
- File: `models/chunk.py`
- Pattern: Pydantic BaseModel; `.model_dump(mode="json")` used as LangChain Document metadata dict

**ExtractedDocument / TextBlock:**
- Purpose: Intermediate representation between PDF parsing and chunking; carries per-block clause refs detected via regex
- File: `scraper/pdf_extractor.py`
- Pattern: Python dataclasses (not Pydantic) — internal to scraper layer only

**QueryResponse / GateFiredResponse:**
- Purpose: API response contract — citations always present, confidence_score always present, gate_fired on fallback
- File: `models/response.py`
- Pattern: Pydantic BaseModel; GateFiredResponse has hardcoded fallback text (must not be altered)

**Quarantine:**
- Purpose: Non-blocking failure recording — documents that fail extraction or produce zero chunks are appended to a JSONL file and excluded from the index without crashing the pipeline
- File: `ingestion/quarantine.py`
- Pattern: Append-only JSONL writer; `list_quarantined()` for inspection

## Entry Points

**Ingestion CLI:**
- Location: `ingestion/pipeline.py` (`__main__` block)
- Triggers: `python -m ingestion.pipeline --source rbi [--year N] [--limit N] [--dry-run]`
- Responsibilities: Full pipeline from scrape to index; returns stats dict

**FastAPI App (planned):**
- Location: `api/` (not yet created)
- Triggers: `uvicorn api.main:app --reload --port 8000`
- Responsibilities: POST /query endpoint, confidence gate middleware, response serialization

**Streamlit UI (planned):**
- Location: `ui/app.py` (not yet created)
- Triggers: `streamlit run ui/app.py`
- Responsibilities: Query form, result display, citation rendering, gate-fired fallback message

**Freshness Scheduler (planned):**
- Location: `scheduler/` (not yet created)
- Triggers: APScheduler at 02:00 IST
- Responsibilities: Delta scrape (diff on scraped_at), re-index new circulars only

## Error Handling

**Strategy:** Fail-narrow — individual document failures never abort the pipeline; they are quarantined and logged

**Patterns:**
- HTTP fetch failures: retry up to 3 times with exponential backoff; raise `RuntimeError` after limit — caught by `download_all()` which logs and continues
- PDF open/extraction failure: `extraction_failed=True` set on `ExtractedDocument`; caller in `pipeline.py` calls `quarantine()` and increments `stats["quarantined"]`
- Chunk metadata validation failure: individual chunk is skipped (logged); sibling chunks from same document continue — document is not quarantined
- Embedding rate limit (429): `index_documents()` retries up to 4 times with 60s base backoff per batch
- Scheduler failures (planned): log error, skip run, alert via console — never swallow silently

## Cross-Cutting Concerns

**Logging:** `structlog` throughout — no `print()` anywhere. Structured key=value events (e.g., `pipeline_start`, `batch_indexed`, `document_quarantined`). Logger instantiated per module with `structlog.get_logger(__name__)`.

**Validation:** Pydantic v2 for all inter-layer data contracts. Internal scraper dataclasses (`TextBlock`, `ExtractedDocument`) are Python dataclasses — not exposed outside `scraper/`.

**Authentication:** Not implemented in v1. No auth middleware planned for MVP.

**Configuration:** `python-dotenv` — all secrets and tunables in `.env`. No hardcoded credentials. Key env vars: `GOOGLE_API_KEY`, `GROQ_API_KEY`, `PINECONE_API_KEY`, `POSTGRES_PASSWORD`, `CHROMA_PERSIST_DIR`, `CONFIDENCE_THRESHOLD`.

**Idempotency:** PDF downloader checks if file already exists before downloading (`dest_path.exists()`). Chroma does not deduplicate on re-run — `data/chroma/` must be wiped before Phase 2 to avoid duplicate retrieval results.

---

*Architecture analysis: 2026-04-11*
