"""create query_audit_log table

Revision ID: 0001
Revises:
Create Date: 2026-04-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.create_table(
        "query_audit_log",
        sa.Column(
            "query_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("retrieved_chunk_ids", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("llm_response", sa.Text, nullable=True),
        sa.Column("citations", postgresql.JSONB, nullable=True),
        sa.Column("gate_fired", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    # Index for time-range queries and gate_fired monitoring
    op.create_index("ix_audit_created_at", "query_audit_log", ["created_at"])
    op.create_index("ix_audit_gate_fired", "query_audit_log", ["gate_fired"])


def downgrade() -> None:
    op.drop_index("ix_audit_gate_fired", "query_audit_log")
    op.drop_index("ix_audit_created_at", "query_audit_log")
    op.drop_table("query_audit_log")
