"""
User service

FastAPI에 의존하지 않는 순수 비즈니스 로직.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    DuplicateRecordError,
    RecordNotFoundError,
    ValidationError,
)
from app.core.jwt import create_access_token
from app.core.security import hash_password, verify_password
from app.repositories.user_repository import UserRepository
from app.services.department_service import DepartmentService
from app.schemas.user import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.schemas.department import UserDepartmentAssignment


class UserService:
    """회원가입 유스케이스를 담당."""

    def __init__(
        self,
        session: AsyncSession,
        repository: UserRepository | None = None,
        department_service: DepartmentService | None = None,
    ):
        self.session = session
        self.repository = repository or UserRepository(session)
        self.department_service = department_service or DepartmentService(session)

    async def signup(self, user_create: UserCreate) -> UserResponse:
        """회원가입 수행."""

        existing = await self.repository.get_by_employee_id(user_create.employee_id)
        if existing is not None:
            raise DuplicateRecordError("Employee ID already exists")

        password_hash = hash_password(user_create.password)
        user = await self.repository.create_user(user_create, password_hash=password_hash)
        if not user_create.department_ids:
            raise ValidationError("적어도 하나의 부서를 지정해야 합니다.")

        assignment = UserDepartmentAssignment(
            department_ids=user_create.department_ids,
            primary_department_id=user_create.primary_department_id,
        )

        await self.department_service.assign_user_departments(user.id, assignment)

        user_with_departments = await self.repository.get_with_departments(user.id)
        if user_with_departments is None:
            raise RecordNotFoundError(f"user_id={user.id}에 해당하는 사용자가 없습니다")

        return UserResponse.model_validate(user_with_departments)

    async def login(self, user_login: UserLogin) -> TokenResponse:
        """로그인 및 액세스 토큰 발급."""

        user = await self.repository.get_by_employee_id(user_login.employee_id)
        if user is None:
            raise AuthenticationError("Invalid credentials")

        if not verify_password(user_login.password, user.password_hash):
            raise AuthenticationError("Invalid credentials")

        payload = {
            "sub": str(user.id),
            "employee_id": user.employee_id,
            "role": user.role.value,
        }
        token = create_access_token(payload)
        return TokenResponse(access_token=token, token_type="bearer")
