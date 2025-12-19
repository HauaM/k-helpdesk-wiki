"""
Admin user management routes
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.dependencies import get_current_user, require_roles
from app.models.user import User, UserRole
from app.schemas.user import (
    UserAdminCreate,
    UserAdminUpdate,
    UserListParams,
    UserListResponse,
    UserResponse,
)
from app.services.user_admin_service import UserAdminService


def get_user_admin_service(session: AsyncSession = Depends(get_session)) -> UserAdminService:
    return UserAdminService(session=session)


router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "",
    response_model=UserListResponse,
    summary="사용자 목록 조회",
)
async def list_users(
    params: UserListParams = Depends(),
    service: UserAdminService = Depends(get_user_admin_service),
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
) -> UserListResponse:
    return await service.list_users(params)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사용자 생성",
)
async def create_user(
    payload: UserAdminCreate,
    service: UserAdminService = Depends(get_user_admin_service),
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
) -> UserResponse:
    return await service.create_user(payload)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="사용자 정보 업데이트",
)
async def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    service: UserAdminService = Depends(get_user_admin_service),
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
) -> UserResponse:
    return await service.update_user(user_id, payload)
