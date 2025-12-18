"""migrate_to_e5_embeddings_384d

Revision ID: 7b806107c5a8
Revises: 20251216_0004
Create Date: 2025-12-18 15:19:48.233434

Migration Strategy:
- Drop existing pgvector tables (consultation_vectors, manual_vectors)
- Tables will be recreated by PGVectorStore._create_extension_and_table()
  with correct 384 dimensions (E5) instead of 1536 (OpenAI)
- All existing embeddings will be lost (acceptable for this project)

BREAKING CHANGE: All vector data will be deleted
- Fresh start with E5 embeddings
- New data will be indexed automatically as it's created

Why dimension change is necessary:
- Old: OpenAI text-embedding-ada-002 (1536 dimensions)
- New: E5 multilingual-e5-small-ko-v2 (384 dimensions)
- Dimension mismatch prevents vector operations
- No conversion possible (information loss), full table drop required

Post-migration:
1. Run application - tables auto-created with new schema (384d)
2. New consultations/manuals will be indexed automatically
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b806107c5a8'
down_revision: Union[str, Sequence[str], None] = '20251216_0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Drop existing pgvector tables to allow recreation with E5 dimensions.

    This is a destructive migration. All vector embeddings will be lost.
    Tables will be auto-recreated by PGVectorStore with 384 dimensions.
    """
    # Drop consultation_vectors table if exists
    op.execute("""
        DROP TABLE IF EXISTS consultation_vectors CASCADE;
    """)

    # Drop manual_vectors table if exists
    op.execute("""
        DROP TABLE IF EXISTS manual_vectors CASCADE;
    """)

    # Note: pgvector extension itself is NOT dropped
    # Tables will be auto-created with correct schema on first access


def downgrade() -> None:
    """
    Downgrade is not supported for this migration.

    Reason: Cannot reconstruct 1536-dimensional embeddings from 384-dimensional ones.
    If rollback is needed, restore from database backup before migration.
    """
    raise NotImplementedError(
        "Downgrade not supported for E5 dimension migration. "
        "Restore from backup if rollback is required."
    )
