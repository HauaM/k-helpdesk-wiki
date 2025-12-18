"""
PGVector VectorStore implementation.

Uses PostgreSQL + pgvector extension to persist embeddings derived from
local E5 semantic model. All embedding operations use EmbeddingService
with async-safe threadpool executor wrapping.

Reference: Unit Specification v1.1
- ASYNC SAFETY: Embeddings via EmbeddingService with executor wrapping
- E5 USAGE: "query:" for searches, "passage:" for documents
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text as sa_text, bindparam, String, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.core.db import get_async_engine
from app.core.logging import get_logger
from app.vectorstore.protocol import VectorStoreProtocol, VectorSearchResult
from app.llm.embedder import get_embedding_service

logger = get_logger(__name__)


class PGVectorStore(VectorStoreProtocol):
    """PostgreSQL + pgvector-backed VectorStore.

    Uses local E5 semantic embeddings with async-safe operations.
    All embeddings routed through EmbeddingService with E5 prefixes.
    Storage: single table per index (consultations/manuals) with JSON metadata.

    Unit Spec v1.1 Compliance:
    - ✅ ASYNC SAFETY: Embeddings via EmbeddingService.embed_query/passage()
    - ✅ E5 USAGE: Query/passage prefixes applied automatically
    """

    def __init__(self, index_name: str, engine: AsyncEngine | None = None) -> None:
        self.index_name = index_name
        self.engine = engine or get_async_engine()
        self.dimension = settings.vectorstore_dimension
        self.table_name = self._resolve_table_name(index_name)
        self.embedding_service = get_embedding_service()
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def index_document(
        self,
        id: UUID,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        await self._ensure_initialized()

        # Use EmbeddingService with "passage:" prefix (E5 requirement)
        embedding = await self.embedding_service.embed_passage(text)
        metadata = metadata or {}
        metadata_json = self._normalize_metadata(metadata)

        params: dict[str, Any] = {
            "id": id,
            "embedding": embedding,
            "metadata": metadata_json,
            "branch_code": metadata.get("branch_code"),
            "business_type": metadata.get("business_type"),
            "error_code": metadata.get("error_code"),
            "created_at": metadata.get("created_at"),
        }

        upsert_sql = f"""
            INSERT INTO {self.table_name}
                (id, embedding, metadata, branch_code, business_type, error_code, created_at)
            VALUES
                (:id, :embedding, :metadata, :branch_code, :business_type, :error_code, :created_at)
            ON CONFLICT (id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata,
                branch_code = EXCLUDED.branch_code,
                business_type = EXCLUDED.business_type,
                error_code = EXCLUDED.error_code,
                created_at = COALESCE(EXCLUDED.created_at, {self.table_name}.created_at)
        """

        stmt = sa_text(upsert_sql).bindparams(
            bindparam("id", type_=PGUUID()),
            bindparam("embedding", type_=Vector(self.dimension)),
            bindparam("metadata", type_=JSONB),
            bindparam("branch_code", type_=String()),
            bindparam("business_type", type_=String()),
            bindparam("error_code", type_=String()),
        )

        async with self.engine.begin() as conn:
            await conn.execute(stmt, params)
            logger.info("pgvector_indexed", index=self.index_name, doc_id=str(id))

    async def search(
        self,
        query: str,
        top_k: int = 10,
        metadata_filter: dict | None = None,
    ) -> list[VectorSearchResult]:
        await self._ensure_initialized()

        # Use EmbeddingService with "query:" prefix (E5 requirement)
        query_embedding = await self.embedding_service.embed_query(query)
        filters: list[str] = []
        params: dict[str, Any] = {"embedding": query_embedding, "limit": top_k}

        metadata_filter = metadata_filter or {}
        for key in ("branch_code", "business_type", "error_code"):
            value = metadata_filter.get(key)
            if value is not None:
                filters.append(f"{key} = :{key}")
                params[key] = value

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        # similarity: convert L2 distance to [0,1) score (1/(1+distance))
        search_sql = f"""
            SELECT
                id,
                metadata,
                1.0 / (1.0 + (embedding <-> :embedding)) AS score
            FROM {self.table_name}
            {where_clause}
            ORDER BY embedding <-> :embedding
            LIMIT :limit
        """

        bind_list = [
            bindparam("embedding", type_=Vector(self.dimension)),
            bindparam("limit", type_=Integer()),
        ]
        for key in ("branch_code", "business_type", "error_code"):
            if key in params:
                bind_list.append(bindparam(key, type_=String(), required=False))

        search_stmt = sa_text(search_sql).bindparams(*bind_list)

        async with self.engine.connect() as conn:
            result = await conn.execute(search_stmt, params)
            rows = result.fetchall()

        return [
            VectorSearchResult(
                id=row.id,
                score=float(row.score) if row.score is not None else 0.0,
                metadata=row.metadata,
            )
            for row in rows
        ]

    async def delete_document(self, id: UUID) -> None:
        await self._ensure_initialized()
        async with self.engine.begin() as conn:
            await conn.execute(sa_text(f"DELETE FROM {self.table_name} WHERE id = :id"), {"id": id})

    async def clear_index(self) -> None:
        await self._ensure_initialized()
        async with self.engine.begin() as conn:
            await conn.execute(sa_text(f"TRUNCATE TABLE {self.table_name}"))
            logger.warning("pgvector_index_cleared", index=self.index_name)

    async def similarity(self, text1: str, text2: str) -> float:
        """
        Calculate cosine similarity between query (text1) and passage (text2).

        Uses E5 query/passage prefixes for consistency with search operations.

        **CORRECTED (Item 2)**: Now uses similarity_query_passage() with E5 prefixes
        to maintain consistency with search embeddings and avoid threshold drift.

        Args:
            text1: Query text (will be prefixed with "query:")
            text2: Passage text (will be prefixed with "passage:")

        Returns:
            Cosine similarity score in range [-1, 1]
            (Practically [0, 1] for E5, but theoretically [-1, 1])

        Unit Spec v1.1 (CORRECTED):
        - Uses EmbeddingService.similarity_query_passage() with E5 prefixes
        - Consistent with search operation embeddings
        - Correct math: cosine ∈ [-1, 1] for L2-normalized vectors
        """
        # Item 2 Fix: Use query/passage prefixes for consistency
        similarity_score = await self.embedding_service.similarity_query_passage(
            query_text=text1, passage_text=text2
        )

        logger.debug(
            "pgvector_similarity_calculated",
            text1_length=len(text1),
            text2_length=len(text2),
            score=f"{similarity_score:.4f}",
        )

        return similarity_score

    # Internal helpers -------------------------------------------------

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return

            await self._create_extension_and_table()
            self._initialized = True

    async def _create_extension_and_table(self) -> None:
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id UUID PRIMARY KEY,
                embedding VECTOR({self.dimension}) NOT NULL,
                metadata JSONB DEFAULT '{{}}'::jsonb,
                branch_code TEXT NULL,
                business_type TEXT NULL,
                error_code TEXT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """

        alter_columns = [
            f"ALTER TABLE {self.table_name} ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{{}}'::jsonb",
            f"ALTER TABLE {self.table_name} ADD COLUMN IF NOT EXISTS branch_code TEXT",
            f"ALTER TABLE {self.table_name} ADD COLUMN IF NOT EXISTS business_type TEXT",
            f"ALTER TABLE {self.table_name} ADD COLUMN IF NOT EXISTS error_code TEXT",
            f"ALTER TABLE {self.table_name} ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        ]

        # Optional helper indexes for metadata filters
        branch_idx = f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_branch ON {self.table_name} (branch_code)"
        business_idx = f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_business ON {self.table_name} (business_type)"
        error_idx = f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_error ON {self.table_name} (error_code)"

        async with self.engine.begin() as conn:
            await conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
            await self._recreate_table_if_incompatible(conn)
            await conn.execute(sa_text(create_table_sql))
            for stmt in alter_columns:
                await conn.execute(sa_text(stmt))
            await conn.execute(sa_text(branch_idx))
            await conn.execute(sa_text(business_idx))
            await conn.execute(sa_text(error_idx))
            logger.info("pgvector_table_ready", table=self.table_name, dimension=self.dimension)

    async def _recreate_table_if_incompatible(self, conn: Any) -> None:
        """Drop and recreate table if existing schema is incompatible.

        If the table exists with a non-UUID id or leftover columns (e.g., consultation_id bigint),
        it will be dropped when empty. If it has data, we raise to avoid destructive migration.
        """

        # Check if table exists
        exists_sql = sa_text(
            """
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = :table
            """
        )
        result = await conn.execute(exists_sql, {"table": self.table_name})
        columns = result.fetchall()
        if not columns:
            return

        col_map = {row.column_name: (row.data_type, row.udt_name) for row in columns}
        id_type = col_map.get("id")
        has_consultation_id = "consultation_id" in col_map

        compatible = id_type is not None and id_type[0] == "uuid" and not has_consultation_id

        if compatible:
            return

        count_res = await conn.execute(sa_text(f"SELECT COUNT(*) FROM {self.table_name}"))
        row_count = count_res.scalar_one()
        if row_count == 0:
            logger.warning(
                "pgvector_incompatible_schema_dropped",
                table=self.table_name,
                columns=list(col_map.keys()),
            )
            await conn.execute(sa_text(f"DROP TABLE {self.table_name}"))
        else:
            raise RuntimeError(
                f"Existing table {self.table_name} has incompatible schema (id type or extra columns). "
                "Drop or migrate it manually to use pgvector store."
            )

    def _resolve_table_name(self, index_name: str) -> str:
        table_name = settings.pgvector_table_consultation
        if index_name == "manuals":
            table_name = settings.pgvector_table_manual

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            raise ValueError(f"Unsafe table name: {table_name}")

        return table_name

    def _normalize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Convert metadata to JSON-serializable values (datetimes -> isoformat)."""

        normalized: dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, datetime):
                normalized[key] = value.isoformat()
            else:
                normalized[key] = value
        return normalized
