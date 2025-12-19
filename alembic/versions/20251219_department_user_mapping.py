"""department_user_mapping

Revision ID: 20251219_department_user_mapping
Revises: 7b806107c5a8
Create Date: 2025-12-19 00:00:00.000000
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20251219_department_user_mapping"
down_revision: Union[str, Sequence[str], None] = "7b806107c5a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_department_name(value: str | None) -> str:
    if value is None:
        return "GENERAL"
    normalized = value.strip()
    return normalized if normalized else "GENERAL"


def upgrade() -> None:
    """Create department tables and migrate existing values."""

    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("department_code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("department_name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "user_departments",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, primary_key=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, primary_key=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    bind = op.get_bind()
    departments_to_insert: dict[str, str] = {}

    result = bind.execute(sa.text("SELECT DISTINCT department FROM users"))
    for row in result:
        normalized = _normalize_department_name(row[0])
        if normalized in departments_to_insert:
            continue
        departments_to_insert[normalized] = str(uuid4())

    for normalized, dept_id in departments_to_insert.items():
        bind.execute(
            sa.text(
                """
                INSERT INTO departments (id, department_code, department_name, is_active, created_at, updated_at)
                VALUES (:id, :code, :name, true, now(), now())
                """,
            ),
            {"id": dept_id, "code": normalized, "name": normalized},
        )

    users = bind.execute(sa.text("SELECT id, department FROM users"))
    for user_id, department_value in users:
        normalized = _normalize_department_name(department_value)
        department_id = departments_to_insert[normalized]
        bind.execute(
            sa.text(
                """
                INSERT INTO user_departments (user_id, department_id, is_primary, created_at, updated_at)
                VALUES (:user_id, :department_id, true, now(), now())
                """,
            ),
            {"user_id": user_id, "department_id": department_id},
        )

    op.drop_column("users", "department")


def downgrade() -> None:
    """Revert department normalization."""

    op.add_column(
        "users",
        sa.Column("department", sa.String(length=100), nullable=False, server_default="General"),
    )

    op.execute("UPDATE users SET department = 'General' WHERE department IS NULL")
    op.drop_table("user_departments")
    op.drop_table("departments")
