"""Add ARCHIVED status to manual_status enum

Revision ID: 0003_manual_status_archived
Revises: 0002_add_comparison_type
Create Date: 2025-12-11 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_manual_status_archived"
down_revision = "0002_add_comparison_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ARCHIVED enum value for manual_status"""

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE manual_status ADD VALUE 'ARCHIVED';")
    else:
        # For databases without native ENUM types (e.g., SQLite), no schema change is required
        pass


def downgrade() -> None:
    """Removing enum values is not supported without recreating the type"""

    raise NotImplementedError(
        "Downgrade not supported for manual_status ARCHIVED addition"
    )
