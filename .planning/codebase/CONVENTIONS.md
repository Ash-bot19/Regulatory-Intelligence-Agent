# Coding Conventions

**Analysis Date:** 2026-04-11

## Naming Patterns

**Files:**
- `snake_case` for all Python module files: `rbi_scraper.py`, `pdf_extractor.py`, `chunker.py`, `quarantine.py`
- Test files prefixed with `test_`: `test_chunker.py`, `test_scraper_parsing.py`
- Internal (private) helpers prefixed with underscore: `_parse_date`, `_normalize_circular_id`, `_get_with_retry`, `_fetch_pdf_url`, `_detect_clause_ref`, `_splitter`

**Functions:**
- Public functions: `snake_case` verbs — `scrape_index`, `download_pdf`, `download_all`, `extract_text`, `chunk_document`, `index_documents`, `quarantine`, `list_quarantined`
- Private helpers: `_snake_case` — `_parse_date`, `_normalize_circular_id`, `_get_with_retry`, `_fetch_pdf_url`, `_detect_clause_ref`, `_splitter`

**Variables:**
- `snake_case` throughout: `circular_id`, `raw_meta`, `pdf_map`, `chunk_index`, `scraped_at`
- Module-level constants: `SCREAMING_SNAKE_CASE` — `CHUNK_SIZE`, `CHUNK_OVERLAP`, `SEPARATORS`, `COLLECTION_NAME`, `EMBEDDING_MODEL`, `RBI_INDEX_URL`, `REQUEST_HEADERS`, `REQUEST_TIMEOUT`, `RETRY_LIMIT`, `RETRY_BACKOFF`, `DEFAULT_QUARANTINE_PATH`
- Private module-level constants: `_RETRY_ATTEMPTS`, `_RETRY_BACKOFF_BASE`

**Types / Classes:**
- `PascalCase` for all Pydantic models and dataclasses: `ChunkMetadata`, `RawCircularMetadata`, `AuditRecord`, `CitationRecord`, `QueryResponse`, `GateFiredResponse`, `TextBlock`, `ExtractedDocument`

**Type Hints:**
- Full type annotations on all function signatures including return types
- Python 3.10+ union syntax: `str | None`, `int | None`, `list[Document]`
- Built-in generics used directly: `list[str]`, `dict[str, Path]`, `list[dict]`

## Code Style

**Formatting:**
- No formatter config file present (no `.prettierrc`, `pyproject.toml`, or `ruff.toml` detected)
- Observed style: 4-space indentation, single blank line between methods, two blank lines between top-level definitions
- String quotes: double quotes for docstrings, single or double quotes for inline strings (inconsistently, but double preferred for URLs and messages)
- Line length: approximately 88–100 chars (Black-compatible style but not enforced by config)

**Linting:**
- No linting config detected (no `.flake8`, `.pylintrc`, `ruff.toml`, or `pyproject.toml`)
- Code is clean and lint-friendly by convention; no noqa comments present

## Import Organization

**Order (observed across all source files):**
1. Standard library: `re`, `time`, `json`, `os`, `argparse`, `pathlib`, `datetime`, `dataclasses`
2. Third-party: `requests`, `structlog`, `bs4`, `fitz`, `langchain.*`, `pydantic`
3. Internal (project modules): `from models.chunk import ...`, `from scraper.pdf_extractor import ...`, `from ingestion.chunker import ...`

Blank line separates each group. No `__future__` imports.

**Path Aliases:**
- None — imports use full module paths from project root (e.g. `from models.chunk import ChunkMetadata`, not relative imports)

## Error Handling

**Patterns:**
- Network errors: caught as `requests.RequestException`, re-tried with backoff, raise `RuntimeError` after exhausting retries (`_get_with_retry` in `scraper/rbi_scraper.py`)
- PDF open failures: caught as bare `Exception`, sets `ExtractedDocument.extraction_failed = True` with `failure_reason` string — caller quarantines (`scraper/pdf_extractor.py`)
- Metadata validation failures: caught as bare `Exception` in `ingestion/chunker.py`, chunk is skipped (not quarantined), error logged
- Rate limit (429): detected by string-matching `"429"` or `"quota"` in exception message, retried with backoff in `ingestion/indexer.py`
- Downstream failures propagate via `RuntimeError` with descriptive message — never silently swallowed
- All failure branches log with `structlog` before returning/raising

