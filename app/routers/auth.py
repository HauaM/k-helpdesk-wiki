"""Authentication routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.dependencies import get_current_user
from app.core.exceptions import AuthenticationError
from app.models.user import User
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_user_service(session: AsyncSession = Depends(get_session)) -> UserService:
    """UserService DI 헬퍼."""

    return UserService(session=session)


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사용자 회원가입",
)
async def signup(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """
    회원가입 엔드포인트.
    """

    return await service.signup(payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="사용자 로그인",
)
async def login(
    payload: UserLogin,
    service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """
    로그인 후 액세스 토큰 발급.
    """

    try:
        return await service.login(payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="현재 사용자 조회",
)
async def read_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """토큰으로 인증된 현재 사용자 정보를 반환."""

    return UserResponse.model_validate(current_user)
