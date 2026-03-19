"""agent/llm/openai_provider.py — OpenAI cloud LLM backend.

Targets the OpenAI REST API at /v1/chat/completions (same endpoint shape as
LMStudioProvider, but remote and API-key required).

Privacy-opt-in: only activated when the user sets llm.default_provider:
openai or includes "openai" in llm.fallback_chain in agent-config.yaml.
"""
from __future__ import annotations

import json

import httpx

from agent.llm.base import AbstractLLMProvider, LLMProviderError

__all__ = ["OpenAIProvider"]


class OpenAIProvider(AbstractLLMProvider):
    """Concrete provider targeting the OpenAI /v1/chat/completions API.

    API key is required — raises ValueError at construction time if absent.
    Authorization header is always sent.

    Stages interact through AbstractLLMProvider only — never import this
    class directly; that is ProviderFactory's concern.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com",
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        api_key: str = "",
    ) -> None:
        if not api_key:
            raise ValueError(
                "OpenAI api_key is required. "
                "Set OPENAI_API_KEY in your environment and configure "
                "llm.providers.openai.api_key_env in agent-config.yaml."
            )
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._api_key = api_key

    # ------------------------------------------------------------------
    # AbstractLLMProvider properties
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        """POST to OpenAI /v1/chat/completions and return the assistant reply.

        Args:
            messages:    OpenAI-compatible message list (role + content dicts).
            temperature: Sampling temperature; 0.0 = greedy/deterministic.
            max_tokens:  Max tokens in completion.

        Returns:
            Non-empty assistant reply string.

        Raises:
            LLMProviderError: On HTTP error, timeout, JSON parse failure,
                              or empty content field.  Original exception
                              stored in .cause.
        """
        url = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers: dict[str, str] = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                content: str = data["choices"][0]["message"]["content"]
                if not content:
                    raise LLMProviderError(
                        "OpenAI returned empty content",
                        provider=self.provider_name,
                        model=self.model_name,
                    )
                return content
        except LLMProviderError:
            raise  # already wrapped — re-raise as-is
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"OpenAI HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise LLMProviderError(
                f"OpenAI request failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError(
                f"OpenAI response parsing failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
