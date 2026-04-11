# Codebase Concerns

**Analysis Date:** 2026-04-11

---

## Tech Debt

**Embedding model mismatch between spec and implementation:**
- Issue: CLAUDE.md specifies `text-embedding-3-small` (OpenAI, 1536-dim). The actual implementation uses `models/gemini-embedding-001` (Google Gemini, 768-dim). The CLAUDE.md "Known Gotchas" section documents this switch but the locked contract section was never updated. Any Phase 2 code written to expect OpenAI embeddings (dimension, normalization behavior) will be wrong.
- Files: `ingestion/indexer.py` (line 18), `requirements.txt` (no openai package present)
- Impact: Retrieval quality and confidence score calibration differ between documented spec and live system. Breaks dimension assumptions if someone switches vector stores.
- Fix approach: Update the "Embedding" section in CLAUDE.md to reflect Gemini as the locked choice, remove `text-embedding-3-small` references entirely.

**`print()` used in pipeline `__main__` block:**
- Issue: `ingestion/pipeline.py` line 140 calls `print(result)` — direct violation of the coding rule "Never use print() — use structlog for all logging."
- Files: `ingestion/pipeline.py` (line 140)
- Impact: Minor — only fires when run as CLI. But it sets a bad precedent and breaks structured log pipelines (e.g., Prometheus log scraping, JSON log aggregation).
- Fix approach: Replace `print(result)` with `logger.info("pipeline_result", **result)`.

**Deprecated `datetime.utcnow()` usage:**
- Issue: `datetime.utcnow()` is deprecated since Python 3.12 and will be removed. Both scraper and quarantine use it.
- Files: `scraper/rbi_scraper.py` (line 123), `ingestion/quarantine.py` (line 34)
- Impact: Generates deprecation warnings on Python 3.12+. Timezone-naive datetimes also create subtle comparison bugs if any downstream code uses timezone-aware datetimes (e.g., PostgreSQL `TIMESTAMPTZ` columns).
- Fix approach: Replace with `datetime.now(UTC)` (requires `from datetime import UTC`) or `datetime.now(timezone.utc)`.

**`load_dotenv()` only called in `__main__` block:**
- Issue: `ingestion/pipeline.py` calls `load_dotenv()` only inside the `if __name__ == "__main__"` block (lines 121–122). When the pipeline is imported as a module (e.g., by the scheduler or tests), env vars are not loaded. `ingestion/indexer.py` immediately crashes on `os.environ["GOOGLE_API_KEY"]` (line 24) with a `KeyError` if dotenv was not loaded by the caller.
- Files: `ingestion/pipeline.py` (line 121), `ingestion/indexer.py` (line 24)
- Impact: Any non-CLI caller of the pipeline or indexer must independently call `load_dotenv()` or set env vars manually. The scheduler (not yet built) will hit this.
- Fix approach: Move `load_dotenv()` to module-level in `ingestion/pipeline.py`, or better, create a `config.py` using `pydantic-settings` `BaseSettings` that loads from env at import time.

**`os.environ["KEY"]` direct access — no graceful failure on missing secrets:**
- Issue: `ingestion/indexer.py` uses `os.environ["GOOGLE_API_KEY"]` and `os.environ["PINECONE_API_KEY"]` (lines 24, 47) — hard `KeyError` crash if keys are absent. No validation at startup; failure happens at call time during indexing, potentially mid-batch.
- Files: `ingestion/indexer.py` (lines 24, 47)
- Impact: Silent partial indexing failure — the pipeline may process 50 of 100 circulars, then crash on first embed call, with no clear error surfaced to the operator.
- Fix approach: Use `pydantic-settings` `BaseSettings` with required fields. Validated at import time, fails fast with a clear message before any pipeline work begins.

