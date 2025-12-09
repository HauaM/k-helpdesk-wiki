"""
FR-15: 공통코드 Pydantic 스키마 (Request/Response DTO)
"""

from typing import Any, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import BaseSchema, BaseResponseSchema


class CommonCodeItemCreate(BaseSchema):
    """
    공통코드 항목 생성 요청
    """

    code_key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="코드 키 (예: RETAIL, LOAN)",
    )
    code_value: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="코드 값/표시명 (예: 리테일, 대출)",
    )
    sort_order: int = Field(
        default=0,
        ge=0,
        description="정렬 순서",
    )
    is_active: bool = Field(
        default=True,
        description="활성화 여부",
    )
    attributes: Optional[dict[str, Any]] = Field(
        default=None,
        description="추가 속성/메타데이터 (선택사항)",
    )

    @field_validator("code_key", "code_value")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """공백 제거"""
        return v.strip() if isinstance(v, str) else v


class CommonCodeItemUpdate(BaseSchema):
    """
    공통코드 항목 수정 요청
    """

    code_key: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="코드 키 (선택사항)",
    )
    code_value: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="코드 값/표시명 (선택사항)",
    )
    sort_order: Optional[int] = Field(
        default=None,
        ge=0,
        description="정렬 순서 (선택사항)",
    )
    is_active: Optional[bool] = Field(
        default=None,
        description="활성화 여부 (선택사항)",
    )
    attributes: Optional[dict[str, Any]] = Field(
        default=None,
        description="추가 속성/메타데이터 (선택사항)",
    )

    @field_validator("code_key", "code_value")
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """공백 제거"""
        return v.strip() if isinstance(v, str) else v


class CommonCodeItemResponse(BaseResponseSchema):
    """
    공통코드 항목 응답
    """

    group_id: UUID = Field(description="상위 그룹 ID")
    code_key: str = Field(description="코드 키")
    code_value: str = Field(description="코드 값/표시명")
    sort_order: int = Field(description="정렬 순서")
    is_active: bool = Field(description="활성화 여부")
    attributes: dict[str, Any] = Field(description="추가 속성/메타데이터")

    class Config:
        from_attributes = True


class CommonCodeGroupCreate(BaseSchema):
    """
    공통코드 그룹 생성 요청
    """

    group_code: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="그룹 고유 코드 (예: BUSINESS_TYPE, ERROR_CODE)",
    )
    group_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="그룹 이름 (예: 업무 구분, 에러코드)",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="그룹 설명 (선택사항)",
    )
    is_active: bool = Field(
        default=True,
        description="활성화 여부",
    )

    @field_validator("group_code", "group_name")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """공백 제거"""
        return v.strip() if isinstance(v, str) else v


class CommonCodeGroupUpdate(BaseSchema):
    """
    공통코드 그룹 수정 요청
    """

    group_code: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="그룹 고유 코드 (선택사항)",
    )
    group_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="그룹 이름 (선택사항)",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="그룹 설명 (선택사항)",
    )
    is_active: Optional[bool] = Field(
        default=None,
        description="활성화 여부 (선택사항)",
    )

    @field_validator("group_code", "group_name")
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """공백 제거"""
        return v.strip() if isinstance(v, str) else v


class CommonCodeGroupResponse(BaseResponseSchema):
    """
    공통코드 그룹 응답 (항목 미포함)
    """

    group_code: str = Field(description="그룹 고유 코드")
    group_name: str = Field(description="그룹 이름")
    description: Optional[str] = Field(description="그룹 설명")
    is_active: bool = Field(description="활성화 여부")

    class Config:
        from_attributes = True


class CommonCodeGroupDetailResponse(CommonCodeGroupResponse):
    """
    공통코드 그룹 상세 응답 (항목 포함)
    """

    items: list[CommonCodeItemResponse] = Field(
        default=[],
        description="하위 코드 항목 목록",
    )


class CommonCodeSimpleResponse(BaseSchema):
    """
    프론트엔드용 공통코드 항목 응답 (축약 버전)
    - id, created_at, updated_at 제외
    """

    code_key: str = Field(description="코드 키")
    code_value: str = Field(description="코드 값/표시명")


class CommonCodeGroupSimpleResponse(BaseSchema):
    """
    프론트엔드용 공통코드 그룹 응답 (축약 버전)
    """

    group_code: str = Field(description="그룹 고유 코드")
    items: list[CommonCodeSimpleResponse] = Field(
        description="하위 코드 항목 목록",
    )


# Bulk Response

class BulkCommonCodeResponse(BaseSchema):
    """
    다중 그룹 조회 응답 (프론트엔드용)

    예시:
    {
        "BUSINESS_TYPE": {
            "group_code": "BUSINESS_TYPE",
            "items": [
                {"code_key": "RETAIL", "code_value": "리테일"},
                {"code_key": "LOAN", "code_value": "대출"}
            ]
        },
        "ERROR_CODE": {...}
    }
    """

    data: dict[str, CommonCodeGroupSimpleResponse] = Field(
        description="그룹 코드를 키로 하는 공통코드 맵",
    )


# Pagination & Search

class CommonCodeGroupListResponse(BaseSchema):
    """
    공통코드 그룹 목록 응답
    """

    items: list[CommonCodeGroupResponse] = Field(description="그룹 목록")
    total: int = Field(description="총 개수")
    page: int = Field(description="현재 페이지")
    page_size: int = Field(description="페이지 크기")
    total_pages: int = Field(description="총 페이지 수")


class CommonCodeItemListResponse(BaseSchema):
    """
    공통코드 항목 목록 응답
    """

    items: list[CommonCodeItemResponse] = Field(description="항목 목록")
    total: int = Field(description="총 개수")
    page: int = Field(description="현재 페이지")
    page_size: int = Field(description="페이지 크기")
    total_pages: int = Field(description="총 페이지 수")


# Error Response

class CommonCodeErrorResponse(BaseSchema):
    """
    에러 응답
    """

    error: str = Field(description="에러 메시지")
    code: str = Field(description="에러 코드")
