"""cases, memories, memos, redactions, document_analyses

Revision ID: 0002_cases
Revises: 0001_init
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_cases"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("client_name", sa.String(512)),
        sa.Column("matter_type", sa.String(128)),
        sa.Column("description", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_documents_case_id", "documents", ["case_id"])

    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_memories_case_id", "memories", ["case_id"])

    op.create_table(
        "memos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_memos_document_id", "memos", ["document_id"])

    op.create_table(
        "redactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="SET NULL"),
        ),
        sa.Column("page", sa.Integer()),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("text_span", sa.Text(), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("reasoning", sa.Text()),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("modified_span", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_redactions_document_id", "redactions", ["document_id"])

    op.create_table(
        "document_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("model", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_document_analyses_document_id",
        "document_analyses",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_analyses_document_id", table_name="document_analyses")
    op.drop_table("document_analyses")
    op.drop_index("ix_redactions_document_id", table_name="redactions")
    op.drop_table("redactions")
    op.drop_index("ix_memos_document_id", table_name="memos")
    op.drop_table("memos")
    op.drop_index("ix_memories_case_id", table_name="memories")
    op.drop_table("memories")
    op.drop_index("ix_documents_case_id", table_name="documents")
    op.drop_column("documents", "case_id")
    op.drop_table("cases")
