"""Unit tests for agent/llm/ollama_provider.py.

Uses pytest-httpx to mock httpx.AsyncClient without network I/O.
All async tests run via pytest-anyio (@pytest.mark.anyio).
"""
from __future__ import annotations

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

from agent.llm.base import AbstractLLMProvider, LLMProviderError
from agent.llm.ollama_provider import OllamaProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_URL = "http://localhost:11434"
_MODEL = "llama3.2"


def _ollama_response(content: str = "Hello from Ollama") -> dict:
    """Minimal valid Ollama /api/chat response payload."""
    return {
        "model": _MODEL,
        "message": {"role": "assistant", "content": content},
        "done": True,
    }


_MESSAGES = [{"role": "user", "content": "Say hello."}]


# ---------------------------------------------------------------------------
# Constructor / property tests  (no network)
# ---------------------------------------------------------------------------


def test_provider_name():
    p = OllamaProvider()
    assert p.provider_name == "ollama"


def test_model_name():
    p = OllamaProvider(model="mistral")
    assert p.model_name == "mistral"


def test_model_name_default():
    p = OllamaProvider()
    assert p.model_name == "llama3.2"


def test_is_abstract_provider_subclass():
    assert issubclass(OllamaProvider, AbstractLLMProvider)


def test_default_base_url():
    p = OllamaProvider()
    assert p._base_url == "http://localhost:11434"


def test_base_url_trailing_slash_stripped():
    p = OllamaProvider(base_url="http://localhost:11434/")
    assert p._base_url == "http://localhost:11434"
    # URL built during chat() will be .../api/chat (no double slash)
    assert not p._base_url.endswith("/")


# ---------------------------------------------------------------------------
# Successful chat() tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_chat_returns_content_string(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        json=_ollama_response("Hi there!"),
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    result = await p.chat(_MESSAGES)
    assert result == "Hi there!"


@pytest.mark.anyio
async def test_chat_uses_correct_endpoint(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        json=_ollama_response(),
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    await p.chat(_MESSAGES)
    request = httpx_mock.get_request()
    assert request is not None
    assert str(request.url) == f"{_BASE_URL}/api/chat"


@pytest.mark.anyio
async def test_chat_passes_stream_false(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        json=_ollama_response(),
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    await p.chat(_MESSAGES)
    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["stream"] is False


@pytest.mark.anyio
async def test_chat_passes_temperature(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        json=_ollama_response(),
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    await p.chat(_MESSAGES, temperature=0.7)
    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["options"]["temperature"] == 0.7


@pytest.mark.anyio
async def test_chat_passes_max_tokens_as_num_predict(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        json=_ollama_response(),
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    await p.chat(_MESSAGES, max_tokens=512)
    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["options"]["num_predict"] == 512


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_chat_http_4xx_raises_llm_provider_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        status_code=422,
        text="Unprocessable Entity",
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.cause is not None
    assert isinstance(exc_info.value.cause, httpx.HTTPStatusError)


@pytest.mark.anyio
async def test_chat_http_5xx_raises_llm_provider_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        status_code=500,
        text="Internal Server Error",
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError):
        await p.chat(_MESSAGES)


@pytest.mark.anyio
async def test_chat_timeout_raises_llm_provider_error(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.TimeoutException("timed out"),
        method="POST",
        url=f"{_BASE_URL}/api/chat",
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.cause is not None


@pytest.mark.anyio
async def test_chat_connect_error_raises_llm_provider_error(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        method="POST",
        url=f"{_BASE_URL}/api/chat",
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.cause is not None


@pytest.mark.anyio
async def test_chat_empty_content_raises_llm_provider_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        json=_ollama_response(content=""),
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert "empty content" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_chat_missing_message_key_raises_llm_provider_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        json={"model": _MODEL, "done": True},  # "message" key missing
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.cause is not None


@pytest.mark.anyio
async def test_chat_invalid_json_raises_llm_provider_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        content=b"not valid json {{{",
        headers={"content-type": "application/json"},
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError):
        await p.chat(_MESSAGES)


@pytest.mark.anyio
async def test_raised_exception_is_not_httpx_type(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        status_code=503,
        text="Service Unavailable",
    )
    p = OllamaProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    # The raised type must be LLMProviderError, NOT any httpx.* type
    assert type(exc_info.value) is LLMProviderError
    assert not isinstance(exc_info.value, httpx.HTTPError)


# ---------------------------------------------------------------------------
# provider_name / model_name populated on error
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_error_carries_provider_and_model(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=f"{_BASE_URL}/api/chat",
        status_code=500,
        text="oops",
    )
    p = OllamaProvider(base_url=_BASE_URL, model="phi3")
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.provider == "ollama"
    assert exc_info.value.model == "phi3"
