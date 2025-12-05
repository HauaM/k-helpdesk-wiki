"""
User service

FastAPI에 의존하지 않는 순수 비즈니스 로직.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, DuplicateRecordError
from app.core.jwt import create_access_token
from app.core.security import hash_password, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)


class UserService:
    """회원가입 유스케이스를 담당."""

    def __init__(self, session: AsyncSession, repository: UserRepository | None = None):
        self.session = session
        self.repository = repository or UserRepository(session)

    async def signup(self, user_create: UserCreate) -> UserResponse:
        """회원가입 수행."""

        existing = await self.repository.get_by_username(user_create.username)
        if existing is not None:
            raise DuplicateRecordError("Username already exists")

        password_hash = hash_password(user_create.password)
        user = await self.repository.create_user(user_create, password_hash=password_hash)
        return UserResponse.model_validate(user)

    async def login(self, user_login: UserLogin) -> TokenResponse:
        """로그인 및 액세스 토큰 발급."""

        user = await self.repository.get_by_username(user_login.username)
        if user is None:
            raise AuthenticationError("Invalid credentials")

        if not verify_password(user_login.password, user.password_hash):
            raise AuthenticationError("Invalid credentials")

        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
        }
        token = create_access_token(payload)
        return TokenResponse(access_token=token, token_type="bearer")
