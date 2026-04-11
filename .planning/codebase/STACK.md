# Technology Stack

**Analysis Date:** 2026-04-11

## Languages

**Primary:**
- Python 3.11 — all application code (scraper, ingestion, API, UI, tests)

**Secondary:**
- SQL — PostgreSQL schema and Alembic migrations (`db/`)

## Runtime

**Environment:**
- Python 3.11.9

**Package Manager:**
- pip
- Lockfile: `requirements.txt` (pinned versions, no lockfile beyond this)

## Frameworks

**Web API:**
- FastAPI 0.111.0 — REST API layer (`api/`); not yet implemented
- Uvicorn 0.30.1 (standard extras) — ASGI server

**UI:**
- Streamlit 1.36.0 — query interface (`ui/`); not yet implemented

**RAG / LLM Orchestration:**
- LangChain 0.2.6 — LCEL chain wiring, text splitter, Document schema
- langchain-community 0.2.6 — Pinecone vectorstore wrapper
- langchain-google-genai 1.0.7 — GoogleGenerativeAIEmbeddings binding
- langchain-chroma 0.1.2 — Chroma vectorstore binding
- langchain-groq 0.1.6 — Groq LLM binding (not yet wired into chain)

**Data Validation:**
- Pydantic 2.8.2 — all models in `models/` (`ChunkMetadata`, `QueryResponse`, `AuditRecord`, etc.)
- pydantic-settings 2.3.4 — settings management

**Testing:**
- pytest 8.2.2 — test runner
- pytest-asyncio 0.23.7 — async test support
- httpx 0.27.0 — async HTTP client for FastAPI test client

**Database / ORM:**
- SQLAlchemy 2.0.31 — ORM / query builder for audit log
- Alembic 1.13.2 — migrations (`db/`)
- psycopg2-binary 2.9.9 — PostgreSQL driver

**Scheduling:**
- APScheduler 3.10.4 — nightly delta re-index job (`scheduler/`); not yet implemented

**Observability:**
- prometheus-client 0.20.0 — metrics exposition (`monitoring/`); not yet implemented
- structlog 24.2.0 — structured logging, used in every module (no `print()` anywhere)

**Build/Dev:**
- Docker + Docker Compose — local service orchestration (`docker-compose.yml`)
- python-dotenv 1.0.1 — `.env` loading

## Key Dependencies

**Critical:**
- `pymupdf==1.24.3` (`fitz`) — primary PDF text extraction from RBI circulars (`scraper/pdf_extractor.py`)
- `camelot-py==0.11.0` — table extraction from PDFs (declared, not yet used in code)
- `requests==2.31.0` + `beautifulsoup4==4.12.3` — RBI index scraping and detail page parsing (`scraper/rbi_scraper.py`)
- `lxml==5.2.1` — HTML parser backend for BeautifulSoup
- `chromadb==0.5.3` — local vector store, persisted at `./data/chroma`
- `pinecone-client==3.2.2` — production/demo vector store
- `google-generativeai==0.7.2` — underlying SDK for Gemini embedding API
- `groq==0.9.0` — underlying SDK for Groq LLM API

**Infrastructure:**
- `python-multipart==0.0.9` — multipart form data support for FastAPI

## Configuration

**Environment:**
- Loaded via `python-dotenv` from `.env` (copy from `.env.example`)
- Required variables:
  - `GOOGLE_API_KEY` — Gemini embeddings (free tier, 100 RPM cap)
  - `GROQ_API_KEY` — Groq LLM generation (free tier)
  - `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT`, `PINECONE_INDEX_NAME` — prod vector store
  - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` — audit log DB
  - `CHROMA_PERSIST_DIR` — local Chroma persistence path (default `./data/chroma`)
  - `CONFIDENCE_THRESHOLD` — gate threshold (default `0.72`)
  - `SCHEDULER_HOUR`, `SCHEDULER_MINUTE`, `SCHEDULER_TIMEZONE` — freshness job schedule
  - `ENV` — environment selector (`local` | `demo` | `prod`)

**Build:**
- `docker-compose.yml` — spins up `postgres:16-alpine` as `ria_postgres` on port 5432
- No additional build config files (no `pyproject.toml`, no `setup.cfg`, no `Makefile`)

## Platform Requirements

**Development:**
- Docker + Docker Compose for PostgreSQL
- Python 3.11
- Windows 11 / WSL2 (primary dev environment)
- `data/chroma` and `data/pdfs` dirs created at runtime (gitignored)

**Production:**
- Chroma replaced by Pinecone free tier (controlled by `ENV=demo` / `ENV=prod`)
- PostgreSQL required for audit log in all environments
- No cloud-native deployment config present in v1

---

*Stack analysis: 2026-04-11*
