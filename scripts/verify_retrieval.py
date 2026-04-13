"""
Phase 1 retrieval verification — 5 domain queries against indexed Chroma store.

Validates:
  - Results returned (non-empty)
  - Required metadata fields present on every result
  - circular_id starts with "RBI/"
  - confidence proxy (similarity score) is numeric

Usage:
    python scripts/verify_retrieval.py

Requires GOOGLE_API_KEY and CHROMA_PERSIST_DIR in .env (or environment).
Exits 0 if all checks pass, 1 if any fail.
"""

import os
import sys
import logging

import structlog
from dotenv import load_dotenv

load_dotenv()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
logger = structlog.get_logger(__name__)

REQUIRED_METADATA_FIELDS = {
    "source",
    "circular_id",
    "circular_title",
    "effective_date",
    "clause_ref",
    "chunk_index",
    "scraped_at",
}

# Five domain queries that probe different regulatory topic areas.
# Each query should return ≥1 result with complete metadata if the corpus
# is indexed correctly.
TEST_QUERIES = [
    {
        "id": "Q1",
        "query": "KYC requirements for prepaid payment instruments above ten thousand rupees",
        "description": "PPI KYC — should hit DPSS/NPCI circulars on PPI limits",
    },
    {
        "id": "Q2",
        "query": "cash reserve ratio maintenance and computation by scheduled commercial banks",
        "description": "CRR — core banking regulation, broad corpus coverage expected",
    },
    {
        "id": "Q3",
        "query": "master direction on interest rate on advances",
        "description": "Interest rate directive — tests master direction retrieval",
    },
    {
        "id": "Q4",
        "query": "cybersecurity framework for banks incident reporting",
        "description": "Cybersecurity circular — tests IT/security topic coverage",
    },
    {
        "id": "Q5",
        "query": "priority sector lending targets and classification",
        "description": "PSL norms — high-frequency regulatory topic",
    },
]


def _get_store():
    from ingestion.indexer import get_chroma_store
    return get_chroma_store()


def _check_metadata(doc, query_id: str) -> list[str]:
    """Return list of missing/invalid field errors for a single doc."""
    errors = []
    meta = doc.metadata

    for field in REQUIRED_METADATA_FIELDS:
        if field not in meta or meta[field] is None or str(meta[field]).strip() == "":
            errors.append(f"{query_id}: missing or empty metadata field '{field}'")

    cid = meta.get("circular_id", "")
    if cid and not cid.startswith("RBI/"):
        errors.append(f"{query_id}: circular_id '{cid}' does not start with 'RBI/'")

    return errors


def run_verification() -> bool:
    """
    Run all test queries and collect failures.
    Returns True if all pass, False otherwise.
    """
    logger.info("verification_start", query_count=len(TEST_QUERIES))

    try:
        store = _get_store()
    except Exception as exc:
        logger.error("chroma_store_open_failed", error=str(exc))
        print(f"\nFATAL: Cannot open Chroma store — {exc}")
        print("Have you run the ingestion pipeline first?  python -m ingestion.pipeline --source rbi")
        return False

    all_errors: list[str] = []
    results_summary: list[dict] = []

    for test in TEST_QUERIES:
        qid = test["id"]
        query = test["query"]

        logger.info("running_query", query_id=qid, query=query)

        try:
            # similarity_search_with_score returns (Document, float) pairs.
            # k=6 matches the MMR k we'll use in Phase 2.
            hits = store.similarity_search_with_score(query, k=6)
        except Exception as exc:
            msg = f"{qid}: similarity_search raised {exc}"
            logger.error("query_failed", query_id=qid, error=str(exc))
            all_errors.append(msg)
            results_summary.append({"id": qid, "status": "ERROR", "hits": 0, "top_score": None})
            continue

        if not hits:
            msg = f"{qid}: returned 0 results — corpus may be empty or query has no coverage"
            all_errors.append(msg)
            results_summary.append({"id": qid, "status": "FAIL", "hits": 0, "top_score": None})
            continue

        top_doc, top_score = hits[0]
        meta_errors = []
        for doc, _score in hits:
            meta_errors.extend(_check_metadata(doc, qid))

        status = "PASS" if not meta_errors else "FAIL"
        results_summary.append(
            {
                "id": qid,
                "status": status,
                "hits": len(hits),
                "top_score": round(float(top_score), 4),
                "top_circular": top_doc.metadata.get("circular_id", "unknown"),
                "top_title": top_doc.metadata.get("circular_title", "")[:80],
            }
        )
        all_errors.extend(meta_errors)

        logger.info(
            "query_result",
            query_id=qid,
            hits=len(hits),
            top_score=round(float(top_score), 4),
            top_circular=top_doc.metadata.get("circular_id"),
            status=status,
        )

    # Print summary table
    print("\n" + "=" * 72)
    print(f"{'ID':<4}  {'STATUS':<6}  {'HITS':<5}  {'TOP SCORE':<10}  {'TOP CIRCULAR'}")
    print("-" * 72)
    for r in results_summary:
        top_circ = r.get("top_circular", "—")
        top_score_str = f"{r['top_score']:.4f}" if r["top_score"] is not None else "—"
        print(f"{r['id']:<4}  {r['status']:<6}  {r['hits']:<5}  {top_score_str:<10}  {top_circ}")
    print("=" * 72)

    if all_errors:
        print("\nFAILURES:")
        for err in all_errors:
            print(f"  - {err}")
        print(f"\n{len(all_errors)} check(s) failed.")
        return False

    passed = sum(1 for r in results_summary if r["status"] == "PASS")
    print(f"\nAll {passed}/{len(TEST_QUERIES)} queries passed. Phase 1 retrieval verification complete.")
    return True


if __name__ == "__main__":
    ok = run_verification()
    sys.exit(0 if ok else 1)
