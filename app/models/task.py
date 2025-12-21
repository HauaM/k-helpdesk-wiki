"""
ERD 요약:
- ManualEntry 1 - N ManualReviewTask (old_entry_id / new_entry_id)
- ManualReviewTask 1 - N TaskHistory
"""

import enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Enum as SQLEnum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.manual import ManualEntry


class TaskStatus(str, enum.Enum):
    """검토 태스크 상태 Enum (FR-5/FR-6 워크플로우)"""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    REJECTED = "REJECTED"


class ComparisonType(str, enum.Enum):
    """
    비교 결과 타입 분류 (v2.1)

    신규 draft를 기존 메뉴얼과 비교한 결과에 따른 분류:
    - SIMILAR: 기존 메뉴얼과 매우 유사 (≥0.95 유사도)
    - SUPPLEMENT: 기존 메뉴얼 보충/개선 (0.7-0.95 유사도)
    - NEW: 신규 메뉴얼 (<0.7 유사도)
    """

    SIMILAR = "similar"
    SUPPLEMENT = "supplement"
    NEW = "new"


class ManualReviewTask(BaseModel):
    """
    FR-4/FR-5/FR-6/FR-7: 메뉴얼 충돌 검출 및 승인/반려 워크플로우 태스크
    """

    __tablename__ = "manual_review_tasks"

    old_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("manual_entries.id", ondelete="CASCADE"),
        nullable=True,
        comment="기존 메뉴얼 (없으면 신규 생성 흐름)",
    )
    new_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("manual_entries.id", ondelete="CASCADE"),
        nullable=False,
        comment="신규 상담 기반 메뉴얼 초안",
    )

    similarity: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="기존/신규 유사도 점수",
    )
    comparison_type: Mapped[ComparisonType] = mapped_column(
        SQLEnum(ComparisonType, name="manual_comparison_type", native_enum=False),
        nullable=False,
        default=ComparisonType.NEW,
        comment="비교 타입: similar/supplement/new (v2.1)",
    )
    compare_version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="비교 로직/threshold 버전 식별 키",
    )

    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.TODO,
    )

    reviewer_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="검토자 식별자 (User 테이블과 향후 연결)",
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        comment="검토 대상 부서 (FR-20 기준 노출 제어)",
    )

    old_entry: Mapped[Optional["ManualEntry"]] = relationship(
        "ManualEntry",
        back_populates="review_tasks_as_old",
        foreign_keys=[old_entry_id],
    )
    new_entry: Mapped["ManualEntry"] = relationship(
        "ManualEntry",
        back_populates="review_tasks_as_new",
        foreign_keys=[new_entry_id],
    )
    history: Mapped[list["TaskHistory"]] = relationship(
        "TaskHistory",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        similarity_text = (
            f"{self.similarity:.2f}" if self.similarity is not None else "None"
        )
        return f"<ManualReviewTask(id={self.id}, status={self.status}, similarity={similarity_text})>"

    @property
    def similarity_score(self) -> float | None:
        """comparison result alias for spec-aligned field name."""
        return self.similarity

    @similarity_score.setter
    def similarity_score(self, value: float | None) -> None:
        self.similarity = value


class TaskHistory(BaseModel):
    """
    FR-7/FR-10: 태스크 상태 변경 이력 기록 (감사 및 재시도 기준)
    """

    __tablename__ = "task_history"

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("manual_review_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[TaskStatus | None] = mapped_column(
        SQLEnum(TaskStatus, name="task_status", create_constraint=False),
        nullable=True,
    )
    to_status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, name="task_status", create_constraint=False),
        nullable=False,
    )
    changed_by: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="상태 변경 주체",
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["ManualReviewTask"] = relationship(
        "ManualReviewTask",
        back_populates="history",
    )

    def __repr__(self) -> str:
        return f"<TaskHistory(task_id={self.task_id}, to={self.to_status})>"


# 기존 코드 호환용 별칭
ReviewTaskStatus = TaskStatus
