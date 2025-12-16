"""
PGVector VectorStore implementation.

Uses PostgreSQL + pgvector extension to persist embeddings. Embeddings are derived
locally via a lightweight hashed bag-of-words so the service can run without an
external embedding provider. Replace `_embed_text` with a real embedder when ready.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
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

logger = get_logger(__name__)


class PGVectorStore(VectorStoreProtocol):
    """Simple pgvector-backed VectorStore.

    Embeddings: deterministic hashed bag-of-words to avoid external calls.
    Storage: single table per index (consultations/manuals) with JSON metadata.
    """

    def __init__(self, index_name: str, engine: AsyncEngine | None = None) -> None:
        self.index_name = index_name
        self.engine = engine or get_async_engine()
        self.dimension = settings.vectorstore_dimension
        self.table_name = self._resolve_table_name(index_name)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def index_document(
        self,
        id: UUID,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        await self._ensure_initialized()

        embedding = self._embed_text(text)
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

        stmt = (
            sa_text(upsert_sql)
            .bindparams(
                bindparam("id", type_=PGUUID()),
                bindparam("embedding", type_=Vector(self.dimension)),
                bindparam("metadata", type_=JSONB),
                bindparam("branch_code", type_=String()),
                bindparam("business_type", type_=String()),
                bindparam("error_code", type_=String()),
            )
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

        query_embedding = self._embed_text(query)
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
        Calculate similarity score between two texts

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0.0 to 1.0)
        """
        embedding1 = self._embed_text(text1)
        embedding2 = self._embed_text(text2)

        # Cosine similarity: dot product of normalized vectors
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        similarity_score = (dot_product + 1.0) / 2.0  # Normalize to [0, 1]

        logger.debug(
            "pgvector_similarity_calculated",
            text1_length=len(text1),
            text2_length=len(text2),
            score=f"{similarity_score:.2f}",
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
        business_idx = (
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_business ON {self.table_name} (business_type)"
        )
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

    async def _recreate_table_if_incompatible(self, conn) -> None:
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

        compatible = (
            id_type is not None
            and id_type[0] == "uuid"
            and not has_consultation_id
        )

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

    def _embed_text(self, text: str) -> list[float]:
        """Deterministic hashed bag-of-words embedding.

        This avoids external API calls while providing stable vectors for the
        same input text. Replace with real embeddings once an embedding client
        is available.
        """

        tokens = re.findall(r"[\w']+", text.lower())
        vector = [0.0] * self.dimension

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            vector[bucket] += 1.0

        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def _normalize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Convert metadata to JSON-serializable values (datetimes -> isoformat)."""

        normalized: dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, datetime):
                normalized[key] = value.isoformat()
            else:
                normalized[key] = value
        return normalized
