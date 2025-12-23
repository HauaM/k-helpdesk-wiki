"""Create pgvector tables for 384d embeddings

Revision ID: 20251223_0001_create_pgvector_tables_384d
Revises: 20251221_1200_drop_username_from_users
Create Date: 2025-12-23 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20251223_0001_create_pgvector_tables_384d"
down_revision: Union[str, Sequence[str], None] = "20251221_1200_drop_username_from_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create pgvector-backed tables for manual/consultation embeddings."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS consultation_vectors (
            id UUID PRIMARY KEY,
            embedding VECTOR(384) NOT NULL,
            metadata JSONB DEFAULT '{}'::jsonb,
            branch_code TEXT,
            business_type TEXT,
            error_code TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_consultation_vectors_error "
        "ON consultation_vectors (error_code);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_consultation_vectors_business "
        "ON consultation_vectors (business_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_consultation_vectors_branch "
        "ON consultation_vectors (branch_code);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_vectors (
            id UUID PRIMARY KEY,
            embedding VECTOR(384) NOT NULL,
            metadata JSONB DEFAULT '{}'::jsonb,
            branch_code TEXT,
            business_type TEXT,
            error_code TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_manual_vectors_error "
        "ON manual_vectors (error_code);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_manual_vectors_business "
        "ON manual_vectors (business_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_manual_vectors_branch "
        "ON manual_vectors (branch_code);"
    )


def downgrade() -> None:
    """Drop pgvector tables and indexes."""
    op.execute("DROP INDEX IF EXISTS idx_manual_vectors_branch")
    op.execute("DROP INDEX IF EXISTS idx_manual_vectors_business")
    op.execute("DROP INDEX IF EXISTS idx_manual_vectors_error")
    op.execute("DROP TABLE IF EXISTS manual_vectors")

    op.execute("DROP INDEX IF EXISTS idx_consultation_vectors_branch")
    op.execute("DROP INDEX IF EXISTS idx_consultation_vectors_business")
    op.execute("DROP INDEX IF EXISTS idx_consultation_vectors_error")
    op.execute("DROP TABLE IF EXISTS consultation_vectors")
