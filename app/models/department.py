"""
Department domain models
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BaseModel, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Department(BaseModel):
    """부서 정보를 나타내는 도메인 모델"""

    __tablename__ = "departments"

    department_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )
    department_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    memberships: Mapped[list["UserDepartment"]] = relationship(
        "UserDepartment",
        back_populates="department",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Department(id={self.id}, code={self.department_code}, name={self.department_name})>"
        )


class UserDepartment(Base, TimestampMixin):
    """사용자-부서 매핑"""

    __tablename__ = "user_departments"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    department_id: Mapped[UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="department_links",
        lazy="joined",
    )
    department: Mapped["Department"] = relationship(
        "Department",
        back_populates="memberships",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<UserDepartment(user_id={self.user_id}, department_id={self.department_id}, "
            f"is_primary={self.is_primary})>"
        )
