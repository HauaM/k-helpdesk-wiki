"""
User repository
"""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.department import Department, UserDepartment
from app.models.user import User, UserRole
from app.schemas.user import UserCreate


SORTABLE_COLUMNS = {
    "username": User.username,
    "employee_id": User.employee_id,
    "name": User.name,
    "created_at": User.created_at,
}


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
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_employee_id(self, employee_id: str) -> User | None:
        """employee_id로 사용자 단건 조회."""

        stmt = select(User).where(User.employee_id == employee_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """username으로 사용자 단건 조회."""

        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(self, data: UserCreate, *, password_hash: str) -> User:
        """회원가입 데이터를 받아 신규 사용자 생성."""

        user = User(
            username=data.username,
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

    async def list_users(
        self,
        *,
        employee_id: str | None = None,
        name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        department_code: str | None = None,
        sort_column: str,
        sort_order: str,
        limit: int,
        offset: int,
    ) -> tuple[list[User], int]:
        """사용자 조회(필터 + 페이징 + 정렬)."""

        base_stmt = select(User).options(
            selectinload(User.department_links).selectinload(UserDepartment.department)
        )
        count_stmt = select(func.count(func.distinct(User.id)))

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
            count_stmt = (
                count_stmt.select_from(User)
                .join(User.department_links)
                .join(UserDepartment.department)
                .where(Department.department_code == department_code)
            )
        else:
            count_stmt = count_stmt.select_from(User)

        if filters:
            base_stmt = base_stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        base_stmt = base_stmt.distinct()
        sort_column_obj = SORTABLE_COLUMNS.get(sort_column, User.created_at)
        ordering = (
            sort_column_obj.asc() if sort_order == "asc" else sort_column_obj.desc()
        )
        base_stmt = base_stmt.order_by(ordering).offset(offset).limit(limit)

        result = await self.session.execute(base_stmt)
        users = result.scalars().all()

        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        return users, total

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
