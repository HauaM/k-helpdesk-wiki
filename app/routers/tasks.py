"""
Manual Review Task API Routes

RFP Reference: Section 10 - API Design
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.manual import (
    ManualReviewTaskResponse,
    ManualReviewApproval,
    ManualReviewRejection,
)
from app.services.manual_service import ManualService
from app.services.task_service import TaskService
from app.repositories.common_code_rdb import CommonCodeItemRepository
from app.vectorstore.factory import get_manual_vectorstore
from app.llm.factory import get_llm_client_instance

router = APIRouter(prefix="/manual-review", tags=["tasks"])


def get_task_service(
    session: AsyncSession = Depends(get_session),
) -> TaskService:
    manual_service = ManualService(
        session=session,
        vectorstore=get_manual_vectorstore(),
        llm_client=get_llm_client_instance(),
    )
    common_code_item_repo = CommonCodeItemRepository(session)
    return TaskService(
        session=session,
        manual_service=manual_service,
        common_code_item_repo=common_code_item_repo,
    )


@router.get(
    "/tasks",
    response_model=list[ManualReviewTaskResponse],
    summary="List manual review tasks",
)
async def list_review_tasks(
    status: str | None = None,
    limit: int = 100,
    service: TaskService = Depends(get_task_service),
) -> list[ManualReviewTaskResponse]:
    """
    List manual review tasks with optional status filter

    RFP Reference: GET /tasks/manual-review
    - Returns pending/in-progress/done/rejected tasks
    - For reviewers to see what needs attention

    TODO: Implement filtering and pagination
    """
    return await service.list_review_tasks(status=status, limit=limit)


@router.post(
    "/tasks/{task_id}/approve",
    response_model=ManualReviewTaskResponse,
    summary="Approve manual review task",
)
async def approve_review_task(
    task_id: UUID,
    data: ManualReviewApproval,
    service: TaskService = Depends(get_task_service),
) -> ManualReviewTaskResponse:
    """
    Approve manual review task

    RFP Reference: POST /tasks/manual-review/{id}/approve
    - Updates task status to DONE
    - Approves new manual entry
    - Deprecates old manual (if exists)
    - Creates new ManualVersion (if requested)

    TODO: Implement approval workflow
    """
    return await service.approve_task(task_id, data)


@router.post(
    "/tasks/{task_id}/reject",
    response_model=ManualReviewTaskResponse,
    summary="Reject manual review task",
)
async def reject_review_task(
    task_id: UUID,
    data: ManualReviewRejection,
    service: TaskService = Depends(get_task_service),
) -> ManualReviewTaskResponse:
    """
    Reject manual review task

    RFP Reference: POST /tasks/manual-review/{id}/reject
    - Updates task status to REJECTED
    - Saves rejection reason
    - Notifies submitter (optional)

    TODO: Implement rejection workflow
    """
    return await service.reject_task(task_id, data)


@router.put(
    "/tasks/{task_id}",
    response_model=ManualReviewTaskResponse,
    summary="Start manual review task",
)
async def start_review_task(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> ManualReviewTaskResponse:
    """FR-6: 검토 태스크 시작 (TODO → IN_PROGRESS)

    검토자가 검토를 시작할 때 태스크 상태를 IN_PROGRESS로 변경합니다.
    이를 통해 미완성 초안이 노출되는 것을 방지합니다.

    요청:
    - PUT /api/v1/manual-review/tasks/{task_id}

    응답 (200 OK):
    - 업데이트된 ManualReviewTask (status=IN_PROGRESS)

    제약사항:
    - TODO 상태인 태스크만 IN_PROGRESS로 변경 가능
    """
    return await service.start_task(task_id)
