"""merge_heads

Revision ID: 20251224_0002
Revises: 20251223_0001_create_pgvector_tables_384d, 20251224_0001
Create Date: 2025-12-24 00:00:00.000000
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "20251224_0002"
down_revision: Union[str, Sequence[str], None] = (
    "20251223_0001_create_pgvector_tables_384d",
    "20251224_0001",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Merge heads: no schema changes.
    """


def downgrade() -> None:
    """
    Downgrade merge: no schema changes.
    """
