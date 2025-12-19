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
from app.models.manual import ManualEntry, ManualStatus
from app.models.user import User, UserRole
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
from app.api.swagger_responses import combined_responses
from app.repositories.manual_rdb import ManualEntryRDBRepository
from app.core.dependencies import get_current_user, require_roles

router = APIRouter(
    prefix="/manuals",
    tags=["manuals"],
    dependencies=[Depends(get_current_user)],
)


def _ensure_draft_view_allowed(manual: ManualEntry, current_user: User) -> None:
    if manual.status != ManualStatus.DRAFT:
        return

    if current_user.role == UserRole.ADMIN:
        return

    consultation = manual.source_consultation
    if consultation is None or consultation.employee_id != current_user.employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="초안 메뉴얼은 작성자 또는 관리자만 조회할 수 있습니다.",
        )


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
    responses=combined_responses(
        status_code=201,
        data_example={
            "comparison_type": "supplement",
            "draft_entry": {"id": "uuid-draft", "topic": "로그인 실패"},
            "existing_manual": {"id": "uuid-existing", "topic": "로그인 오류"},
            "similarity_score": 0.82,
            "review_task_id": "uuid-task-123",
        },
        include_errors=[400, 404, 422, 500],
    ),
)
async def create_manual_draft(
    payload: ManualDraftCreateFromConsultationRequest,
    service: ManualService = Depends(get_manual_service),
) -> ManualDraftCreateResponse:
    """
    상담 기반 메뉴얼 초안 생성 + 비교 + 리뷰 태스크

    FR-2, FR-9, FR-11: 메뉴얼 초안 생성 및 비교 분석

    **요청:**
    ```json
    {
      "consultation_id": "uuid-xxx",
      "enforce_hallucination_check": true,
      "compare_with_manual_id": "uuid-yyy"
    }
    ```

    **응답 - 3가지 경로 (201 Created):**

    **1️⃣ SIMILAR (기존 메뉴얼과 매우 유사):**
    ```json
    {
      "success": true,
      "data": {
        "comparison_type": "similar",
        "draft_entry": {
          "id": "uuid-draft-1",
          "business_type": "인터넷뱅킹",
          "error_code": "E001",
          "topic": "로그인 실패",
          "keywords": ["로그인", "인증", "실패"],
          "background": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상",
          "guidelines": [{"title": "조치1", "description": "비밀번호 초기화..."}],
          "status": "DRAFT",
          "version": null,
          "created_at": "2024-12-16T10:35:00Z"
        },
        "existing_manual": {
          "id": "uuid-existing-1",
          "business_type": "인터넷뱅킹",
          "error_code": "E001",
          "topic": "로그인 오류",
          "keywords": ["로그인", "인증"],
          "background": "로그인 인증 실패",
          "guidelines": [{"title": "조치1", "description": "비밀번호 초기화..."}],
          "status": "APPROVED",
          "version": "v1.6",
          "created_at": "2024-12-15T09:00:00Z"
        },
        "similarity_score": 0.97,
        "review_task_id": null,
        "message": "기존 메뉴얼(v1.6)과 99% 유사합니다. 기존 메뉴얼 사용을 권장합니다."
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **2️⃣ SUPPLEMENT (기존 메뉴얼 개선/보충):**
    ```json
    {
      "success": true,
      "data": {
        "comparison_type": "supplement",
        "draft_entry": {...},
        "existing_manual": {...},
        "similarity_score": 0.82,
        "review_task_id": "uuid-task-123",
        "message": "기존 메뉴얼(v1.6)의 내용을 보충했습니다. 검토 태스크가 생성되었습니다."
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **3️⃣ NEW (신규 메뉴얼):**
    ```json
    {
      "success": true,
      "data": {
        "comparison_type": "new",
        "draft_entry": {...},
        "existing_manual": null,
        "similarity_score": null,
        "review_task_id": "uuid-task-456",
        "message": "신규 메뉴얼 초안으로 생성되었습니다. 검토 태스크가 생성되었습니다."
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **에러 응답:**
    - 404 Not Found: 상담/메뉴얼을 찾을 수 없음
    - 400 Bad Request: 비즈니스 로직 오류
    - 422 Unprocessable Entity: 검증 실패
    - 500 Internal Server Error: LLM/VectorStore 오류

    **주요 필드 설명:**
    - comparison_type: "similar"|"supplement"|"new"
      - similar: 기존 메뉴얼과 유사도 95% 이상 (리뷰 태스크 미생성)
      - supplement: 유사도 70~95% (리뷰 태스크 생성, 개선 내용 검토)
      - new: 유사 메뉴얼 없음 (리뷰 태스크 생성, 새 항목 검토)
    - review_task_id: 검토 필요 시 자동 생성 (similar만 null)
    - draft_entry: 생성된 초안 (DRAFT 상태)
    - existing_manual: 기존 버전 (similar/supplement만 포함)

    **프론트엔드 처리:**
    1. comparison_type별로 UI 다르게 표시
    2. SIMILAR: 기존 메뉴얼 사용 권장, 초안 자동 버림
    3. SUPPLEMENT/NEW: 검토 태스크 목록으로 이동, 승인/거절 대기
    """

    return await service.create_draft_from_consultation(payload)


