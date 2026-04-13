"""
Ingestion pipeline entry point.

Orchestrates: scrape → download → extract → chunk → index.
Quarantines documents that fail at any stage.

Usage:
    python -m ingestion.pipeline --source rbi
    python -m ingestion.pipeline --source rbi --year 2024 --limit 20
"""

import argparse
from pathlib import Path

import structlog

from scraper.rbi_scraper import scrape_index, download_all
from scraper.pdf_extractor import extract_text
from ingestion.chunker import chunk_document
from ingestion.indexer import index_documents, get_chroma_store
from ingestion.quarantine import quarantine

logger = structlog.get_logger(__name__)

PDF_DIR = Path("./data/pdfs")


def run_pipeline(
    year_filter: int | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Full ingest: scrape RBI index → download PDFs → extract → chunk → index.

    Args:
        year_filter: restrict to circulars from a given fiscal year start
        limit: cap the number of circulars to process (useful for testing)
        dry_run: scrape and download but skip indexing

    Returns:
        Summary dict with counts for each stage.
    """
    stats = {
        "scraped": 0,
        "downloaded": 0,
        "extracted": 0,
        "chunked": 0,
        "indexed": 0,
        "quarantined": 0,
    }

    logger.info("pipeline_start", year_filter=year_filter, limit=limit, dry_run=dry_run)

    # Stage 1: Scrape index
    circulars = scrape_index(year_filter=year_filter)
    if limit:
        circulars = circulars[:limit]
    stats["scraped"] = len(circulars)
    logger.info("stage_scrape_complete", count=stats["scraped"])

    if not circulars:
        logger.warning("no_circulars_found")
        return stats

    # Stage 2: Download PDFs
    pdf_map = download_all(circulars, dest_dir=PDF_DIR)
    stats["downloaded"] = len(pdf_map)
    logger.info("stage_download_complete", count=stats["downloaded"])

    # Build lookup for metadata
    meta_by_id = {c.circular_id: c for c in circulars}

    if dry_run:
        logger.info("dry_run_complete", stats=stats)
        return stats

    # Stage 3–5: Extract → chunk → index
    store = get_chroma_store()
    all_chunks = []

    for circular_id, pdf_path in pdf_map.items():
        raw_meta = meta_by_id[circular_id]

        # Extract
        extracted = extract_text(pdf_path, circular_id)
        if extracted.extraction_failed:
            quarantine(
                circular_id=circular_id,
                reason=extracted.failure_reason,
                pdf_path=str(pdf_path),
            )
            stats["quarantined"] += 1
            continue
        stats["extracted"] += 1

        # Chunk
        chunks = chunk_document(extracted, raw_meta)
        if not chunks:
            quarantine(
                circular_id=circular_id,
                reason="chunking_produced_no_chunks",
                pdf_path=str(pdf_path),
            )
            stats["quarantined"] += 1
            continue
        stats["chunked"] += len(chunks)
        all_chunks.extend(chunks)

    # Index in one pass for efficiency
    if all_chunks:
        stats["indexed"] = index_documents(all_chunks, store=store)

    logger.info("pipeline_complete", stats=stats)
    return stats


if __name__ == "__main__":
    import logging
    import structlog
    from dotenv import load_dotenv
    load_dotenv()

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

    parser = argparse.ArgumentParser(description="RBI Regulatory Intelligence ingestion pipeline")
    parser.add_argument("--source", choices=["rbi"], required=True)
    parser.add_argument("--year", type=int, default=None, help="Fiscal year start (e.g. 2024)")
    parser.add_argument("--limit", type=int, default=None, help="Max circulars to process")
    parser.add_argument("--dry-run", action="store_true", help="Skip indexing")
    args = parser.parse_args()

    result = run_pipeline(
        year_filter=args.year,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(result)
