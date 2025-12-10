"""Add business_type and error_code to ManualVersion, change unique constraint."""

from alembic import op
import sqlalchemy as sa

revision = "20251211_0001_group_fields"
down_revision = "a11804d6157b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "manual_versions_version_key",
        "manual_versions",
        type_="unique",
    )

    op.add_column(
        "manual_versions",
        sa.Column(
            "business_type",
            sa.String(50),
            nullable=True,
            comment="업무구분 (그룹 식별용)",
        ),
    )
    op.add_column(
        "manual_versions",
        sa.Column(
            "error_code",
            sa.String(50),
            nullable=True,
            comment="에러코드 (그룹 식별용)",
        ),
    )

    op.create_index(
        "ix_manual_versions_business_type",
        "manual_versions",
        ["business_type"],
    )
    op.create_index(
        "ix_manual_versions_error_code",
        "manual_versions",
        ["error_code"],
    )

    op.create_unique_constraint(
        "uq_manual_version_group",
        "manual_versions",
        ["business_type", "error_code", "version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_manual_version_group",
        "manual_versions",
        type_="unique",
    )

    op.drop_index(
        "ix_manual_versions_error_code",
        table_name="manual_versions",
    )
    op.drop_index(
        "ix_manual_versions_business_type",
        table_name="manual_versions",
    )

    op.drop_column("manual_versions", "error_code")
    op.drop_column("manual_versions", "business_type")

    op.create_unique_constraint(
        "manual_versions_version_key",
        "manual_versions",
        ["version"],
    )
