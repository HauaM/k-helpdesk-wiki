"""
FR-15: 공통코드 관리 모델

CommonCodeGroup: 공통코드 그룹 (예: BUSINESS_TYPE, ERROR_CODE)
CommonCodeItem: 공통코드 항목 (예: {"key": "RETAIL", "value": "리테일"})
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.sqlalchemy_types import JSONB

from app.models.base import BaseModel


class CommonCodeGroup(BaseModel):
    """
    FR-15: 공통코드 그룹 정의
    - group_code: 그룹 고유 코드 (예: BUSINESS_TYPE, ERROR_CODE)
    - group_name: 그룹 이름
    - description: 설명
    - is_active: 활성화 여부
    """

    __tablename__ = "common_code_groups"

    group_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="그룹 고유 코드 (예: BUSINESS_TYPE, ERROR_CODE)",
    )
    group_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="그룹 이름 (예: 업무 구분, 에러코드)",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="그룹 설명",
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        index=True,
        comment="활성화 여부",
    )

    # Relationships
    items: Mapped[list["CommonCodeItem"]] = relationship(
        "CommonCodeItem",
        back_populates="group",
        cascade="all, delete-orphan",
        uselist=True,
    )

    def __repr__(self) -> str:
        return f"<CommonCodeGroup(code={self.group_code}, name={self.group_name})>"


class CommonCodeItem(BaseModel):
    """
    FR-15: 공통코드 항목
    - code_key: 코드 키 (예: RETAIL, LOAN)
    - code_value: 코드 값/표시명 (예: 리테일, 대출)
    - group_id: 상위 그룹 FK
    - sort_order: 정렬 순서
    - is_active: 활성화 여부
    - metadata: 추가 메타데이터 (JSON, 선택사항)
    """

    __tablename__ = "common_code_items"

    # Foreign Key (stored as UUID string for reliable querying)
    group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("common_code_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="상위 공통코드 그룹 ID",
    )

    # Code fields
    code_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="코드 키 (예: RETAIL, LOAN)",
    )
    code_value: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="코드 값/표시명 (예: 리테일, 대출)",
    )

    # Ordering and status
    sort_order: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="정렬 순서",
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        index=True,
        comment="활성화 여부",
    )

    # Optional metadata
    attributes: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="추가 속성/메타데이터 (선택사항)",
    )

    # Relationships
    group: Mapped["CommonCodeGroup"] = relationship(
        "CommonCodeGroup",
        back_populates="items",
        uselist=False,
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "code_key",
            name="uq_common_code_item_group_key",
        ),
    )

    def __repr__(self) -> str:
        return f"<CommonCodeItem(key={self.code_key}, value={self.code_value})>"
