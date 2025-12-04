"""
Manual Service
Business logic for manual operations

RFP Reference: Section 8 - Service Layer Responsibilities
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.manual_rdb import (
    ManualEntryRDBRepository,
    ManualVersionRepository,
    ManualReviewTaskRepository,
)
from app.vectorstore.protocol import VectorStoreProtocol
from app.llm.protocol import LLMClientProtocol
from app.models.manual import ManualEntry, ManualStatus
from app.models.task import ManualReviewTask, TaskStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class ManualService:
    """
    Manual business logic

    RFP Requirements:
    1. generate_manual_draft() - LLM-based manual generation
    2. detect_manual_conflicts() - Find similar existing manuals
    3. review_manual_task() - Approve/reject workflow
    4. Manual version management

    MCP-Ready: No FastAPI dependencies
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
            vectorstore: VectorStore for manuals
            llm_client: LLM client for content generation
        """
        self.session = session
        self.manual_repo = ManualEntryRDBRepository(session)
        self.version_repo = ManualVersionRepository(session)
        self.review_repo = ManualReviewTaskRepository(session)
        self.vectorstore = vectorstore
        self.llm_client = llm_client

    async def generate_manual_draft(
        self,
        consultation_id: UUID,
        inquiry_text: str,
        action_taken: str,
        business_type: str | None = None,
        error_code: str | None = None,
    ) -> ManualEntry:
        """
        Generate manual draft from consultation

        RFP Reference: Section 5.1, Steps 4-6
        1. LLM extracts keywords (1-3)
        2. LLM generates topic/background/guideline
        3. Create ManualEntry (DRAFT status)
        4. Return for user review

        Args:
            consultation_id: Source consultation UUID
            inquiry_text: Inquiry text
            action_taken: Action taken
            business_type: Optional business type
            error_code: Optional error code

        Returns:
            ManualEntry in DRAFT status

        Raises:
            LLMError: If LLM call fails
            LLMHallucinationError: If LLM creates new information
        """
        logger.info(
            "generate_manual_draft_start",
            consultation_id=str(consultation_id),
        )

        # TODO: Implement full logic
        # 1. Call LLM to extract keywords (from prompts.py)
        # 2. Call LLM to generate topic/background/guideline
        # 3. Validate LLM output (no hallucination)
        # 4. Create ManualEntry model (status=DRAFT)
        # 5. Save to RDB
        # 6. Return draft

        # Placeholder
        raise NotImplementedError("generate_manual_draft() - TODO")

    async def detect_manual_conflicts(
        self,
        manual_entry_id: UUID,
        similarity_threshold: float = 0.85,
    ) -> list[tuple[ManualEntry, float]]:
        """
        Detect similar existing manuals

        RFP Reference: Section 5.2, Steps 1-2
        1. Search Manual VectorStore for similar entries
        2. If similarity > threshold, potential conflict

        Args:
            manual_entry_id: New manual entry UUID
            similarity_threshold: Minimum similarity to consider conflict

        Returns:
            List of (similar_manual, similarity_score) tuples

        Raises:
            VectorSearchError: If search fails
        """
        logger.info(
            "detect_conflicts_start",
            manual_id=str(manual_entry_id),
            threshold=similarity_threshold,
        )

        # TODO: Implement full logic
        # 1. Get new manual entry from RDB
        # 2. Build search text from keywords/topic/guideline
        # 3. VectorStore search in Manual index
        # 4. Filter by threshold
        # 5. Return similar manuals

        # Placeholder
        raise NotImplementedError("detect_manual_conflicts() - TODO")

    async def create_review_task(
        self,
        old_entry_id: UUID | None,
        new_entry_id: UUID,
        similarity: float,
    ) -> ManualReviewTask:
        """
        Create manual review task

        RFP Reference: Section 5.2, Step 2
        When conflict detected, create review task

        Args:
            old_entry_id: Existing manual (None if new)
            new_entry_id: New manual entry
            similarity: Similarity score

        Returns:
            Created ManualReviewTask
        """
        logger.info(
            "create_review_task",
            old_entry_id=str(old_entry_id) if old_entry_id else "None",
            new_entry_id=str(new_entry_id),
            similarity=similarity,
        )

        # TODO: Implement
        # 1. Create ManualReviewTask model
        # 2. Set status = TODO
        # 3. Save to RDB
        # 4. (Optional) Send notification

        # Placeholder
        raise NotImplementedError("create_review_task() - TODO")

    async def approve_review_task(
        self,
        task_id: UUID,
        reviewer_id: UUID,
        create_new_version: bool = True,
    ) -> ManualEntry:
        """
        Approve manual review task

        RFP Reference: Section 5.2, Step 6
        1. Update task status to DONE
        2. Deprecate old manual (if exists)
        3. Set new manual to APPROVED
        4. Create new ManualVersion (if requested)

        Args:
            task_id: Review task UUID
            reviewer_id: Reviewer UUID
            create_new_version: Whether to create new version

        Returns:
            Approved ManualEntry

        Raises:
            RecordNotFoundError: If task not found
            InvalidStatusTransitionError: If task already processed
        """
        logger.info(
            "approve_review_task",
            task_id=str(task_id),
            reviewer_id=str(reviewer_id),
        )

        # TODO: Implement workflow
        # 1. Get review task
        # 2. Validate status (must be TODO or IN_PROGRESS)
        # 3. Update old entry (deprecated)
        # 4. Update new entry (approved)
        # 5. Update task status (DONE)
        # 6. Create version if requested
        # 7. Index approved manual in VectorStore

        # Placeholder
        raise NotImplementedError("approve_review_task() - TODO")

    async def reject_review_task(
        self,
        task_id: UUID,
        reviewer_id: UUID,
        reason: str,
    ) -> None:
        """
        Reject manual review task

        RFP Reference: Section 5.2, Step 5
        Mark task as REJECTED with reason

        Args:
            task_id: Review task UUID
            reviewer_id: Reviewer UUID
            reason: Rejection reason
        """
        logger.info(
            "reject_review_task",
            task_id=str(task_id),
            reviewer_id=str(reviewer_id),
        )

        # TODO: Implement
        # 1. Get review task
        # 2. Update status to REJECTED
        # 3. Save rejection reason
        # 4. (Optional) Notify submitter

        # Placeholder
        raise NotImplementedError("reject_review_task() - TODO")
