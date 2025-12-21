"""
Manual Schemas
Pydantic models for Manual API requests/responses
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field, ConfigDict

from app.models.manual import ManualStatus
from app.models.task import TaskStatus
from app.schemas.base import BaseSchema, BaseResponseSchema


class BusinessType(str, Enum):
    """
    메뉴얼 업무구분
    """

    INTERNET_BANKING = "인터넷뱅킹"
    MOBILE_BANKING = "모바일뱅킹"
    LOAN = "대출"
    DEPOSIT = "예금"
    CARD = "카드"


class ComparisonType(str, Enum):
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
    business_type_name: str | None = Field(
        default=None,
        description="업무구분 이름 (공통코드값)",
    )


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
    Manual version response for version list (v2.1 개선)

    기존 /{manual_id}/versions와 새로운 /versions 쿼리 엔드포인트에서
    모두 사용 가능하도록 구조화

    RFP Reference: GET /api/v1/manuals/{manual_id}/versions, GET /api/v1/manuals/versions
    """

    model_config = ConfigDict(populate_by_name=True)

    value: str = Field(alias="version", description="버전 번호 (예: v1.6)")
    label: str = Field(
        description="사용자 표시용 레이블 (버전 + 상태)"
    )
    date: str = Field(
        description="버전 생성/승인 날짜 (YYYY-MM-DD 형식)"
    )
    status: ManualStatus | None = Field(
        default=None,
        description="버전 상태 (APPROVED, DEPRECATED) - v2.1에서 추가",
    )
    manual_id: UUID | None = Field(
        default=None,
        description="이 버전의 메뉴얼 ID (비교 시 사용) - v2.1에서 추가",
    )


class ManualReviewTaskResponse(BaseResponseSchema):
    """
    Manual review task response

    RFP Reference: GET /tasks/manual-review
    """

    old_entry_id: UUID | None
    new_entry_id: UUID
    similarity: float | None
    status: TaskStatus
    reviewer_id: str | None
    reviewer_department_id: UUID | None = Field(
        default=None,
        description="검토 태스크 노출 대상 부서 ID",
    )
    review_notes: str | None
    old_manual_summary: str | None = Field(default=None, description="기존 메뉴얼 요약")
    new_manual_summary: str | None = Field(default=None, description="신규 초안 요약")
    diff_text: str | None = Field(default=None, description="LLM 비교 결과 요약")
    diff_json: dict[str, Any] | None = Field(default=None, description="LLM 비교 결과 JSON")
    business_type: str | None = Field(
        default=None,
        description="신규 초안(new_entry)의 업무구분 코드",
    )
    business_type_name: str | None = Field(
        default=None,
        description="신규 초안(new_entry)의 업무구분 이름 (공통코드값)",
    )
    new_error_code: str | None = Field(
        default=None,
        description="신규 초안(new_entry)의 에러코드",
    )
    new_manual_topic: str | None = Field(
        default=None,
        description="신규 초안(new_entry)의 주제",
    )
    new_manual_keywords: list[str] | None = Field(
        default=None,
        description="신규 초안(new_entry)의 키워드",
    )
    old_business_type: str | None = Field(
        default=None,
        description="기존 메뉴얼(old_entry)의 업무구분 코드 - old_entry_id가 있을 때만 표시",
    )
    old_business_type_name: str | None = Field(
        default=None,
        description="기존 메뉴얼(old_entry)의 업무구분 이름 (공통코드값) - old_entry_id가 있을 때만 표시",
    )
    old_error_code: str | None = Field(
        default=None,
        description="기존 메뉴얼(old_entry)의 에러코드 - old_entry_id가 있을 때만 표시",
    )
    old_manual_topic: str | None = Field(
        default=None,
        description="기존 메뉴얼(old_entry)의 주제 - old_entry_id가 있을 때만 표시",
    )

    # TODO: Optionally include full manual entries for comparison
    # old_entry: ManualEntryResponse | None
    # new_entry: ManualEntryResponse


