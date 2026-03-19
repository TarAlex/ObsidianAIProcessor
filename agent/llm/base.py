"""LLM provider base ABC and shared exception.

This module is a pure contract — no HTTP, no I/O, no agent.* imports.
Only stdlib `abc` is used at runtime.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["AbstractLLMProvider", "LLMProviderError"]


class LLMProviderError(Exception):
    """Raised by concrete providers on any backend failure.

    Wraps the underlying cause so callers never see raw httpx / openai /
    anthropic exceptions.
    """

    def __init__(
        self,
        message: str,
        provider: str = "",
        model: str = "",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.cause = cause


class AbstractLLMProvider(ABC):
    """Formal ABC for all LLM backend implementations.

    Concrete subclasses: OllamaProvider, LMStudioProvider,
    OpenAIProvider, AnthropicProvider.

    Pipeline stages depend only on this interface; they never import
    concrete providers directly.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier used by this provider (e.g. 'llama3.2')."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short lowercase identifier (e.g. 'ollama').

        Used to populate ProcessingRecord.llm_provider.
        """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        """Send a messages-format request and return the assistant reply.

        Args:
            messages: OpenAI-compatible message list.  Each dict has
                      'role' ('system' | 'user' | 'assistant') and 'content'.
            temperature: Sampling temperature; 0.0 = deterministic/greedy.
            max_tokens: Maximum tokens in the completion.

        Returns:
            The assistant reply as a raw string (never None, never empty
            on success).  Callers call json.loads() if structured output
            is expected.

        Raises:
            LLMProviderError: On any provider-level failure (HTTP error,
                timeout, invalid response structure).
        """
