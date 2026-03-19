"""Unit tests for agent/llm/lmstudio_provider.py.

Uses pytest-httpx to mock httpx.AsyncClient without network I/O.
All async tests run via pytest-anyio (@pytest.mark.anyio).
"""
from __future__ import annotations

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

from agent.llm.base import AbstractLLMProvider, LLMProviderError
from agent.llm.lmstudio_provider import LMStudioProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_URL = "http://localhost:1234"
_MODEL = "local-model"


def _lmstudio_response(content: str = "Hello from LM Studio") -> dict:
    """Minimal valid LM Studio /v1/chat/completions response payload."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }
        ]
    }


_MESSAGES = [{"role": "user", "content": "Say hello."}]
_ENDPOINT = f"{_BASE_URL}/v1/chat/completions"


# ---------------------------------------------------------------------------
# Constructor / property tests  (no network)
# ---------------------------------------------------------------------------


def test_provider_name():
    p = LMStudioProvider()
    assert p.provider_name == "lmstudio"


def test_model_name():
    p = LMStudioProvider(model="mistral-7b")
    assert p.model_name == "mistral-7b"


def test_model_name_default():
    p = LMStudioProvider()
    assert p.model_name == "local-model"


def test_is_abstract_provider_subclass():
    assert issubclass(LMStudioProvider, AbstractLLMProvider)


def test_default_base_url():
    p = LMStudioProvider()
    assert p._base_url == "http://localhost:1234"


def test_base_url_trailing_slash():
    p = LMStudioProvider(base_url="http://localhost:1234/")
    assert p._base_url == "http://localhost:1234"
    assert not p._base_url.endswith("/")


# ---------------------------------------------------------------------------
# Successful chat() tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_chat_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        json=_lmstudio_response("Great response!"),
    )
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    result = await p.chat(_MESSAGES)
    assert result == "Great response!"


@pytest.mark.anyio
async def test_chat_uses_correct_endpoint(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_lmstudio_response())
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    await p.chat(_MESSAGES)
    request = httpx_mock.get_request()
    assert request is not None
    assert str(request.url) == _ENDPOINT


@pytest.mark.anyio
async def test_chat_passes_stream_false(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_lmstudio_response())
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    await p.chat(_MESSAGES)
    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["stream"] is False


@pytest.mark.anyio
async def test_chat_passes_temperature(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_lmstudio_response())
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    await p.chat(_MESSAGES, temperature=0.7)
    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["temperature"] == 0.7


@pytest.mark.anyio
async def test_chat_passes_max_tokens(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_lmstudio_response())
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    await p.chat(_MESSAGES, max_tokens=512)
    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["max_tokens"] == 512


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_chat_empty_content(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        json=_lmstudio_response(content=""),
    )
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert "empty content" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_chat_http_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        status_code=503,
        text="Service Unavailable",
    )
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert "503" in str(exc_info.value)
    assert exc_info.value.cause is not None
    assert isinstance(exc_info.value.cause, httpx.HTTPStatusError)


@pytest.mark.anyio
async def test_chat_timeout(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.TimeoutException("timed out"),
        method="POST",
        url=_ENDPOINT,
    )
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.cause is not None


@pytest.mark.anyio
async def test_chat_request_error(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        method="POST",
        url=_ENDPOINT,
    )
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.cause is not None


@pytest.mark.anyio
async def test_chat_malformed_json(httpx_mock: HTTPXMock):
    """Missing 'choices' key → KeyError → LLMProviderError."""
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        json={"model": _MODEL},  # no "choices" key
    )
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.cause is not None


@pytest.mark.anyio
async def test_chat_invalid_json_body(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        content=b"not valid json {{{",
        headers={"content-type": "application/json"},
    )
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError):
        await p.chat(_MESSAGES)


@pytest.mark.anyio
async def test_raised_exception_is_not_httpx_type(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        status_code=500,
        text="Internal Server Error",
    )
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert type(exc_info.value) is LLMProviderError
    assert not isinstance(exc_info.value, httpx.HTTPError)


# ---------------------------------------------------------------------------
# API key header tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_api_key_header_sent(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_lmstudio_response())
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL, api_key="sk-test-key")
    await p.chat(_MESSAGES)
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers.get("authorization") == "Bearer sk-test-key"


@pytest.mark.anyio
async def test_no_api_key_no_header(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_lmstudio_response())
    p = LMStudioProvider(base_url=_BASE_URL, model=_MODEL, api_key="")
    await p.chat(_MESSAGES)
    request = httpx_mock.get_request()
    assert request is not None
    assert "authorization" not in request.headers


# ---------------------------------------------------------------------------
# provider_name / model_name populated on error
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_error_carries_provider_and_model(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        status_code=500,
        text="oops",
    )
    p = LMStudioProvider(base_url=_BASE_URL, model="phi-3")
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.provider == "lmstudio"
    assert exc_info.value.model == "phi-3"
