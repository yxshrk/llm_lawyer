"""Relevancy fields on documents + audit_events table.

Revision ID: 0005_relevancy_audit
Revises: 0004_production_type
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_relevancy_audit"
down_revision = "0004_production_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("relevancy_label", sa.String(32)))
    op.add_column("documents", sa.Column("relevancy_score", sa.Float()))
    op.add_column("documents", sa.Column("relevancy_reasoning", sa.Text()))
    op.add_column(
        "documents",
        sa.Column("relevancy_classified_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_documents_relevancy_label", "documents", ["relevancy_label"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
        ),
        sa.Column("actor", sa.String(128), nullable=False, server_default="system"),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", sa.String(64)),
        sa.Column("summary", sa.Text()),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_events_case_id", "audit_events", ["case_id"])
    op.create_index("ix_audit_events_document_id", "audit_events", ["document_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_document_id", table_name="audit_events")
    op.drop_index("ix_audit_events_case_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_documents_relevancy_label", table_name="documents")
    op.drop_column("documents", "relevancy_classified_at")
    op.drop_column("documents", "relevancy_reasoning")
    op.drop_column("documents", "relevancy_score")
    op.drop_column("documents", "relevancy_label")
