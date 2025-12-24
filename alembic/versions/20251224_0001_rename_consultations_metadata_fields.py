"""rename_consultations_metadata_fields

Revision ID: 20251224_0001
Revises: 20250214_0001
Create Date: 2025-12-24 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20251224_0001"
down_revision: Union[str, Sequence[str], None] = "20250214_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    상담 메타데이터 컬럼명을 metadata -> metadata_fields로 변경
    """
    op.alter_column(
        "consultations",
        "metadata",
        new_column_name="metadata_fields",
    )


def downgrade() -> None:
    """
    롤백: 컬럼명을 metadata_fields -> metadata로 복원
    """
    op.alter_column(
        "consultations",
        "metadata_fields",
        new_column_name="metadata",
    )
