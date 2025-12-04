"""
ERD 요약:
- ManualEntry 1 - N ManualReviewTask (old_entry_id / new_entry_id)
- ManualReviewTask 1 - N TaskHistory
"""

import enum
from typing import TYPE_CHECKING
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

    similarity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="기존/신규 유사도 점수",
    )

    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.TODO,
    )

    reviewer_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
        comment="검토자 식별자 (User 테이블과 향후 연결)",
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    old_entry: Mapped["ManualEntry" | None] = relationship(
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
        return (
            f"<ManualReviewTask(id={self.id}, status={self.status}, similarity={self.similarity:.2f})>"
        )


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
    changed_by: Mapped[UUID | None] = mapped_column(
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
