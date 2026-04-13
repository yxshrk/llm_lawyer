"""emails table + documents.author/last_opened_at/email_id

Revision ID: 0003_emails
Revises: 0002_cases
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_emails"
down_revision = "0002_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_addr", sa.String(512)),
        sa.Column("to_addrs", sa.Text()),
        sa.Column("subject", sa.String(1024)),
        sa.Column("body", sa.Text()),
        sa.Column("timestamp", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_emails_case_id", "emails", ["case_id"])

    op.add_column("documents", sa.Column("author", sa.String(512)))
    op.add_column(
        "documents", sa.Column("last_opened_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "documents",
        sa.Column(
            "email_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("emails.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_documents_email_id", "documents", ["email_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_email_id", table_name="documents")
    op.drop_column("documents", "email_id")
    op.drop_column("documents", "last_opened_at")
    op.drop_column("documents", "author")
    op.drop_index("ix_emails_case_id", table_name="emails")
    op.drop_table("emails")
