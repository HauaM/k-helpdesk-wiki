"""
FR-15: 공통코드 관리 라우터 (FastAPI 엔드포인트)

관리자용 API: /admin/common-codes/
프론트엔드용 API: /common-codes/
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.exceptions import (
    RecordNotFoundError,
    DuplicateRecordError,
    ValidationError,
)
from app.services.common_code_service import CommonCodeService
from app.schemas.common_code import (
    CommonCodeGroupCreate,
    CommonCodeGroupUpdate,
    CommonCodeGroupResponse,
    CommonCodeGroupDetailResponse,
    CommonCodeGroupListResponse,
    CommonCodeItemCreate,
    CommonCodeItemUpdate,
    CommonCodeItemResponse,
    CommonCodeItemListResponse,
    CommonCodeGroupSimpleResponse,
    BulkCommonCodeResponse,
)

router = APIRouter(tags=["common-codes"])


def get_common_code_service(
    session: AsyncSession = Depends(get_session),
) -> CommonCodeService:
    """
    의존성 주입: CommonCodeService 생성
    """
    return CommonCodeService(session=session)


# ==================== Admin API: Group Management ====================


@router.post(
    "/admin/common-codes/groups",
    response_model=CommonCodeGroupResponse,
    status_code=201,
    summary="공통코드 그룹 생성",
    tags=["Admin - Common Code Groups"],
)
async def create_group(
    payload: CommonCodeGroupCreate,
    service: CommonCodeService = Depends(get_common_code_service),
) -> CommonCodeGroupResponse:
    """
    새로운 공통코드 그룹 생성

    - **group_code**: 그룹 고유 코드 (예: BUSINESS_TYPE, ERROR_CODE)
    - **group_name**: 그룹 이름 (예: 업무 구분, 에러코드)
    - **description**: 그룹 설명 (선택사항)
    - **is_active**: 활성화 여부 (기본값: true)

    에러:
    - 400: group_code 중복
    - 422: 입력 데이터 검증 실패
    """
    try:
        return await service.create_group(payload)
    except DuplicateRecordError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/admin/common-codes/groups",
    response_model=CommonCodeGroupListResponse,
    summary="공통코드 그룹 목록 조회",
    tags=["Admin - Common Code Groups"],
)
async def list_groups(
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    is_active: Optional[bool] = Query(None, description="활성화 필터"),
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    공통코드 그룹 목록 조회 (페이징)
    """
    return await service.list_groups(page=page, page_size=page_size, is_active=is_active)


