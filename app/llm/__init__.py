"""
LLM Client Abstraction
Interface for LLM providers and prompt templates
"""

from app.llm.protocol import LLMClientProtocol, LLMResponse
from app.llm.factory import get_llm_client

__all__ = ["LLMClientProtocol", "LLMResponse", "get_llm_client"]
