"""Department schemas"""

from typing import List
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseResponseSchema, BaseSchema


class DepartmentBase(BaseSchema):
    department_code: str = Field(min_length=1, max_length=50)
    department_name: str = Field(min_length=1, max_length=100)
    is_active: bool = Field(default=True)


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentResponse(DepartmentBase, BaseResponseSchema):
    pass


class UserDepartmentAssignment(BaseSchema):
    department_ids: List[UUID] = Field(min_items=1)
    primary_department_id: UUID | None = Field(default=None)


class UserDepartmentListResponse(BaseSchema):
    user_id: int
    departments: List[DepartmentResponse]
    primary_department_id: UUID | None