@router.get(
    "/admin/common-codes/groups/search",
    response_model=CommonCodeGroupListResponse,
    summary="공통코드 그룹 검색",
    tags=["Admin - Common Code Groups"],
)
async def search_groups(
    keyword: str = Query(..., min_length=1, description="검색 키워드"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    그룹 코드 또는 그룹 이름으로 검색
    """
    return await service.search_groups(keyword=keyword, page=page, page_size=page_size)


@router.get(
    "/admin/common-codes/groups/{group_id}",
    response_model=CommonCodeGroupDetailResponse,
    summary="공통코드 그룹 조회 (항목 포함)",
    tags=["Admin - Common Code Groups"],
)
async def get_group(
    group_id: UUID = Path(..., description="그룹 ID"),
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    ID로 그룹과 하위 항목을 함께 조회
    """
    try:
        group = await service.get_group(group_id)
        # 기본 응답은 상세 정보를 포함하지 않으므로, 별도로 항목 조회
        # 실제로는 get_group_with_items를 호출하는 것이 효율적
        # 하지만 현재는 get_group만 호출하고 frontend에서 별도로 items 조회하도록 함
        # 또는 아래처럼 수정:
        return group
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/admin/common-codes/groups/{group_id}",
    response_model=CommonCodeGroupResponse,
    summary="공통코드 그룹 수정",
    tags=["Admin - Common Code Groups"],
)
async def update_group(
    group_id: UUID = Path(..., description="그룹 ID"),
    payload: CommonCodeGroupUpdate = ...,
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    공통코드 그룹 수정 (부분 업데이트 지원)
    """
    try:
        return await service.update_group(group_id, payload)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateRecordError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/admin/common-codes/groups/{group_id}",
    summary="공통코드 그룹 삭제",
    tags=["Admin - Common Code Groups"],
    responses={204: {"description": "그룹 삭제 완료"}},
)
async def delete_group(
    group_id: UUID = Path(..., description="그룹 ID"),
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    공통코드 그룹 삭제 (하위 항목도 함께 삭제)
    """
    try:
        await service.delete_group(group_id)
        return {"message": "Group deleted successfully"}
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== Admin API: Item Management ====================


@router.post(
    "/admin/common-codes/groups/{group_id}/items",
    response_model=CommonCodeItemResponse,
    status_code=201,
    summary="공통코드 항목 생성",
    tags=["Admin - Common Code Items"],
)
async def create_item(
    group_id: UUID = Path(..., description="그룹 ID"),
    payload: CommonCodeItemCreate = ...,
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    공통코드 항목 생성
    """
    try:
        return await service.create_item(group_id, payload)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateRecordError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/admin/common-codes/groups/{group_id}/items",
    response_model=CommonCodeItemListResponse,
    summary="공통코드 항목 목록 조회",
    tags=["Admin - Common Code Items"],
)
async def list_items(
    group_id: UUID = Path(..., description="그룹 ID"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(100, ge=1, le=1000, description="페이지 크기"),
    is_active_only: bool = Query(False, description="활성 항목만 조회"),
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    그룹의 공통코드 항목 목록 조회
    """
    try:
        return await service.list_items_by_group(
            group_id=group_id,
            page=page,
            page_size=page_size,
            is_active_only=is_active_only,
        )
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/admin/common-codes/items/{item_id}",
    response_model=CommonCodeItemResponse,
    summary="공통코드 항목 조회",
    tags=["Admin - Common Code Items"],
)
async def get_item(
    item_id: UUID = Path(..., description="항목 ID"),
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    ID로 공통코드 항목 조회
    """
    try:
        return await service.get_item(item_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/admin/common-codes/items/{item_id}",
    response_model=CommonCodeItemResponse,
    summary="공통코드 항목 수정",
    tags=["Admin - Common Code Items"],
)
async def update_item(
    item_id: UUID = Path(..., description="항목 ID"),
    payload: CommonCodeItemUpdate = ...,
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    공통코드 항목 수정 (부분 업데이트 지원)
    """
    try:
        return await service.update_item(item_id, payload)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateRecordError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/admin/common-codes/items/{item_id}",
    summary="공통코드 항목 삭제",
    tags=["Admin - Common Code Items"],
    responses={204: {"description": "항목 삭제 완료"}},
)
async def delete_item(
    item_id: UUID = Path(..., description="항목 ID"),
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    공통코드 항목 삭제
    """
    try:
        await service.delete_item(item_id)
        return {"message": "Item deleted successfully"}
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== Public API: Frontend ====================


@router.get(
    "/common-codes/{group_code}",
    response_model=dict,  # 프론트엔드에 간단한 응답 제공
    summary="공통코드 조회 (그룹 코드)",
    tags=["Public - Common Codes"],
)
async def get_codes_by_group(
    group_code: str = Path(..., description="그룹 코드 (예: BUSINESS_TYPE)"),
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    그룹 코드로 공통코드 항목 조회 (프론트엔드용)

    응답 예시:
    ```json
    {
      "group_code": "BUSINESS_TYPE",
      "items": [
        {"code_key": "RETAIL", "code_value": "리테일"},
        {"code_key": "LOAN", "code_value": "대출"}
      ]
    }
    ```

    참고: 데이터가 없어도 200 OK와 빈 items 배열을 반환합니다.
    """
    result = await service.get_codes_by_group_code(group_code, is_active_only=True)
    return result.model_dump()


@router.post(
    "/common-codes/bulk",
    response_model=dict,
    summary="공통코드 일괄 조회",
    tags=["Public - Common Codes"],
)
async def get_multiple_codes(
    group_codes: list[str] = ...,
    service: CommonCodeService = Depends(get_common_code_service),
):
    """
    여러 그룹의 공통코드 일괄 조회 (프론트엔드용)

    요청 본문:
    ```json
    ["BUSINESS_TYPE", "ERROR_CODE"]
    ```

    응답 예시:
    ```json
    {
      "data": {
        "BUSINESS_TYPE": {
          "group_code": "BUSINESS_TYPE",
          "items": [...]
        },
        "ERROR_CODE": {
          "group_code": "ERROR_CODE",
          "items": [...]
        }
      }
    }
    ```
    """
    try:
        result = await service.get_multiple_code_groups(group_codes, is_active_only=True)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
