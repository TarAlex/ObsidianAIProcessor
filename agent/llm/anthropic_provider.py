"""agent/llm/anthropic_provider.py — Anthropic cloud LLM backend.

Uses the official anthropic.AsyncAnthropic SDK (anthropic>=0.25).

Privacy-opt-in: only activated when the user sets llm.default_provider:
anthropic or includes "anthropic" in llm.fallback_chain in agent-config.yaml.
"""
from __future__ import annotations

import anthropic

from agent.llm.base import AbstractLLMProvider, LLMProviderError

__all__ = ["AnthropicProvider"]


class AnthropicProvider(AbstractLLMProvider):
    """Concrete provider targeting the Anthropic Messages API.

    API key is required — raises ValueError at construction time if absent.
    SDK auth, retries (disabled), and connection pooling are handled by
    anthropic.AsyncAnthropic.

    Stages interact through AbstractLLMProvider only — never import this
    class directly; that is ProviderFactory's concern.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        timeout: float = 60.0,
        api_key: str = "",
    ) -> None:
        if not api_key:
            raise ValueError(
                "Anthropic api_key is required. "
                "Set ANTHROPIC_API_KEY in your environment and configure "
                "llm.providers.anthropic.api_key_env in agent-config.yaml."
            )
        self._model = model
        self._timeout = timeout
        self._api_key = api_key
        # Client is instantiated per-call (inside chat()) to stay anyio-safe
        # and avoid holding a connection across event loop changes.

    # ------------------------------------------------------------------
    # AbstractLLMProvider properties
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        """Call Anthropic Messages API and return the assistant reply.

        System messages are extracted from the messages list and passed as
        the top-level system= parameter, as required by the Anthropic API.

        Args:
            messages:    OpenAI-compatible message list (role + content dicts).
            temperature: Sampling temperature; 0.0 = greedy/deterministic.
            max_tokens:  Max tokens in completion.

        Returns:
            Non-empty assistant reply string.

        Raises:
            LLMProviderError: On API error, timeout, connection failure,
                              or empty/malformed content. Original exception
                              stored in .cause.
        """
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] != "system"]
        system_text: str = "\n\n".join(system_parts) if system_parts else ""

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system_text:
            kwargs["system"] = system_text

        try:
            async with anthropic.AsyncAnthropic(
                api_key=self._api_key,
                timeout=self._timeout,
                max_retries=0,
            ) as client:
                message = await client.messages.create(**kwargs)
                content: str = message.content[0].text
                if not content:
                    raise LLMProviderError(
                        "Anthropic returned empty content",
                        provider=self.provider_name,
                        model=self.model_name,
                    )
                return content
        except LLMProviderError:
            raise  # already wrapped — re-raise as-is
        except anthropic.APIStatusError as exc:
            raise LLMProviderError(
                f"Anthropic API error {exc.status_code}: {str(exc)[:200]}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderError(
                f"Anthropic request failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
        except (IndexError, AttributeError, KeyError) as exc:
            raise LLMProviderError(
                f"Anthropic response parsing failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
