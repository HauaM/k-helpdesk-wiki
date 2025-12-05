"""
LLM Client Factory
Creates appropriate LLM client based on configuration
"""

from app.llm.protocol import LLMClientProtocol
from app.llm.mock import MockLLMClient
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_llm_client() -> LLMClientProtocol:
    """
    Get LLM client implementation based on configuration

    Returns:
        LLM client implementation

    Raises:
        ValueError: If llm_provider is not supported

    Usage:
        llm_client = get_llm_client()
        response = await llm_client.complete("Hello")
    """
    provider = settings.llm_provider

    logger.info("llm_factory", provider=provider, model=settings.llm_model)

    if provider == "mock":
        return MockLLMClient(model=settings.llm_model)

    # TODO: Implement real LLM clients
    # elif provider == "openai":
    #     return OpenAIClient(
    #         api_key=settings.openai_api_key,
    #         model=settings.llm_model,
    #     )
    # elif provider == "anthropic":
    #     return AnthropicClient(
    #         api_key=settings.anthropic_api_key,
    #         model=settings.llm_model,
    #     )

    else:
        raise ValueError(
            f"Unsupported llm_provider: {provider}. "
            f"Supported providers: mock, openai, anthropic"
        )


# Singleton instance for dependency injection
_llm_client: LLMClientProtocol | None = None


def get_llm_client_instance() -> LLMClientProtocol:
    """
    Get singleton LLM client instance

    Returns:
        LLM client instance
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = get_llm_client()
    return _llm_client
