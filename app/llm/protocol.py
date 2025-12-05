"""
LLM Client Protocol (Interface)
Defines contract for all LLM implementations
"""

from typing import Protocol, NamedTuple


class LLMResponse(NamedTuple):
    """
    LLM response container

    Attributes:
        content: Generated text content
        usage: Token usage info (prompt_tokens, completion_tokens, total_tokens)
        model: Model name used
    """

    content: str
    usage: dict | None = None
    model: str | None = None


class LLMClientProtocol(Protocol):
    """
    Protocol for LLM client implementations

    RFP Reference: Section 7 - LLM 활용 규칙 (환각 방지)
    LLM should only summarize/organize existing content, not create new facts
    """

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """
        Generate completion from LLM

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            max_tokens: Maximum tokens to generate

        Returns:
            LLM response

        Raises:
            LLMError: If LLM call fails
            LLMRateLimitError: If rate limit exceeded
        """
        ...

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.3,
    ) -> dict:
        """
        Generate JSON-formatted completion

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature

        Returns:
            Parsed JSON dict

        Raises:
            LLMError: If LLM call fails or JSON parsing fails
            LLMValidationError: If response is not valid JSON
        """
        ...
