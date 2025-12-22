"""
User repository
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.department import Department, UserDepartment
from app.models.user import User, UserRole
from app.schemas.user import UserCreate


class UserRepository:
    """사용자 계정 관련 DB 접근 로직을 담당."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """PK로 사용자 조회."""

        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_departments(self, user_id: int) -> User | None:
        """부서 정보를 함께 로딩한 사용자 조회."""

        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.department_links).selectinload(UserDepartment.department),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_departments_by_employee_id(self, employee_id: str) -> User | None:
        """employee_id로 해당 사용자의 부서 정보를 함께 로딩하여 조회."""

        stmt = (
            select(User)
            .where(User.employee_id == employee_id)
            .options(
                selectinload(User.department_links).selectinload(UserDepartment.department),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_employee_id(self, employee_id: str) -> User | None:
        """employee_id로 사용자 단건 조회."""

        stmt = select(User).where(User.employee_id == employee_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(self, data: UserCreate, *, password_hash: str) -> User:
        """회원가입 데이터를 받아 신규 사용자 생성."""

        user = User(
            employee_id=data.employee_id,
            name=data.name,
            role=data.role,
            password_hash=password_hash,
            is_active=data.is_active,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def update_user(self, user: User) -> User:
        """사용자 업데이트 처리."""

        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def delete_user(self, user: User) -> None:
        """사용자 삭제 처리."""

        await self.session.delete(user)
        await self.session.flush()

    async def list_users(
        self,
        *,
        employee_id: str | None = None,
        name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        department_code: str | None = None,
    ) -> list[User]:
        """사용자 조회(필터)."""

        base_stmt = (
            select(User)
            .options(
                selectinload(User.department_links).selectinload(UserDepartment.department)
            )
            .execution_options(populate_existing=True)
        )
        filters = []
        if employee_id:
            filters.append(User.employee_id == employee_id)
        if name:
            filters.append(User.name.ilike(f"%{name}%"))
        if role:
            filters.append(User.role == role)
        if is_active is not None:
            filters.append(User.is_active == is_active)

        if department_code:
            base_stmt = (
                base_stmt.join(User.department_links)
                .join(UserDepartment.department)
                .where(Department.department_code == department_code)
            )

        if filters:
            base_stmt = base_stmt.where(*filters)
        base_stmt = base_stmt.distinct()

        result = await self.session.execute(base_stmt)
        users = result.scalars().all()

        return users

    async def replace_user_departments(
        self,
        user: User,
        departments: list[Department],
        *,
        primary_department_id: UUID,
    ) -> list[UserDepartment]:
        """사용자에 연결된 부서 매핑을 교체한다."""

        await self.session.execute(
            delete(UserDepartment).where(UserDepartment.user_id == user.id)
        )

        links: list[UserDepartment] = []
        for department in departments:
            link = UserDepartment(
                user_id=user.id,
                department_id=department.id,
                is_primary=department.id == primary_department_id,
            )
            self.session.add(link)
            links.append(link)

        await self.session.flush()
        return links
