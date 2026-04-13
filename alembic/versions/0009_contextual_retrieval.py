"""Chunk.context + Chunk.ts (tsvector) for Contextual Retrieval + Hybrid BM25.

- context TEXT: LLM-generated 1-2 sentence situating context for each chunk.
  Prepended before the raw chunk text when computing the embedding (per
  Anthropic's Contextual Retrieval, Sept 2024: 35-49% retrieval-failure
  reduction on public benchmarks).
- ts TSVECTOR GENERATED: auto-populated from context || text. Lets us run
  Postgres full-text (BM25-style) ranking alongside pgvector cosine and fuse
  results with Reciprocal Rank Fusion in the retriever.

Revision ID: 0009_contextual_retrieval
Revises: 0008_widen_difficulty
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_contextual_retrieval"
down_revision = "0008_widen_difficulty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain columns only — GENERATED STORED would need to recompute every
    # existing row and busts Supabase's 32MB maintenance_work_mem.
    # Ingest-time Python populates both columns for new chunks; existing
    # rows stay NULL and fall back to dense cosine only (still searchable).
    op.add_column("chunks", sa.Column("context", sa.Text(), nullable=True))
    op.execute("ALTER TABLE chunks ADD COLUMN ts tsvector")


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS ts")
    op.drop_column("chunks", "context")
