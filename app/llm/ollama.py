"""
Ollama LLM Client

로컬 Ollama 서버(qwen3:4b 등)와 통신하여 프롬프트 기반 응답을 반환한다.
"""

from __future__ import annotations

import json
import re

import httpx

from app.core.config import settings
from app.core.exceptions import LLMError, LLMValidationError
from app.core.logging import get_logger
from app.llm.protocol import LLMClientProtocol, LLMResponse

logger = get_logger(__name__)


class OllamaLLMClient(LLMClientProtocol):
    """Ollama 기반 LLM 클라이언트."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
        logger.info("ollama_llm_initialized", base_url=self.base_url, model=self.model)

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                # Ollama는 `num_predict`가 생성 토큰 수를 제한한다.
                "num_predict": max_tokens,
            },
        }

        try:
            resp = await self._client.post("/api/generate", json=payload)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Ollama 요청 실패: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMError(f"Ollama 응답 오류: {resp.status_code} {resp.text}")

        data = resp.json()
        content = data.get("response") or data.get("message") or ""
        prompt_tokens = data.get("prompt_eval_count")
        completion_tokens = data.get("eval_count")
        total_tokens = None
        if prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens
        usage_dict = None
        if prompt_tokens is not None or completion_tokens is not None:
            usage_dict = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }

        return LLMResponse(content=content, usage=usage_dict, model=self.model)

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
    ) -> dict:
        response = await self.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens,
        )

        try:
            logger.info("Ollama JSON 응답 파싱 시도", response=response.content)
            cleaned = self._extract_json_content(response.content)
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMValidationError("JSON 파싱 실패") from exc

    @staticmethod
    def _extract_json_content(content: str) -> str:
        """Strip Markdown 코드블록이 포함된 JSON 응답을 정제."""

        stripped = content.strip()
        if not stripped:
            return stripped

        code_block_pattern = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
        match = code_block_pattern.match(stripped)
        if match:
            return match.group(1).strip()

        return stripped

    async def __aenter__(self) -> "OllamaLLMClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001, D401
        await self._client.__aexit__(exc_type, exc, tb)
