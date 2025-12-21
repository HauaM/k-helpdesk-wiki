"""Add reviewer_department_id to manual_review_tasks for FR-20 visibility control."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251219_0002"
down_revision = "20251219_department_user_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "manual_review_tasks",
        sa.Column(
            "reviewer_department_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_manual_review_tasks_reviewer_department_id_departments",
        "manual_review_tasks",
        "departments",
        ["reviewer_department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_manual_review_tasks_reviewer_department_id",
        "manual_review_tasks",
        ["reviewer_department_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_manual_review_tasks_reviewer_department_id",
        table_name="manual_review_tasks",
    )
    op.drop_constraint(
        "fk_manual_review_tasks_reviewer_department_id_departments",
        "manual_review_tasks",
        type_="foreignkey",
    )
    op.drop_column("manual_review_tasks", "reviewer_department_id")
