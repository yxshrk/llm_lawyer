"""Pipeline 2: redaction_challenges table.

Revision ID: 0007_qa_challenges
Revises: 0006_case_cascade
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_qa_challenges"
down_revision = "0006_case_cascade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "redaction_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "redaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("redactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("challenge_question", sa.Text(), nullable=False),
        sa.Column("suggested_answer", sa.Text()),
        sa.Column("legal_basis", sa.Text()),
        sa.Column("risk_flag", sa.Text()),
        sa.Column("difficulty", sa.String(16), nullable=False, server_default="standard"),
        sa.Column("inconsistency_peer_id", postgresql.UUID(as_uuid=True)),
        sa.Column("lawyer_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("lawyer_notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_qa_case_id", "redaction_challenges", ["case_id"])
    op.create_index("ix_qa_redaction_id", "redaction_challenges", ["redaction_id"])
    op.create_index("ix_qa_run_id", "redaction_challenges", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_qa_run_id", table_name="redaction_challenges")
    op.drop_index("ix_qa_redaction_id", table_name="redaction_challenges")
    op.drop_index("ix_qa_case_id", table_name="redaction_challenges")
    op.drop_table("redaction_challenges")
