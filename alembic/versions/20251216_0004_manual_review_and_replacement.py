"""Add manual review metadata and replacement links

Revision ID: 20251216_0004
Revises: 0003_manual_status_archived
Create Date: 2025-12-16 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20251216_0004"
down_revision = "0003_manual_status_archived"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add review metadata columns and replacement tracking."""

    # 1. sync manual_review_tasks metadata
    op.add_column(
        "manual_review_tasks",
        sa.Column(
            "compare_version",
            sa.String(length=20),
            nullable=True,
            comment="Comparison logic version (thresholds, keyword rules)",
        ),
    )
    op.alter_column(
        "manual_review_tasks",
        "similarity",
        nullable=True,
    )

    op.create_index(
        "idx_manual_review_tasks_new_entry",
        "manual_review_tasks",
        ["new_entry_id"],
    )

    # 2. manual_entries replacement tracking
    op.add_column(
        "manual_entries",
        sa.Column(
            "replaced_manual_id",
            UUID(as_uuid=True),
            sa.ForeignKey("manual_entries.id", ondelete="SET NULL"),
            nullable=True,
            comment="Deprecated manual that was replaced",
        ),
    )
    op.add_column(
        "manual_entries",
        sa.Column(
            "replaced_by_manual_id",
            UUID(as_uuid=True),
            sa.ForeignKey("manual_entries.id", ondelete="SET NULL"),
            nullable=True,
            comment="New manual that replaced this entry",
        ),
    )
    op.create_index(
        "idx_manual_entries_replaced_manual_id",
        "manual_entries",
        ["replaced_manual_id"],
    )
    op.create_index(
        "idx_manual_entries_replaced_by_manual_id",
        "manual_entries",
        ["replaced_by_manual_id"],
    )


def downgrade() -> None:
    """Remove review metadata and replacement tracking."""

    op.drop_index("idx_manual_entries_replaced_by_manual_id", table_name="manual_entries")
    op.drop_index("idx_manual_entries_replaced_manual_id", table_name="manual_entries")
    op.drop_column("manual_entries", "replaced_by_manual_id")
    op.drop_column("manual_entries", "replaced_manual_id")

    op.drop_index("idx_manual_review_tasks_new_entry", table_name="manual_review_tasks")
    op.drop_column("manual_review_tasks", "compare_version")
    op.alter_column(
        "manual_review_tasks",
        "similarity",
        nullable=False,
    )
