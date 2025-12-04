"""
ERD 요약:
- Consultation 1 - 1 ConsultationVectorIndex
- ManualEntry 1 - 1 ManualVectorIndex
- RetryQueueJob N - 1 대상(manual/consultation) by target_type + target_id
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.consultation import Consultation
    from app.models.manual import ManualEntry


class IndexStatus(str, enum.Enum):
    """FR-11: 벡터 인덱스 상태 관리"""

    PENDING = "PENDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class RetryJobStatus(str, enum.Enum):
    """벡터 인덱싱 재시도 상태"""

    PENDING = "PENDING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RetryTarget(str, enum.Enum):
    """재시도 대상 인덱스"""

    CONSULTATION = "CONSULTATION"
    MANUAL = "MANUAL"


class ConsultationVectorIndex(BaseModel):
    """
    FR-2/FR-6/FR-11: 상담 벡터 인덱스 메타데이터 저장 (branch/business/error 필터)
    """

    __tablename__ = "consultation_vector_index"

    consultation_id: Mapped[UUID] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    embedding: Mapped[list[float]] = mapped_column(
        ARRAY(Float),
        nullable=False,
        comment="임베딩 벡터",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        comment="FR-11 메타 스키마: branch_code, business_type, error_code, created_at",
    )
    branch_code: Mapped[str | None] = mapped_column(String(50), index=True)
    business_type: Mapped[str | None] = mapped_column(String(50), index=True)
    error_code: Mapped[str | None] = mapped_column(String(50), index=True)
    status: Mapped[IndexStatus] = mapped_column(
        SQLEnum(IndexStatus, name="index_status"),
        nullable=False,
        default=IndexStatus.PENDING,
    )

    consultation: Mapped["Consultation"] = relationship(
        "Consultation",
        back_populates="vector_index",
    )

    def __repr__(self) -> str:
        return f"<ConsultationVectorIndex(consultation_id={self.consultation_id})>"


class ManualVectorIndex(BaseModel):
    """
    FR-2/FR-4/FR-11: 메뉴얼 벡터 인덱스 메타데이터 저장 (business/error 필터)
    """

    __tablename__ = "manual_vector_index"

    manual_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("manual_entries.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    embedding: Mapped[list[float]] = mapped_column(
        ARRAY(Float),
        nullable=False,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        comment="FR-11 메타 스키마: business_type, error_code, created_at",
    )
    business_type: Mapped[str | None] = mapped_column(String(50), index=True)
    error_code: Mapped[str | None] = mapped_column(String(50), index=True)
    status: Mapped[IndexStatus] = mapped_column(
        SQLEnum(IndexStatus, name="index_status", create_constraint=False),
        nullable=False,
        default=IndexStatus.PENDING,
    )

    manual_entry: Mapped["ManualEntry"] = relationship(
        "ManualEntry",
        back_populates="vector_index",
    )

    def __repr__(self) -> str:
        return f"<ManualVectorIndex(manual_entry_id={self.manual_entry_id})>"


class RetryQueueJob(BaseModel):
    """
    FR-10: VectorStore 인덱싱 실패를 위한 재시도 큐
    """

    __tablename__ = "retry_queue_jobs"

    target_type: Mapped[RetryTarget] = mapped_column(
        SQLEnum(RetryTarget, name="retry_target"),
        nullable=False,
    )
    target_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="인덱싱 재시도에 필요한 입력/메타데이터",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    status: Mapped[RetryJobStatus] = mapped_column(
        SQLEnum(RetryJobStatus, name="retry_job_status"),
        nullable=False,
        default=RetryJobStatus.PENDING,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="재시도 예정 시각",
    )

    def __repr__(self) -> str:
        return f"<RetryQueueJob(target={self.target_type}, target_id={self.target_id}, status={self.status})>"
