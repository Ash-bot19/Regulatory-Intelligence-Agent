"""
Quarantine store for documents that failed metadata extraction.

Writes failed circular IDs and reasons to a JSONL file so they can be
inspected and re-processed without polluting the index.
"""

import json
from datetime import datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_QUARANTINE_PATH = Path("./data/quarantine.jsonl")


def quarantine(
    circular_id: str,
    reason: str,
    pdf_path: str | None = None,
    quarantine_file: Path = DEFAULT_QUARANTINE_PATH,
) -> None:
    """
    Append a quarantine record. Thread-safe for single-process use.
    Creates the file and parent directory if they don't exist.
    """
    quarantine_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "circular_id": circular_id,
        "reason": reason,
        "pdf_path": pdf_path,
        "quarantined_at": datetime.utcnow().isoformat(),
    }
    with quarantine_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    logger.warning(
        "document_quarantined",
        circular_id=circular_id,
        reason=reason,
    )


def list_quarantined(
    quarantine_file: Path = DEFAULT_QUARANTINE_PATH,
) -> list[dict]:
    """Return all quarantine records as a list of dicts."""
    if not quarantine_file.exists():
        return []
    records = []
    with quarantine_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
