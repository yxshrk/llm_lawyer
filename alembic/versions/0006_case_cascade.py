"""documents.case_id CASCADE — deleting a case must purge its docs.

Revision ID: 0006_case_cascade
Revises: 0005_relevancy_audit
"""
from __future__ import annotations

from alembic import op

revision = "0006_case_cascade"
down_revision = "0005_relevancy_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("documents_case_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key(
        "documents_case_id_fkey",
        "documents",
        "cases",
        ["case_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("documents_case_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key(
        "documents_case_id_fkey",
        "documents",
        "cases",
        ["case_id"],
        ["id"],
        ondelete="SET NULL",
    )
