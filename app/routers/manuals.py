"""
Manual API Routes

RFP Reference: Section 10 - API Design
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.exceptions import (
    RecordNotFoundError,
    ValidationError,
    BusinessLogicError,
)
from app.models.manual import ManualStatus
from app.schemas.manual import (
    ManualApproveRequest,
    ManualDraftCreateFromConsultationRequest,
    ManualDraftResponse,
    ManualEntryResponse,
    ManualEntryUpdate,
    ManualSearchParams,
    ManualVersionInfo,
    ManualReviewTaskResponse,
    ManualSearchResult,
    ManualVersionResponse,
    ManualVersionDiffResponse,
    ManualDetailResponse,
)
from app.services.manual_service import ManualService
from app.llm.factory import get_llm_client_instance
from app.vectorstore.factory import get_manual_vectorstore

router = APIRouter(prefix="/manuals", tags=["manuals"])


def get_manual_service(
    session: AsyncSession = Depends(get_session),
) -> ManualService:
    """
    Dependency: Get ManualService instance
    """
    return ManualService(
        session=session,
        llm_client=get_llm_client_instance(),
        vectorstore=get_manual_vectorstore(),
    )


@router.post(
    "/draft",
    response_model=ManualDraftResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual draft from consultation",
)
async def create_manual_draft(
    payload: ManualDraftCreateFromConsultationRequest,
    service: ManualService = Depends(get_manual_service),
) -> ManualDraftResponse:
    """FR-2/FR-9: 상담 기반 메뉴얼 초안 생성 (환각 검증 포함)."""

    return await service.create_draft_from_consultation(payload)


@router.post(
    "/draft/{manual_id}/conflict-check",
    response_model=ManualReviewTaskResponse | None,
    summary="Check conflict and create review task",
)
async def check_conflict(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> ManualReviewTaskResponse | None:
    """FR-6: 신규 초안과 기존 메뉴얼 자동 비교."""

    return await service.check_conflict_and_create_task(manual_id)


@router.post(
    "/approve/{manual_id}",
    response_model=ManualVersionInfo,
    summary="Approve manual and bump version set",
)
async def approve_manual(
    manual_id: UUID,
    payload: ManualApproveRequest,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionInfo:
    """FR-4/FR-5: 메뉴얼 승인 및 전체 버전 세트 관리."""

    return await service.approve_manual(manual_id, payload)


@router.get(
    "/{manual_id}/versions",
    response_model=list[ManualVersionResponse],
    summary="List manual versions",
)
async def list_versions(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> list[ManualVersionResponse]:
    """FR-14: 메뉴얼 그룹의 버전 목록 조회.

    특정 메뉴얼(manual_id)과 같은 business_type/error_code를 가진 메뉴얼 그룹의
    모든 버전을 최신순으로 반환합니다.
    """

    try:
        return await service.list_versions(manual_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{manual_id}/versions/{version}",
    response_model=ManualDetailResponse,
    summary="Get manual detail by version",
)
async def get_manual_by_version(
    manual_id: UUID,
    version: str,
    service: ManualService = Depends(get_manual_service),
) -> ManualDetailResponse:
    """FR-14: 특정 버전의 메뉴얼 상세 조회.

    특정 버전의 메뉴얼 상세 정보를 반환합니다.
    guideline 필드는 문자열에서 배열로 변환되어 반환됩니다.

    응답 필드:
    - manual_id: 메뉴얼 ID
    - version: 버전 번호
    - topic: 메뉴얼 주제
    - keywords: 키워드 배열
    - background: 배경 정보
    - guidelines: 조치사항/가이드라인 배열 (title + description)
    - status: 메뉴얼 상태 (APPROVED, DEPRECATED)
    - updated_at: 업데이트 시간 (ISO 8601)
    """

    try:
        return await service.get_manual_by_version(manual_id, version)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{manual_group_id}/diff",
    response_model=ManualVersionDiffResponse,
    summary="Diff manual versions",
)
async def diff_manual_versions(
    manual_group_id: str,
    base_version: str | None = None,
    compare_version: str | None = None,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionDiffResponse:
    """FR-14: 최신/임의 버전 간 Diff."""

    try:
        return await service.diff_versions(
            manual_group_id,
            base_version=base_version,
            compare_version=compare_version,
            summarize=summarize,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/drafts/{draft_id}/diff-with-active",
    response_model=ManualVersionDiffResponse,
    summary="Diff draft set with active version",
)
async def diff_draft_with_active(
    draft_id: UUID,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionDiffResponse:
    """FR-14: 운영 버전 vs 특정 DRAFT 세트 Diff."""

    try:
        return await service.diff_draft_with_active(
            draft_id,
            summarize=summarize,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (BusinessLogicError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "",
    response_model=list[ManualEntryResponse],
    summary="List manual entries",
)
async def list_manuals(
    status_filter: ManualStatus | None = None,
    limit: int = 100,
    service: ManualService = Depends(get_manual_service),
) -> list[ManualEntryResponse]:
    """
    List manual entries with optional status filter

    RFP Reference: GET /manuals
    TODO: Implement pagination and filtering
    """
    return await service.list_manuals(
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/search",
    response_model=list[ManualSearchResult],
    summary="Search manuals by similarity",
)
async def search_manuals(
    params: ManualSearchParams = Depends(),
    service: ManualService = Depends(get_manual_service),
) -> list[ManualSearchResult]:
    """
    Search manuals using vector similarity

    RFP Reference: GET /manuals/search
    - Vector-based semantic search
    - Filter by status, business_type, error_code
    """
    results = await service.search_manuals(params)
    return results


@router.post(
    "/{manual_id}/review",
    response_model=dict[str, str],
    summary="Create review task for manual",
)
async def create_manual_review(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> dict[str, str]:
    """
    Create review task for manual entry

    RFP Reference: POST /manuals/{id}/review
    - Detects conflicts with existing manuals
    - Creates ManualReviewTask if needed
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Manual review creation not yet implemented",
    )


@router.put(
    "/{manual_id}",
    response_model=ManualEntryResponse,
    summary="Update manual entry",
)
async def update_manual(
    manual_id: UUID,
    payload: ManualEntryUpdate,
    service: ManualService = Depends(get_manual_service),
) -> ManualEntryResponse:
    """DRAFT 상태 메뉴얼 항목 업데이트.

    요청 필드:
    - topic: string (5-200자, 선택사항)
    - keywords: list[string] (1-3개, 선택사항)
    - background: string (최소 10자, 선택사항)
    - guideline: string (줄바꿈으로 구분, 선택사항)
    - status: DRAFT|APPROVED|DEPRECATED (선택사항, APPROVED는 /approve 사용)

    응답 (200 OK):
    메뉴얼 항목의 전체 정보

    제약사항:
    - DRAFT 상태인 메뉴얼만 수정 가능
    - APPROVED 상태로의 변경은 /approve 엔드포인트 사용 필수
    """

    try:
        return await service.update_manual(manual_id, payload)
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{manual_id}",
    response_model=ManualEntryResponse,
    summary="Get manual detail",
)
async def get_manual_detail(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> ManualEntryResponse:
    """메뉴얼 단건 상세 조회."""

    try:
        return await service.get_manual(manual_id)
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
