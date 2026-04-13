"""
Audit log writer — append-only writes to query_audit_log (PostgreSQL).

No UPDATE or DELETE, ever. Every request is logged, including gate-fired ones.
Schema is managed by Alembic — this module assumes the table exists.
"""

import os
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _get_connection():
    """Return a psycopg2 connection from env vars."""
    import psycopg2
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def write_audit_record(
    query_id: uuid.UUID,
    query_text: str,
    retrieved_chunk_ids: list[str],
    confidence_score: float,
    llm_response: str | None,
    citations: list[dict[str, Any]] | None,
    gate_fired: bool,
) -> None:
    """
    Append one row to query_audit_log.

    Never raises — logs the error and returns so the API response is not blocked
    by an audit failure. Audit integrity is monitored via Prometheus alerts.
    """
    import json
    import psycopg2.extras

    sql = """
        INSERT INTO query_audit_log (
            query_id,
            query_text,
            retrieved_chunk_ids,
            confidence_score,
            llm_response,
            citations,
            gate_fired
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        str(query_id),
        query_text,
        retrieved_chunk_ids,
        confidence_score,
        llm_response,
        json.dumps(citations) if citations is not None else None,
        gate_fired,
    )

    try:
        conn = _get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
        conn.close()
        logger.info("audit_record_written", query_id=str(query_id), gate_fired=gate_fired)
    except Exception as exc:
        logger.error(
            "audit_write_failed",
            query_id=str(query_id),
            error=str(exc),
        )
