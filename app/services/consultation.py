"""
Consultation Service
Business logic for consultation operations

RFP Reference: Section 8 - Service Layer Responsibilities
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.consultation_rdb import ConsultationRDBRepository
from app.vectorstore.protocol import VectorStoreProtocol
from app.llm.protocol import LLMClientProtocol
from app.models.consultation import Consultation
from app.core.logging import get_logger

logger = get_logger(__name__)


class ConsultationService:
    """
    Consultation business logic

    RFP Requirements:
    1. register_consultation() - Save to RDB + VectorStore
    2. search_similar_consultations() - Vector search + RDB filter
    3. Manual generation trigger

    MCP-Ready: No FastAPI dependencies, pure Pydantic/types
    """

    def __init__(
        self,
        session: AsyncSession,
        vectorstore: VectorStoreProtocol,
        llm_client: LLMClientProtocol,
    ):
        """
        Initialize service with dependencies

        Args:
            session: Database session
            vectorstore: VectorStore for consultations
            llm_client: LLM client for text processing
        """
        self.session = session
        self.repo = ConsultationRDBRepository(session)
        self.vectorstore = vectorstore
        self.llm_client = llm_client

    async def register_consultation(
        self,
        summary: str,
        inquiry_text: str,
        action_taken: str,
        branch_code: str,
        employee_id: str,
        **metadata,
    ) -> Consultation:
        """
        Register new consultation

        RFP Reference: Section 5.1, Step 1-2
        1. Save to RDB
        2. Index in VectorStore

        Args:
            summary: Consultation summary
            inquiry_text: Customer inquiry
            action_taken: Actions taken
            branch_code: Branch code
            employee_id: Employee ID
            **metadata: Additional fields (screen_id, business_type, etc.)

        Returns:
            Created Consultation instance

        Raises:
            DatabaseError: If RDB save fails
            VectorIndexError: If vector indexing fails
        """
        logger.info(
            "register_consultation_start",
            branch_code=branch_code,
            employee_id=employee_id,
        )

        # TODO: Implement full logic
        # 1. Create Consultation model instance
        # 2. Save to RDB via repository
        # 3. Build text for embedding (summary + inquiry + action)
        # 4. Index in VectorStore with metadata
        # 5. Return created consultation

        # Placeholder
        raise NotImplementedError("register_consultation() - TODO")

    async def search_similar_consultations(
        self,
        query: str,
        top_k: int = 10,
        branch_code: str | None = None,
        business_type: str | None = None,
        error_code: str | None = None,
        similarity_threshold: float = 0.7,
    ) -> list[tuple[Consultation, float]]:
        """
        Search for similar consultations

        RFP Reference: Section 6 - Search Requirements
        1. Query → embedding
        2. VectorStore search
        3. Get Top-K IDs
        4. RDB filter by metadata
        5. Re-rank and apply threshold

        Args:
            query: Search query text
            top_k: Number of results
            branch_code: Optional branch filter
            business_type: Optional business type filter
            error_code: Optional error code filter
            similarity_threshold: Minimum similarity score

        Returns:
            List of (Consultation, similarity_score) tuples

        Raises:
            VectorSearchError: If vector search fails
        """
        logger.info(
            "search_consultations_start",
            query_length=len(query),
            top_k=top_k,
        )

        # TODO: Implement full logic
        # 1. VectorStore search → get IDs + scores
        # 2. Fetch consultations from RDB by IDs
        # 3. Apply metadata filters (branch, business_type, error_code)
        # 4. Apply similarity threshold
        # 5. Return sorted results

        # Placeholder
        raise NotImplementedError("search_similar_consultations() - TODO")

    async def should_generate_manual(self, consultation_id: UUID) -> bool:
        """
        Determine if consultation should generate manual

        RFP Reference: Section 5.1, Step 3
        Business rule: Popup asks user "메뉴얼 생성하시겠습니까?"

        Args:
            consultation_id: Consultation UUID

        Returns:
            True if manual should be generated (decision logic TBD)
        """
        logger.debug("check_manual_generation", consultation_id=str(consultation_id))

        # TODO: Implement business logic
        # Possible rules:
        # - Check if error_code exists
        # - Check if similar consultations exist
        # - Check consultation quality/completeness
        # For now, always return True for user to decide

        return True
