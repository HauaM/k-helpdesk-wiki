"""
VectorStore Abstraction
Interface and implementations for vector similarity search
"""

from app.vectorstore.protocol import VectorStoreProtocol, VectorSearchResult
from app.vectorstore.factory import get_vectorstore

__all__ = ["VectorStoreProtocol", "VectorSearchResult", "get_vectorstore"]
