"""
Demo script — verifies both locked demo queries produce the expected outcomes.

Query 1 (gate passes): KYC requirements for full-KYC PPI
Query 2 (gate fires): SEBI insider trading penalties

Usage:
    # Requires API running: uvicorn api.main:app --port 8000
    python scripts/demo.py

    # Or against a different API URL:
    API_BASE_URL=http://localhost:8000/api/v1 python scripts/demo.py
"""

import json
import os
import sys

import httpx

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")
TIMEOUT = 60

DEMO_QUERIES = [
    {
        "name": "Q1 — KYC PPI (gate should PASS)",
        "query": "prepaid payment instrument KYC norms customer due diligence",
        "expect_gate_fired": False,
        "min_citations": 2,
        "min_confidence": 0.65,
    },
    {
        "name": "Q2 — SEBI insider trading (gate should FIRE)",
        "query": "What penalties does SEBI impose for insider trading violations?",
        "expect_gate_fired": True,
        "min_citations": 0,
        "min_confidence": 0.0,
    },
]

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def check(condition: bool, label: str) -> bool:
    status = f"{GREEN}PASS{RESET}" if condition else f"{RED}FAIL{RESET}"
    print(f"  [{status}] {label}")
    return condition


def run_query(query: str) -> dict:
    response = httpx.post(
        f"{API_BASE}/query",
        json={"query": query},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    print(f"\n{BOLD}Regulatory Intelligence Agent — Demo Script{RESET}")
    print(f"API: {API_BASE}\n")

    all_passed = True

    for demo in DEMO_QUERIES:
        print(f"{BOLD}{demo['name']}{RESET}")
        print(f"  Query: \"{demo['query']}\"")

        try:
            data = run_query(demo["query"])
        except httpx.ConnectError:
            print(f"  {RED}ERROR: Could not connect to {API_BASE}{RESET}")
            print(f"  Make sure the API is running: uvicorn api.main:app --port 8000\n")
            return 1
        except httpx.HTTPStatusError as exc:
            print(f"  {RED}ERROR: HTTP {exc.response.status_code} — {exc.response.text}{RESET}\n")
            all_passed = False
            continue

        gate_fired = data.get("gate_fired", False)
        confidence = data.get("confidence_score", 0.0)
        citations = data.get("citations", [])
        answer = data.get("answer", "")
        query_id = data.get("query_id", "")

        print(f"  Confidence: {confidence:.4f} | Gate fired: {gate_fired} | Citations: {len(citations)}")

        passed = True
        passed &= check(
            gate_fired == demo["expect_gate_fired"],
            f"gate_fired == {demo['expect_gate_fired']}",
        )
        passed &= check(
            confidence >= demo["min_confidence"],
            f"confidence {confidence:.4f} >= {demo['min_confidence']}",
        )
        if not demo["expect_gate_fired"]:
            passed &= check(
                len(citations) >= demo["min_citations"],
                f"citations {len(citations)} >= {demo['min_citations']}",
            )
            passed &= check(
                bool(answer),
                "answer is non-empty",
            )
        else:
            passed &= check(
                "Insufficient regulatory basis" in answer,
                "fallback text present verbatim",
            )

        if query_id:
            print(f"  Query ID: {query_id}  (check audit log: SELECT * FROM query_audit_log WHERE query_id = '{query_id}';)")

        if not demo["expect_gate_fired"] and citations:
            print(f"\n  {YELLOW}Citations:{RESET}")
            for c in citations:
                print(f"    • {c['circular_id']} — {c['circular_title'][:60]}")
                print(f"      Effective: {c.get('effective_date', 'n/a')}  Clause: {c.get('clause_ref', 'n/a')}")

        result_label = f"{GREEN}PASSED{RESET}" if passed else f"{RED}FAILED{RESET}"
        print(f"\n  Result: {result_label}\n")
        all_passed &= passed

    print("-" * 60)
    if all_passed:
        print(f"{GREEN}{BOLD}All demo queries passed.{RESET}")
    else:
        print(f"{RED}{BOLD}One or more demo queries failed.{RESET}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
