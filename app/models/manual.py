"""
ERD 요약:
- Consultation 1 - N ManualEntry (source_consultation_id)
- ManualVersion 1 - N ManualEntry
- ManualEntry 1 - N ManualReviewTask (old/new 각각)  # defined in task.py
- ManualEntry 1 - 1 ManualVectorIndex
"""

import enum
from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum, ForeignKey, String, Text
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
    consultation_reference: Mapped["Consultation" | None] = relationship(
        "Consultation",
        back_populates="manual_entry",
        foreign_keys="Consultation.manual_entry_id",
        uselist=False,
    )
    version: Mapped["ManualVersion | None"] = relationship(
        "ManualVersion", back_populates="entries"
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
    vector_index: Mapped["ManualVectorIndex | None"] = relationship(
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

    version: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    changelog: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    entries: Mapped[list[ManualEntry]] = relationship(
        "ManualEntry",
        back_populates="version",
    )

    def __repr__(self) -> str:
        return f"<ManualVersion(id={self.id}, version={self.version})>"
