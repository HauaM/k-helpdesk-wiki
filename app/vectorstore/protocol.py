"""
VectorStore Protocol (Interface)
Defines contract for all VectorStore implementations
"""

from typing import Protocol, NamedTuple
from uuid import UUID


class VectorSearchResult(NamedTuple):
    """
    Single vector search result

    Attributes:
        id: Document UUID
        score: Similarity score (0.0 to 1.0, higher is more similar)
        metadata: Optional metadata dict
    """

    id: UUID
    score: float
    metadata: dict | None = None


class VectorStoreProtocol(Protocol):
    """
    Protocol for VectorStore implementations

    RFP Reference: Section 2 - VectorStore requirements
    - Must support abstract interface
    - Implementation can be swapped (Pinecone, Qdrant, Milvus, FAISS)
    - Two separate indices: Consultation and Manual
    """

    async def index_document(
        self,
        id: UUID,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Index a document (create embedding and store)

        Args:
            id: Document UUID
            text: Text to embed and index
            metadata: Optional metadata to store with vector

        Raises:
            VectorIndexError: If indexing fails
        """
        ...

    async def search(
        self,
        query: str,
        top_k: int = 10,
        metadata_filter: dict | None = None,
    ) -> list[VectorSearchResult]:
        """
        Search for similar documents

        Args:
            query: Query text to embed and search
            top_k: Number of results to return
            metadata_filter: Optional metadata filters

        Returns:
            List of search results ordered by similarity (highest first)

        Raises:
            VectorSearchError: If search fails
        """
        ...

    async def delete_document(self, id: UUID) -> None:
        """
        Delete document from index

        Args:
            id: Document UUID to delete
        """
        ...

    async def update_document(
        self,
        id: UUID,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Update existing document

        Args:
            id: Document UUID
            text: New text to embed
            metadata: New metadata

        Default implementation: delete + index
        """
        await self.delete_document(id)
        await self.index_document(id, text, metadata)

    async def clear_index(self) -> None:
        """
        Clear all documents from index

        WARNING: Destructive operation. Use with caution.
        """
        ...
