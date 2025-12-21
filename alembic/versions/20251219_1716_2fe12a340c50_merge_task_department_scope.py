"""merge task department scope

Revision ID: 2fe12a340c50
Revises: 20250214_0001, 20251219_0002
Create Date: 2025-12-19 17:16:47.226147

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2fe12a340c50'
down_revision: Union[str, Sequence[str], None] = ('20250214_0001', '20251219_0002')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
