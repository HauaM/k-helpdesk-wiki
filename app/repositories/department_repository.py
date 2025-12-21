"""
Department repository
"""

from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department


class DepartmentRepository:
    """부서 관련 CRUD를 담당하는 Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, department_id: UUID) -> Department | None:
        """ID 기반 단건 조회"""

        stmt = select(Department).where(Department.id == department_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, department_code: str) -> Department | None:
        """부서 코드로 조회"""

        stmt = select(Department).where(Department.department_code == department_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ids(self, department_ids: list[UUID]) -> list[Department]:
        """여러 부서를 조회한다"""

        if not department_ids:
            return []

        stmt = select(Department).where(Department.id.in_(department_ids))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_all(
        self,
        *,
        is_active: bool | None = None,
        department_code: str | None = None,
        department_name: str | None = None,
    ) -> Sequence[Department]:
        """모든 부서 목록 조회"""

        stmt = select(Department)
        if is_active is not None:
            stmt = stmt.where(Department.is_active == is_active)
        if department_code:
            stmt = stmt.where(Department.department_code.ilike(f"%{department_code}%"))
        if department_name:
            stmt = stmt.where(Department.department_name.ilike(f"%{department_name}%"))

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_department(self, department: Department) -> Department:
        """부서 생성"""

        self.session.add(department)
        await self.session.flush()
        await self.session.refresh(department)
        return department

    async def delete_department(self, department: Department) -> None:
        """부서 삭제"""

        await self.session.delete(department)
        await self.session.flush()
