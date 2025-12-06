"""
Mock LLM Client
For development and testing without actual LLM API calls
"""

import json
import asyncio

from app.llm.protocol import LLMClientProtocol, LLMResponse
from app.core.exceptions import LLMError, LLMValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)


class MockLLMClient:
    """
    Mock LLM client that returns predefined responses

    RFP Reference: Section 2 - LLM Configuration
    """

    def __init__(self, model: str = "mock-model"):
        self.model = model
        logger.info("mock_llm_initialized", model=model)

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """
        Generate mock completion

        Returns simple echo response for testing
        """
        # Simulate API latency
        await asyncio.sleep(0.1)

        logger.debug(
            "llm_complete_called",
            prompt_length=len(prompt),
            temperature=temperature,
        )

        # Simple mock response
        content = f"Mock LLM Response: Processed {len(prompt)} characters"

        return LLMResponse(
            content=content,
            usage={"prompt_tokens": len(prompt) // 4, "completion_tokens": 20, "total_tokens": len(prompt) // 4 + 20},
            model=self.model,
        )

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
    ) -> dict:
        """
        Generate mock JSON completion

        Returns sample JSON based on prompt keywords
        """
        await asyncio.sleep(0.1)

        logger.debug("llm_complete_json_called", prompt_length=len(prompt))

        lowered = prompt.lower()

        # 메뉴얼 초안 생성용: keywords/topic/background/guideline 모두 반환
        if ("keywords" in lowered or "키워드" in prompt) and ("topic" in lowered or "주제" in prompt):
            return {
                "keywords": ["시스템", "로그인"],
                "topic": "로그인 오류 안내",
                "background": "사용자가 로그인 시도 시 오류가 발생했다는 상담 내용",
                "guideline": "재시도 전 캐시 삭제 및 비밀번호 확인을 안내",
            }

        # Detect prompt type and return appropriate mock response
        if "keywords" in lowered or "키워드" in prompt:
            return {
                "keywords": ["키워드1", "키워드2"],
            }
        elif "topic" in lowered or "주제" in prompt:
            return {
                "topic": "Mock 주제",
                "background": "Mock 배경 설명",
                "guideline": "Mock 조치사항",
                "notes": "Mock 응답입니다",
            }
        elif "differences" in prompt.lower() or "차이점" in prompt:
            return {
                "differences": ["차이점 1", "차이점 2"],
                "recommendation": "merge",
            }
        elif "is_valid" in prompt.lower() or "검증" in prompt:
            return {
                "is_valid": True,
                "violations": [],
                "reason": "Mock 검증 통과",
            }
        else:
            return {"result": "Mock JSON response"}
