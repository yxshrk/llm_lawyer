"""add production_type to documents + emails (own | opposing)

Revision ID: 0004_production_type
Revises: 0003_emails
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_production_type"
down_revision = "0003_emails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "production_type",
            sa.String(16),
            nullable=False,
            server_default="own",
        ),
    )
    op.create_index(
        "ix_documents_production_type", "documents", ["production_type"]
    )
    op.add_column(
        "emails",
        sa.Column(
            "production_type",
            sa.String(16),
            nullable=False,
            server_default="own",
        ),
    )
    op.create_index(
        "ix_emails_production_type", "emails", ["production_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_emails_production_type", table_name="emails")
    op.drop_column("emails", "production_type")
    op.drop_index("ix_documents_production_type", table_name="documents")
    op.drop_column("documents", "production_type")
