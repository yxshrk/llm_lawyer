"""Widen redaction_challenges.difficulty from String(16) to String(32).

String(16) could not hold "hard_low_confidence" (19) or
"priority_inconsistency" (22). Postgres rejected the INSERT on the
priority path.

Revision ID: 0008_widen_difficulty
Revises: 0007_qa_challenges
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_widen_difficulty"
down_revision = "0007_qa_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "redaction_challenges",
        "difficulty",
        type_=sa.String(32),
        existing_type=sa.String(16),
        existing_nullable=False,
        existing_server_default="standard",
    )


def downgrade() -> None:
    op.alter_column(
        "redaction_challenges",
        "difficulty",
        type_=sa.String(16),
        existing_type=sa.String(32),
        existing_nullable=False,
        existing_server_default="standard",
    )
