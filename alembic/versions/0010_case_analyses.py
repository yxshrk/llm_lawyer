"""case_analyses table — case-level synthesis output.

Backs the Consolidated Case Brief: one row per generated brief, keyed by
case (not document). Mirrors document_analyses but case-scoped.

Revision ID: 0010_case_analyses
Revises: 0009_contextual_retrieval
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0010_case_analyses"
down_revision = "0009_contextual_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_case_analyses_case_id", "case_analyses", ["case_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_case_analyses_case_id", table_name="case_analyses")
    op.drop_table("case_analyses")
