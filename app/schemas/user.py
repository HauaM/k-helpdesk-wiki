"""
User schemas
"""

from datetime import datetime

from pydantic import Field

from app.models.user import UserRole
from app.schemas.base import BaseSchema


class UserBase(BaseSchema):
    username: str = Field(min_length=3, max_length=50)
    employee_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    department: str = Field(min_length=1, max_length=100)
    role: UserRole = Field(default=UserRole.CONSULTANT)
    is_active: bool = Field(default=True)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseSchema):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseSchema):
    access_token: str
    token_type: str = "bearer"
