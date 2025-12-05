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
        },
    )
    results = await service.search_consultations(request)
    return {
        "results": results,
        "total_found": len(results),
        "query": params.query,
    }


@router.post(
    "/search",
    response_model=list[ConsultationSearchResult],
    summary="Search consultations (vector)",
)
async def search_consultations_post(
    search_request: ConsultationSearchRequest,
    service: ConsultationService = Depends(get_consultation_service),
) -> list[ConsultationSearchResult]:
    """FR-3/FR-8: 벡터 기반 상담 검색 (POST)."""

    return await service.search_consultations(search_request)


@router.post(
    "/{consultation_id}/manual-draft",
    response_model=dict,  # TODO: Use proper ManualEntryResponse
    summary="Generate manual draft from consultation",
)
async def generate_manual_draft(
    consultation_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Generate manual draft from consultation using LLM

    RFP Reference: POST /consultations/{id}/manual-draft
    - LLM extracts keywords
    - LLM generates manual structure
    - Returns draft for user review

    TODO: Implement actual logic
    """
    # TODO:
    # 1. Get consultation by ID
    # 2. Call ManualService.generate_manual_draft()
    # 3. Return draft

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Manual draft generation not yet implemented",
    )
