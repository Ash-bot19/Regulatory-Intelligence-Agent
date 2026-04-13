"""
FastAPI application entry point.

Usage:
    uvicorn api.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

from api.routes import router  # noqa: E402 — must import after load_dotenv
from monitoring.metrics import metrics_app  # noqa: E402

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background scheduler in non-local environments
    scheduler = None
    if os.environ.get("ENV", "local") != "local":
        from scheduler.freshness import make_scheduler
        scheduler = make_scheduler(background=True)
        scheduler.start()
        logger.info("scheduler_started")

    yield

    if scheduler is not None:
        scheduler.shutdown()
        logger.info("scheduler_stopped")


app = FastAPI(
    title="Regulatory Intelligence Agent",
    description="RBI circular RAG system with confidence gating and citation grounding",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")
app.mount("/metrics", metrics_app())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