**`camelot-py` dependency is dead weight:**
- Issue: `camelot-py==0.11.0` is in `requirements.txt` but is not imported or used anywhere in the current codebase. It requires `ghostscript` as a system dependency, which is non-trivial to install in Docker.
- Files: `requirements.txt` (line 8)
- Impact: Inflates Docker image, adds a system dependency that must be present at build time, introduces a potential install failure on Alpine-based images.
- Fix approach: Remove from `requirements.txt` until table extraction is actually needed. Document it in CLAUDE.md as "deferred to post-v1."

**Chroma deduplication not implemented:**
- Issue: The indexer has no dedup logic. As documented in CLAUDE.md Known Gotchas: "data/chroma accumulates duplicates across pipeline re-runs." Every re-run adds duplicate chunk embeddings without checking if a `circular_id + chunk_index` combination already exists.
- Files: `ingestion/indexer.py` (`index_documents` function)
- Impact: Duplicate retrieval results degrade answer quality. Six retrieved chunks for a query could be six duplicates from the same source, breaking the MMR diversity rationale.
- Fix approach: Before indexing a batch, query Chroma by `circular_id` metadata filter and skip chunks that already exist. Alternatively, use Chroma's `upsert` with deterministic IDs constructed from `circular_id + chunk_index`.

---

## Known Bugs

**`page_num` variable undefined when PDF has no extractable blocks:**
- Symptoms: `pdf_extractor.py` line 127 references `page_num` in the final `logger.info` call: `pages=page_num if doc.blocks else 0`. If the PDF has zero text blocks, `doc.blocks` is empty and the ternary returns 0 — but `page_num` is defined only inside the `for page_num, page in enumerate(pdf)` loop. If the PDF has zero pages (malformed PDF that opens but is empty), the loop never executes, and `page_num` is an `UnboundLocalError`.
- Files: `scraper/pdf_extractor.py` (line 127)
- Trigger: Open a valid but zero-page PDF file through the pipeline.
- Workaround: The `if not doc.blocks` branch catches legitimate empty PDFs and marks `extraction_failed=True` before the logger call, so in practice `page_num` is always defined when doc.blocks is non-empty. However the code is fragile — a PDF with pages but all-image blocks (no text block type 0) will also produce empty `doc.blocks`, and at that point the ternary goes to `0` without attempting to read `page_num`. This masks a real `UnboundLocalError` risk on truly empty PDFs.
- Fix approach: Initialize `page_num = 0` before the loop.

**`year_filter` string matching is imprecise:**
- Symptoms: `scraper/rbi_scraper.py` line 169 filters with `if str(year_filter) not in circular_id`. Passing `year_filter=20` would match all circulars (since "20" appears in "2024-25"). Passing `year_filter=2026` matches both "2026-27" and "2026-2027" (the format seen in downloaded PDFs `RBI_2026-2027_*.pdf`).
- Files: `scraper/rbi_scraper.py` (lines 168–169)
- Trigger: Any non-standard fiscal year integer input, or future RBI ID format changes.
- Fix approach: Match against a regex like `r"RBI/(?:\w+/)?{year}-" ` to anchor to the fiscal year start in the circular ID structure.

---

## Security Considerations

**No rate limiting or input validation on future API layer:**
- Risk: The API layer (`api/` directory) does not exist yet. When built, POST /query with no input length cap, no rate limiting, and no authentication means an unauthenticated caller can flood the embedding service (Gemini free tier: 100 RPM), exhaust the Groq free tier quota, and fill the audit log with garbage.
- Files: `api/` (not yet built)
- Current mitigation: None — the API does not exist.
- Recommendations: Add `slowapi` rate limiting middleware, enforce `max_length` on `query_text` in the Pydantic request model, add basic API key header check as a stop-gap before auth is considered for v2.

**Browser User-Agent spoofing:**
- Risk: The scraper uses a Chrome browser User-Agent string and sets `Referer: https://www.rbi.org.in/` to bypass bot detection (lines 25–32 in `rbi_scraper.py`). This is a terms-of-service gray area. If RBI adds more sophisticated fingerprinting (TLS fingerprint, cookie challenge), this breaks silently — the scraper gets 200 responses with CAPTCHA HTML instead of content, producing garbled chunks that pass extraction.
- Files: `scraper/rbi_scraper.py` (lines 25–32)
- Current mitigation: None — no HTML content validation after fetch.
- Recommendations: Add a post-fetch content check: if the response body contains "CAPTCHA" or lacks expected table structure, treat as a failed scrape rather than parsing garbage HTML.