class ManualReviewApproval(BaseSchema):
    """
    Schema for approving manual review

    RFP Reference: POST /tasks/manual-review/{id}/approve
    """

    employee_id: str
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
    """FR-2/FR-11(v2.1): 상담을 기반으로 메뉴얼 초안을 생성하기 위한 요청.

    v2.1: 사용자가 특정 버전과 비교할 수 있는 compare_with_manual_id 추가
    """

    consultation_id: UUID
    enforce_hallucination_check: bool = Field(
        default=True,
        description="환각 검증 실패 시 리뷰 태스크 생성 여부",
    )
    compare_with_manual_id: UUID | None = Field(
        default=None,
        description="(선택) 특정 메뉴얼과 비교하고 싶을 경우 해당 ID 지정. None이면 최신 APPROVED 버전 비교",
    )

class ManualDraftResponse(BaseResponseSchema):
    """FR-2: 생성된 메뉴얼 초안 반환 (기존 응답 - 호환성 유지)."""

    status: ManualStatus
    keywords: list[str]
    topic: str
    background: str
    guideline: str
    source_consultation_id: UUID



class ManualDraftCreateResponse(BaseResponseSchema):
    """FR-2/FR-11(v2.1): 메뉴얼 초안 생성 응답 (개선된 버전)

    3가지 경로:
    1. SIMILAR: 기존 메뉴얼 반환, draft 미생성
    2. SUPPLEMENT: 초안 생성 + 자동 병합 + 리뷰 태스크 생성
    3. NEW: 초안 생성 + 리뷰 태스크 생성
    """

    comparison_type: ComparisonType = Field(
        description="비교 결과 타입: similar/supplement/new"
    )
    draft_entry: ManualEntryResponse = Field(
        description="생성되거나 기존 메뉴얼 정보"
    )
    existing_manual: ManualEntryResponse | None = Field(
        default=None,
        description="SIMILAR 경로에서만 존재: 기존 메뉴얼 정보",
    )
    review_task_id: UUID | None = Field(
        default=None,
        description="SUPPLEMENT/NEW 경로에서만 존재: 생성된 리뷰 태스크 ID",
    )
    similarity_score: float | None = Field(
        default=None,
        description="SIMILAR/SUPPLEMENT에서 유사도 점수. NEW에서는 null",
    )
    comparison_version: str | None = Field(
        default=None,
        description="초안 비교 로직 버전",
    )
    message: str = Field(
        description="사용자 친화적 메시지"
    )


class ManualApproveRequest(BaseSchema):
    """FR-4: 메뉴얼 승인 요청."""

    approver_id: str
    notes: str | None = Field(default=None, description="승인 메모")


class ManualVersionInfo(BaseSchema):
    """FR-5: 전체 문서 세트 버전 정보."""

    version: str
    approved_at: datetime


class ManualDiffEntrySnapshot(BaseSchema):
    """메뉴얼 항목 스냅샷 (Diff용)."""

    logical_key: str
    keywords: list[str]
    topic: str
    background: str
    guideline: str
    business_type: str | None = None
    error_code: str | None = None


class ManualModifiedEntry(BaseSchema):
    """수정된 메뉴얼 항목 정보."""

    logical_key: str
    before: ManualDiffEntrySnapshot
    after: ManualDiffEntrySnapshot
    changed_fields: list[str]


class ManualVersionDiffResponse(BaseSchema):
    """버전 간 메뉴얼 Diff 결과."""

    base_version: str | None
    compare_version: str
    added_entries: list[ManualDiffEntrySnapshot]
    removed_entries: list[ManualDiffEntrySnapshot]
    modified_entries: list[ManualModifiedEntry]
    llm_summary: str | None = None


class ManualGuidelineItem(BaseSchema):
    """메뉴얼 가이드라인 항목."""

    title: str = Field(description="조치사항 제목")
    description: str = Field(description="조치사항 설명")


class ManualDetailResponse(BaseResponseSchema):
    """
    Manual detail response for specific version

    RFP Reference: GET /api/v1/manuals/{manual_id}/versions/{version}
    """

    manual_id: UUID = Field(description="메뉴얼 ID")
    version: str = Field(description="버전 번호")
    topic: str = Field(description="메뉴얼 주제")
    keywords: list[str] = Field(description="키워드 배열")
    background: str = Field(description="배경 정보")
    guidelines: list[ManualGuidelineItem] = Field(description="조치사항/가이드라인 배열")
    status: ManualStatus = Field(description="메뉴얼 상태 (APPROVED, DEPRECATED)")
    updated_at: datetime = Field(description="업데이트 시간 (ISO 8601)")
