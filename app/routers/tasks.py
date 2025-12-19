"""
Manual Review Task API Routes

RFP Reference: Section 10 - API Design
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.manual import (
    ManualReviewTaskResponse,
    ManualReviewApproval,
    ManualReviewRejection,
)
from app.services.manual_service import ManualService
from app.services.task_service import TaskService
from app.repositories.common_code_rdb import CommonCodeItemRepository
from app.vectorstore.factory import get_manual_vectorstore
from app.llm.factory import get_llm_client_instance
from app.api.swagger_responses import combined_responses
from app.core.dependencies import get_current_user, require_roles
from app.models.user import User, UserRole

router = APIRouter(
    prefix="/manual-review",
    tags=["tasks"],
    dependencies=[Depends(get_current_user)],
)


def get_task_service(
    session: AsyncSession = Depends(get_session),
) -> TaskService:
    manual_service = ManualService(
        session=session,
        vectorstore=get_manual_vectorstore(),
        llm_client=get_llm_client_instance(),
    )
    common_code_item_repo = CommonCodeItemRepository(session)
    return TaskService(
        session=session,
        manual_service=manual_service,
        common_code_item_repo=common_code_item_repo,
    )


@router.get(
    "/tasks",
    response_model=list[ManualReviewTaskResponse],
    summary="List manual review tasks",
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
        include_errors=[500],
    ),
)
async def list_review_tasks(
    status: str | None = None,
    limit: int = 100,
    service: TaskService = Depends(get_task_service),
    _current_user: User = Depends(
        require_roles(UserRole.REVIEWER, UserRole.ADMIN),
    ),
) -> list[ManualReviewTaskResponse]:
    """
    메뉴얼 검토 태스크 목록 조회

    FR-6: 메뉴얼 검토 태스크 관리

    **쿼리 파라미터:**
    - status: 상태 필터 (TODO, IN_PROGRESS, DONE, REJECTED, 선택사항)
    - limit: 반환 개수 제한 (기본값: 100)

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

    **상태별 필터링:**
    - status=TODO: 미처리 (검토 대기)
    - status=IN_PROGRESS: 검토 중
    - status=DONE: 승인됨
    - status=REJECTED: 거절됨
    - 미지정: 전체 태스크 조회

    **검토자 워크플로우:**
    1. 목록에서 status=TODO인 항목 조회
    2. /manual-review/tasks/{task_id} (PUT)로 검토 시작 (상태→IN_PROGRESS)
    3. /manual-review/tasks/{task_id}/approve (POST)로 승인 또는
       /manual-review/tasks/{task_id}/reject (POST)로 거절

    TODO: 페이지네이션, 정렬 옵션 추가 예정
    """
    return await service.list_review_tasks(status=status, limit=limit)


@router.post(
    "/tasks/{task_id}/approve",
    response_model=ManualReviewTaskResponse,
    summary="Approve manual review task",
    responses=combined_responses(
        status_code=200,
        data_example={
            "id": "uuid-task-1",
            "status": "DONE",
            "review_notes": "내용이 정확합니다",
        },
        include_errors=[400, 404, 409, 500],
    ),
)
async def approve_review_task(
    task_id: UUID,
    data: ManualReviewApproval,
    service: TaskService = Depends(get_task_service),
    current_user: User = Depends(
        require_roles(UserRole.REVIEWER, UserRole.ADMIN),
    ),
) -> ManualReviewTaskResponse:
    """
    메뉴얼 검토 태스크 승인

    FR-7: 메뉴얼 검토 완료 및 승인

    **경로 파라미터:**
    - task_id: 태스크 ID (UUID)

    **요청:**
    ```json
    {
      "reviewer_notes": "내용이 정확하고 구체적입니다. 승인합니다.",
      "approved": true
    }
    ```

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "id": "uuid-task-1",
        "status": "DONE",
        "reviewer_id": "reviewer-001",
        "review_notes": "내용이 정확하고 구체적입니다. 승인합니다.",
        "comparison_type": "supplement",
        "new_entry_id": "uuid-manual-draft",
        "old_entry_id": "uuid-manual-existing",
        ...
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **동작:**
    1. 태스크 상태를 DONE으로 변경
    2. 신규 메뉴얼을 APPROVED로 변경
    3. 기존 메뉴얼(old_entry_id)이 있으면 DEPRECATED로 변경
    4. 새 버전 번호 생성 (v1.6 → v1.7)
    5. 벡터스토어 인덱스 업데이트

    **reviewer_notes:**
    - 검토자의 피드백 (선택사항)
    - 승인 사유 또는 주요 수정 내용 기입

    **에러 응답:**
    - 404 Not Found: 태스크를 찾을 수 없음
    - 400 Bad Request: 태스크가 검토 중(IN_PROGRESS) 상태가 아님
    - 409 Conflict: 재검토 필요 (비즈니스 로직 오류)
    """
    sanitized_payload = data.model_copy(
        update={"employee_id": current_user.employee_id}
    )
    return await service.approve_task(task_id, sanitized_payload)


@router.post(
    "/tasks/{task_id}/reject",
    response_model=ManualReviewTaskResponse,
    summary="Reject manual review task",
    responses=combined_responses(
        status_code=200,
        data_example={
            "id": "uuid-task-1",
            "status": "REJECTED",
            "review_notes": "배경 정보가 부족합니다",
        },
        include_errors=[400, 404, 500],
    ),
)
async def reject_review_task(
    task_id: UUID,
    data: ManualReviewRejection,
    service: TaskService = Depends(get_task_service),
    _current_user: User = Depends(
        require_roles(UserRole.REVIEWER, UserRole.ADMIN),
    ),
) -> ManualReviewTaskResponse:
    """
    메뉴얼 검토 태스크 거절

    FR-7: 메뉴얼 검토 거절 및 재작성 요청

    **경로 파라미터:**
    - task_id: 태스크 ID (UUID)

    **요청:**
    ```json
    {
      "reason": "배경 정보가 부족합니다. 더 자세한 설명을 추가해주세요.",
      "rejected": true
    }
    ```

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "id": "uuid-task-1",
        "status": "REJECTED",
        "reviewer_id": "reviewer-001",
        "review_notes": "배경 정보가 부족합니다. 더 자세한 설명을 추가해주세요.",
        "comparison_type": "supplement",
        "new_entry_id": "uuid-manual-draft",
        ...
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **동작:**
    1. 태스크 상태를 REJECTED로 변경
    2. 거절 사유 저장
    3. 신규 메뉴얼(초안)은 DRAFT 상태로 유지
    4. 검토자는 재작성 사유 확인 후 초안 수정 가능

    **reason:**
    - 거절 사유 (필수)
    - 재작성 필요한 부분 상세 설명
    - 예: "배경 정보가 부족합니다", "조치사항이 명확하지 않습니다"

    **재검토 흐름:**
    1. 작성자가 초안 수정 (PUT /manuals/{manual_id})
    2. 새로운 검토 태스크 생성 (POST /manuals/draft)
    3. 검토자가 재검토 (승인 또는 재거절)

    **에러 응답:**
    - 404 Not Found: 태스크를 찾을 수 없음
    - 400 Bad Request: 태스크가 검토 중(IN_PROGRESS) 상태가 아님
    """
    return await service.reject_task(task_id, data)


@router.put(
    "/tasks/{task_id}",
    response_model=ManualReviewTaskResponse,
    summary="Start manual review task",
    responses=combined_responses(
        status_code=200,
        data_example={
            "id": "uuid-task-1",
            "status": "IN_PROGRESS",
            "reviewer_id": "reviewer-001",
        },
        include_errors=[400, 404, 500],
    ),
)
async def start_review_task(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
    _current_user: User = Depends(
        require_roles(UserRole.REVIEWER, UserRole.ADMIN),
    ),
) -> ManualReviewTaskResponse:
    """
    메뉴얼 검토 태스크 시작

    FR-6: 검토 태스크 상태 변경 (TODO → IN_PROGRESS)

    **경로 파라미터:**
    - task_id: 태스크 ID (UUID)

    **요청:**
    ```
    PUT /manual-review/tasks/{task_id}
    ```

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "id": "uuid-task-1",
        "status": "IN_PROGRESS",
        "reviewer_id": "reviewer-001",
        "review_notes": null,
        "comparison_type": "supplement",
        "new_entry_id": "uuid-manual-draft",
        "old_entry_id": "uuid-manual-existing",
        ...
      },
      "error": null,
      "meta": {...},
      "feedback": []
    }
    ```

    **동작:**
    1. 태스크 상태를 TODO → IN_PROGRESS로 변경
    2. 검토자 ID 자동 할당 (현재 사용자)
    3. 초안 메뉴얼 상태를 DRAFT → IN_PROGRESS로 변경
    4. 다른 사용자가 같은 초안을 수정하지 못하도록 보호

    **용도:**
    - 검토자가 태스크 클릭 후 검토 시작할 때
    - 동시 검토 방지 (한 명만 IN_PROGRESS 가능)
    - 미완성 초안이 노출되지 않도록 보호

    **제약사항:**
    - TODO 상태인 태스크만 시작 가능
    - 이미 IN_PROGRESS/DONE/REJECTED인 경우 오류

    **에러 응답:**
    - 404 Not Found: 태스크를 찾을 수 없음
    - 400 Bad Request: 태스크가 TODO 상태가 아님
    """
    return await service.start_task(task_id)
