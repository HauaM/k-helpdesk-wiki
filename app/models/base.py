"""
SQLAlchemy Declarative Base와 공통 믹스인 정의
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    모든 도메인 모델이 상속하는 Declarative Base
    """

    pass


class TimestampMixin:
    """
    공통 생성/수정 시각 필드 제공
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """
    UUID 기본 키 제공
    """

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        nullable=False,
    )


class BaseModel(Base, UUIDMixin, TimestampMixin):
    """
    UUID + 타임스탬프를 포함한 추상 베이스 모델
    """

    __abstract__ = True
