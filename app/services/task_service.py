"""
Task Service (FR-7/FR-10)

ManualReviewTask 승인/반려 및 히스토리 기록을 담당한다.
"""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.core.logging import get_logger
from app.models.manual import ManualEntry, ManualStatus
from app.models.task import ManualReviewTask, TaskHistory, TaskStatus
from app.repositories.manual_rdb import ManualEntryRDBRepository, ManualReviewTaskRepository
from app.repositories.common_code_rdb import CommonCodeItemRepository
from app.schemas.manual import (
    ManualApproveRequest,
    ManualReviewApproval,
    ManualReviewRejection,
    ManualReviewTaskResponse,
)
from app.services.manual_service import ManualService
from app.core.logging import metrics_counter

logger = get_logger(__name__)


class TaskService:
    """ManualReviewTask 워크플로우를 담당하는 서비스."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        manual_service: ManualService,
        task_repo: ManualReviewTaskRepository | None = None,
        manual_repo: ManualEntryRDBRepository | None = None,
        common_code_item_repo: CommonCodeItemRepository | None = None,
    ) -> None:
        self.session = session
        self.manual_service = manual_service
        self.task_repo = task_repo or ManualReviewTaskRepository(session)
        self.manual_repo = manual_repo or ManualEntryRDBRepository(session)
        self.common_code_item_repo = common_code_item_repo or CommonCodeItemRepository(session)

    async def list_review_tasks(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ManualReviewTaskResponse]:
        tasks: Sequence[ManualReviewTask]
        if status:
            try:
                status_enum = TaskStatus(status)
            except ValueError:
                status_enum = None
            tasks = await self.task_repo.find_by_status(status_enum, limit=limit) if status_enum else []
        else:
            stmt = select(ManualReviewTask).order_by(ManualReviewTask.created_at.desc()).limit(limit)
            result = await self.session.execute(stmt)
            tasks = result.scalars().all()

        return [await self._to_response(task) for task in tasks]

    async def approve_task(
        self,
        task_id: UUID,
        payload: ManualReviewApproval,
    ) -> ManualReviewTaskResponse:
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise RecordNotFoundError(f"ManualReviewTask(id={task_id}) not found")

        await self._add_history(
            task,
            TaskStatus.DONE,
            changed_by=payload.employee_id,
            reason=payload.review_notes,
        )

        task.status = TaskStatus.DONE
        task.reviewer_id = payload.employee_id
        task.review_notes = payload.review_notes
        await self.task_repo.update(task)

        # 승인 시 신규 메뉴얼도 승인 처리하여 버전 세트에 반영
        await self.manual_service.approve_manual(
            manual_id=task.new_entry_id,
            request=ManualApproveRequest(approver_id=payload.employee_id, notes=payload.review_notes),
        )

        return await self._to_response(task)

    async def reject_task(
        self,
        task_id: UUID,
        payload: ManualReviewRejection,
    ) -> ManualReviewTaskResponse:
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise RecordNotFoundError(f"ManualReviewTask(id={task_id}) not found")

        await self._add_history(task, TaskStatus.REJECTED, reason=payload.review_notes)

        task.status = TaskStatus.REJECTED
        task.review_notes = payload.review_notes
        await self.task_repo.update(task)

        # 반려 시 신규 초안을 DRAFT로 유지, 추가 작업 없음
        return await self._to_response(task)

    async def start_task(
        self,
        task_id: UUID,
    ) -> ManualReviewTaskResponse:
        """검토 태스크 시작 (TODO → IN_PROGRESS)

        검토자가 태스크 검토를 시작할 때 상태를 IN_PROGRESS로 변경합니다.
        이를 통해 미완성 초안 노출을 방지합니다.

        Args:
            task_id: 검토 태스크 ID

        Returns:
            업데이트된 ManualReviewTaskResponse

        Raises:
            RecordNotFoundError: 태스크를 찾을 수 없을 때
        """
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise RecordNotFoundError(f"ManualReviewTask(id={task_id}) not found")

        await self._add_history(task, TaskStatus.IN_PROGRESS)

        task.status = TaskStatus.IN_PROGRESS
        await self.task_repo.update(task)

        return await self._to_response(task)

    async def _add_history(
        self,
        task: ManualReviewTask,
        to_status: TaskStatus,
        *,
        changed_by: str | None = None,
        reason: str | None = None,
    ) -> TaskHistory:
        history = TaskHistory(
            task_id=task.id,
            from_status=task.status,
            to_status=to_status,
            changed_by=changed_by,
            reason=reason,
        )
        self.session.add(history)
        await self.session.flush()
        logger.info(
            "task_status_change",
            task_id=str(task.id),
            from_status=task.status.value if task.status else None,
            to_status=to_status.value,
            changed_by=str(changed_by) if changed_by else None,
        )
        metrics_counter("task_status_change", to_status=to_status.value)
        return history

    async def _to_response(self, task: ManualReviewTask) -> ManualReviewTaskResponse:
        old_manual = await self.manual_repo.get_by_id(task.old_entry_id) if task.old_entry_id else None
        new_manual = await self.manual_repo.get_by_id(task.new_entry_id)

        # 신규 메뉴얼 business_type 정보 조회
        new_business_type_name = await self._get_business_type_name(new_manual)
        # 기존 메뉴얼 business_type 정보 조회
        old_business_type_name = await self._get_business_type_name(old_manual)

        return ManualReviewTaskResponse(
            id=task.id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            old_entry_id=task.old_entry_id,
            new_entry_id=task.new_entry_id,
            similarity=task.similarity,
            status=task.status,
            reviewer_id=task.reviewer_id,
            review_notes=task.review_notes,
            old_manual_summary=self._summarize_manual(old_manual),
            new_manual_summary=self._summarize_manual(new_manual),
            diff_text=None,
            diff_json=None,
            # 신규 메뉴얼 정보
            business_type=new_manual.business_type if new_manual else None,
            business_type_name=new_business_type_name,
            new_error_code=new_manual.error_code if new_manual else None,
            new_manual_topic=new_manual.topic if new_manual else None,
            new_manual_keywords=new_manual.keywords if new_manual else None,
            # 기존 메뉴얼 정보 (old_entry_id가 있을 때만)
            old_business_type=old_manual.business_type if old_manual else None,
            old_business_type_name=old_business_type_name,
            old_error_code=old_manual.error_code if old_manual else None,
            old_manual_topic=old_manual.topic if old_manual else None,
        )

    def _summarize_manual(self, manual: ManualEntry | None) -> str | None:
        if manual is None:
            return None
        return f"{manual.topic} | {manual.background[:80]}" if manual.background else manual.topic

    async def _get_business_type_name(self, manual: ManualEntry | None) -> str | None:
        """
        공통코드에서 business_type의 이름(code_value)을 조회

        Args:
            manual: ManualEntry 또는 None

        Returns:
            업무구분 이름 (예: "인터넷뱅킹") 또는 None
        """
        if manual is None or manual.business_type is None:
            return None

        try:
            # BUSINESS_TYPE 그룹의 항목들 조회
            items = await self.common_code_item_repo.get_by_group_code(
                "BUSINESS_TYPE", is_active_only=True
            )

            # business_type 코드와 일치하는 항목 찾기
            for item in items:
                if item.code_key == manual.business_type:
                    return item.code_value

            # 일치하는 항목이 없으면 None 반환
            logger.warning(
                "business_type_not_found_in_common_code",
                manual_id=str(manual.id),
                business_type=manual.business_type,
            )
            return None
        except Exception as e:
            logger.warning(
                "error_getting_business_type_name",
                manual_id=str(manual.id),
                business_type=manual.business_type,
                error=str(e),
            )
            return None
