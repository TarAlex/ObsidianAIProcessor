"""agent/llm/provider_factory.py — registry-based LLM provider wiring.

This is the ONLY place in the codebase that imports concrete provider classes.
All pipeline code imports only ProviderFactory.get or get_provider — never
individual provider modules directly.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from agent.llm.base import AbstractLLMProvider, LLMProviderError
from agent.llm.ollama_provider import OllamaProvider
from agent.llm.lmstudio_provider import LMStudioProvider
from agent.llm.openai_provider import OpenAIProvider
from agent.llm.anthropic_provider import AnthropicProvider
from agent.llm.gemini_provider import GeminiProvider

if TYPE_CHECKING:
    from agent.core.config import AgentConfig

__all__ = ["ProviderFactory", "get_provider"]

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry — add new providers here and nowhere else
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[AbstractLLMProvider]] = {
    "ollama": OllamaProvider,
    "lmstudio": LMStudioProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_provider(name: str, config: AgentConfig) -> AbstractLLMProvider:
    """Instantiate a provider by registry name, wiring config kwargs.

    Raises:
        ValueError: if name is not in the registry (propagated from no-op
                    lookup) or if a cloud provider receives an empty api_key.
    """
    if name not in _REGISTRY:
        raise ValueError(
            f"Unknown LLM provider: {name!r}. "
            f"Known providers: {sorted(_REGISTRY)}"
        )
    cls = _REGISTRY[name]
    pconf = config.llm.providers.get(name)  # ProviderConfig | None
    kwargs: dict[str, object] = {}

    # base_url — passed to ollama, lmstudio, openai; not accepted by anthropic
    if pconf and pconf.base_url and name != "anthropic":
        kwargs["base_url"] = pconf.base_url

    # default_model → model constructor kwarg
    if pconf and pconf.default_model:
        kwargs["model"] = pconf.default_model

    # api_key resolution — read env var at construction time; never logged
    if pconf and pconf.api_key_env:
        kwargs["api_key"] = os.environ.get(pconf.api_key_env, "")

    return cls(**kwargs)


class _FallbackProvider(AbstractLLMProvider):
    """Transparent fallback wrapper — callers see AbstractLLMProvider only.

    Tries the primary provider first; on LLMProviderError logs a WARNING and
    tries each fallback in order. Re-raises the last LLMProviderError if all
    providers fail.

    Non-LLMProviderError exceptions propagate immediately as programming errors.
    """

    def __init__(
        self,
        primary: AbstractLLMProvider,
        fallbacks: list[AbstractLLMProvider],
    ) -> None:
        self._primary = primary
        self._fallbacks = fallbacks

    @property
    def model_name(self) -> str:
        return self._primary.model_name

    @property
    def provider_name(self) -> str:
        return self._primary.provider_name

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        providers = [self._primary] + self._fallbacks
        last_exc: LLMProviderError | None = None
        for provider in providers:
            try:
                return await provider.chat(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
            except LLMProviderError as exc:
                _log.warning(
                    "LLM provider %s/%s failed (%s) — trying next in chain",
                    provider.provider_name,
                    provider.model_name,
                    exc,
                )
                last_exc = exc
        raise last_exc  # type: ignore[misc]  — always set since providers >= 1


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

class ProviderFactory:
    """Registry-based factory for AbstractLLMProvider instances.

    Usage:
        provider = ProviderFactory.get(config)
        reply = await provider.chat(messages)
    """

    @classmethod
    def get(cls, config: AgentConfig) -> AbstractLLMProvider:
        """Build and return a fully-configured provider for the given config.

        If config.llm.fallback_chain contains providers other than the
        default_provider, returns a _FallbackProvider wrapper that tries
        them in order on LLMProviderError.

        All providers in the chain are constructed eagerly — config errors
        surface at startup, not on the first LLM call.

        Raises:
            ValueError: unknown provider name or missing required api_key.
        """
        primary_name = config.llm.default_provider
        primary = _build_provider(primary_name, config)

        # Filter out duplicates of the primary from the fallback chain
        fallback_names = [
            n for n in config.llm.fallback_chain
            if n != primary_name
        ]
        if not fallback_names:
            return primary  # no wrapper needed

        fallbacks = [_build_provider(n, config) for n in fallback_names]
        return _FallbackProvider(primary, fallbacks)


# ---------------------------------------------------------------------------
# Module-level alias (preferred import for pipeline code)
# ---------------------------------------------------------------------------

def get_provider(config: AgentConfig) -> AbstractLLMProvider:
    """Module-level alias for ProviderFactory.get().

    Preferred import for pipeline code:
        from agent.llm.provider_factory import get_provider
    """
    return ProviderFactory.get(config)
