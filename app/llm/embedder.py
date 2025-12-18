"""
E5 Semantic Embedding Service

Provides async-safe embedding operations for local E5 model.
All embedding operations are wrapped in threadpool executor to prevent
blocking the asyncio event loop.

Reference: Unit Specification v1.1 - ASYNC SAFETY & E5 USAGE RULES
Corrections Applied (2025-12-18):
- Item 1: asyncio.get_running_loop() + Semaphore concurrency control
- Item 2: Removed raw similarity(), added similarity_query_passage() with E5 prefixes
- Item 3: Corrected cosine similarity math explanation ([-1,1] range acknowledged)
"""

from __future__ import annotations

import asyncio
from typing import Optional

from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import VectorIndexError

logger = get_logger(__name__)


class EmbeddingService:
    """
    Async-safe embedding service using local E5 model.

    Key Features:
    - Singleton pattern: single model instance for entire application
    - Async safety: SentenceTransformer.encode() runs in threadpool executor
    - Concurrency control: Semaphore limits concurrent encoding operations
    - E5 prefixes: "query:" for searches, "passage:" for documents
    - Warmup: model preloaded at startup to avoid first-request delay
    - Error handling: fast-fail semantics with logging

    Unit Spec v1.1 Compliance (CORRECTED):
    - ✅ ASYNC SAFETY: asyncio.get_running_loop() + Semaphore throttling
    - ✅ E5 USAGE: Query/passage prefixes enforced, NO raw similarity
    - ✅ SINGLE ENTRY POINT: All embeddings through this service
    - ✅ LIFECYCLE: warmup() method for startup initialization
    - ✅ CORRECT MATH: Cosine similarity in [-1, 1] range acknowledged
    """

    _instance: Optional[EmbeddingService] = None

    def __new__(cls) -> EmbeddingService:
        """Singleton pattern: only one instance per app."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize embedding service (only runs once due to singleton)."""
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.model_name = settings.e5_model_name
        self.device = settings.embedding_device
        self.max_concurrency = settings.embedding_max_concurrency
        self.model: Optional[SentenceTransformer] = None
        self._initialized: bool = False
        self._load_lock = asyncio.Lock()

        # Semaphore for concurrency control (Item 1 fix)
        # Prevents threadpool flooding under high load
        self._semaphore: Optional[asyncio.Semaphore] = None

        logger.info(
            "embedding_service_created",
            model_name=self.model_name,
            device=self.device,
            max_concurrency=self.max_concurrency,
        )

    async def warmup(self) -> None:
        """
        Preload model at application startup.

        This prevents the first embedding request from triggering a
        slow model download/initialization. Must be called in app
        startup event before accepting requests.

        Raises:
            VectorIndexError: If model loading fails
        """
        import time

        try:
            if self._initialized:
                logger.debug("embedding_service_already_warmed")
                return

            async with self._load_lock:
                if self._initialized:
                    return

                t0 = time.perf_counter()
                logger.info(
                    "embedding_service_warming_start",
                    model_name=self.model_name,
                    device=self.device,
                )

                # Load model in executor to avoid blocking (Item 1: get_running_loop)
                t_model_start = time.perf_counter()
                logger.info("embedding_service_loading_model", model_name=self.model_name)

                loop = asyncio.get_running_loop()
                self.model = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: SentenceTransformer(self.model_name, device=self.device),
                    ),
                    timeout=300,  # 5 min timeout for model download
                )

                t_model_elapsed = time.perf_counter() - t_model_start
                logger.info(
                    "embedding_service_model_loaded",
                    model_name=self.model_name,
                    elapsed_seconds=f"{t_model_elapsed:.2f}",
                )

                # Initialize semaphore after event loop is running
                self._semaphore = asyncio.Semaphore(self.max_concurrency)

                # Warmup with a simple test embedding (use _encode_async to avoid re-initialization)
                t_encode_start = time.perf_counter()
                logger.info("embedding_service_first_encode_start")

                _ = await self._encode_async("test")

                t_encode_elapsed = time.perf_counter() - t_encode_start
                logger.info(
                    "embedding_service_first_encode_done",
                    elapsed_seconds=f"{t_encode_elapsed:.2f}",
                )

                self._initialized = True
                t_total_elapsed = time.perf_counter() - t0
                logger.info(
                    "embedding_service_warmed",
                    model_name=self.model_name,
                    device=self.device,
                    total_elapsed_seconds=f"{t_total_elapsed:.2f}",
                    model_load_seconds=f"{t_model_elapsed:.2f}",
                    first_encode_seconds=f"{t_encode_elapsed:.2f}",
                )

        except asyncio.TimeoutError as e:
            logger.error(
                "embedding_service_warmup_timeout",
                model_name=self.model_name,
                error=str(e),
            )
            raise VectorIndexError(
                f"Timeout loading embedding model {self.model_name}: {e}"
            )
        except Exception as e:
            logger.error(
                "embedding_service_warmup_failed",
                model_name=self.model_name,
                error=str(e),
            )
            raise VectorIndexError(f"Failed to load embedding model {self.model_name}: {e}")

    async def embed_query(self, text: str) -> list[float]:
        """
        Embed a search query with "query:" prefix (E5 requirement).

        Args:
            text: The query text to embed

        Returns:
            Embedding vector (384 dimensions for multilingual-e5-small)

        Raises:
            VectorIndexError: If embedding fails
        """
        await self._ensure_initialized()
        try:
            prefixed_text = f"query: {text}"
            embedding = await self._encode_async(prefixed_text)
            logger.debug(
                "query_embedded",
                text_length=len(text),
                embedding_dim=len(embedding),
            )
            return embedding
        except Exception as e:
            logger.error("query_embedding_failed", error=str(e), text=text)
            raise VectorIndexError(f"Failed to embed query: {e}")

    async def embed_passage(self, text: str) -> list[float]:
        """
        Embed a document passage with "passage:" prefix (E5 requirement).

        Args:
            text: The document text to embed

        Returns:
            Embedding vector (384 dimensions for multilingual-e5-small)

        Raises:
            VectorIndexError: If embedding fails
        """
        await self._ensure_initialized()
        try:
            prefixed_text = f"passage: {text}"
            embedding = await self._encode_async(prefixed_text)
            logger.debug(
                "passage_embedded",
                text_length=len(text),
                embedding_dim=len(embedding),
            )
            return embedding
        except Exception as e:
            logger.error("passage_embedding_failed", error=str(e), text_length=len(text))
            raise VectorIndexError(f"Failed to embed passage: {e}")

    async def similarity_query_passage(self, query_text: str, passage_text: str) -> float:
        """
        Calculate cosine similarity between query and passage with E5 prefixes.

        This is the ONLY similarity method. It ensures consistency with search
        embeddings by using the same E5 query/passage convention.

        **Item 2 Fix**: Removed raw similarity(). All similarity calculations
        now use E5 prefixes to maintain consistency with search operations.

        **Item 3 Fix**: Cosine similarity math corrected:
        - For L2-normalized vectors, cosine similarity = dot product
        - Theoretical range: [-1, 1] (though E5 rarely produces negatives)
        - No transformation applied; returns raw dot product

        Args:
            query_text: Query text (will be prefixed with "query:")
            passage_text: Passage text (will be prefixed with "passage:")

        Returns:
            Cosine similarity score in range [-1, 1]
            (Practically [0, 1] for E5, but [-1, 1] is theoretically possible)

        Raises:
            VectorIndexError: If embedding fails

        Example:
            score = await service.similarity_query_passage(
                "로그인 오류",           # query: 로그인 오류
                "로그인 오류 해결 방법"   # passage: 로그인 오류 해결 방법
            )
            # score ≈ 0.85 (high similarity)
        """
        await self._ensure_initialized()
        try:
            # Embed with E5 prefixes (Item 2: consistency with search)
            query_embedding = await self.embed_query(query_text)
            passage_embedding = await self.embed_passage(passage_text)

            # Cosine similarity for L2-normalized vectors (Item 3: correct math)
            # E5 normalizes vectors, so cosine = dot product
            # Range: [-1, 1] theoretically, [0, 1] practically for E5
            dot_product = sum(a * b for a, b in zip(query_embedding, passage_embedding))
            similarity_score = float(dot_product)

            logger.debug(
                "similarity_calculated",
                query_length=len(query_text),
                passage_length=len(passage_text),
                score=f"{similarity_score:.4f}",
            )

            return similarity_score

        except Exception as e:
            logger.error("similarity_calculation_failed", error=str(e))
            raise VectorIndexError(f"Failed to calculate similarity: {e}")

    # Private helper methods ------------------------------------------------

    async def _ensure_initialized(self) -> None:
        """Ensure model is loaded (lazy initialization as fallback)."""
        if self._initialized:
            return

        logger.warning("embedding_service_lazy_initialization")
        await self.warmup()

    async def _encode_async(self, text: str) -> list[float]:
        """
        Encode text using SentenceTransformer in threadpool executor.

        This wrapper ensures SentenceTransformer.encode() (blocking CPU/GPU op)
        doesn't stall the asyncio event loop.

        **Item 1 Fixes Applied**:
        - asyncio.get_running_loop() instead of get_event_loop()
        - Semaphore wraps executor call to prevent threadpool flooding

        Args:
            text: Text to encode

        Returns:
            Embedding vector as list of floats

        Raises:
            RuntimeError: If model not initialized
            ValueError: If encoding produces invalid output
        """
        if self.model is None:
            raise RuntimeError("Model not initialized. Call warmup() first.")

        if self._semaphore is None:
            raise RuntimeError("Semaphore not initialized. Call warmup() first.")

        # Item 1 Fix: Use get_running_loop() for correct loop reference
        loop = asyncio.get_running_loop()
        model = self.model  # Capture reference for closure

        # Item 1 Fix: Semaphore limits concurrent encoding operations
        async with self._semaphore:
            # Run blocking encoding in threadpool executor
            embedding_array = await loop.run_in_executor(
                None,
                lambda: model.encode(text, normalize_embeddings=True),
            )

        # Convert numpy array to list of floats
        embedding_list = embedding_array.tolist()

        if not isinstance(embedding_list, list) or len(embedding_list) == 0:
            raise ValueError(f"Invalid embedding output: {embedding_list}")

        return embedding_list


# Singleton getter function for dependency injection
def get_embedding_service() -> EmbeddingService:
    """Get or create the singleton EmbeddingService instance."""
    return EmbeddingService()
