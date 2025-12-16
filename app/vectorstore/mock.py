"""
Mock VectorStore Implementation
In-memory implementation for development/testing
"""

from uuid import UUID
from typing import Dict
import asyncio

from app.vectorstore.protocol import VectorSearchResult
from app.core.exceptions import VectorIndexError, VectorSearchError
from app.core.logging import get_logger

logger = get_logger(__name__)


class MockVectorStore:
    """
    Mock VectorStore using in-memory dictionary

    RFP Reference: Section 2 - Mock implementation
    Uses simple text matching instead of real embeddings
    """

    def __init__(self, index_name: str):
        """
        Initialize mock vector store

        Args:
            index_name: Name of the index (e.g., "consultations", "manuals")
        """
        self.index_name = index_name
        self._storage: Dict[UUID, tuple[str, dict | None]] = {}
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
        Simple keyword-based search (mock implementation)

        Args:
            query: Query text
            top_k: Number of results
            metadata_filter: Optional filters (not implemented in mock)

        Returns:
            List of search results
        """
        try:
            # Simulate async operation
            await asyncio.sleep(0.02)

            query_lower = query.lower()
            results = []

            for doc_id, (text, metadata) in self._storage.items():
                # Simple keyword matching (not real vector similarity)
                text_lower = text.lower()

                # Simple substring + word-overlap matching
                substring_score = 0.0
                if query_lower in text_lower:
                    substring_score = min(len(query_lower) / max(len(text_lower), 1), 1.0)

                query_words = set(query_lower.split())
                text_words = set(text_lower.split())
                matches = len(query_words & text_words)

                overlap_score = 0.0
                if matches > 0:
                    overlap_score = min(matches / len(query_words), 1.0)

                score = max(substring_score, overlap_score)
                if score > 0:
                    results.append(
                        VectorSearchResult(id=doc_id, score=score, metadata=metadata)
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
        Calculate similarity score between two texts (mock implementation)

        Uses same keyword-overlap logic as search()

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0.0 to 1.0)
        """
        try:
            # Simulate async operation
            await asyncio.sleep(0.01)

            text1_lower = text1.lower()
            text2_lower = text2.lower()

            # Substring matching
            substring_score = 0.0
            if text1_lower in text2_lower or text2_lower in text1_lower:
                min_len = min(len(text1_lower), len(text2_lower))
                max_len = max(len(text1_lower), len(text2_lower))
                substring_score = min_len / max(max_len, 1)

            # Word overlap matching
            text1_words = set(text1_lower.split())
            text2_words = set(text2_lower.split())
            matches = len(text1_words & text2_words)

            overlap_score = 0.0
            if matches > 0:
                union = len(text1_words | text2_words)
                overlap_score = matches / max(union, 1)

            # Use max of both scores
            score = max(substring_score, overlap_score)

            logger.debug(
                "similarity_calculated",
                index=self.index_name,
                text1_length=len(text1),
                text2_length=len(text2),
                score=f"{score:.2f}",
            )

            return score

        except Exception as e:
            logger.error("similarity_error", error=str(e))
            raise VectorSearchError(f"Failed to calculate similarity: {e}")
