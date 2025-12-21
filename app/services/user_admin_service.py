"""
Admin user management service
"""

import re
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateRecordError, RecordNotFoundError, ValidationError
from app.core.security import hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.department import UserDepartmentAssignment
from app.schemas.user import (
    UserAdminCreate,
    UserAdminUpdate,
    UserCreate,
    UserListParams,
    UserResponse,
    UserSearchParams,
)
from app.services.department_service import DepartmentService


class UserAdminService:
    """관리자용 사용자 조회/생성/수정 서비스."""

    _PASSWORD_MIN_LENGTH = 12

    def __init__(
        self,
        session: AsyncSession,
        *,
        user_repo: UserRepository | None = None,
        department_service: DepartmentService | None = None,
    ):
        self.session = session
        self.user_repo = user_repo or UserRepository(session)
        self.department_service = department_service or DepartmentService(session)

    async def list_users(self, params: UserListParams) -> list[UserResponse]:
        users = await self.user_repo.list_users(
            employee_id=params.employee_id,
            name=params.name,
            role=params.role,
            is_active=params.is_active,
            department_code=params.department_code,
        )

        return [UserResponse.model_validate(user) for user in users]

    async def search_users(self, params: UserSearchParams) -> list[UserResponse]:
        users = await self.user_repo.list_users(
            employee_id=params.employee_id,
            name=params.name,
            role=None,
            is_active=params.is_active,
            department_code=params.department_code,
        )
        return [UserResponse.model_validate(user) for user in users]

    async def create_user(self, payload: UserAdminCreate) -> UserResponse:
        await self._enforce_password_policy(payload.password)

        existing_by_employee = await self.user_repo.get_by_employee_id(payload.employee_id)
        if existing_by_employee:
            raise DuplicateRecordError(
                f"employee_id={payload.employee_id}은(는) 이미 등록된 사용자입니다."
            )

        user_create = UserCreate(
            employee_id=payload.employee_id,
            name=payload.name,
            role=payload.role,
            password=payload.password,
            is_active=payload.is_active,
            department_ids=payload.department_ids,
            primary_department_id=payload.primary_department_id,
        )

        hashed_password = hash_password(user_create.password)
        new_user = await self.user_repo.create_user(user_create, password_hash=hashed_password)

        assignment = UserDepartmentAssignment(
            department_ids=payload.department_ids,
            primary_department_id=payload.primary_department_id,
        )
        await self.department_service.assign_user_departments(new_user.id, assignment)

        user_with_departments = await self.user_repo.get_with_departments(new_user.id)
        if user_with_departments is None:
            raise RecordNotFoundError(f"사용자(id={new_user.id})을(를) 찾을 수 없습니다.")

        return UserResponse.model_validate(user_with_departments)

    async def update_user(self, user_id: int, payload: UserAdminUpdate) -> UserResponse:
        user = await self.user_repo.get_with_departments(user_id)
        if user is None:
            raise RecordNotFoundError(f"user_id={user_id}에 해당하는 사용자가 없습니다.")

        if payload.password is not None:
            await self._enforce_password_policy(payload.password)
            user.password_hash = hash_password(payload.password)

        if payload.name is not None:
            user.name = payload.name

        if payload.role is not None:
            user.role = payload.role

        if payload.is_active is not None:
            user.is_active = payload.is_active

        await self.user_repo.update_user(user)

        if payload.department_ids is not None:
            assignment = UserDepartmentAssignment(
                department_ids=payload.department_ids,
                primary_department_id=payload.primary_department_id,
            )
            await self.department_service.assign_user_departments(user.id, assignment)
            user = await self.user_repo.get_with_departments(user.id)
            if user is None:
                raise RecordNotFoundError(f"user_id={user.id}에 해당하는 사용자가 없습니다.")
        else:
            refreshed = await self.user_repo.get_with_departments(user.id)
            if refreshed is None:
                raise RecordNotFoundError(f"user_id={user.id}에 해당하는 사용자가 없습니다.")
            user = refreshed
        return UserResponse.model_validate(user)

    async def delete_user(self, user_id: int) -> None:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise RecordNotFoundError(f"user_id={user_id}에 해당하는 사용자가 없습니다.")

        await self.user_repo.delete_user(user)

    async def _enforce_password_policy(self, password: str) -> None:
        if len(password) < self._PASSWORD_MIN_LENGTH:
            raise ValidationError(
                f"비밀번호는 최소 {self._PASSWORD_MIN_LENGTH}자 이상이어야 합니다."
            )

        if not re.search(r"[A-Z]", password):
            raise ValidationError("비밀번호에는 최소 1개의 영어 대문자가 포함되어야 합니다.")

        if not re.search(r"[a-z]", password):
            raise ValidationError("비밀번호에는 최소 1개의 영어 소문자가 포함되어야 합니다.")

        if not re.search(r"[^A-Za-z0-9]", password):
            raise ValidationError("비밀번호에는 최소 1개의 특수문자가 포함되어야 합니다.")
