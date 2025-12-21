"""Department service"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateRecordError, RecordNotFoundError, ValidationError
from app.models.department import Department
from app.repositories.department_repository import DepartmentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.department import (
    DepartmentCreate,
    DepartmentResponse,
    UserDepartmentAssignment,
    UserDepartmentListResponse,
)


class DepartmentService:
    """부서 CRUD 및 사용자-부서 매핑 비즈니스 로직"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.department_repo = DepartmentRepository(session)
        self.user_repo = UserRepository(session)

    async def list_departments(
        self,
        *,
        is_active: bool | None = None,
        department_code: str | None = None,
        department_name: str | None = None,
    ) -> list[DepartmentResponse]:
        departments = await self.department_repo.list_all(
            is_active=is_active,
            department_code=department_code,
            department_name=department_name,
        )
        return [DepartmentResponse.model_validate(dept) for dept in departments]

    async def create_department(
        self,
        payload: DepartmentCreate,
    ) -> DepartmentResponse:
        existing = await self.department_repo.get_by_code(payload.department_code)
        if existing:
            raise DuplicateRecordError(
                f"부서코드 '{payload.department_code}'은(는) 이미 등록된 코드입니다."
            )

        department = await self.department_repo.create_department(
            Department(
                department_code=payload.department_code,
                department_name=payload.department_name,
                is_active=payload.is_active,
            )
        )
        return DepartmentResponse.model_validate(department)

    async def assign_user_departments(
        self,
        user_id: int,
        payload: UserDepartmentAssignment,
    ) -> UserDepartmentListResponse:
        if not payload.department_ids:
            raise ValidationError("최소 하나의 부서를 지정해야 합니다.")

        unique_ids: list[UUID] = []
        seen: set[UUID] = set()
        for department_id in payload.department_ids:
            if department_id not in seen:
                seen.add(department_id)
                unique_ids.append(department_id)

        departments = await self.department_repo.get_by_ids(unique_ids)
        dept_map = {dept.id: dept for dept in departments}
        missing = [str(dept_id) for dept_id in unique_ids if dept_id not in dept_map]
        if missing:
            raise RecordNotFoundError(
                f"다음 부서를 찾을 수 없습니다: {', '.join(missing)}"
            )

        primary_department_id = payload.primary_department_id or unique_ids[0]
        if primary_department_id not in unique_ids:
            raise ValidationError("primary_department_id는 department_ids에 포함되어야 합니다.")

        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise RecordNotFoundError(f"user_id={user_id}에 해당하는 사용자가 없습니다")

        await self.user_repo.replace_user_departments(
            user,
            [dept_map[dept_id] for dept_id in unique_ids],
            primary_department_id=primary_department_id,
        )

        user_with_departments = await self.user_repo.get_with_departments(user_id)
        if user_with_departments is None:
            raise RecordNotFoundError(f"user_id={user_id}에 해당하는 사용자가 없습니다")

        departments_response = [
            DepartmentResponse.model_validate(link.department)
            for link in user_with_departments.department_links
        ]
        primary_link = next(
            (link for link in user_with_departments.department_links if link.is_primary),
            None,
        )

        return UserDepartmentListResponse(
            user_id=user_with_departments.id,
            departments=departments_response,
            primary_department_id=primary_link.department_id if primary_link else None,
        )

    async def get_user_departments(self, user_id: int) -> UserDepartmentListResponse:
        user = await self.user_repo.get_with_departments(user_id)
        if user is None:
            raise RecordNotFoundError(f"user_id={user_id}에 해당하는 사용자가 없습니다")

        departments_response = [
            DepartmentResponse.model_validate(link.department)
            for link in user.department_links
        ]
        primary_link = next((link for link in user.department_links if link.is_primary), None)

        return UserDepartmentListResponse(
            user_id=user.id,
            departments=departments_response,
            primary_department_id=primary_link.department_id if primary_link else None,
        )

    async def delete_department(self, department_id: UUID) -> None:
        department = await self.department_repo.get_by_id(department_id)
        if department is None:
            raise RecordNotFoundError(f"department_id={department_id}에 해당하는 부서가 없습니다")

        await self.department_repo.delete_department(department)