**`.env` file not confirmed gitignored for all patterns:**
- Risk: `.gitignore` gitignores `.env` but not `.env.local`, `.env.production`, or `.env.backup` variants. The `.env.example` file is committed (correct), but any developer who creates `.env.local` would not be covered.
- Files: `.gitignore` (line 1)
- Current mitigation: `.env` is gitignored.
- Recommendations: Expand to `.env.*` pattern in `.gitignore`.

---

## Performance Bottlenecks

**Sequential scraping with no parallelism:**
- Problem: `scrape_index` fetches every detail page sequentially with a 0.5s polite delay (line 205 in `rbi_scraper.py`), and `download_all` downloads all PDFs sequentially with a 1.0s delay. For a full corpus (hundreds of circulars), this is a multi-hour operation.
- Files: `scraper/rbi_scraper.py` (`scrape_index` lines 136–212, `download_all` lines 249–280)
- Cause: Intentional politeness delay + no async I/O or thread pool.
- Improvement path: Use `concurrent.futures.ThreadPoolExecutor` with bounded concurrency (2–3 workers) to parallelize detail page fetches and downloads while remaining polite. For the scheduler's nightly delta run, this matters less since only new circulars are fetched.

**Embedding batching burns free tier quota in 60-second stalls:**
- Problem: The indexer's retry backoff for Gemini 429 errors is 60 seconds × attempt number (lines 59, 106 in `indexer.py`). With `batch_size=100`, every batch after the first triggers a 60s wait. For 712 chunks (the current smoke test count), that is 7 batches × 60s = 7 minutes of idle stalls in a best case.
- Files: `ingestion/indexer.py` (lines 59, 98–105)
- Cause: Free tier is 100 RPM — 100 embed requests per minute — and batch_size matches the RPM cap exactly, leaving no headroom.
- Improvement path: Reduce `batch_size` to 80–90 to stay under the 100 RPM cap, or implement token bucket pacing instead of reactive retry.

**Full corpus re-index on every pipeline run (no incremental check):**
- Problem: The pipeline has no mechanism to detect previously indexed circulars before the scrape stage. Even with `download_pdf` skipping already-downloaded PDFs (line 231 in `rbi_scraper.py`), the extract → chunk → index stages still run on every circular that has a local PDF.
- Files: `ingestion/pipeline.py` (`run_pipeline` function)
- Cause: No circular-level "already indexed" check in Chroma before processing.
- Improvement path: Query Chroma for existing `circular_id` values before stage 3 and skip those. This is the same fix as the deduplication concern above.

---

## Fragile Areas

**Entire Phase 2–5 architecture does not exist yet:**
- Files: `retrieval/`, `chain/`, `api/`, `audit/`, `scheduler/`, `db/`, `ui/`, `monitoring/`, `scripts/` — all empty directories
- Why fragile: The confidence gate, audit log, RAG chain, and freshness scheduler are documented contracts but have zero implementation. Any integration work between Phase 1 outputs (Chroma + chunk metadata) and Phase 2 inputs (MMR retriever) must handle the Gemini embedding dimension (768) vs the OpenAI dimension (1536) that some LangChain MMR examples assume.
- Safe modification: Do not change the Chroma collection name, embedding model, or metadata schema in Phase 1 before Phase 2 retriever is wired — changes will require a full re-index.
- Test coverage: No retrieval, chain, API, or scheduler tests exist.

