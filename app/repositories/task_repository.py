"""
Task Repository Layer

메뉴얼 검토 태스크 관련 기본 INSERT/SELECT/UPDATE 쿼리를 제공합니다.
서비스에서 상태 전이와 트랜잭션을 관리하므로 여기서는 단순 DB 조작만 수행합니다.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import ManualReviewTask, TaskStatus


@dataclass(slots=True)
class TaskFilter:
    """태스크 목록 조회 시 사용할 필터."""

    status: TaskStatus | None = None
    reviewer_id: str | None = None
    new_entry_id: UUID | None = None
    old_entry_id: UUID | None = None
    reviewer_department_ids: list[UUID] | None = None


class TaskRepository:
    """ManualReviewTask 중심의 RDB 접근."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_review_task(
        self,
        new_entry_id: UUID,
        similarity: float,
        old_entry_id: UUID | None = None,
        reviewer_id: str | None = None,
    ) -> ManualReviewTask:
        """유사 메뉴얼 검토 태스크 생성."""

        task = ManualReviewTask(
            old_entry_id=old_entry_id,
            new_entry_id=new_entry_id,
            similarity=similarity,
            status=TaskStatus.TODO,
            reviewer_id=reviewer_id,
        )
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def update_status(
        self,
        task: ManualReviewTask,
        status: TaskStatus,
        review_notes: str | None = None,
        decision_reason: str | None = None,
    ) -> ManualReviewTask:
        """태스크 상태 및 메모 업데이트."""

        task.status = status
        if review_notes is not None:
            task.review_notes = review_notes
        if decision_reason is not None:
            task.decision_reason = decision_reason

        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def list_tasks(
        self,
        filters: TaskFilter,
        *,
        limit: int | None = None,
    ) -> list[ManualReviewTask]:
        """필터 조건에 따른 태스크 목록 조회."""

        conditions = []
        if filters.status:
            conditions.append(ManualReviewTask.status == filters.status)
        if filters.reviewer_id:
            conditions.append(ManualReviewTask.reviewer_id == filters.reviewer_id)
        if filters.new_entry_id:
            conditions.append(ManualReviewTask.new_entry_id == filters.new_entry_id)
        if filters.old_entry_id:
            conditions.append(ManualReviewTask.old_entry_id == filters.old_entry_id)
        if filters.reviewer_department_ids:
            conditions.append(
                ManualReviewTask.reviewer_department_id.in_(filters.reviewer_department_ids)
            )

        stmt = select(ManualReviewTask)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(ManualReviewTask.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
