"""agent/llm/lmstudio_provider.py — LM Studio local LLM backend.

LM Studio exposes an OpenAI-compatible REST endpoint at /v1/chat/completions,
served locally — no API key required, no cloud traffic.

Structural mirror of OllamaProvider; only the base URL, endpoint path,
JSON payload shape, and response extraction path differ.
"""
from __future__ import annotations

import json

import httpx

from agent.llm.base import AbstractLLMProvider, LLMProviderError

__all__ = ["LMStudioProvider"]


class LMStudioProvider(AbstractLLMProvider):
    """Concrete provider targeting the local LM Studio HTTP API.

    Privacy-first: no API key required by default; optional Bearer auth
    is supported for LM Studio builds that enable it.

    Stages interact through AbstractLLMProvider only — never import this
    class directly; that is ProviderFactory's concern.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:1234",
        model: str = "local-model",
        timeout: float = 120.0,
        api_key: str = "",
    ) -> None:
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
        return "lmstudio"

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        """POST to LM Studio /v1/chat/completions and return the assistant reply.

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
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                content: str = data["choices"][0]["message"]["content"]
                if not content:
                    raise LLMProviderError(
                        "LM Studio returned empty content",
                        provider=self.provider_name,
                        model=self.model_name,
                    )
                return content
        except LLMProviderError:
            raise  # already wrapped — re-raise as-is
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"LM Studio HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise LLMProviderError(
                f"LM Studio request failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError(
                f"LM Studio response parsing failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