**RBI HTML structure assumed stable:**
- Files: `scraper/rbi_scraper.py` (`scrape_index` lines 130–211)
- Why fragile: The scraper hardcodes column positions (cells[0], cells[1], cells[3]) and assumes a 5-column table. RBI has restructured this page historically. Any column reordering or table redesign silently produces wrong metadata (wrong date in `circular_id` field, wrong title) rather than failing loudly.
- Safe modification: Add an assertion or content-type check on cell[0] to confirm it contains an "RBI/" pattern before extracting other fields. Currently a header row or layout row with 4+ cells could be partially parsed.
- Test coverage: Unit tests for `_parse_date` and `_normalize_circular_id` exist, but there are no tests for `scrape_index` table parsing with malformed or rearranged columns.

**Quarantine file is not idempotent:**
- Files: `ingestion/quarantine.py` (`quarantine` function)
- Why fragile: The quarantine JSONL is append-only with no dedup. Re-running the pipeline on a document that previously failed appends a second quarantine record for the same `circular_id`. This is minor but means `list_quarantined()` returns duplicates, which could confuse any future tooling that uses it to drive re-processing.
- Safe modification: Before appending, check if the `circular_id` is already present.
- Test coverage: No tests for quarantine deduplication behavior.

**`_fetch_pdf_url` pattern match is case-sensitive only for `.PDF`:**
- Files: `scraper/rbi_scraper.py` (line 96): `href.upper().endswith(".PDF")`
- Why fragile: The code uppercases the href before checking `.PDF`. However, the `"rbidocs.rbi.org.in" in href` check is case-sensitive on the domain. If RBI changes to lowercase `.pdf` extensions (which some circulars use), the `.upper()` handles it. But if the domain or path casing changes, the domain check fails silently and the circular is skipped with a warning rather than erroring.
- Safe modification: Use `href.lower()` consistently for both checks.

---

## Scaling Limits

**Chroma local persistence is not production-grade:**
- Current capacity: In-process Chroma (`data/chroma/`) — single process, no replication, no concurrent write safety.
- Limit: Breaks under any concurrent write scenario (e.g., scheduler running a delta index while the API is serving queries that trigger Chroma reads). Chroma's SQLite backend has a single-writer lock.
- Scaling path: Migrate to Pinecone for prod (already provisioned in `get_pinecone_store()`), or run Chroma in server mode.

**Gemini free tier: 100 embed requests/minute hard cap:**
- Current capacity: 100 RPM, batch_size=100 → effectively 1 batch/minute.
- Limit: A full corpus of 500 circulars × ~142 chunks each = ~71,000 chunks → 710 batches → ~12 hours of indexing.
- Scaling path: Upgrade to paid Gemini tier, or switch to a self-hosted embedding model (e.g., `nomic-embed-text` via Ollama) for bulk indexing.

---

## Dependencies at Risk

**`pinecone-client==3.2.2` with `langchain_community.vectorstores.Pinecone`:**
- Risk: `langchain-community`'s Pinecone integration (`langchain_community.vectorstores.Pinecone`) is deprecated in favor of `langchain-pinecone`. The `pinecone-client` package was also renamed to `pinecone` in v3+. The current combination of `pinecone-client==3.2.2` and `langchain_community.vectorstores.Pinecone` may not be compatible — `langchain-community==0.2.6` expects the older `pinecone-client` API surface.
- Files: `ingestion/indexer.py` (lines 44–55), `requirements.txt` (line 19)
- Impact: `get_pinecone_store()` may crash at first use in the demo environment. This function is untested.
- Migration plan: Replace with `langchain-pinecone` package and `from langchain_pinecone import PineconeVectorStore`.

**`langchain==0.2.6` is a pinned old minor:**
- Risk: LangChain's LCEL API had significant changes between 0.2.x and 0.3.x. `langchain.schema.Document` and `langchain.text_splitter` imports used in the codebase were moved in 0.3+. The current pin works but upgrading for any reason will require import path migration.
- Files: `requirements.txt` (line 12), `ingestion/chunker.py` (lines 11–12), `ingestion/indexer.py` (line 12)
- Impact: Version constraint conflicts if any dependency pulls in langchain 0.3+.
- Migration plan: When Phase 2 chain is built, audit all `langchain.*` imports and migrate to the 0.3 namespace (`langchain_core`, `langchain_text_splitters`) to avoid a forced migration later.

