"""
VectorStore DTO definitions

RPF FR-11 메타데이터 스키마를 반영하여 모든 VectorStore 구현체가
일관된 입력/출력 타입을 사용하도록 한다.
"""

from datetime import datetime
from uuid import UUID

from app.schemas.base import BaseSchema


class VectorMetadata(BaseSchema):
    """FR-11: branch/business/error 필터 및 인덱싱 시각을 포함한 메타데이터."""

    branch_code: str | None = None
    business_type: str | None = None
    error_code: str | None = None
    created_at: datetime | None = None


class VectorItem(BaseSchema):
    """VectorStore에 추가될 개별 벡터 항목."""

    id: UUID
    embedding: list[float]
    metadata: VectorMetadata | None = None


class SearchResult(BaseSchema):
    """VectorStore 검색 결과 단위."""

    id: UUID
    score: float
    metadata: VectorMetadata | None = None
