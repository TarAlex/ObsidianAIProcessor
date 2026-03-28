"""agent/llm/gemini_provider.py — Google Gemini via google-genai SDK."""
from __future__ import annotations

from google import genai
from google.genai import types

from agent.llm.base import AbstractLLMProvider, LLMProviderError

__all__ = ["GeminiProvider"]


def _flatten_messages(messages: list[dict[str, str]]) -> str:
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    users = [m["content"] for m in messages if m["role"] == "user"]
    assistants = [m["content"] for m in messages if m["role"] == "assistant"]
    parts: list[str] = []
    if system:
        parts.append(f"[System]\n{system}")
    if assistants:
        parts.append("[Assistant]\n" + "\n\n".join(assistants))
    if users:
        parts.append("[User]\n" + "\n\n".join(users))
    return "\n\n".join(parts).strip()


class GeminiProvider(AbstractLLMProvider):
    """Gemini Developer API (or compatible base_url) via Async client."""

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: str = "",
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError(
                "Gemini api_key is required. "
                "Set GOOGLE_API_KEY or GEMINI_API_KEY in your environment and "
                "llm.providers.gemini.api_key_env in agent-config.yaml."
            )
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/") if base_url else None
        self._timeout = timeout
        timeout_ms = max(1000, int(timeout * 1000))
        if self._base_url:
            self._http_options = types.HttpOptions(
                base_url=self._base_url,
                timeout=timeout_ms,
            )
        else:
            self._http_options = types.HttpOptions(timeout=timeout_ms)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        text = _flatten_messages(messages)
        if not text:
            raise LLMProviderError(
                "Gemini: empty message contents",
                provider=self.provider_name,
                model=self.model_name,
            )
        try:
            client = genai.Client(api_key=self._api_key, http_options=self._http_options)
            async with client.aio as aclient:
                response = await aclient.models.generate_content(
                    model=self._model,
                    contents=text,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
            out = (response.text or "").strip()
            if not out:
                raise LLMProviderError(
                    "Gemini returned empty content",
                    provider=self.provider_name,
                    model=self.model_name,
                )
            return out
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                f"Gemini request failed: {exc}",
                provider=self.provider_name,
                model=self.model_name,
                cause=exc,
            ) from exc
