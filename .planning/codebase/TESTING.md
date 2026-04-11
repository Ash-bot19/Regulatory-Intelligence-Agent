# Testing Patterns

**Analysis Date:** 2026-04-11

## Test Framework

**Runner:**
- `pytest` 8.2.2
- No config file detected (`pytest.ini`, `pyproject.toml`, `setup.cfg` absent) — pytest runs with defaults, discovered by `test_` prefix
- Cache directory: `.pytest_cache/` (committed, standard)

**Assertion Library:**
- pytest built-in `assert` — no separate assertion library

**Run Commands:**
```bash
# Run all tests (from project root)
pytest tests/

# Run only unit tests
pytest tests/unit/

# Run a specific test file
pytest tests/unit/test_chunker.py

# Verbose output
pytest tests/unit/ -v

# Coverage (requires pytest-cov, not currently in requirements.txt)
# Not configured yet
```

**Async Support:**
- `pytest-asyncio` 0.23.7 is installed but no async tests exist yet (reserved for Phase 3+ API tests)
- `httpx` 0.27.0 installed for async HTTP testing of FastAPI endpoints (Phase 3)

## Test File Organization

**Location:**
- Separate `tests/` directory at project root — not co-located with source modules
- Subdirectory per test type: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- `__init__.py` in `tests/` and `tests/unit/` (empty, for import resolution)

**Naming:**
- Files: `test_{module_name}.py` — `test_chunker.py`, `test_scraper_parsing.py`
- Test classes: `Test{ClassName}` — `TestChunkDocument`, `TestParseDate`, `TestNormalizeCircularId`
- Test methods: `test_{behavior_description}` — `test_returns_empty_on_failed_extraction`, `test_chunk_has_required_metadata_fields`

**Structure:**
```
tests/
├── __init__.py
├── unit/
│   ├── __init__.py
│   ├── test_chunker.py          # tests for ingestion/chunker.py
│   └── test_scraper_parsing.py  # tests for scraper/rbi_scraper.py helpers
├── integration/                 # directory exists, empty (not yet implemented)
└── e2e/                         # directory exists, empty (not yet implemented)
```

## Test Structure

**Suite Organization:**
```python
"""Module docstring explaining what is tested and what is NOT required (e.g. no network)."""

import pytest
from models.chunk import RawCircularMetadata
from ingestion.chunker import chunk_document


# Module-level shared fixtures built as plain constants or helper functions
SAMPLE_META = RawCircularMetadata(...)

def _make_extracted(text: str, failed: bool = False) -> ExtractedDocument:
    """Factory helper — underscore prefix, not a pytest fixture."""
    ...


class TestChunkDocument:
    def test_returns_empty_on_failed_extraction(self):
        ...

    def test_chunk_has_required_metadata_fields(self):
        ...
```

**Patterns:**
- Tests grouped into classes by the subject under test (one class per public function or logical group)
- No `setUp`/`tearDown` — test state built inline or via module-level factory functions
- No `conftest.py` exists yet — fixtures are local factory helpers with `_` prefix
- Each test method has a single, specific behavioral assertion

## Mocking

**Framework:** None currently — no `unittest.mock`, `pytest-mock`, or `MagicMock` in any test file

**Current approach:**
- Tests avoid mocking by testing only pure/deterministic logic that requires no network or file I/O
- `test_scraper_parsing.py` tests private helpers `_parse_date` and `_normalize_circular_id` directly — no HTTP calls
- `test_chunker.py` builds `ExtractedDocument` and `TextBlock` instances manually — no PDF files needed
- I/O-dependent code (scraper network calls, PDF file reads, Chroma indexing) has no unit tests yet

**What to mock when integration tests are added:**
- `requests.Session.get` — mock with `unittest.mock.patch` or `responses` library for scraper tests
- `fitz.open` — mock for PDF extractor tests
- `Chroma.add_documents` — mock for indexer tests
- PostgreSQL writes — use a test database or mock `psycopg2` connection

## Fixtures and Factories

