"""
ERD 요약:
- Consultation 1 - N ManualEntry (source_consultation_id)
- ManualVersion 1 - N ManualEntry
- ManualEntry 1 - N ManualReviewTask (old/new 각각)  # defined in task.py
- ManualEntry 1 - 1 ManualVectorIndex
"""

import enum
from uuid import UUID
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum as SQLEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.consultation import Consultation
    from app.models.task import ManualReviewTask
    from app.models.vector_index import ManualVectorIndex


class ManualStatus(str, enum.Enum):
    """메뉴얼 상태 Enum (FR-4 승인/반려 흐름 반영)"""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class ManualEntry(BaseModel):
    """
    FR-1/FR-2/FR-4/FR-6: 상담 기반 메뉴얼 생성·승인·Deprecated 관리
    """

    __tablename__ = "manual_entries"

    keywords: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="1-3개 핵심 키워드",
    )
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    background: Mapped[str] = mapped_column(Text, nullable=False)
    guideline: Mapped[str] = mapped_column(Text, nullable=False)

    business_type: Mapped[str | None] = mapped_column(String(50), index=True)
    error_code: Mapped[str | None] = mapped_column(String(50), index=True)

    source_consultation_id: Mapped[UUID] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("manual_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[ManualStatus] = mapped_column(
        SQLEnum(ManualStatus, name="manual_status"),
        nullable=False,
        default=ManualStatus.DRAFT,
    )

    # Relationships
    source_consultation: Mapped["Consultation"] = relationship(
        "Consultation",
        back_populates="manual_drafts",
        foreign_keys=[source_consultation_id],
    )
    consultation_reference: Mapped[Optional["Consultation"]] = relationship(
        "Consultation",
        back_populates="manual_entry",
        foreign_keys="Consultation.manual_entry_id",
        uselist=False,
    )
    version: Mapped[Optional["ManualVersion"]] = relationship(
        "ManualVersion", back_populates="entries"
    )
    replaced_manual_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("manual_entries.id", ondelete="SET NULL"),
        nullable=True,
        comment="이 메뉴얼이 대체한 기존 메뉴얼 ID",
    )
    replaced_by_manual_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("manual_entries.id", ondelete="SET NULL"),
        nullable=True,
        comment="이 메뉴얼을 대체한 신규 메뉴얼 ID",
    )

    replaced_manual: Mapped[Optional["ManualEntry"]] = relationship(
        "ManualEntry",
        foreign_keys=[replaced_manual_id],
        remote_side="ManualEntry.id",
        back_populates="replaced_by_manuals",
        uselist=False,
    )
    replaced_by_manuals: Mapped[list["ManualEntry"]] = relationship(
        "ManualEntry",
        foreign_keys=[replaced_manual_id],
        back_populates="replaced_manual",
    )
    replaced_by: Mapped[Optional["ManualEntry"]] = relationship(
        "ManualEntry",
        foreign_keys=[replaced_by_manual_id],
        remote_side="ManualEntry.id",
        back_populates="deprecated_manuals",
        uselist=False,
    )
    deprecated_manuals: Mapped[list["ManualEntry"]] = relationship(
        "ManualEntry",
        foreign_keys=[replaced_by_manual_id],
        back_populates="replaced_by",
    )
    review_tasks_as_old: Mapped[list["ManualReviewTask"]] = relationship(
        "ManualReviewTask",
        back_populates="old_entry",
        foreign_keys="ManualReviewTask.old_entry_id",
    )
    review_tasks_as_new: Mapped[list["ManualReviewTask"]] = relationship(
        "ManualReviewTask",
        back_populates="new_entry",
        foreign_keys="ManualReviewTask.new_entry_id",
    )
    vector_index: Mapped[Optional["ManualVectorIndex"]] = relationship(
        "ManualVectorIndex",
        back_populates="manual_entry",
        uselist=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ManualEntry(id={self.id}, topic={self.topic}, status={self.status})>"
        )


class ManualVersion(BaseModel):
    """
    FR-5: 메뉴얼 버전 관리
    """

    __tablename__ = "manual_versions"

    business_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="업무구분 (그룹 식별용)",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="에러코드 (그룹 식별용)",
    )

    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="버전 번호 (그룹 내에서 유일)",
    )
    description: Mapped[str | None] = mapped_column(Text)
    changelog: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    entries: Mapped[list[ManualEntry]] = relationship(
        "ManualEntry",
        back_populates="version",
    )

    __table_args__ = (
        UniqueConstraint(
            "business_type",
            "error_code",
            "version",
            name="uq_manual_version_group",
        ),
    )

    def __repr__(self) -> str:
        group_key = (
            f"{self.business_type}::{self.error_code}"
            if self.business_type and self.error_code
            else "unknown"
        )
        return (
            f"<ManualVersion(id={self.id}, group={group_key}, version={self.version})>"
        )
