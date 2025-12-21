"""expand alembic_version length

Revision ID: 20251221_1210_alembic_version_len
Revises: 2fe12a340c50, 20251219_department_user_mapping
Create Date: 2025-12-21 12:10:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20251221_1210_alembic_version_len"
down_revision: Union[str, Sequence[str], None] = (
    "2fe12a340c50",
    "20251219_department_user_mapping",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(64)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE alembic_version SET version_num = LEFT(version_num, 32)")
    op.execute(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(32)"
    )
