"""
ERD 요약:
- Consultation 1 - N ManualEntry (source_consultation_id)
- Consultation 1 - 1 ManualEntry (manual_entry_id: 승인된 메뉴얼 링크)
- Consultation 1 - 1 ConsultationVectorIndex
"""

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.sqlalchemy_types import JSONB

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.manual import ManualEntry
    from app.models.user import User
    from app.models.vector_index import ConsultationVectorIndex


class Consultation(BaseModel):
    """
    FR-1/FR-2/FR-6: 상담 이력 저장 및 메뉴얼 파생, 벡터 인덱스 메타 필터용 컬럼 포함
    """

    __tablename__ = "consultations"

    summary: Mapped[str] = mapped_column(Text, nullable=False)
    inquiry_text: Mapped[str] = mapped_column(Text, nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)

    branch_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(50), nullable=False)
    screen_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    transaction_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    metadata_fields: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    manual_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("manual_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="승인된 메뉴얼 항목 연결 (옵션)",
    )

    user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="[Consultation.employee_id]",
        primaryjoin="Consultation.employee_id == User.employee_id",
        uselist=False,
        viewonly=True,
    )

    manual_entry: Mapped[Optional["ManualEntry"]] = relationship(
        "ManualEntry",
        back_populates="consultation_reference",
        foreign_keys=[manual_entry_id],
        uselist=False,
    )
    manual_drafts: Mapped[list["ManualEntry"]] = relationship(
        "ManualEntry",
        back_populates="source_consultation",
        foreign_keys="ManualEntry.source_consultation_id",
    )
    vector_index: Mapped[Optional["ConsultationVectorIndex"]] = relationship(
        "ConsultationVectorIndex",
        back_populates="consultation",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<Consultation(id={self.id}, branch={self.branch_code})>"
