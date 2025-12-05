"""
Manual Schemas
Pydantic models for Manual API requests/responses
"""

from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.models.manual import ManualStatus
from app.models.task import TaskStatus
from app.schemas.base import BaseSchema, BaseResponseSchema


class ManualEntryBase(BaseSchema):
    """
    Base manual entry fields
    """

    keywords: list[str] = Field(min_length=1, max_length=3)
    topic: str = Field(min_length=5, max_length=200)
    background: str = Field(min_length=10)
    guideline: str = Field(min_length=10)
    business_type: str | None = None
    error_code: str | None = None


class ManualEntryCreate(ManualEntryBase):
    """
    Schema for creating manual entry draft

    RFP Reference: POST /consultations/{id}/manual-draft
    """

    source_consultation_id: UUID


class ManualEntryUpdate(BaseSchema):
    """
    Schema for updating manual entry
    """

    keywords: list[str] | None = None
    topic: str | None = None
    background: str | None = None
    guideline: str | None = None
    status: ManualStatus | None = None


class ManualEntryResponse(ManualEntryBase, BaseResponseSchema):
    """
    Schema for manual entry response
    """

    source_consultation_id: UUID
    version_id: UUID | None
    status: ManualStatus


class ManualSearchParams(BaseSchema):
    """
    Search parameters for manuals

    RFP Reference: GET /manuals/search
    """

    query: str = Field(min_length=1)
    business_type: str | None = None
    error_code: str | None = None
    status: ManualStatus | None = None
    top_k: int = Field(default=10, ge=1, le=50)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class ManualSearchResult(BaseSchema):
    """
    Single manual search result
    """

    manual: ManualEntryResponse
    similarity_score: float


class ManualVersionResponse(BaseResponseSchema):
    """
    Manual version response
    """

    version: str
    description: str | None
    changelog: dict | None


class ManualReviewTaskResponse(BaseResponseSchema):
    """
    Manual review task response

    RFP Reference: GET /tasks/manual-review
    """

    old_entry_id: UUID | None
    new_entry_id: UUID
    similarity: float
    status: TaskStatus
    reviewer_id: UUID | None
    review_notes: str | None
    old_manual_summary: str | None = Field(default=None, description="기존 메뉴얼 요약")
    new_manual_summary: str | None = Field(default=None, description="신규 초안 요약")
    diff_text: str | None = Field(default=None, description="LLM 비교 결과 요약")
    diff_json: dict | None = Field(default=None, description="LLM 비교 결과 JSON")

    # TODO: Optionally include full manual entries for comparison
    # old_entry: ManualEntryResponse | None
    # new_entry: ManualEntryResponse


class ManualReviewApproval(BaseSchema):
    """
    Schema for approving manual review

    RFP Reference: POST /tasks/manual-review/{id}/approve
    """

    reviewer_id: UUID
    review_notes: str | None = None
    create_new_version: bool = Field(
        default=True, description="Create new manual version"
    )


class ManualReviewRejection(BaseSchema):
    """
    Schema for rejecting manual review

    RFP Reference: POST /tasks/manual-review/{id}/reject
    """

    review_notes: str = Field(min_length=10, description="Reason for rejection")


class ManualDraftCreateFromConsultationRequest(BaseSchema):
    """FR-2: 상담을 기반으로 메뉴얼 초안을 생성하기 위한 요청."""

    consultation_id: UUID
    enforce_hallucination_check: bool = Field(
        default=True,
        description="환각 검증 실패 시 리뷰 태스크 생성 여부",
    )


class ManualDraftResponse(BaseResponseSchema):
    """FR-2: 생성된 메뉴얼 초안 반환."""

    status: ManualStatus
    keywords: list[str]
    topic: str
    background: str
    guideline: str
    source_consultation_id: UUID


class ManualApproveRequest(BaseSchema):
    """FR-4: 메뉴얼 승인 요청."""

    approver_id: UUID
    notes: str | None = Field(default=None, description="승인 메모")


class ManualVersionInfo(BaseSchema):
    """FR-5: 전체 문서 세트 버전 정보."""

    version: str
    approved_at: datetime