@router.post(
    "/approve/{manual_id}",
    response_model=ManualVersionInfo,
    summary="Approve manual and bump version set",
    responses=combined_responses(
        status_code=200,
        data_example={
            "manual_id": "uuid-manual-1",
            "version": "v1.7",
            "status": "APPROVED",
            "topic": "로그인 실패",
        },
        include_errors=[400, 404, 409, 500],
    ),
)
async def approve_manual(
    manual_id: UUID,
    payload: ManualApproveRequest,
    service: ManualService = Depends(get_manual_service),
    current_user: User = Depends(
        require_roles(UserRole.REVIEWER, UserRole.ADMIN),
    ),
) -> ManualVersionInfo:
    """
    메뉴얼 초안 승인 및 버전 관리

    FR-4, FR-5: 메뉴얼 검토 완료 및 버전 업그레이드

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)

    **요청:**
    ```json
    {
      "reviewer_notes": "검토 의견: 내용이 정확합니다",
      "create_version": true
    }
    ```

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "manual_id": "uuid-manual-1",
        "version": "v1.7",
        "status": "APPROVED",
        "topic": "로그인 실패",
        "keywords": ["로그인", "인증", "실패"],
        "background": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상",
        "guidelines": [{"title": "조치1", "description": "비밀번호 초기화..."}],
        "business_type": "인터넷뱅킹",
        "error_code": "E001",
        "created_at": "2024-12-16T10:35:00Z",
        "updated_at": "2024-12-16T11:00:00Z"
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **에러 응답:**
    - 404 Not Found: 메뉴얼을 찾을 수 없음
    - 400 Bad Request: 비즈니스 로직 오류 (DRAFT 아님, 이미 승인됨 등)
    - 409 Conflict: 재검토 필요 (NeedsReReviewError)

    **동작:**
    1. DRAFT 상태 메뉴얼만 승인 가능
    2. 메뉴얼 상태를 APPROVED로 변경
    3. 버전 번호 자동 상향 (v1.6 → v1.7)
    4. 기존 APPROVED 메뉴얼은 DEPRECATED로 변경
    5. 벡터스토어 인덱스 업데이트

    **reviewer_notes:**
    - 검토자의 의견/피드백
    - 거절 시 이유 기입 필수
    """

    sanitized_payload = payload.model_copy(
        update={"approver_id": current_user.employee_id}
    )

    try:
        return await service.approve_manual(manual_id, sanitized_payload)
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
    responses=combined_responses(
        status_code=200,
        data_example=[
            {"value": "v1.6", "label": "v1.6 (현재 버전)", "status": "APPROVED"}
        ],
        include_errors=[404, 500],
    ),
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
    메뉴얼 버전 목록 조회 (업무 구분 + 에러 코드별)

    FR-11: 메뉴얼 버전 관리

    **쿼리 파라미터:**
    - business_type: 업무 구분 (필수, 예: "인터넷뱅킹")
    - error_code: 에러 코드 (필수, 예: "E001")
    - include_deprecated: DEPRECATED 버전 포함 여부 (기본값: false)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": [
        {
          "value": "v1.5",
          "label": "v1.5 (구 버전)",
          "date": "2024-12-01",
          "status": "DEPRECATED",
          "manual_id": "uuid-xxx"
        },
        {
          "value": "v1.6",
          "label": "v1.6 (현재 운영 버전)",
          "date": "2024-12-05",
          "status": "APPROVED",
          "manual_id": "uuid-yyy"
        }
      ],
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **용도:**
    - 초안 작성 전: UI의 드롭다운에서 과거 버전 선택 가능
    - 특정 버전과 비교하고 싶을 때 선택
    - 버전 히스토리 확인

    **응답 정렬:**
    - 최신순 (v1.6 → v1.5)

    **에러 응답:**
    - 404 Not Found: 해당 조건의 메뉴얼 없음
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
    responses=combined_responses(
        status_code=200,
        data_example=[{"value": "v1.6", "label": "v1.6 (현재 버전)"}],
        include_errors=[404, 500],
    ),
)
async def list_versions(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> list[ManualVersionResponse]:
    """
    특정 메뉴얼의 버전 목록 조회

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": [
        {
          "value": "v1.6",
          "label": "v1.6 (현재 버전)",
          "date": "2024-12-05",
          "status": "APPROVED",
          "manual_id": "uuid-yyy"
        },
        {
          "value": "v1.5",
          "label": "v1.5 (구 버전)",
          "date": "2024-12-01",
          "status": "DEPRECATED",
          "manual_id": "uuid-xxx"
        }
      ],
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **동작:**
    - 지정된 메뉴얼과 같은 business_type/error_code를 가진 그룹의 모든 버전 반환
    - 최신순 정렬 (v1.6 → v1.5)

    **에러 응답:**
    - 404 Not Found: 메뉴얼을 찾을 수 없음
    """

    try:
        return await service.list_versions(manual_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{manual_id}/versions/{version}",
    response_model=ManualDetailResponse,
    summary="Get manual detail by version",
    responses=combined_responses(
        status_code=200,
        data_example={
            "manual_id": "uuid-xxx",
            "version": "v1.6",
            "topic": "로그인 실패",
            "guidelines": [{"title": "비밀번호 초기화"}],
        },
        include_errors=[404, 500],
    ),
)
async def get_manual_by_version(
    manual_id: UUID,
    version: str,
    service: ManualService = Depends(get_manual_service),
) -> ManualDetailResponse:
    """
    특정 버전의 메뉴얼 상세 조회

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)
    - version: 버전 (예: "v1.6", "DRAFT")

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "manual_id": "uuid-xxx",
        "version": "v1.6",
        "topic": "로그인 실패",
        "keywords": ["로그인", "인증", "실패"],
        "background": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상",
        "guidelines": [
          {
            "title": "비밀번호 초기화",
            "description": "사용자의 비밀번호를 임시 비밀번호로 초기화합니다"
          },
          {
            "title": "계정 확인",
            "description": "계정이 잠금 상태인지 확인합니다"
          }
        ],
        "status": "APPROVED",
        "business_type": "인터넷뱅킹",
        "error_code": "E001",
        "updated_at": "2024-12-05T10:00:00Z"
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **주요 필드:**
    - guidelines: 배열로 변환 (각 항목은 {title, description})
    - status: APPROVED, DEPRECATED, DRAFT
    - version: 버전 번호 (v1.6, DRAFT 등)

    **에러 응답:**
    - 404 Not Found: 메뉴얼 또는 버전을 찾을 수 없음
    """

    try:
        return await service.get_manual_by_version(manual_id, version)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/{manual_id}/diff",
    response_model=ManualVersionDiffResponse,
    summary="Diff manual versions in the same group",
    responses=combined_responses(
        status_code=200,
        data_example={
            "manual_id": "uuid-xxx",
            "base_version": "v1.5",
            "compare_version": "v1.6",
            "differences": {"added_entries": [], "modified_entries": []},
        },
        include_errors=[400, 404, 500],
    ),
)
async def diff_manual_versions(
    manual_id: UUID,
    base_version: str | None = None,
    compare_version: str | None = None,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
) -> ManualVersionDiffResponse:
    """
    메뉴얼 버전 간 차이 비교

    FR-14: 메뉴얼 버전 비교

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)

    **쿼리 파라미터:**
    - base_version: 비교 기준 버전 (예: "v1.5")
    - compare_version: 비교 대상 버전 (예: "v1.6")
    - summarize: 변경사항 요약 여부 (기본값: false)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "manual_id": "uuid-xxx",
        "base_version": "v1.5",
        "compare_version": "v1.6",
        "differences": {
          "added_entries": [
            {
              "field": "guidelines[2]",
              "value": {
                "title": "계정 확인",
                "description": "계정이 잠금 상태인지 확인합니다"
              }
            }
          ],
          "modified_entries": [
            {
              "field": "background",
              "old_value": "로그인 인증 실패",
              "new_value": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상"
            }
          ],
          "removed_entries": []
        },
        "summary": "배경 정보 수정, 가이드라인 1개 추가"
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **에러 응답:**
    - 404 Not Found: 메뉴얼 또는 버전을 찾을 수 없음
    - 400 Bad Request: 유효하지 않은 버전
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
    responses=combined_responses(
        status_code=200,
        data_example={
            "manual_id": "uuid-xxx",
            "base_version": "v1.6",
            "compare_version": "DRAFT",
            "differences": {"added_entries": []},
        },
        include_errors=[400, 404, 500],
    ),
)
async def diff_draft_with_active(
    draft_id: UUID,
    summarize: bool = False,
    service: ManualService = Depends(get_manual_service),
    current_user: User = Depends(get_current_user),
) -> ManualVersionDiffResponse:
    """
    초안 vs 운영 버전 비교

    FR-14: 메뉴얼 초안 검토 전 변화 미리보기

    **경로 파라미터:**
    - draft_id: 초안 메뉴얼 ID (UUID)

    **쿼리 파라미터:**
    - summarize: 변경사항 요약 여부 (기본값: false)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "manual_id": "uuid-xxx",
        "base_version": "v1.6",
        "compare_version": "DRAFT",
        "differences": {
          "added_entries": [...],
          "modified_entries": [...],
          "removed_entries": []
        },
        "summary": "배경 정보 수정, 가이드라인 1개 추가"
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **용도:**
    - 검토자가 초안 승인 전 변화 확인
    - 현재 운영 버전과의 차이 시각화

    **에러 응답:**
    - 404 Not Found: 초안을 찾을 수 없음
    - 400 Bad Request: 초안이 DRAFT 상태가 아님
    """

    repo = ManualEntryRDBRepository(service.session)
    manual_entry = await repo.get_by_id(draft_id)
    if manual_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ManualEntry(id={draft_id}) not found",
        )

    _ensure_draft_view_allowed(manual_entry, current_user)

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
    responses=combined_responses(
        status_code=200,
        data_example=[{"id": "uuid-1", "topic": "로그인 실패", "status": "APPROVED"}],
        include_errors=[500],
    ),
)
async def list_manuals(
    status_filter: ManualStatus | None = None,
    limit: int = 100,
    service: ManualService = Depends(get_manual_service),
    current_user: User = Depends(get_current_user),
) -> list[ManualEntryResponse]:
    """
    메뉴얼 목록 조회

    **쿼리 파라미터:**
    - status_filter: 상태 필터 (DRAFT, APPROVED, DEPRECATED, 선택사항)
    - limit: 반환 개수 제한 (기본값: 100)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": [
        {
          "id": "uuid-1",
          "business_type": "인터넷뱅킹",
          "error_code": "E001",
          "topic": "로그인 실패",
          "keywords": ["로그인", "인증", "실패"],
          "background": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상",
          "guidelines": [{"title": "비밀번호 초기화", "description": "..."}],
          "status": "APPROVED",
          "version": "v1.6",
          "created_at": "2024-12-16T10:35:00Z"
        }
      ],
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **프론트엔드 필터링:**
    - status_filter=DRAFT: DRAFT 상태만 (초안)
    - status_filter=APPROVED: APPROVED 상태만 (운영)
    - status_filter=DEPRECATED: DEPRECATED 상태만 (구 버전)
    - 미지정: 전체 메뉴얼 조회

    TODO: 페이지네이션 추가 예정
    """
    employee_filter = None
    if status_filter == ManualStatus.DRAFT and current_user.role != UserRole.ADMIN:
        employee_filter = current_user.employee_id

    return await service.list_manuals(
        status=status_filter,
        limit=limit,
        employee_id=employee_filter,
    )


@router.get(
    "/search",
    response_model=list[ManualSearchResult],
    summary="Search manuals by similarity",
    responses=combined_responses(
        status_code=200,
        data_example=[{"id": "uuid-1", "topic": "로그인 실패", "similarity_score": 0.92}],
        include_errors=[400, 500],
    ),
)
async def search_manuals(
    params: ManualSearchParams = Depends(),
    service: ManualService = Depends(get_manual_service),
) -> list[ManualSearchResult]:
    """
    메뉴얼 검색 (벡터 유사도 기반)

    FR-8: 메뉴얼 검색 기능

    **쿼리 파라미터:**
    - query: 검색어 (필수, 예: "로그인 오류")
    - top_k: 상위 결과 개수 (기본값: 10)
    - status: 상태 필터 (APPROVED, DRAFT, DEPRECATED, 선택사항)
    - business_type: 업무 구분 필터 (선택사항)
    - error_code: 에러 코드 필터 (선택사항)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": [
        {
          "id": "uuid-1",
          "business_type": "인터넷뱅킹",
          "error_code": "E001",
          "topic": "로그인 실패",
          "keywords": ["로그인", "인증", "실패"],
          "background": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상",
          "guidelines": [{"title": "비밀번호 초기화", "description": "..."}],
          "status": "APPROVED",
          "version": "v1.6",
          "similarity_score": 0.92
        }
      ],
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **동작:**
    1. 쿼리를 벡터화하여 VectorStore에서 semantic search
    2. 상위 top_k개 결과 반환
    3. 메타데이터 필터 (status, business_type, error_code) 적용
    4. 유사도 임계값(threshold) 이상의 결과만 필터링
    5. 유사도 점수(0-1) 포함하여 반환

    **프론트엔드 필터:**
    - status=APPROVED: 운영 중인 메뉴얼만
    - status=DRAFT: 검토 중인 초안만
    - 미지정: 전체 조회

    **예시:**
    ```
    GET /manuals/search?query=로그인&top_k=5&status=APPROVED
    ```
    """
    results = await service.search_manuals(params)
    return results


@router.put(
    "/{manual_id}",
    response_model=ManualEntryResponse,
    summary="Update manual entry",
    responses=combined_responses(
        status_code=200,
        data_example={"id": "uuid-xxx", "topic": "로그인 오류 해결 방법", "status": "DRAFT"},
        include_errors=[400, 404, 500],
    ),
)
async def update_manual(
    manual_id: UUID,
    payload: ManualEntryUpdate,
    service: ManualService = Depends(get_manual_service),
) -> ManualEntryResponse:
    """
    메뉴얼 초안 수정

    FR-4: 메뉴얼 초안 편집

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)

    **요청:**
    ```json
    {
      "topic": "로그인 오류 해결 방법",
      "keywords": ["로그인", "인증", "실패"],
      "background": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상",
      "guideline": "비밀번호 초기화\n\n계정 확인"
    }
    ```

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "id": "uuid-xxx",
        "business_type": "인터넷뱅킹",
        "error_code": "E001",
        "topic": "로그인 오류 해결 방법",
        "keywords": ["로그인", "인증", "실패"],
        "background": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상",
        "guidelines": [{"title": "비밀번호 초기화", "description": "..."}],
        "status": "DRAFT",
        "version": null,
        "created_at": "2024-12-16T10:35:00Z"
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **요청 필드:**
    - topic: 메뉴얼 제목 (5-200자, 선택사항)
    - keywords: 검색 키워드 배열 (1-3개, 선택사항)
    - background: 배경 정보 (최소 10자, 선택사항)
    - guideline: 조치사항 (줄바꿈으로 구분, 선택사항)

    **제약사항:**
    - DRAFT 상태인 메뉴얼만 수정 가능
    - APPROVED 상태로의 변경은 /approve 엔드포인트 사용
    - 검토 중(IN_PROGRESS) 상태에서는 수정 불가

    **에러 응답:**
    - 404 Not Found: 메뉴얼을 찾을 수 없음
    - 400 Bad Request: DRAFT 상태가 아님, 검증 실패
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
    "/{manual_id}/approved-group",
    response_model=list[ManualEntryResponse],
    summary="Get approved manuals sharing business_type and error_code",
    responses=combined_responses(
        status_code=200,
        data_example=[{"id": "uuid-1", "topic": "로그인 실패", "status": "APPROVED"}],
        include_errors=[400, 404, 500],
    ),
)
async def get_approved_group_manuals(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> list[ManualEntryResponse]:
    """
    동일 그룹의 APPROVED 메뉴얼 목록 조회

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": [
        {
          "id": "uuid-1",
          "business_type": "인터넷뱅킹",
          "error_code": "E001",
          "topic": "로그인 실패",
          "status": "APPROVED",
          "version": "v1.6",
          "created_at": "2024-12-05T10:00:00Z"
        }
      ],
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **동작:**
    - 지정된 메뉴얼과 같은 business_type + error_code를 가진 APPROVED 메뉴얼만 반환
    - 운영 중인 버전 목록 (과거 DEPRECATED 버전 제외)

    **에러 응답:**
    - 404 Not Found: 메뉴얼을 찾을 수 없음
    - 400 Bad Request: 그룹 정보 오류
    """

    try:
        return await service.get_approved_group_by_manual_id(manual_id)
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
    "/{manual_id}",
    response_model=ManualEntryResponse,
    summary="Get manual detail",
    responses=combined_responses(
        status_code=200,
        data_example={"id": "uuid-xxx", "topic": "로그인 실패", "status": "APPROVED"},
        include_errors=[404, 500],
    ),
)
async def get_manual_detail(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
    current_user: User = Depends(get_current_user),
) -> ManualEntryResponse:
    """
    메뉴얼 상세 조회

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "id": "uuid-xxx",
        "business_type": "인터넷뱅킹",
        "error_code": "E001",
        "topic": "로그인 실패",
        "keywords": ["로그인", "인증", "실패"],
        "background": "고객이 올바른 자격증명으로 로그인 시도 시 실패하는 현상",
        "guidelines": [{"title": "비밀번호 초기화", "description": "..."}],
        "status": "APPROVED",
        "version": "v1.6",
        "created_at": "2024-12-05T10:00:00Z"
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **에러 응답:**
    - 404 Not Found: 메뉴얼을 찾을 수 없음
    """

    repo = ManualEntryRDBRepository(service.session)
    manual_entry = await repo.get_by_id(manual_id)
    if manual_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ManualEntry(id={manual_id}) not found",
        )

    _ensure_draft_view_allowed(manual_entry, current_user)

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
    responses=combined_responses(
        status_code=204,
        include_errors=[400, 404, 500],
    ),
)
async def delete_manual(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> None:
    """
    메뉴얼 초안 삭제

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)

    **요청:**
    ```
    DELETE /manuals/{manual_id}
    ```

    **응답:**
    - 204 No Content: 삭제 성공 (응답 본문 없음)

    **에러 응답:**
    - 404 Not Found: 메뉴얼을 찾을 수 없음
    - 400 Bad Request: DRAFT 상태가 아님

    **제약사항:**
    - DRAFT 상태인 메뉴얼만 삭제 가능
    - APPROVED/DEPRECATED 상태는 삭제 불가
    - 삭제 시 다음도 함께 삭제:
      - 벡터스토어 인덱스
      - 관련 리뷰 태스크

    **프론트엔드 처리:**
    - 204 응답 시: 목록에서 해당 항목 제거
    - 400 응답 시: "DRAFT 상태 초안만 삭제 가능합니다" 메시지 표시
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
    responses=combined_responses(
        status_code=200,
        data_example=[
            {
                "id": "uuid-task-1",
                "status": "TODO",
                "comparison_type": "supplement",
                "similarity": 0.82,
            }
        ],
        include_errors=[404, 500],
    ),
)
async def get_manual_review_tasks(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> list[ManualReviewTaskResponse]:
    """
    메뉴얼의 검토 태스크 목록 조회

    FR-6: 메뉴얼 검토 태스크 조회

    **경로 파라미터:**
    - manual_id: 메뉴얼 ID (UUID)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": [
        {
          "id": "uuid-task-1",
          "new_entry_id": "uuid-manual-draft",
          "old_entry_id": "uuid-manual-existing",
          "similarity": 0.82,
          "comparison_type": "supplement",
          "status": "TODO",
          "reviewer_id": null,
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
          "old_manual_keywords": ["로그인"],
          "created_at": "2024-12-10T12:00:00Z",
          "updated_at": "2024-12-10T12:00:00Z"
        }
      ],
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **주요 필드 설명:**
    - new_entry_id: 신규 상담 기반 초안 ID
    - old_entry_id: 기존 메뉴얼 ID (신규인 경우 null)
    - similarity: 유사도 점수 (0-1, new인 경우 null)
    - comparison_type: "similar"|"supplement"|"new"
      - similar: 기존과 99% 이상 유사 (자동 승인 가능)
      - supplement: 기존 개선 버전 (검토 필요)
      - new: 신규 메뉴얼 (검토 필요)
    - status: "TODO"|"IN_PROGRESS"|"DONE"|"REJECTED"
      - TODO: 미처리
      - IN_PROGRESS: 검토 중
      - DONE: 승인됨
      - REJECTED: 거절됨

    **에러 응답:**
    - 404 Not Found: 메뉴얼을 찾을 수 없음

    **프론트엔드 처리:**
    - status=TODO인 항목: "검토 대기중" 표시
    - status=IN_PROGRESS인 항목: "검토 중" 표시
    - status=DONE인 항목: "승인됨" 표시
    - status=REJECTED인 항목: "거절됨" 표시
    """

    try:
        return await service.get_review_tasks_by_manual_id(manual_id)
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
