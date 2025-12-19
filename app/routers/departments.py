"""Department management router"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.dependencies import require_roles
from app.core.exceptions import DuplicateRecordError, RecordNotFoundError, ValidationError
from app.models.user import UserRole
from app.schemas.department import (
    DepartmentCreate,
    DepartmentResponse,
    UserDepartmentAssignment,
    UserDepartmentListResponse,
)
from app.services.department_service import DepartmentService


router = APIRouter(
    tags=["departments"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


def get_department_service(
    session: AsyncSession = Depends(get_session),
) -> DepartmentService:
    return DepartmentService(session=session)


@router.get(
    "/admin/departments",
    response_model=list[DepartmentResponse],
    summary="부서 목록 조회",
)
async def list_departments(
    is_active: Optional[bool] = Query(None, description="활성화 여부 필터"),
    service: DepartmentService = Depends(get_department_service),
) -> list[DepartmentResponse]:
    return await service.list_departments(is_active=is_active)


@router.post(
    "/admin/departments",
    response_model=DepartmentResponse,
    status_code=201,
    summary="부서 생성",
)
async def create_department(
    payload: DepartmentCreate,
    service: DepartmentService = Depends(get_department_service),
) -> DepartmentResponse:
    try:
        return await service.create_department(payload)
    except (DuplicateRecordError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/admin/users/{user_id}/departments",
    response_model=UserDepartmentListResponse,
    summary="사용자 부서 매핑 조회",
)
async def get_user_departments(
    user_id: int,
    service: DepartmentService = Depends(get_department_service),
) -> UserDepartmentListResponse:
    try:
        return await service.get_user_departments(user_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put(
    "/admin/users/{user_id}/departments",
    response_model=UserDepartmentListResponse,
    summary="사용자 부서 매핑 갱신",
)
async def update_user_departments(
    user_id: int,
    payload: UserDepartmentAssignment,
    service: DepartmentService = Depends(get_department_service),
) -> UserDepartmentListResponse:
    try:
        return await service.assign_user_departments(user_id, payload)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