---

## Missing Critical Features

**No integration or e2e tests:**
- Problem: `tests/integration/` and `tests/e2e/` directories exist but are empty. The only integration validation is a manual smoke test documented in CLAUDE.md.
- Blocks: Cannot verify that scraper → extractor → chunker → indexer → retriever chain works end-to-end without running the full pipeline against the live RBI website.
- Priority: High — the confidence gate correctness (0.72 threshold, no LLM call when gate fires) cannot be verified without integration tests.

**No `conftest.py` or pytest configuration:**
- Problem: No `conftest.py` at root or test level. No `pytest.ini`, `pyproject.toml`, or `setup.cfg` with `[tool.pytest.ini_options]`. This means `pytest-asyncio` mode is not configured, test discovery paths are defaults, and there is no shared fixture infrastructure for future integration tests.
- Files: `tests/` directory
- Blocks: Adding async tests or shared test fixtures without first adding `conftest.py` will produce confusing pytest errors.

**No chunk-level unique ID assigned at index time:**
- Problem: Chunks have `circular_id + chunk_index` as a logical key, but no `id` field is assigned before passing to `Chroma.add_documents()`. Chroma auto-generates UUIDs, which are not deterministic. The audit log schema requires `retrieved_chunk_ids: TEXT[]`, but there is no mechanism to recover or reference these IDs from the metadata.
- Files: `ingestion/indexer.py` (`index_documents`), `ingestion/chunker.py` (`chunk_document`), `models/audit.py`
- Blocks: The audit log `retrieved_chunk_ids` field will be empty or contain opaque Chroma-generated UUIDs that cannot be cross-referenced with the chunk metadata.
- Fix approach: Construct a deterministic chunk ID as `sha256(circular_id + str(chunk_index))[:16]` and pass it explicitly to `Chroma.add_documents(ids=[...])`.

---

## Test Coverage Gaps

**Quarantine logic:**
- What's not tested: `quarantine()` function's append behavior, `list_quarantined()` with malformed JSONL lines, dedup behavior on repeated quarantine of the same circular.
- Files: `ingestion/quarantine.py`
- Risk: Silent corruption of the quarantine file if a write is interrupted.
- Priority: Low

**PDF extraction with edge cases:**
- What's not tested: Zero-page PDFs, image-only PDFs (all block type != 0), PDFs with mixed encodings, PDFs that open successfully but fail on specific pages.
- Files: `scraper/pdf_extractor.py`
- Risk: `UnboundLocalError` on `page_num` (see Known Bugs section), silent quarantine of legitimate scanned circulars without operator notification.
- Priority: Medium

**Scraper HTML parsing with malformed or rearranged table structure:**
- What's not tested: Rows with fewer than 4 columns, rows where cell[0] has no link, rows where cell[1] contains an unparseable date, detail pages that 404, detail pages that return HTML without a PDF link.
- Files: `scraper/rbi_scraper.py`
- Risk: Metadata corruption silently passes quarantine check because a row that partially parses still produces a `RawCircularMetadata` object.
- Priority: High — this is the entry point of the entire data pipeline.

**Year filter boundary conditions:**
- What's not tested: `year_filter=2026` matching "2026-2027" format seen in filenames vs "2026-27" format in circular IDs, `year_filter` with a two-digit year substring.
- Files: `scraper/rbi_scraper.py` (lines 168–169)
- Risk: Incorrect corpus scope — wrong year circulars indexed, or correct year circulars excluded.
- Priority: Medium

**Indexer retry logic:**
- What's not tested: Behavior when all 4 retry attempts fail, behavior when a non-429 exception is raised (e.g., connection timeout mid-batch), partial batch indexing count accuracy.
- Files: `ingestion/indexer.py`
- Risk: `stats["indexed"]` in the pipeline summary may be wrong if a batch fails mid-attempt, since `indexed` is only incremented on success.
- Priority: Medium

---

*Concerns audit: 2026-04-11*
