import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NeedsReReviewError
from app.models.manual import ManualEntry, ManualStatus
from app.models.task import ManualReviewTask, TaskStatus, ComparisonType
from app.repositories.manual_rdb import (
    ManualEntryRDBRepository,
    ManualReviewTaskRepository,
    ManualVersionRepository,
)
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.common_code_rdb import CommonCodeItemRepository
from app.schemas.manual import ManualApproveRequest
from app.services.manual_service import ManualService
from app.services.comparison_service import ComparisonService
from app.llm.protocol import LLMClientProtocol


class DummyLLM:
    async def complete_json(self, *args, **kwargs):
        return {}

    async def complete(self, *args, **kwargs):
        return {"content": ""}


@pytest.mark.asyncio
async def test_approve_guard_requires_rereview_when_candidate_changes():
    manual = ManualEntry(
        id=uuid4(),
        keywords=["test"],
        topic="Draft topic",
        background="Background",
        guideline="Guide",
        business_type="결제",
        error_code="E001",
        source_consultation_id=uuid4(),
        status=ManualStatus.DRAFT,
    )

    old_manual = ManualEntry(
        id=uuid4(),
        keywords=["test"],
        topic="Existing",
        background="Legacy",
        guideline="Old guide",
        business_type="결제",
        error_code="E001",
        source_consultation_id=uuid4(),
        status=ManualStatus.APPROVED,
    )

    review_task = ManualReviewTask(
        old_entry_id=old_manual.id,
        new_entry_id=manual.id,
        similarity=0.92,
        comparison_type=ComparisonType.SUPPLEMENT,
        status=TaskStatus.TODO,
    )
    review_task.id = uuid4()

    manual_repo = AsyncMock(spec=ManualEntryRDBRepository)
    review_repo = AsyncMock(spec=ManualReviewTaskRepository)
    version_repo = AsyncMock(spec=ManualVersionRepository)
    consultation_repo = AsyncMock(spec=ConsultationRepository)
    common_code_repo = AsyncMock(spec=CommonCodeItemRepository)

    manual_repo.get_by_id.return_value = manual
    review_repo.get_latest_by_manual_id.return_value = review_task
    version_repo.get_latest_version.return_value = None
    version_repo.create = AsyncMock()
    manual_repo.update = AsyncMock()
    review_repo.update = AsyncMock()

    comparison_service = AsyncMock(spec=ComparisonService)
    comparison_service.find_best_match_candidate.return_value = ManualEntry(
        id=uuid4(),
        keywords=["test"],
        topic="Different best match",
        background="Background",
        guideline="Guide",
        business_type="결제",
        error_code="E001",
        source_consultation_id=uuid4(),
        status=ManualStatus.APPROVED,
    )

    service = ManualService(
        session=AsyncMock(spec=AsyncSession),
        llm_client=DummyLLM(),
        vectorstore=None,
        manual_repo=manual_repo,
        review_repo=review_repo,
        version_repo=version_repo,
        consultation_repo=consultation_repo,
        common_code_item_repo=common_code_repo,
        comparison_service=comparison_service,
    )

    with pytest.raises(NeedsReReviewError):
        await service.approve_manual(manual.id, ManualApproveRequest(approver_id="rev1"))
