"""
System bootstrap service for initial admin setup.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.department import Department
from app.models.user import UserRole
from app.repositories.department_repository import DepartmentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.department import UserDepartmentAssignment
from app.schemas.user import UserCreate
from app.services.department_service import DepartmentService


logger = get_logger(__name__)


class SystemBootstrapService:
    """시스템 시작 시 관리자/부서 초기화를 담당."""

    SYSTEM_DEPARTMENT_CODE = "SYSTEM_HQ"
    SYSTEM_DEPARTMENT_NAME = "시스템관리"
    DEFAULT_ADMIN_NAME = "시스템 관리자"

    def __init__(
        self,
        session: AsyncSession,
        *,
        user_repo: UserRepository | None = None,
        department_repo: DepartmentRepository | None = None,
        department_service: DepartmentService | None = None,
    ) -> None:
        self.session = session
        self.user_repo = user_repo or UserRepository(session)
        self.department_repo = department_repo or DepartmentRepository(session)
        self.department_service = department_service or DepartmentService(session)

    async def ensure_system_admin(self, admin_id: str, admin_password: str) -> None:
        logger.info("system_admin_bootstrap_start", employee_id=admin_id)

        department = await self._ensure_system_department()
        user = await self.user_repo.get_with_departments_by_employee_id(admin_id)

        if user is None:
            logger.info("system_admin_user_missing", employee_id=admin_id)
            await self._create_admin_user(admin_id, admin_password, department.id)
            logger.info("system_admin_user_created", employee_id=admin_id)
            return

        logger.info("system_admin_user_exists", employee_id=admin_id, user_id=user.id)

        updated_fields: list[str] = []
        if user.role != UserRole.ADMIN:
            user.role = UserRole.ADMIN
            updated_fields.append("role")

        if not verify_password(admin_password, user.password_hash):
            user.password_hash = hash_password(admin_password)
            updated_fields.append("password")
            logger.info("system_admin_password_updated", employee_id=admin_id)
        else:
            logger.info("system_admin_password_unchanged", employee_id=admin_id)

        if updated_fields:
            await self.user_repo.update_user(user)
            logger.info(
                "system_admin_user_updated",
                employee_id=admin_id,
                updated_fields=updated_fields,
            )
        else:
            logger.info("system_admin_user_no_change", employee_id=admin_id)

        await self._ensure_admin_department_link(user.id, department.id, admin_id)

    async def _ensure_system_department(self) -> Department:
        logger.info(
            "system_department_lookup",
            department_code=self.SYSTEM_DEPARTMENT_CODE,
        )
        department = await self.department_repo.get_by_code(self.SYSTEM_DEPARTMENT_CODE)
        if department is not None:
            logger.info(
                "system_department_exists",
                department_code=self.SYSTEM_DEPARTMENT_CODE,
            )
            return department

        logger.info(
            "system_department_missing",
            department_code=self.SYSTEM_DEPARTMENT_CODE,
        )
        department = await self.department_repo.create_department(
            Department(
                department_code=self.SYSTEM_DEPARTMENT_CODE,
                department_name=self.SYSTEM_DEPARTMENT_NAME,
                is_active=True,
            )
        )
        logger.info(
            "system_department_created",
            department_code=self.SYSTEM_DEPARTMENT_CODE,
            department_id=str(department.id),
        )
        return department

    async def _create_admin_user(
        self,
        admin_id: str,
        admin_password: str,
        department_id: UUID,
    ) -> None:
        user_create = UserCreate(
            employee_id=admin_id,
            name=self.DEFAULT_ADMIN_NAME,
            role=UserRole.ADMIN,
            password=admin_password,
            is_active=True,
            department_ids=[department_id],
            primary_department_id=department_id,
        )
        hashed_password = hash_password(admin_password)
        user = await self.user_repo.create_user(user_create, password_hash=hashed_password)

        assignment = UserDepartmentAssignment(
            department_ids=[department_id],
            primary_department_id=department_id,
        )
        await self.department_service.assign_user_departments(user.id, assignment)

    async def _ensure_admin_department_link(
        self,
        user_id: int,
        department_id: UUID,
        admin_id: str,
    ) -> None:
        user = await self.user_repo.get_with_departments(user_id)
        if user is None:
            logger.info("system_admin_department_skip_missing_user", employee_id=admin_id)
            return

        department_ids = [link.department_id for link in user.department_links]
        if department_id in department_ids:
            logger.info(
                "system_admin_department_exists",
                employee_id=admin_id,
                department_code=self.SYSTEM_DEPARTMENT_CODE,
            )
            return

        logger.info(
            "system_admin_department_missing",
            employee_id=admin_id,
            department_code=self.SYSTEM_DEPARTMENT_CODE,
        )
        department_ids.append(department_id)
        primary_department_id = next(
            (link.department_id for link in user.department_links if link.is_primary),
            department_id,
        )
        assignment = UserDepartmentAssignment(
            department_ids=department_ids,
            primary_department_id=primary_department_id,
        )
        await self.department_service.assign_user_departments(user.id, assignment)
        logger.info(
            "system_admin_department_linked",
            employee_id=admin_id,
            department_code=self.SYSTEM_DEPARTMENT_CODE,
        )
