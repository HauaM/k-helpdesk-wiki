"""Initial schema from models

Revision ID: 943361c7c44d
Revises: 
Create Date: 2025-12-05 09:55:48.450152

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '943361c7c44d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # Create enum types first to avoid duplicate CREATE TYPE in multiple tables.
    user_role_enum = postgresql.ENUM(
        "CONSULTANT",
        "REVIEWER",
        "ADMIN",
        name="user_role",
    )
    task_status_enum = postgresql.ENUM(
        "TODO",
        "IN_PROGRESS",
        "DONE",
        "REJECTED",
        name="task_status",
    )
    manual_status_enum = postgresql.ENUM(
        "DRAFT",
        "APPROVED",
        "DEPRECATED",
        name="manual_status",
    )
    index_status_enum = postgresql.ENUM(
        "PENDING",
        "INDEXED",
        "FAILED",
        name="index_status",
    )
    retry_target_enum = postgresql.ENUM(
        "CONSULTATION",
        "MANUAL",
        name="retry_target",
    )
    retry_job_status_enum = postgresql.ENUM(
        "PENDING",
        "RETRYING",
        "COMPLETED",
        "FAILED",
        name="retry_job_status",
    )

    for enum_type in (
        user_role_enum,
        task_status_enum,
        manual_status_enum,
        index_status_enum,
        retry_target_enum,
        retry_job_status_enum,
    ):
        enum_type.create(bind, checkfirst=True)

    # Ensure pgvector extension exists before creating vector tables.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "CONSULTANT",
                "REVIEWER",
                "ADMIN",
                name="user_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    op.create_table(
        "manual_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("changelog", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("version", name="manual_versions_version_key"),
    )

    op.create_table(
        "consultations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("inquiry_text", sa.Text(), nullable=False),
        sa.Column("action_taken", sa.Text(), nullable=False),
        sa.Column("branch_code", sa.String(length=50), nullable=False),
        sa.Column("employee_id", sa.String(length=50), nullable=False),
        sa.Column("screen_id", sa.String(length=50), nullable=True),
        sa.Column("transaction_name", sa.String(length=100), nullable=True),
        sa.Column("business_type", sa.String(length=50), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("manual_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_consultations_branch_code", "consultations", ["branch_code"])
    op.create_index("ix_consultations_business_type", "consultations", ["business_type"])
    op.create_index("ix_consultations_error_code", "consultations", ["error_code"])
    op.create_index("ix_consultations_manual_entry_id", "consultations", ["manual_entry_id"])

    op.create_table(
        "manual_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="1-3개 핵심 키워드",
        ),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("background", sa.Text(), nullable=False),
        sa.Column("guideline", sa.Text(), nullable=False),
        sa.Column("business_type", sa.String(length=50), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column(
            "source_consultation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manual_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "DRAFT",
                "APPROVED",
                "DEPRECATED",
                name="manual_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_manual_entries_business_type", "manual_entries", ["business_type"])
    op.create_index("ix_manual_entries_error_code", "manual_entries", ["error_code"])

    op.create_foreign_key(
        "fk_consultations_manual_entry_id",
        "consultations",
        "manual_entries",
        ["manual_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "manual_review_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "old_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manual_entries.id", ondelete="CASCADE"),
            nullable=True,
            comment="기존 메뉴얼 (없으면 신규 생성 흐름)",
        ),
        sa.Column(
            "new_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manual_entries.id", ondelete="CASCADE"),
            nullable=False,
            comment="신규 상담 기반 메뉴얼 초안",
        ),
        sa.Column(
            "similarity",
            sa.Float(),
            nullable=False,
            comment="기존/신규 유사도 점수",
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "TODO",
                "IN_PROGRESS",
                "DONE",
                "REJECTED",
                name="task_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'TODO'"),
        ),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="검토자 식별자 (User 테이블과 향후 연결)",
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "task_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manual_review_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_status",
            postgresql.ENUM(
                "TODO",
                "IN_PROGRESS",
                "DONE",
                "REJECTED",
                name="task_status",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            postgresql.ENUM(
                "TODO",
                "IN_PROGRESS",
                "DONE",
                "REJECTED",
                name="task_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="상태 변경 주체",
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_task_history_task_id", "task_history", ["task_id"])

    op.create_table(
        "consultation_vector_index",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "consultation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "embedding",
            postgresql.ARRAY(sa.Float()),
            nullable=False,
            comment="임베딩 벡터",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="FR-11 메타 스키마: branch_code, business_type, error_code, created_at",
        ),
        sa.Column("branch_code", sa.String(length=50), nullable=True),
        sa.Column("business_type", sa.String(length=50), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "INDEXED",
                "FAILED",
                name="index_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_consultation_vector_index_branch_code",
        "consultation_vector_index",
        ["branch_code"],
    )
    op.create_index(
        "ix_consultation_vector_index_business_type",
        "consultation_vector_index",
        ["business_type"],
    )
    op.create_index(
        "ix_consultation_vector_index_error_code",
        "consultation_vector_index",
        ["error_code"],
    )

    op.create_table(
        "manual_vector_index",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "manual_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manual_entries.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "embedding",
            postgresql.ARRAY(sa.Float()),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="FR-11 메타 스키마: business_type, error_code, created_at",
        ),
        sa.Column("business_type", sa.String(length=50), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "INDEXED",
                "FAILED",
                name="index_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_manual_vector_index_business_type",
        "manual_vector_index",
        ["business_type"],
    )
    op.create_index(
        "ix_manual_vector_index_error_code",
        "manual_vector_index",
        ["error_code"],
    )

    op.create_table(
        "retry_queue_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "target_type",
            postgresql.ENUM(
                "CONSULTATION",
                "MANUAL",
                name="retry_target",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "RETRYING",
                "COMPLETED",
                "FAILED",
                name="retry_job_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_retry_queue_jobs_target_id", "retry_queue_jobs", ["target_id"])

    op.create_table(
        "consultation_vectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        sa.Column("branch_code", sa.Text(), nullable=True),
        sa.Column("business_type", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("consultation_vectors_pkey")),
    )
    op.create_index(
        op.f("idx_consultation_vectors_error"),
        "consultation_vectors",
        ["error_code"],
        unique=False,
    )
    op.create_index(
        op.f("idx_consultation_vectors_business"),
        "consultation_vectors",
        ["business_type"],
        unique=False,
    )
    op.create_index(
        op.f("idx_consultation_vectors_branch"),
        "consultation_vectors",
        ["branch_code"],
        unique=False,
    )

    op.create_table(
        "manual_vectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        sa.Column("branch_code", sa.Text(), nullable=True),
        sa.Column("business_type", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("manual_vectors_pkey")),
    )
    op.create_index(
        op.f("idx_manual_vectors_error"),
        "manual_vectors",
        ["error_code"],
        unique=False,
    )
    op.create_index(
        op.f("idx_manual_vectors_business"),
        "manual_vectors",
        ["business_type"],
        unique=False,
    )
    op.create_index(
        op.f("idx_manual_vectors_branch"),
        "manual_vectors",
        ["branch_code"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("idx_manual_vectors_branch"), table_name="manual_vectors")
    op.drop_index(op.f("idx_manual_vectors_business"), table_name="manual_vectors")
    op.drop_index(op.f("idx_manual_vectors_error"), table_name="manual_vectors")
    op.drop_table("manual_vectors")

    op.drop_index(op.f("idx_consultation_vectors_branch"), table_name="consultation_vectors")
    op.drop_index(op.f("idx_consultation_vectors_business"), table_name="consultation_vectors")
    op.drop_index(op.f("idx_consultation_vectors_error"), table_name="consultation_vectors")
    op.drop_table("consultation_vectors")

    op.drop_index("ix_retry_queue_jobs_target_id", table_name="retry_queue_jobs")
    op.drop_table("retry_queue_jobs")

    op.drop_index(
        "ix_manual_vector_index_error_code",
        table_name="manual_vector_index",
    )
    op.drop_index(
        "ix_manual_vector_index_business_type",
        table_name="manual_vector_index",
    )
    op.drop_table("manual_vector_index")

    op.drop_index(
        "ix_consultation_vector_index_error_code",
        table_name="consultation_vector_index",
    )
    op.drop_index(
        "ix_consultation_vector_index_business_type",
        table_name="consultation_vector_index",
    )
    op.drop_index(
        "ix_consultation_vector_index_branch_code",
        table_name="consultation_vector_index",
    )
    op.drop_table("consultation_vector_index")

    op.drop_index("ix_task_history_task_id", table_name="task_history")
    op.drop_table("task_history")

    op.drop_table("manual_review_tasks")

    op.drop_constraint(
        "fk_consultations_manual_entry_id",
        "consultations",
        type_="foreignkey",
    )
    op.drop_index("ix_manual_entries_error_code", table_name="manual_entries")
    op.drop_index("ix_manual_entries_business_type", table_name="manual_entries")
    op.drop_table("manual_entries")

    op.drop_index("ix_consultations_manual_entry_id", table_name="consultations")
    op.drop_index("ix_consultations_error_code", table_name="consultations")
    op.drop_index("ix_consultations_business_type", table_name="consultations")
    op.drop_index("ix_consultations_branch_code", table_name="consultations")
    op.drop_table("consultations")

    op.drop_table("manual_versions")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_name in (
        "retry_job_status",
        "retry_target",
        "index_status",
        "manual_status",
        "task_status",
        "user_role",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
