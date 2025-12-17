"""
Consultation API Routes

RFP Reference: Section 10 - API Design
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.consultation import (
    ConsultationCreate,
    ConsultationResponse,
    ConsultationSearchParams,
    ConsultationSearchRequest,
    ConsultationSearchResponse,
    ConsultationSearchResult,
)
from app.schemas.response import ResponseEnvelope
from app.services.consultation_service import ConsultationService
from app.vectorstore.factory import get_consultation_vectorstore
from app.queue.inmemory import InMemoryRetryQueue
from app.api.swagger_responses import combined_responses


_retry_queue = InMemoryRetryQueue()

router = APIRouter(prefix="/consultations", tags=["consultations"])


def get_consultation_service(
    session: AsyncSession = Depends(get_session),
) -> ConsultationService:
    """
    Dependency: Get ConsultationService instance

    Returns:
        ConsultationService with injected dependencies
    """
    return ConsultationService(
        session=session,
        vectorstore=get_consultation_vectorstore(),
        retry_queue=_retry_queue,
    )


@router.post(
    "",
    response_model=ConsultationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new consultation",
    responses=combined_responses(
        status_code=201,
        data_example={
            "id": "uuid-xxx",
            "branch_code": "INTERNET_BANKING",
            "inquiry_text": "로그인이 안 됩니다",
            "created_at": "2024-12-16T10:35:00Z",
        },
        include_errors=[400, 422, 500],
    ),
)
async def create_consultation(
    data: ConsultationCreate,
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationResponse:
    """
    상담 등록 (RDB 저장 + VectorStore 인덱싱)

    FR-1: 상담 등록 기능

    **요청:**
    ```json
    {
      "branch_code": "INTERNET_BANKING",
      "business_type": "인터넷뱅킹",
      "error_code": "E001",
      "inquiry_text": "로그인이 안 됩니다",
      "employee_id": "emp001",
      "employee_name": "홍길동",
      "action_taken": "임시 비밀번호 발급",
      "consultation_date": "2024-12-16T10:30:00Z"
    }
    ```

    **응답 (201 Created):**
    ```json
    {
      "success": true,
      "data": {
        "id": "uuid-xxx",
        "branch_code": "INTERNET_BANKING",
        "business_type": "인터넷뱅킹",
        "error_code": "E001",
        "inquiry_text": "로그인이 안 됩니다",
        "employee_id": "emp001",
        "employee_name": "홍길동",
        "action_taken": "임시 비밀번호 발급",
        "consultation_date": "2024-12-16T10:30:00Z",
        "created_at": "2024-12-16T10:35:00Z"
      },
      "error": null,
      "meta": {
        "requestId": "req-xxx",
        "timestamp": "2024-12-16T10:35:00Z"
      },
      "feedback": []
    }
    ```

    **에러 응답:**
    - 400 Bad Request: 유효하지 않은 입력
    - 422 Unprocessable Entity: 필드 검증 실패
    - 500 Internal Server Error: 서버 오류

    **주요 필드:**
    - branch_code: 지점 코드 (필수)
    - business_type: 업무 구분 (필수)
    - error_code: 에러 코드 (필수)
    - inquiry_text: 상담 내용 (필수)

    **저장 위치:**
    - RDB (PostgreSQL): 전체 상담 데이터
    - VectorStore: 벡터화된 inquiry_text (유사 검색용)

    TODO: current_user = Depends(get_current_user) 추가 후 created_by_user_id 매핑
    """
    return await service.create_consultation(data)


@router.get(
    "/search",
    response_model=ConsultationSearchResponse,
    summary="Search similar consultations",
    responses=combined_responses(
        status_code=200,
        data_example={
            "results": [
                {
                    "id": "uuid-1",
                    "inquiry_text": "로그인이 안 됩니다",
                    "similarity_score": 0.95,
                }
            ],
            "total_found": 1,
            "query": "로그인",
        },
        include_errors=[400, 500],
    ),
)
async def search_consultations(
    params: ConsultationSearchParams = Depends(),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationSearchResponse:
    """
    상담 검색 (벡터 유사도 기반)

    FR-3, FR-8: 상담 검색 기능

    **쿼리 파라미터:**
    - query: 검색어 (필수, 예: "로그인이 안 됨")
    - top_k: 상위 결과 개수 (기본값: 10)
    - branch_code: 지점 필터 (선택사항)
    - business_type: 업무 구분 필터 (선택사항)
    - error_code: 에러 코드 필터 (선택사항)
    - start_date: 시작일 필터 (선택사항, ISO 8601)
    - end_date: 종료일 필터 (선택사항, ISO 8601)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "results": [
          {
            "id": "uuid-1",
            "branch_code": "INTERNET_BANKING",
            "business_type": "인터넷뱅킹",
            "error_code": "E001",
            "inquiry_text": "로그인이 안 됩니다",
            "employee_name": "홍길동",
            "action_taken": "임시 비밀번호 발급",
            "consultation_date": "2024-12-16T10:30:00Z",
            "similarity_score": 0.95
          }
        ],
        "total_found": 1,
        "query": "로그인이 안 됨"
      },
      "error": null,
      "meta": {
        "requestId": "req-yyy",
        "timestamp": "2024-12-16T10:35:00Z"
      },
      "feedback": []
    }
    ```

    **동작:**
    1. 쿼리를 벡터화하여 VectorStore에서 semantic search
    2. 상위 top_k개 결과 반환
    3. 메타데이터 필터 (branch_code, business_type, error_code, 날짜) 적용
    4. 유사도 임계값(threshold) 이상의 결과만 필터링
    5. 유사도 점수(0-1) 포함하여 반환

    **결과가 없는 경우:**
    - 200 OK, results=[], total_found=0 반환
    - 에러가 아니라 정상 응답

    **예시:**
    ```
    GET /consultations/search?query=로그인&top_k=5&business_type=인터넷뱅킹
    ```
    """
    request = ConsultationSearchRequest(
        query=params.query,
        top_k=params.top_k,
        filters={
            "branch_code": params.branch_code,
            "business_type": params.business_type,
            "error_code": params.error_code,
            "start_date": params.start_date,
            "end_date": params.end_date,
        },
    )
    results = await service.search_consultations(request)
    return {
        "results": results,
        "total_found": len(results),
        "query": params.query,
    }


@router.get(
    "/{consultation_id}",
    response_model=ConsultationResponse,
    summary="Get consultation details",
    responses=combined_responses(
        status_code=200,
        data_example={
            "id": "uuid-xxx",
            "inquiry_text": "로그인이 안 됩니다",
            "created_at": "2024-12-16T10:35:00Z",
        },
        include_errors=[404, 500],
    ),
)
async def get_consultation(
    consultation_id: str,
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationResponse:
    """
    상담 상세 조회

    **경로 파라미터:**
    - consultation_id: 상담 ID (UUID)

    **응답 (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "id": "uuid-xxx",
        "branch_code": "INTERNET_BANKING",
        "business_type": "인터넷뱅킹",
        "error_code": "E001",
        "inquiry_text": "로그인이 안 됩니다",
        "employee_id": "emp001",
        "employee_name": "홍길동",
        "action_taken": "임시 비밀번호 발급",
        "consultation_date": "2024-12-16T10:30:00Z",
        "created_at": "2024-12-16T10:35:00Z"
      },
      "error": null,
      "meta": {
        "requestId": "req-zzz",
        "timestamp": "2024-12-16T10:35:00Z"
      },
      "feedback": []
    }
    ```

    **에러 응답:**
    - 404 Not Found: 상담을 찾을 수 없음
      ```json
      {
        "success": false,
        "data": null,
        "error": {
          "code": "RecordNotFoundError",
          "message": "상담을 찾을 수 없습니다",
          "details": null,
          "hint": null
        },
        "meta": {...},
        "feedback": []
      }
      ```

    **주요 필드:**
    - id: 상담 고유 ID
    - inquiry_text: 고객의 상담 내용
    - action_taken: 상담원이 취한 조치
    - consultation_date: 상담 발생 일시
    """
    return await service.get_consultation(consultation_id)