**Return-on-failure pattern:**
- Functions that may partially fail return empty collections (`[]`, `{}`) rather than raising, and let the caller decide to quarantine
- Example: `chunk_document` returns `[]` on failed extraction; `scrape_index` returns partial `results` list with `skipped` count logged

## Logging

**Framework:** `structlog` — module-level logger created with `logger = structlog.get_logger(__name__)` in every module

**Patterns:**
- Use `logger.info(event_key, **context_fields)` for normal milestones
- Use `logger.warning(event_key, **context_fields)` for recoverable anomalies (missing dates, missing PDFs, unparseable fields)
- Use `logger.error(event_key, **context_fields)` for failures that cause skipping/quarantine
- Event keys are `snake_case` strings, no spaces: `"pdf_open_failed"`, `"batch_indexed"`, `"rate_limit_backoff"`, `"index_scrape_complete"`
- Context fields are keyword args, never string interpolation: `logger.error("pdf_open_failed", circular_id=..., path=..., error=str(exc))`
- `print()` is prohibited — the one exception is `pipeline.py`'s `__main__` block which prints the final stats dict

## Comments

**Module docstrings:**
- Every module has a top-level triple-quoted docstring explaining purpose, key design decisions, and usage (`ingestion/pipeline.py`, `scraper/rbi_scraper.py`, `ingestion/chunker.py`, etc.)

**Function docstrings:**
- Public functions have docstrings. Private helpers (`_parse_date`, `_normalize_circular_id`, etc.) have one-line docstrings
- Docstrings explain behavior, not implementation — what args mean, what is returned, what triggers failure
- No formal parameter documentation style (no `:param` or `Args:` sections in most functions — plain prose)

**Inline comments:**
- Used sparingly for non-obvious decisions: RBI-specific parsing quirks, magic numbers, data shape explanations
- Example: `# chars ≈ tokens * 4`, `# 0 = text block; skip image blocks`, `# polite delay between detail page requests`

## Function Design

**Size:** Functions are focused and short — longest is `scrape_index` at ~90 lines, but it is a multi-step orchestrated process with inline comments per step. All helpers are under 30 lines.

**Parameters:**
- Required args positional, optional args keyword with defaults
- `None` as default for optional IDs/filters: `year_filter: int | None = None`, `limit: int | None = None`
- Dependency injection for external objects (session, store) with `None` default causing internal construction: `session: requests.Session | None = None`

**Return Values:**
- Always typed; empty collections (`[]`, `{}`, `0`) returned on no-op rather than `None`
- Dataclass/Pydantic model instances returned for structured data
- `dict` returned for stats/summary (pipeline entry point)

## Module Design

**Exports:**
- `__init__.py` files are empty — no re-exports. All imports use full module paths.

**Barrel Files:**
- Not used. Consumers always import directly from the implementing module.

## Pydantic Usage

**All schemas in `models/`:**
- `models/chunk.py`: `ChunkMetadata`, `RawCircularMetadata`
- `models/audit.py`: `AuditRecord`
- `models/response.py`: `CitationRecord`, `QueryResponse`, `GateFiredResponse`

**Validation:**
- `@field_validator` with `@classmethod` decorator for custom field checks (e.g. `circular_id` must start with `"RBI/"`)
- `model_dump(mode="json")` used when converting to dict for LangChain Document metadata

**Dataclasses for non-validated internal structures:**
- `TextBlock` and `ExtractedDocument` in `scraper/pdf_extractor.py` use `@dataclass` since they are internal transfer objects, not API-facing schemas

## Environment & Secrets

- `python-dotenv` with `load_dotenv()` called in `__main__` blocks; never in module scope
- All secrets via `os.environ["KEY"]` with hard failure on missing key (KeyError is intentional — fail fast at startup)
- No hardcoded credentials anywhere in source

---

*Convention analysis: 2026-04-11*
