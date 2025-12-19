"""
User schemas
"""

from datetime import datetime
from enum import Enum
from typing import List
from uuid import UUID

from pydantic import Field

from app.models.user import UserRole
from app.schemas.base import BaseSchema, PaginatedResponse
from app.schemas.department import DepartmentResponse


class UserBase(BaseSchema):
    username: str = Field(min_length=3, max_length=50)
    employee_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    role: UserRole = Field(default=UserRole.CONSULTANT)
    is_active: bool = Field(default=True)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    department_ids: list[UUID] = Field(
        min_items=1,
        description="사용자가 속할 부서 ID 목록 (최소 1개)",
    )
    primary_department_id: UUID | None = Field(
        default=None,
        description="기본 부서로 사용할 ID (생략 시 첫번째 부서)",
    )


class UserLogin(BaseSchema):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    departments: List[DepartmentResponse] = Field(default_factory=list)


class UserSortBy(str, Enum):
    username = "username"
    employee_id = "employee_id"
    name = "name"
    created_at = "created_at"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class UserListParams(BaseSchema):
    employee_id: str | None = Field(default=None, description="사번 필터")
    name: str | None = Field(default=None, description="이름 필터 (부분 검색)")
    department_code: str | None = Field(default=None, description="부서 코드 필터")
    role: UserRole | None = Field(default=None, description="역할 필터")
    is_active: bool | None = Field(default=None, description="활성 상태 필터")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: UserSortBy = Field(default=UserSortBy.created_at, description="정렬 기준")
    sort_order: SortOrder = Field(default=SortOrder.desc, description="정렬 방향 (asc/desc)")


class UserAdminCreate(BaseSchema):
    username: str = Field(min_length=3, max_length=50)
    employee_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    role: UserRole = Field(default=UserRole.CONSULTANT)
    is_active: bool = Field(default=True)
    password: str = Field(min_length=12, max_length=128)
    department_ids: list[UUID] = Field(
        min_items=1,
        description="부서 ID 목록 (최소 1개)",
    )
    primary_department_id: UUID | None = Field(
        default=None,
        description="기본 부서 (생략하면 department_ids[0])",
    )


class UserAdminUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    password: str | None = Field(default=None, min_length=12, max_length=128)
    department_ids: list[UUID] | None = Field(
        default=None,
        min_items=1,
        description="새로 연결할 부서 ID 목록",
    )
    primary_department_id: UUID | None = Field(
        default=None,
        description="기본 부서 (department_ids 포함되어야 함)",
    )


class UserListResponse(PaginatedResponse):
    items: list[UserResponse]


class TokenResponse(BaseSchema):
    access_token: str
    token_type: str = "bearer"
