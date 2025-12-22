"""
Manual RDB Repositories
Database operations for Manual models
"""

from uuid import UUID
from typing import Any, Literal, Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manual import ManualEntry, ManualStatus, ManualVersion
from app.models.consultation import Consultation
from app.models.task import ManualReviewTask, TaskStatus
from app.repositories.task_repository import TaskFilter
from app.repositories.base import BaseRepository


class ManualEntryRDBRepository(BaseRepository[ManualEntry]):
    """
    Repository for ManualEntry RDB operations

    RFP Reference: Section 9 - Repository Layer
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ManualEntry, session)

    async def get_by_id_with_consultation(self, id: UUID) -> ManualEntry | None:
        """
        Get manual entry by ID with source consultation eagerly loaded.

        Args:
            id: ManualEntry UUID

        Returns:
            ManualEntry instance or None if not found
        """
        stmt = (
            select(ManualEntry)
            .where(ManualEntry.id == id)
            .options(selectinload(ManualEntry.source_consultation))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_status(
        self,
        status: ManualStatus,
        limit: int = 100,
    ) -> Sequence[ManualEntry]:
        """
        Find manual entries by status

        Args:
            status: Manual status to filter by
            limit: Maximum number of results

        Returns:
            List of manual entries
        """
        stmt = select(ManualEntry).where(ManualEntry.status == status).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_ids(self, ids: list[UUID]) -> Sequence[ManualEntry]:
        """
        Find manual entries by list of IDs

        Used after VectorStore search

        Args:
            ids: List of manual entry UUIDs

        Returns:
            List of manual entries
        """
        if not ids:
            return []

        stmt = select(ManualEntry).where(ManualEntry.id.in_(ids))
        result = await self.session.execute(stmt)
        manuals = result.scalars().all()

        # Preserve order
        id_to_manual = {m.id: m for m in manuals}
        return [id_to_manual[id] for id in ids if id in id_to_manual]

    async def list_entries(
        self,
        *,
        statuses: set[ManualStatus] | None = None,
        limit: int = 100,
        employee_id: str | None = None,
    ) -> Sequence[ManualEntry]:
        """
        List manual entries with optional status filter.

        Args:
            statuses: Optional set of statuses to filter
            limit: Maximum number of results

        Returns:
            Ordered list of manual entries
        """
        stmt = select(ManualEntry)
        if employee_id:
            stmt = (
                stmt.join(ManualEntry.source_consultation)
                .where(Consultation.employee_id == employee_id)
            )
        if statuses:
            stmt = stmt.where(ManualEntry.status.in_(list(statuses)))
        stmt = stmt.order_by(ManualEntry.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_consultation_id(
        self,
        consultation_id: UUID,
    ) -> Sequence[ManualEntry]:
        """
        Find manual entries created from specific consultation

        Args:
            consultation_id: Source consultation UUID

        Returns:
            List of manual entries
        """
        stmt = select(ManualEntry).where(
            ManualEntry.source_consultation_id == consultation_id
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_version(
        self,
        version_id: UUID,
        *,
        statuses: set[ManualStatus] | None = None,
    ) -> Sequence[ManualEntry]:
        """
        Find manual entries that belong to a specific version.

        Args:
            version_id: ManualVersion UUID
            statuses: Optional status filter set

        Returns:
            List of manual entries for the version
        """
        stmt = select(ManualEntry).where(ManualEntry.version_id == version_id)
        if statuses:
            stmt = stmt.where(ManualEntry.status.in_(list(statuses)))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_business_and_error(
        self,
        business_type: str | None,
        error_code: str | None,
        *,
        statuses: set[ManualStatus] | None = None,
    ) -> Sequence[ManualEntry]:
        """
        Find manual entries by business_type and error_code (manual group).

        Used to find all entries that belong to the same "group" for version comparison.

        Args:
            business_type: Business type (e.g., "인터넷뱅킹")
            error_code: Error code (e.g., "E001")
            statuses: Optional status filter set (e.g., {ManualStatus.APPROVED})

        Returns:
            List of manual entries in the same group
        """
        stmt = select(ManualEntry).where(
            ManualEntry.business_type == business_type,
            ManualEntry.error_code == error_code,
        )
        if statuses:
            stmt = stmt.where(ManualEntry.status.in_(list(statuses)))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_group(
        self,
        business_type: str,
        error_code: str,
        statuses: set[ManualStatus] | None = None,
    ) -> Sequence[ManualEntry]:
        """
        Find all manual entries for a specific group (FR-11 v2.1).

        Used to list all versions of a manual group for user selection.

        Args:
            business_type: Business type (e.g., "인터넷뱅킹")
            error_code: Error code (e.g., "E001")
            statuses: Optional status filter (None = all statuses)

        Returns:
            Manual entries in the group, ordered by created_at DESC (newest first)
        """
        stmt = select(ManualEntry).where(
            ManualEntry.business_type == business_type,
            ManualEntry.error_code == error_code,
        )

        if statuses:
            stmt = stmt.where(ManualEntry.status.in_(list(statuses)))

        stmt = stmt.order_by(ManualEntry.created_at.desc())

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_all_approved_by_group(
        self,
        business_type: str | None,
        error_code: str | None,
    ) -> list[ManualEntry]:
        """
        Get all APPROVED manuals in the same group.
        """
        if business_type is None or error_code is None:
            return []

        stmt = (
            select(ManualEntry)
            .where(
                ManualEntry.business_type == business_type,
                ManualEntry.error_code == error_code,
                ManualEntry.status == ManualStatus.APPROVED,
            )
            .order_by(ManualEntry.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_replacement_chain(
        self,
        manual_id: UUID,
        direction: Literal["forward", "backward"] = "forward",
    ) -> list[ManualEntry]:
        """
        Retrieve replacement chain (past or future) for a manual.
        """
        chain: list[ManualEntry] = []
        current = await self.get_by_id(manual_id)

        for _ in range(100):
            if current is None:
                break

            next_id = (
                current.replaced_manual_id
                if direction == "forward"
                else current.replaced_by_manual_id
            )
            if next_id is None:
                break

            next_entry = await self.get_by_id(next_id)
            if next_entry is None:
                break

            chain.append(next_entry)
            current = next_entry

        return chain

    async def find_latest_by_group(
        self,
        business_type: str,
        error_code: str,
        status: ManualStatus | None = None,
        exclude_id: UUID | None = None,
    ) -> ManualEntry | None:
        """
        Find the latest manual entry for a specific group (FR-11 v2.1).

        Used by ComparisonService to find the latest version to compare against.

        Args:
            business_type: Business type (e.g., "인터넷뱅킹")
            error_code: Error code (e.g., "E001")
            status: Optional status filter (e.g., ManualStatus.APPROVED)
            exclude_id: Optional ID to exclude (e.g., new draft)

        Returns:
            Latest manual entry or None if not found
        """
        stmt = select(ManualEntry).where(
            ManualEntry.business_type == business_type,
            ManualEntry.error_code == error_code,
        )

        if status is not None:
            stmt = stmt.where(ManualEntry.status == status)

        if exclude_id is not None:
            stmt = stmt.where(ManualEntry.id != exclude_id)

        stmt = stmt.order_by(ManualEntry.created_at.desc()).limit(1)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # TODO: Add more query methods
    # async def find_approved_by_keywords(...)
    # async def deprecate_entry(...)


class ManualVersionRepository(BaseRepository[ManualVersion]):
    """
    Repository for ManualVersion operations
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ManualVersion, session)

    async def get_latest_version(
        self,
        business_type: str | None = None,
        error_code: str | None = None,
    ) -> ManualVersion | None:
        """
        Get the latest manual version (optionally filtered by group).

        Args:
            business_type: Optional business_type filter
            error_code: Optional error_code filter

        Returns:
            Latest ManualVersion or None
        """
        stmt = select(ManualVersion)
        if business_type is not None:
            stmt = stmt.where(ManualVersion.business_type == business_type)
        if error_code is not None:
            stmt = stmt.where(ManualVersion.error_code == error_code)
        stmt = stmt.order_by(ManualVersion.created_at.desc(), ManualVersion.id.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_version(
        self,
        version: str,
        business_type: str | None = None,
        error_code: str | None = None,
    ) -> ManualVersion | None:
        """
        Get ManualVersion by version string (with optional group filter).
        """
        stmt = select(ManualVersion).where(ManualVersion.version == version)
        if business_type is not None:
            stmt = stmt.where(ManualVersion.business_type == business_type)
        if error_code is not None:
            stmt = stmt.where(ManualVersion.error_code == error_code)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_versions(
        self,
        business_type: str | None = None,
        error_code: str | None = None,
        limit: int = 100,
    ) -> Sequence[ManualVersion]:
        """
        List manual versions ordered by creation time (desc) with optional group filter.
        """
        stmt = select(ManualVersion)
        if business_type is not None:
            stmt = stmt.where(ManualVersion.business_type == business_type)
        if error_code is not None:
            stmt = stmt.where(ManualVersion.error_code == error_code)
        stmt = stmt.order_by(ManualVersion.created_at.desc(), ManualVersion.id.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class ManualReviewTaskRepository(BaseRepository[ManualReviewTask]):
    """
    Repository for ManualReviewTask operations

    RFP Reference: Section 4.4, 5.2
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ManualReviewTask, session)

    def _with_manual_entries(self, stmt):
        return stmt.options(
            selectinload(ManualReviewTask.old_entry),
            selectinload(ManualReviewTask.new_entry),
        )

    async def find_by_status(
        self,
        status: TaskStatus,
        limit: int = 100,
    ) -> Sequence[ManualReviewTask]:
        """
        Find review tasks by status

        Args:
            status: Review task status
            limit: Maximum number of results

        Returns:
            List of review tasks
        """
        stmt = (
            select(ManualReviewTask)
            .where(ManualReviewTask.status == status)
            .order_by(ManualReviewTask.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_pending_for_reviewer(
        self,
        reviewer_id: str,
    ) -> Sequence[ManualReviewTask]:
        """
        Find pending tasks assigned to reviewer

        Args:
            reviewer_id: Reviewer employee_id

        Returns:
            List of pending review tasks
        """
        stmt = select(ManualReviewTask).where(
            ManualReviewTask.reviewer_id == reviewer_id,
            ManualReviewTask.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_tasks(
        self,
        filters: TaskFilter,
        *,
        limit: int | None = None,
    ) -> list[ManualReviewTask]:
        conditions: list[Any] = []
        if filters.status:
            conditions.append(ManualReviewTask.status == filters.status)
        if filters.reviewer_id:
            conditions.append(ManualReviewTask.reviewer_id == filters.reviewer_id)
        if filters.new_entry_id:
            conditions.append(ManualReviewTask.new_entry_id == filters.new_entry_id)
        if filters.old_entry_id:
            conditions.append(ManualReviewTask.old_entry_id == filters.old_entry_id)
        # if filters.reviewer_department_ids:
        #     conditions.append(
        #         ManualReviewTask.reviewer_department_id.in_(filters.reviewer_department_ids)
        #     )

        stmt = select(ManualReviewTask)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(ManualReviewTask.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_tasks_with_entries(
        self,
        filters: TaskFilter,
        *,
        limit: int | None = None,
    ) -> list[ManualReviewTask]:
        """
        List review tasks with related manual entries eagerly loaded.
        """
        conditions: list[Any] = []
        if filters.status:
            conditions.append(ManualReviewTask.status == filters.status)
        if filters.reviewer_id:
            conditions.append(ManualReviewTask.reviewer_id == filters.reviewer_id)
        if filters.new_entry_id:
            conditions.append(ManualReviewTask.new_entry_id == filters.new_entry_id)
        if filters.old_entry_id:
            conditions.append(ManualReviewTask.old_entry_id == filters.old_entry_id)

        stmt = select(ManualReviewTask)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(ManualReviewTask.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)

        stmt = self._with_manual_entries(stmt)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_manual_id(
        self,
        manual_id: UUID,
        *,
        reviewer_department_ids: list[UUID] | None = None,
    ) -> Sequence[ManualReviewTask]:
        """
        Find review tasks by new_entry_id (manual_id)

        Args:
            manual_id: Manual entry UUID (matches new_entry_id)

        Returns:
            List of review tasks for the manual
        """
        stmt = select(ManualReviewTask).where(
            ManualReviewTask.new_entry_id == manual_id,
        )
        if reviewer_department_ids:
            stmt = stmt.where(
                ManualReviewTask.reviewer_department_id.in_(reviewer_department_ids)
            )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_manual_id_with_entries(
        self,
        manual_id: UUID,
        *,
        reviewer_department_ids: list[UUID] | None = None,
    ) -> Sequence[ManualReviewTask]:
        """
        Find review tasks by new_entry_id with related manual entries eagerly loaded.
        """
        stmt = select(ManualReviewTask).where(
            ManualReviewTask.new_entry_id == manual_id,
        )
        if reviewer_department_ids:
            stmt = stmt.where(
                ManualReviewTask.reviewer_department_id.in_(reviewer_department_ids)
            )

        stmt = self._with_manual_entries(stmt)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_by_manual_id(
        self,
        manual_id: UUID,
    ) -> ManualReviewTask | None:
        """
        Get latest review task for the manual entry (new_entry_id).
        """
        stmt = (
            select(ManualReviewTask)
            .where(ManualReviewTask.new_entry_id == manual_id)
            .order_by(ManualReviewTask.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    # TODO: Add workflow methods
    # async def approve_task(...)
    # async def reject_task(...)