**Test Data:**
```python
# Module-level constant — shared across all tests in the file
SAMPLE_META = RawCircularMetadata(
    circular_id="RBI/2024-25/67",
    circular_title="Test Circular",
    effective_date=date(2024, 9, 1),
    pdf_url="https://example.com/test.pdf",
    scraped_at=datetime(2024, 10, 1, 12, 0, 0),
)

# Private factory function for building complex objects
def _make_extracted(text: str, failed: bool = False) -> ExtractedDocument:
    doc = ExtractedDocument(circular_id="RBI/2024-25/67")
    if failed:
        doc.extraction_failed = True
        doc.failure_reason = "test_failure"
    else:
        doc.blocks = [TextBlock(text=text, page_number=1, clause_ref="4.2", block_index=0)]
    return doc
```

**Location:**
- Fixtures/factories defined at module level in the test file that uses them
- No shared `conftest.py` — add one when fixtures need to be shared across test files

## Coverage

**Requirements:** Not enforced — no coverage threshold configured, `pytest-cov` not in `requirements.txt`

**Current coverage state:**
- `ingestion/chunker.py`: covered by `tests/unit/test_chunker.py` (4 tests)
- `scraper/rbi_scraper.py` (helpers only): covered by `tests/unit/test_scraper_parsing.py` (10 tests)
- `scraper/rbi_scraper.py` (network paths): not tested
- `scraper/pdf_extractor.py`: not tested
- `ingestion/indexer.py`: not tested
- `ingestion/quarantine.py`: not tested
- `ingestion/pipeline.py`: not tested
- `models/*.py`: not directly tested (validated via chunker tests)
- `retrieval/`, `chain/`, `api/`, `audit/`, `scheduler/`, `ui/`: not yet implemented

## Test Types

**Unit Tests (`tests/unit/`):**
- Scope: single function or class, no I/O, no network, no filesystem
- What is tested: pure logic — date parsing, circular ID normalization, chunking behavior, metadata propagation
- What is explicitly excluded: anything requiring network (`no network calls` stated in docstrings)

**Integration Tests (`tests/integration/`):**
- Directory exists, no tests yet
- Intended for: full scrape → extract → chunk → index pipeline with a real (or mocked) Chroma store
- Likely pattern: spin up test Chroma instance in a temp dir, run `run_pipeline(limit=5)`, assert chunk counts

**E2E Tests (`tests/e2e/`):**
- Directory exists, no tests yet
- Intended for: FastAPI endpoint tests using `httpx.AsyncClient` against a running app with test DB
- `pytest-asyncio` and `httpx` already installed for this purpose

## Common Patterns

**Testing behavior, not implementation:**
```python
# Tests assert on observable output (return value, metadata fields)
# — never on internal state or call counts
def test_chunk_has_required_metadata_fields(self):
    chunks = chunk_document(doc, SAMPLE_META)
    meta = chunks[0].metadata
    assert meta["source"] == "RBI"
    assert meta["circular_id"] == "RBI/2024-25/67"
    assert "effective_date" in meta
```

**Failure path testing:**
```python
# Explicit test for failure/edge-case inputs
def test_returns_empty_on_failed_extraction(self):
    doc = _make_extracted("", failed=True)
    result = chunk_document(doc, SAMPLE_META)
    assert result == []

def test_unparseable_returns_none(self):
    assert _parse_date("not a date") is None
```

**Sequential assertion on ordered output:**
```python
def test_chunk_indices_are_sequential(self):
    chunks = chunk_document(doc, SAMPLE_META)
    indices = [c.metadata["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))
```

**Async Testing (planned, not yet implemented):**
```python
import pytest
import httpx

@pytest.mark.asyncio
async def test_query_endpoint_returns_citations():
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/query", json={"query": "KYC PPI requirements"})
    assert response.status_code == 200
    body = response.json()
    assert "citations" in body
    assert body["confidence_score"] >= 0.72
```

## Missing Test Infrastructure

**No `conftest.py`:** Add one at `tests/conftest.py` when shared fixtures are needed (e.g. temp Chroma dir, test DB connection, sample PDF bytes).

**No pytest markers:** No `@pytest.mark.slow`, `@pytest.mark.integration`, etc. — add these when integration/e2e tests are created to allow selective running.

**No coverage enforcement:** Add `pytest-cov` to `requirements.txt` and a `[tool.pytest.ini_options]` section to `pyproject.toml` (or `pytest.ini`) with `--cov=. --cov-fail-under=80` when Phase 3 work begins.

---

*Testing analysis: 2026-04-11*
