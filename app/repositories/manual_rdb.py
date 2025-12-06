"""
Manual RDB Repositories
Database operations for Manual models
"""

from uuid import UUID
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manual import ManualEntry, ManualStatus, ManualVersion
from app.models.task import ManualReviewTask, TaskStatus
from app.repositories.base import BaseRepository


class ManualEntryRDBRepository(BaseRepository[ManualEntry]):
    """
    Repository for ManualEntry RDB operations

    RFP Reference: Section 9 - Repository Layer
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ManualEntry, session)

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

    # TODO: Add more query methods
    # async def find_approved_by_keywords(...)
    # async def deprecate_entry(...)


class ManualVersionRepository(BaseRepository[ManualVersion]):
    """
    Repository for ManualVersion operations
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ManualVersion, session)

    async def get_latest_version(self) -> ManualVersion | None:
        """
        Get the latest manual version

        Returns:
            Latest ManualVersion or None
        """
        stmt = select(ManualVersion).order_by(ManualVersion.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_version(self, version: str) -> ManualVersion | None:
        """
        Get ManualVersion by version string
        """
        stmt = select(ManualVersion).where(ManualVersion.version == version)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_versions(self, limit: int | None = None) -> Sequence[ManualVersion]:
        """
        List manual versions ordered by creation time (desc)
        """
        stmt = select(ManualVersion).order_by(ManualVersion.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class ManualReviewTaskRepository(BaseRepository[ManualReviewTask]):
    """
    Repository for ManualReviewTask operations

    RFP Reference: Section 4.4, 5.2
    """

    def __init__(self, session: AsyncSession):
        super().__init__(ManualReviewTask, session)

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
        reviewer_id: UUID,
    ) -> Sequence[ManualReviewTask]:
        """
        Find pending tasks assigned to reviewer

        Args:
            reviewer_id: Reviewer UUID

        Returns:
            List of pending review tasks
        """
        stmt = select(ManualReviewTask).where(
            ManualReviewTask.reviewer_id == reviewer_id,
            ManualReviewTask.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # TODO: Add workflow methods
    # async def approve_task(...)
    # async def reject_task(...)
