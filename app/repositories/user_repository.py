"""
User repository
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
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
            department=data.department,
            role=data.role,
            password_hash=password_hash,
            is_active=data.is_active,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user
