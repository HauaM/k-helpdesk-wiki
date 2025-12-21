"""
User domain model
"""

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum as SQLEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.department import Department, UserDepartment


class UserRole(str, enum.Enum):
    """시스템 사용자 역할"""

    CONSULTANT = "CONSULTANT"
    REVIEWER = "REVIEWER"
    ADMIN = "ADMIN"


class User(Base, TimestampMixin):
    """사용자 계정 모델"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.CONSULTANT,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    department_links: Mapped[list["UserDepartment"]] = relationship(
        "UserDepartment",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, employee_id={self.employee_id}, role={self.role})>"

    @property
    def departments(self) -> list["Department"]:
        """사용자가 속한 부서 리스트"""

        return [link.department for link in self.department_links]
