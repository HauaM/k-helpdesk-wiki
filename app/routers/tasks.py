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
    return TaskService(session=session, manual_service=manual_service)


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
