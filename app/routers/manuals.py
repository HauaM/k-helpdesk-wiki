"""
Manual API Routes

RFP Reference: Section 10 - API Design
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.exceptions import (
    RecordNotFoundError,
    ValidationError,
    BusinessLogicError,
    NeedsReReviewError,
)
from app.models.manual import ManualStatus
from app.schemas.manual import (
    ManualApproveRequest,
    ManualDraftCreateFromConsultationRequest,
    ManualDraftCreateResponse,
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
from app.repositories.common_code_rdb import CommonCodeItemRepository
from app.llm.factory import get_llm_client_instance
from app.vectorstore.factory import get_manual_vectorstore

router = APIRouter(prefix="/manuals", tags=["manuals"])


def get_manual_service(
    session: AsyncSession = Depends(get_session),
) -> ManualService:
    """
    Dependency: Get ManualService instance
    """
    common_code_item_repo = CommonCodeItemRepository(session)
    return ManualService(
        session=session,
        llm_client=get_llm_client_instance(),
        vectorstore=get_manual_vectorstore(),
        common_code_item_repo=common_code_item_repo,
    )


@router.post(
    "/draft",
    response_model=ManualDraftCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual draft from consultation (v2.1 with comparison)",
)
async def create_manual_draft(
    payload: ManualDraftCreateFromConsultationRequest,
    service: ManualService = Depends(get_manual_service),
) -> ManualDraftCreateResponse:
    """
    FR-2/FR-9/FR-11(v2.1): 상담 기반 메뉴얼 초안 생성 + 비교 + 리뷰 태스크

    **Request:**
    ```json
    {
      "consultation_id": "uuid-xxx",
      "enforce_hallucination_check": true,
      "compare_with_manual_id": "uuid-yyy"  // Optional: 특정 버전과 비교
    }
    ```

    **Response (3 가지 경로):**

    1. SIMILAR (기존 메뉴얼과 유사):
    ```json
    {
      "comparison_type": "similar",
      "draft_entry": {...},
      "existing_manual": {...},
      "similarity_score": 0.97,
      "message": "기존 메뉴얼과 매우 유사합니다..."
    }
    ```

    2. SUPPLEMENT (기존 메뉴얼 보충):
    ```json
    {
      "comparison_type": "supplement",
      "draft_entry": {...},
      "existing_manual": {...},
      "review_task_id": "uuid-task",
      "similarity_score": 0.82,
      "message": "기존 메뉴얼의 내용을 보충했습니다..."
    }
    ```

    3. NEW (신규 메뉴얼):
    ```json
    {
      "comparison_type": "new",
      "draft_entry": {...},
      "existing_manual": null,
      "review_task_id": "uuid-task",
      "similarity_score": null,
      "message": "신규 메뉴얼 초안으로 생성되었습니다."
    }
    ```

    - `comparison_view` 필드는 좌측(기존) / 우측(신규) 비교 컨텍스트 및 `comparison_version`을 제공합니다 (SIMILAR/SUPPLEMENT).
    """

    return await service.create_draft_from_consultation(payload)


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

    try:
        return await service.approve_manual(manual_id, payload)
    except NeedsReReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except BusinessLogicError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/versions",
    response_model=list[ManualVersionResponse],
    summary="Get manual versions by business type and error code",
)
async def get_versions_by_group(
    business_type: str = Query(..., description="업무 구분 (예: 인터넷뱅킹)"),
    error_code: str = Query(..., description="에러 코드 (예: E001)"),
    include_deprecated: bool = Query(
        default=False,
        description="DEPRECATED 버전 포함 여부",
    ),
    service: ManualService = Depends(get_manual_service),
) -> list[ManualVersionResponse]:
    """
    FR-11(v2.1): business_type + error_code로 메뉴얼 그룹의 버전 목록 조회

    **용도:**
    - 초안 작성 전: UI에서 과거 버전 목록 표시
    - 사용자가 특정 버전과 비교하고 싶을 때 선택

    **Query Parameters:**
    - business_type: 업무 구분 (필수)
    - error_code: 에러 코드 (필수)
    - include_deprecated: DEPRECATED 버전도 반환할지 여부 (optional)

    **Returns:**
    ```json
    [
      {
        "value": "v1.5",
        "label": "v1.5 (DEPRECATED)",
        "date": "2024-12-01",
        "status": "DEPRECATED",
        "manual_id": "uuid-xxx"
      },
      {
        "value": "v1.6",
        "label": "v1.6 (현재 버전)",
        "date": "2024-12-05",
        "status": "APPROVED",
        "manual_id": "uuid-yyy"
      }
    ]
    ```
    """
    try:
        return await service.get_manual_versions_by_group(
            business_type=business_type,
            error_code=error_code,
            include_deprecated=include_deprecated,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


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
    "/{manual_id}/diff",
    response_model=ManualVersionDiffResponse,
    summary="Diff manual versions in the same group",
)
async def diff_manual_versions(
    manual_id: UUID,
    base_version: str | None = None,
    compare_version: str | None = None,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionDiffResponse:
    """
    FR-14: 같은 그룹의 메뉴얼 버전 간 Diff
    """

    try:
        return await service.diff_versions(
            manual_id,
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



@router.delete(
    "/{manual_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete manual draft",
)
async def delete_manual(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> None:
    """
    DRAFT 상태 메뉴얼 항목 삭제.

    **요청:**
    - DELETE /manuals/{manual_id}

    **응답:**
    - 204 No Content: 삭제 성공
    - 404 Not Found: 메뉴얼을 찾을 수 없음
    - 400 Bad Request: DRAFT 상태가 아님

    **제약사항:**
    - DRAFT 상태인 메뉴얼만 삭제 가능
    - 벡터스토어에서도 삭제됨
    - 관련 리뷰 태스크도 함께 삭제됨
    """

    try:
        await service.delete_manual(manual_id)
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
    "/{manual_id}/review-tasks",
    response_model=list[ManualReviewTaskResponse],
    summary="Get review tasks for a manual",
)
async def get_manual_review_tasks(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> list[ManualReviewTaskResponse]:
    """
    메뉴얼에 해당하는 검토 로직 정보 조회

    프론트엔드에서 메뉴얼 상세 페이지에서 해당 메뉴얼의 검토 태스크 정보를 불러올 때 사용.

    **요청:**
    - GET /manuals/{manual_id}/review-tasks

    **응답 (200 OK):**
    ```json
    [
      {
        "id": "uuid-task-1",
        "new_entry_id": "uuid-manual-draft",
        "old_entry_id": "uuid-manual-existing",
        "similarity": 0.82,
        "comparison_type": "supplement",
        "status": "TODO",
        "reviewer_id": "reviewer-001",
        "review_notes": null,
        "new_manual_summary": "신규 메뉴얼 요약",
        "old_manual_summary": "기존 메뉴얼 요약",
        "business_type": "INTERNET_BANKING",
        "business_type_name": "인터넷뱅킹",
        "new_error_code": "E001",
        "new_manual_topic": "로그인 실패",
        "new_manual_keywords": ["로그인", "실패"],
        "old_business_type": "INTERNET_BANKING",
        "old_business_type_name": "인터넷뱅킹",
        "old_error_code": "E001",
        "old_manual_topic": "로그인 오류",
        "created_at": "2024-12-10T12:00:00Z",
        "updated_at": "2024-12-10T12:00:00Z"
      }
    ]
    ```

    **에러 응답:**
    - 404 Not Found: 메뉴얼을 찾을 수 없음

    **주요 필드:**
    - new_entry_id: 신규 상담 기반 초안 (검색 대상)
    - old_entry_id: 기존 메뉴얼 (없으면 신규 생성)
    - similarity: 기존/신규 유사도 점수 (0-1)
    - comparison_type: similar/supplement/new (비교 타입)
    - status: TODO/IN_PROGRESS/DONE/REJECTED (검토 상태)
    """

    try:
        return await service.get_review_tasks_by_manual_id(manual_id)
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
