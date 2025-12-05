"""
VectorStore Factory
Creates appropriate VectorStore implementation based on configuration
"""

from typing import Literal

from app.vectorstore.protocol import VectorStoreProtocol
from app.vectorstore.mock import MockVectorStore
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# Index names (RFP Section 3: Two separate indices)
CONSULTATION_INDEX = "consultations"
MANUAL_INDEX = "manuals"


def get_vectorstore(
    index_name: Literal["consultations", "manuals"],
) -> VectorStoreProtocol:
    """
    Get VectorStore implementation based on configuration

    Args:
        index_name: Name of the index to use

    Returns:
        VectorStore implementation

    Raises:
        ValueError: If vectorstore_type is not supported

    Usage:
        consultation_vs = get_vectorstore("consultations")
        manual_vs = get_vectorstore("manuals")
    """
    vectorstore_type = settings.vectorstore_type

    logger.info(
        "vectorstore_factory",
        index_name=index_name,
        vectorstore_type=vectorstore_type,
    )

    if vectorstore_type == "mock":
        return MockVectorStore(index_name=index_name)

    # TODO: Implement other vectorstore types
    # elif vectorstore_type == "pgvector":
    #     return PGVectorStore(index_name=index_name)
    # elif vectorstore_type == "pinecone":
    #     return PineconeVectorStore(index_name=index_name)
    # elif vectorstore_type == "qdrant":
    #     return QdrantVectorStore(index_name=index_name)

    else:
        raise ValueError(
            f"Unsupported vectorstore_type: {vectorstore_type}. "
            f"Supported types: mock, pgvector, pinecone, qdrant"
        )


# Singleton instances for dependency injection
_consultation_vectorstore: VectorStoreProtocol | None = None
_manual_vectorstore: VectorStoreProtocol | None = None


def get_consultation_vectorstore() -> VectorStoreProtocol:
    """
    Get singleton Consultation VectorStore instance

    Returns:
        VectorStore for consultations
    """
    global _consultation_vectorstore
    if _consultation_vectorstore is None:
        _consultation_vectorstore = get_vectorstore(CONSULTATION_INDEX)
    return _consultation_vectorstore


def get_manual_vectorstore() -> VectorStoreProtocol:
    """
    Get singleton Manual VectorStore instance

    Returns:
        VectorStore for manuals
    """
    global _manual_vectorstore
    if _manual_vectorstore is None:
        _manual_vectorstore = get_vectorstore(MANUAL_INDEX)
    return _manual_vectorstore
