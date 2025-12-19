"""fr17_manual_flag

Revision ID: 20250214_0001
Revises: 7b806107c5a8
Create Date: 2025-02-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20250214_0001"
down_revision: Union[str, Sequence[str], None] = "7b806107c5a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    FR-17: 상담 메뉴얼 생성 플래그 컬럼 추가
    """
    op.add_column(
        "consultations",
        sa.Column(
            "is_manual_generated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="상담 기반 메뉴얼 초안 생성 프로세스 완료 여부",
        ),
    )
    op.add_column(
        "consultations",
        sa.Column(
            "manual_generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="상담이 마지막으로 메뉴얼 초안을 생성한 시각",
        ),
    )


def downgrade() -> None:
    """
    FR-17 rollback: 컬럼 제거
    """
    op.drop_column("consultations", "manual_generated_at")
    op.drop_column("consultations", "is_manual_generated")
