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
from app.services.consultation_service import ConsultationService
from app.vectorstore.factory import get_consultation_vectorstore
from app.queue.inmemory import InMemoryRetryQueue


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
)
async def create_consultation(
    data: ConsultationCreate,
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationResponse:
    """
    Create new consultation record

    RFP Reference: POST /consultations
    - Saves to RDB
    - Indexes in VectorStore
    - Returns created consultation

    FR-1: 상담 등록 (RDB 저장 + VectorStore 인덱싱/재시도 큐 연동)
    TODO: current_user = Depends(get_current_user) 추가 후 created_by_user_id 매핑
    """
    return await service.create_consultation(data)


@router.get(
    "/search",
    response_model=ConsultationSearchResponse,
    summary="Search similar consultations",
)
async def search_consultations(
    params: ConsultationSearchParams = Depends(),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationSearchResponse:
    """
    Search for similar consultations using vector similarity

    RFP Reference: GET /consultations/search
    - Vector-based semantic search
    - Metadata filtering (branch, business_type, error_code)
    - Threshold-based result filtering
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
)
async def get_consultation(
    consultation_id: str,
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationResponse:
    """
    Get detailed consultation information by ID

    RFP Reference: GET /consultations/{id}
    - Returns full consultation details including summary, inquiry, action
    - Returns user information (employee name)
    """
    return await service.get_consultation(consultation_id)
