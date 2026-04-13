"""
PDF text extraction using PyMuPDF.

Extracts text and attempts to tag clause references (section/paragraph
numbers) from the document structure. Returns structured text blocks
with best-effort clause refs.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import structlog

logger = structlog.get_logger(__name__)

# Patterns that suggest a clause/section header
CLAUSE_PATTERNS = [
    re.compile(r"^(\d+\.\d+(?:\.\d+)*)\s"),          # 4.2.1 style
    re.compile(r"^(\d+)\.\s+[A-Z]"),                  # 1. Title style
    re.compile(r"^\(([a-z]+|\d+)\)\s"),                # (a) or (1) style
    re.compile(r"^(Section\s+\d+)", re.IGNORECASE),    # Section 4 style
    re.compile(r"^(Para(?:graph)?\s+\d+)", re.IGNORECASE),
]


@dataclass
class TextBlock:
    text: str
    page_number: int
    clause_ref: str = ""
    block_index: int = 0


@dataclass
class ExtractedDocument:
    circular_id: str
    blocks: list[TextBlock] = field(default_factory=list)
    extraction_failed: bool = False
    failure_reason: str = ""


def _detect_clause_ref(text: str) -> str:
    """Return the first matching clause ref pattern, or empty string."""
    first_line = text.split("\n")[0].strip()
    for pattern in CLAUSE_PATTERNS:
        match = pattern.match(first_line)
        if match:
            return match.group(1)
    return ""


def extract_text(pdf_path: Path, circular_id: str) -> ExtractedDocument:
    """
    Extract text blocks from a PDF.

    Each block represents a paragraph/section from the PDF structure.
    Empty or whitespace-only blocks are discarded.

    Returns ExtractedDocument with extraction_failed=True if PyMuPDF
    cannot open or read the file — caller must quarantine.
    """
    doc = ExtractedDocument(circular_id=circular_id)

    try:
        pdf = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.error(
            "pdf_open_failed",
            circular_id=circular_id,
            path=str(pdf_path),
            error=str(exc),
        )
        doc.extraction_failed = True
        doc.failure_reason = f"pdf_open_failed: {exc}"
        return doc

    block_index = 0
    for page_num, page in enumerate(pdf, start=1):
        try:
            raw_blocks = page.get_text("blocks")  # [(x0,y0,x1,y1,text,block_no,block_type)]
        except Exception as exc:
            logger.warning(
                "page_extraction_failed",
                circular_id=circular_id,
                page=page_num,
                error=str(exc),
            )
            continue

        for block in raw_blocks:
            block_type = block[6]
            if block_type != 0:  # 0 = text block; skip image blocks
                continue

            text = block[4].strip()
            if not text:
                continue

            clause_ref = _detect_clause_ref(text)
            doc.blocks.append(
                TextBlock(
                    text=text,
                    page_number=page_num,
                    clause_ref=clause_ref,
                    block_index=block_index,
                )
            )
            block_index += 1

    pdf.close()

    if not doc.blocks:
        logger.warning(
            "no_text_extracted",
            circular_id=circular_id,
            path=str(pdf_path),
        )
        doc.extraction_failed = True
        doc.failure_reason = "no_text_blocks_found"

    logger.info(
        "extraction_complete",
        circular_id=circular_id,
        blocks=len(doc.blocks),
        pages=page_num if doc.blocks else 0,
    )
    return doc
