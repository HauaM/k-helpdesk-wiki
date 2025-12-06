"""
Consultation Schemas
Pydantic models for Consultation API requests/responses
"""

from typing import Any
from uuid import UUID
from datetime import datetime
from pydantic import Field

from app.schemas.base import BaseSchema, BaseResponseSchema


class ConsultationBase(BaseSchema):
    """
    Base consultation fields
    """

    summary: str = Field(min_length=10, max_length=500)
    inquiry_text: str = Field(min_length=10)
    action_taken: str = Field(min_length=10)
    branch_code: str = Field(min_length=1, max_length=50)
    employee_id: str = Field(min_length=1, max_length=50)
    screen_id: str | None = Field(default=None, max_length=50)
    transaction_name: str | None = Field(default=None, max_length=100)
    business_type: str | None = Field(default=None, max_length=50)
    error_code: str | None = Field(default=None, max_length=50)
    metadata_fields: dict[str, Any] = Field(default_factory=dict)


class ConsultationCreate(ConsultationBase):
    """
    Schema for creating new consultation

    RFP Reference: POST /consultations
    """

    pass


class ConsultationSearchFilters(BaseSchema):
    """
    VectorStore 재조회 시 적용할 메타데이터 필터 (FR-3 대비 사전 정의).

    나중 Task에서 사용할 예정이지만, Repository와 Service 계약을 맞추기 위해
    기본 필드를 미리 선언한다.
    """

    branch_code: str | None = Field(default=None, max_length=50)
    business_type: str | None = Field(default=None, max_length=50)
    error_code: str | None = Field(default=None, max_length=50)
    start_date: datetime | None = Field(
        default=None,
        description="조회 시작 시각 (created_at 이상)",
    )
    end_date: datetime | None = Field(
        default=None,
        description="조회 종료 시각 (created_at 이하)",
    )


class ConsultationUpdate(BaseSchema):
    """
    Schema for updating consultation (partial updates allowed)
    """

    summary: str | None = None
    inquiry_text: str | None = None
    action_taken: str | None = None
    # TODO: Add other optional fields


class ConsultationResponse(ConsultationBase, BaseResponseSchema):
    """
    Schema for consultation response

    Includes all base fields plus ID and timestamps
    """

    manual_entry_id: UUID | None = None


class ConsultationSearchParams(BaseSchema):
    """
    Search parameters for consultations

    RFP Reference: GET /consultations/search
    """

    query: str = Field(min_length=1, description="Search query text")
    branch_code: str | None = Field(default=None, description="Filter by branch")
    business_type: str | None = Field(default=None, description="Filter by business type")
    error_code: str | None = Field(default=None, description="Filter by error code")
    start_date: datetime | None = Field(
        default=None, description="Filter by created_at >= start_date"
    )
    end_date: datetime | None = Field(
        default=None, description="Filter by created_at <= end_date"
    )
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results")
    similarity_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum similarity score"
    )


class ConsultationSearchRequest(BaseSchema):
    """FR-3: 상담 검색 요청 스키마."""

    query: str = Field(min_length=1, description="검색 쿼리")
    top_k: int = Field(default=10, ge=1, le=50)
    filters: ConsultationSearchFilters = Field(
        default_factory=ConsultationSearchFilters,
        description="branch/business/error 등 메타 필터",
    )


class ConsultationSearchVectorMetadata(BaseSchema):
    """검색 결과에 포함될 Vector 메타데이터."""

    branch_code: str | None = None
    business_type: str | None = None
    error_code: str | None = None
    created_at: datetime | None = None


class ConsultationSearchResult(BaseSchema):
    """
    검색 결과 단위 (상담 + 점수 + 메타데이터).
    """

    consultation: ConsultationResponse
    score: float = Field(ge=0.0, le=1.0)
    metadata: ConsultationSearchVectorMetadata | None = None


class ConsultationSearchResponse(BaseSchema):
    """
    Search results response
    """

    results: list[ConsultationSearchResult]
    total_found: int
    query: str
