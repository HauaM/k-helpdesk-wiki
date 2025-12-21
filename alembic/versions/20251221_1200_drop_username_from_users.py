"""drop username from users

Revision ID: 20251221_1200_drop_username_from_users
Revises: 2fe12a340c50, 20251219_department_user_mapping
Create Date: 2025-12-21 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251221_1200_drop_username_from_users"
down_revision: Union[str, Sequence[str], None] = (
    "2fe12a340c50",
    "20251219_department_user_mapping",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("username")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("username", sa.String(length=50), nullable=True))

    op.execute("UPDATE users SET username = employee_id WHERE username IS NULL")

    with op.batch_alter_table("users") as batch_op:
        batch_op.create_unique_constraint(None, ["username"])
        batch_op.create_index("ix_users_username", ["username"], unique=False)
        batch_op.alter_column("username", nullable=False)
