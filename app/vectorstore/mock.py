"""
Mock VectorStore Implementation
In-memory implementation for development/testing.

Uses EmbeddingService for semantic embeddings (E5 model).
All embedding operations are async-safe and include E5 prefixes.

Reference: Unit Specification v1.1
- ASYNC SAFETY: Embeddings via EmbeddingService with executor wrapping
- E5 USAGE: "query:" for searches, "passage:" for documents
"""

from uuid import UUID
from typing import Dict
import asyncio

from app.vectorstore.protocol import VectorSearchResult
from app.core.exceptions import VectorIndexError, VectorSearchError
from app.core.logging import get_logger
from app.llm.embedder import get_embedding_service

logger = get_logger(__name__)


class MockVectorStore:
    """
    Mock VectorStore using in-memory dictionary.

    Uses EmbeddingService for semantic embeddings (E5 model).
    All embedding operations are async-safe with proper E5 prefixes.

    Unit Spec v1.1 Compliance:
    - ✅ ASYNC SAFETY: Embeddings via EmbeddingService
    - ✅ E5 USAGE: Query/passage prefixes applied automatically
    """

    def __init__(self, index_name: str):
        """
        Initialize mock vector store

        Args:
            index_name: Name of the index (e.g., "consultations", "manuals")
        """
        self.index_name = index_name
        self._storage: Dict[UUID, tuple[str, dict | None]] = {}
        self.embedding_service = get_embedding_service()
        logger.info("mock_vectorstore_initialized", index_name=index_name)

    async def index_document(
        self,
        id: UUID,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Store document in memory

        Args:
            id: Document UUID
            text: Text content
            metadata: Optional metadata
        """
        try:
            # Simulate async operation
            await asyncio.sleep(0.01)

            self._storage[id] = (text, metadata)
            logger.debug(
                "document_indexed",
                index=self.index_name,
                doc_id=str(id),
                text_length=len(text),
            )
        except Exception as e:
            logger.error("index_error", error=str(e), doc_id=str(id))
            raise VectorIndexError(f"Failed to index document: {e}")

    async def search(
        self,
        query: str,
        top_k: int = 10,
        metadata_filter: dict | None = None,
    ) -> list[VectorSearchResult]:
        """
        Semantic search using E5 embeddings (mock implementation).

        Uses EmbeddingService for async-safe embedding operations.
        All embeddings include proper E5 prefixes.

        Args:
            query: Query text
            top_k: Number of results
            metadata_filter: Optional filters (not implemented in mock)

        Returns:
            List of search results sorted by semantic similarity

        Unit Spec v1.1:
        - ASYNC SAFETY: Uses EmbeddingService.embed_query() with executor
        - E5 USAGE: Query embedding includes "query:" prefix
        """
        try:
            # Embed query using EmbeddingService with "query:" prefix
            query_embedding = await self.embedding_service.embed_query(query)
            results = []

            # Calculate similarity for each stored document
            for doc_id, (text, metadata) in self._storage.items():
                # Embed document using EmbeddingService with "passage:" prefix
                doc_embedding = await self.embedding_service.embed_passage(text)

                # Cosine similarity: dot product of L2-normalized vectors
                score = sum(a * b for a, b in zip(query_embedding, doc_embedding))

                if score > 0:
                    results.append(
                        VectorSearchResult(id=doc_id, score=float(score), metadata=metadata)
                    )

            # Sort by score descending
            results.sort(key=lambda r: r.score, reverse=True)

            # Return top K
            top_results = results[:top_k]

            logger.debug(
                "search_completed",
                index=self.index_name,
                query_length=len(query),
                results_found=len(results),
                top_k=top_k,
            )

            return top_results

        except Exception as e:
            logger.error("search_error", error=str(e), query=query)
            raise VectorSearchError(f"Failed to search: {e}")

    async def delete_document(self, id: UUID) -> None:
        """
        Delete document from storage

        Args:
            id: Document UUID
        """
        if id in self._storage:
            del self._storage[id]
            logger.debug("document_deleted", index=self.index_name, doc_id=str(id))

    async def update_document(
        self,
        id: UUID,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Update existing document (delete + re-index)

        Args:
            id: Document UUID
            text: New text content
            metadata: New metadata
        """
        await self.delete_document(id)
        await self.index_document(id, text, metadata)

    async def clear_index(self) -> None:
        """
        Clear all documents
        """
        count = len(self._storage)
        self._storage.clear()
        logger.info("index_cleared", index=self.index_name, documents_removed=count)

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
        try:
            # Item 2 Fix: Use query/passage prefixes for consistency
            score = await self.embedding_service.similarity_query_passage(
                query_text=text1, passage_text=text2
            )

            logger.debug(
                "similarity_calculated",
                index=self.index_name,
                text1_length=len(text1),
                text2_length=len(text2),
                score=f"{score:.4f}",
            )

            return score

        except Exception as e:
            logger.error("similarity_error", error=str(e))
            raise VectorSearchError(f"Failed to calculate similarity: {e}")
