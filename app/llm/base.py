"""
LLM 클라이언트 인터페이스

FR-2/FR-6/FR-9 및 Prompt Template 아키텍처 요구사항을 반영하여
메뉴얼 초안 생성과 메뉴얼 비교 기능을 추상화한다.
"""

from typing import Protocol, runtime_checkable

from app.llm.schemas import (
    ManualDiffInput,
    ManualDiffOutput,
    ManualDraftInput,
    ManualDraftOutput,
)


@runtime_checkable
class LLMClient(Protocol):
    """LLM 클라이언트 추상 인터페이스."""

    def generate_manual_draft(self, input: ManualDraftInput) -> ManualDraftOutput:
        """상담 텍스트 기반 메뉴얼 초안 생성 (FR-2/FR-6)."""

    def compare_manuals(self, input: ManualDiffInput) -> ManualDiffOutput:
        """기존 vs 신규 메뉴얼 비교 결과 반환 (FR-6/FR-9)."""


class LLMClientStub(LLMClient):
    """실제 API 호출 대신 타입 안전성을 위한 Stub."""

    def generate_manual_draft(self, input: ManualDraftInput) -> ManualDraftOutput:  # pragma: no cover - stub
        raise NotImplementedError("LLMClient.generate_manual_draft 구현체가 필요합니다")

    def compare_manuals(self, input: ManualDiffInput) -> ManualDiffOutput:  # pragma: no cover - stub
        raise NotImplementedError("LLMClient.compare_manuals 구현체가 필요합니다")
