"""agent/llm/ollama_provider.py — Ollama local LLM backend.

Reference implementation for all subsequent providers.
Establishes the httpx.AsyncClient request/response pattern,
LLMProviderError wrapping strategy, and stream:false contract.
"""
from __future__ import annotations

import json

import httpx

from agent.llm.base import AbstractLLMProvider, LLMProviderError

__all__ = ["OllamaProvider"]


class OllamaProvider(AbstractLLMProvider):
    """Concrete provider targeting the local Ollama HTTP API.

    Privacy-first default: no API key, no cloud, no telemetry.
    Stages interact through AbstractLLMProvider only — never import this
    class directly; that is ProviderFactory's concern.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    # ------------------------------------------------------------------
    # AbstractLLMProvider properties
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        """POST to Ollama /api/chat and return the assistant reply string.

        Args:
            messages:    OpenAI-compatible message list (role + content dicts).
            temperature: Sampling temperature; 0.0 = greedy/deterministic.
            max_tokens:  Max tokens in completion (mapped to num_predict).

        Returns:
            Non-empty assistant reply string.

        Raises:
            LLMProviderError: On HTTP error, timeout, JSON parse failure,
                              or empty content field.  Original exception
                              stored in .cause.
        """
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                content: str = data["message"]["content"]
                if not content:
                    raise LLMProviderError(
                        "Ollama returned empty content",
                        provider=self.provider_name,
                        model=self.model_name,
                    )
                return content
        except LLMProviderError:
            raise  # already wrapped — re-raise as-is
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise LLMProviderError(
                f"Ollama request failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError(
                f"Ollama response parsing failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
