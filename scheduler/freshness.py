"""
Nightly freshness scheduler — delta re-index of new RBI circulars.

Runs at 02:00 IST (configurable via SCHEDULER_HOUR / SCHEDULER_MINUTE env vars).
Delta logic: compares scraped circular IDs against what is already in Chroma.
Only new circulars (not present in the collection) are downloaded and indexed.
Never performs a full re-index — only processes the diff.

Usage (standalone):
    python -m scheduler.freshness

The scheduler is also embedded in the FastAPI app lifespan when ENV != "local".
"""

import os
import logging
from datetime import datetime
from pathlib import Path

import structlog
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

logger = structlog.get_logger(__name__)

PDF_DIR = Path("./data/pdfs")

_CURRENT_YEAR = datetime.utcnow().year


def _get_indexed_ids() -> set[str]:
    """Return the set of circular_ids already in the Chroma collection."""
    from ingestion.indexer import get_chroma_store
    store = get_chroma_store()
    coll = store._collection
    # Fetch all metadata — only IDs, no embeddings
    result = coll.get(include=["metadatas"])
    return {m.get("circular_id") for m in result["metadatas"] if m.get("circular_id")}


def run_delta_index(year: int | None = None) -> dict:
    """
    Scrape the current year's circulars, diff against Chroma, index only new ones.

    Args:
        year: calendar year to check. Defaults to the current year.

    Returns:
        Stats dict with new_found / downloaded / indexed / quarantined counts.
    """
    from scraper.rbi_scraper import scrape_index, download_all
    from scraper.pdf_extractor import extract_text
    from ingestion.chunker import chunk_document
    from ingestion.indexer import index_documents, get_chroma_store
    from ingestion.quarantine import quarantine

    target_year = year or _CURRENT_YEAR
    stats = {"new_found": 0, "downloaded": 0, "indexed": 0, "quarantined": 0}

    logger.info("freshness_run_start", year=target_year)

    try:
        all_circulars = scrape_index(year_filter=target_year if target_year != _CURRENT_YEAR else None)
        indexed_ids = _get_indexed_ids()

        new_circulars = [c for c in all_circulars if c.circular_id not in indexed_ids]
        stats["new_found"] = len(new_circulars)
        logger.info("freshness_diff", total=len(all_circulars), new=len(new_circulars))

        if not new_circulars:
            logger.info("freshness_no_new_circulars")
            return stats

        # Download new PDFs
        pdf_map = download_all(new_circulars, dest_dir=PDF_DIR)
        stats["downloaded"] = len(pdf_map)
        meta_by_id = {c.circular_id: c for c in new_circulars}

        store = get_chroma_store()
        all_chunks = []

        for circular_id, pdf_path in pdf_map.items():
            raw_meta = meta_by_id[circular_id]
            extracted = extract_text(pdf_path, circular_id)

            if extracted.extraction_failed:
                quarantine(
                    circular_id=circular_id,
                    reason=extracted.failure_reason,
                    pdf_path=str(pdf_path),
                )
                stats["quarantined"] += 1
                continue

            chunks = chunk_document(extracted, raw_meta)
            if not chunks:
                quarantine(
                    circular_id=circular_id,
                    reason="chunking_produced_no_chunks",
                    pdf_path=str(pdf_path),
                )
                stats["quarantined"] += 1
                continue

            all_chunks.extend(chunks)

        if all_chunks:
            stats["indexed"] = index_documents(all_chunks, store=store)

        logger.info("freshness_run_complete", stats=stats)
        return stats

    except Exception as exc:
        # Never swallow silently — log error, skip run
        logger.error("freshness_run_failed", error=str(exc))
        raise


def make_scheduler(background: bool = False):
    """
    Build and return an APScheduler instance with the freshness job configured.

    Args:
        background: if True, returns a BackgroundScheduler (for embedding in FastAPI).
                    if False, returns a BlockingScheduler (for standalone invocation).
    """
    hour = int(os.environ.get("SCHEDULER_HOUR", 2))
    minute = int(os.environ.get("SCHEDULER_MINUTE", 0))
    timezone = os.environ.get("SCHEDULER_TIMEZONE", "Asia/Kolkata")

    SchedulerClass = BackgroundScheduler if background else BlockingScheduler
    scheduler = SchedulerClass(timezone=timezone)
    scheduler.add_job(
        run_delta_index,
        trigger="cron",
        hour=hour,
        minute=minute,
        id="nightly_freshness",
        name="Nightly RBI circular delta re-index",
        misfire_grace_time=3600,  # allow up to 1h late if system was down
        coalesce=True,            # skip missed runs, don't catch up
    )
    logger.info(
        "scheduler_configured",
        hour=hour,
        minute=minute,
        timezone=timezone,
    )
    return scheduler


if __name__ == "__main__":
    scheduler = make_scheduler(background=False)
    logger.info("scheduler_starting")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("scheduler_stopped")
