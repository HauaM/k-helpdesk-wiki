"""Change reviewer_id and changed_by to string employee_id

Revision ID: a1f3c2d4e5f6
Revises: 8851865e5633
Create Date: 2025-12-06 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f3c2d4e5f6"
down_revision: Union[str, Sequence[str], None] = "8851865e5633"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Convert reviewer/actor identifiers from UUID to string employee_id.
    Data가 삭제되고 재적재될 예정이므로 단순 타입 변경만 수행한다.
    """

    op.alter_column(
        "manual_review_tasks",
        "reviewer_id",
        existing_type=sa.dialects.postgresql.UUID(),
        type_=sa.String(length=50),
        existing_nullable=True,
    )

    op.alter_column(
        "task_history",
        "changed_by",
        existing_type=sa.dialects.postgresql.UUID(),
        type_=sa.String(length=50),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema.

    Revert employee_id strings back to UUID columns.
    """

    op.alter_column(
        "task_history",
        "changed_by",
        existing_type=sa.String(length=50),
        type_=sa.dialects.postgresql.UUID(),
        existing_nullable=True,
    )

    op.alter_column(
        "manual_review_tasks",
        "reviewer_id",
        existing_type=sa.String(length=50),
        type_=sa.dialects.postgresql.UUID(),
        existing_nullable=True,
    )
