"""
Full corpus indexer — scrapes and indexes RBI circulars across multiple calendar years.

Usage:
    python scripts/index_corpus.py                     # 2022–2025, all circulars
    python scripts/index_corpus.py --years 2024 2025   # specific years
    python scripts/index_corpus.py --limit 50          # cap per year (testing)
    python scripts/index_corpus.py --dry-run           # scrape+download, skip embedding

This script calls run_pipeline() once per year so each year's scrape is independent.
Failed years are logged but do not abort remaining years.

Run after wiping data/chroma to ensure a clean index:
    rm -rf data/chroma && python scripts/index_corpus.py
"""

import argparse
import logging
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Project root on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

from ingestion.pipeline import run_pipeline  # noqa: E402

logger = structlog.get_logger(__name__)

DEFAULT_YEARS = [2022, 2023, 2024, 2025]


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-year RBI corpus indexer")
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=DEFAULT_YEARS,
        help="Calendar years to index (default: 2022–2025)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max circulars per year (for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and download only — skip embedding",
    )
    args = parser.parse_args()

    totals = {"scraped": 0, "indexed": 0, "quarantined": 0}

    for year in args.years:
        logger.info("year_start", year=year)
        try:
            stats = run_pipeline(
                year_filter=year,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            totals["scraped"] += stats.get("scraped", 0)
            totals["indexed"] += stats.get("indexed", 0)
            totals["quarantined"] += stats.get("quarantined", 0)
            logger.info("year_complete", year=year, stats=stats)
        except Exception as exc:
            logger.error("year_failed", year=year, error=str(exc))

    logger.info("corpus_index_complete", totals=totals)
    print(f"\nCorpus index complete: {totals}")


if __name__ == "__main__":
    main()
