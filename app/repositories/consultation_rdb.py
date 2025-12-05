"""
Consultation RDB Repository
Database operations for Consultation model
"""

from uuid import UUID
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation import Consultation
from app.repositories.base import BaseRepository


class ConsultationRDBRepository(BaseRepository[Consultation]):
    """
    Repository for Consultation RDB operations

    RFP Reference: Section 9 - Repository Layer
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Consultation, session)

    async def find_by_branch_code(
        self,
        branch_code: str,
        limit: int = 100,
    ) -> Sequence[Consultation]:
        """
        Find consultations by branch code

        Args:
            branch_code: Branch code to filter by
            limit: Maximum number of results

        Returns:
            List of consultations
        """
        stmt = (
            select(Consultation)
            .where(Consultation.branch_code == branch_code)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_error_code(
        self,
        error_code: str,
        limit: int = 100,
    ) -> Sequence[Consultation]:
        """
        Find consultations by error code

        Args:
            error_code: Error code to filter by
            limit: Maximum number of results

        Returns:
            List of consultations
        """
        stmt = (
            select(Consultation)
            .where(Consultation.error_code == error_code)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def find_by_ids(self, ids: list[UUID]) -> Sequence[Consultation]:
        """
        Find consultations by list of IDs

        Used after VectorStore returns Top-K IDs

        Args:
            ids: List of consultation UUIDs

        Returns:
            List of consultations (order preserved if possible)
        """
        if not ids:
            return []

        stmt = select(Consultation).where(Consultation.id.in_(ids))
        result = await self.session.execute(stmt)
        consultations = result.scalars().all()

        # Preserve order from input IDs
        id_to_consultation = {c.id: c for c in consultations}
        return [id_to_consultation[id] for id in ids if id in id_to_consultation]

    # TODO: Add more domain-specific query methods
    # async def find_by_business_type_and_error(...)
    # async def find_recent_by_employee(...)
