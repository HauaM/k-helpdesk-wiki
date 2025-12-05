"""
LLM Client DTOs

FR-2/FR-6: 상담 기반 메뉴얼 생성과 업데이트 판단에 필요한 입력 스키마
FR-9: Prompt Template 아키텍처(템플릿 이름/버전) 메타데이터를 명시적으로 전달
"""

from uuid import UUID
from typing import Literal

from pydantic import Field

from app.schemas.base import BaseSchema


class PromptTemplateRef(BaseSchema):
    """LLM Prompt Template 식별자."""

    name: str = Field(description="템플릿 이름(예: manual_draft, manual_diff)")
    version: str | None = Field(default=None, description="템플릿 버전 혹은 리비전")


class ManualDraftInput(BaseSchema):
    """FR-2/FR-6: 상담 텍스트를 메뉴얼 초안 생성에 사용하기 위한 입력."""

    source_consultation_id: UUID | None = Field(
        default=None, description="LLM 호출을 유발한 상담 ID"
    )
    inquiry_text: str = Field(min_length=1)
    action_taken: str = Field(min_length=1)
    business_type: str | None = None
    error_code: str | None = None
    branch_code: str | None = None
    prompt: PromptTemplateRef = Field(
        default_factory=lambda: PromptTemplateRef(name="manual_draft"),
        description="사용할 Prompt Template 메타데이터",
    )


class ManualDraftOutput(BaseSchema):
    """LLM이 반환하는 메뉴얼 초안 결과."""

    keywords: list[str] = Field(default_factory=list, max_length=3)
    topic: str
    background: str
    guideline: str
    notes: str | None = Field(
        default=None,
        description="환각 방지 규칙을 따랐음을 나타내는 메모",
    )
    prompt: PromptTemplateRef = Field(
        default_factory=lambda: PromptTemplateRef(name="manual_draft"),
        description="호출 시 사용된 템플릿 정보",
    )


class ManualDiffInput(BaseSchema):
    """FR-6/FR-9: 기존/신규 메뉴얼 비교 요청."""

    old_manual: str = Field(min_length=1, description="기존 메뉴얼 전문")
    new_manual: str = Field(min_length=1, description="신규 메뉴얼 초안 전문")
    business_type: str | None = None
    error_code: str | None = None
    prompt: PromptTemplateRef = Field(
        default_factory=lambda: PromptTemplateRef(name="manual_diff"),
        description="사용할 비교 템플릿",
    )


class ManualDiffOutput(BaseSchema):
    """LLM 비교 결과."""

    differences: list[str] = Field(default_factory=list)
    recommendation: Literal["merge", "replace", "keep_both"]
    prompt: PromptTemplateRef = Field(
        default_factory=lambda: PromptTemplateRef(name="manual_diff"),
        description="사용된 템플릿 정보",
    )
