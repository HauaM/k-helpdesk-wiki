"""Add comparison_type field to manual_review_tasks (v2.1)

Revision ID: 0002_add_comparison_type
Revises: 20251211_0001_group_fields
Create Date: 2025-12-11 00:00:00.000000

FR-11(v2.1): ManualReviewTask에 comparison_type 필드 추가
- SIMILAR: 기존 메뉴얼과 매우 유사 (≥0.95 유사도)
- SUPPLEMENT: 기존 메뉴얼 보충/개선 (0.7-0.95 유사도)
- NEW: 신규 메뉴얼 (<0.7 유사도)

마이그레이션 전략:
1. comparison_type VARCHAR(20) NULL로 추가
2. 기존 모든 행에 'new' 값 할당
3. NOT NULL 제약 추가
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_add_comparison_type"
down_revision = "20251211_0001_group_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add comparison_type column to manual_review_tasks"""

    # Step 1: nullable=True로 컬럼 추가
    op.add_column(
        "manual_review_tasks",
        sa.Column(
            "comparison_type",
            sa.String(20),
            nullable=True,
            comment="비교 타입: similar/supplement/new",
        ),
    )

    # Step 2: 기존 데이터에 default value 'new' 적용
    op.execute(
        "UPDATE manual_review_tasks SET comparison_type = 'new' "
        "WHERE comparison_type IS NULL"
    )

    # Step 3: NOT NULL 제약 추가
    op.alter_column(
        "manual_review_tasks",
        "comparison_type",
        nullable=False,
    )


def downgrade() -> None:
    """Remove comparison_type column from manual_review_tasks"""
    op.drop_column("manual_review_tasks", "comparison_type")
