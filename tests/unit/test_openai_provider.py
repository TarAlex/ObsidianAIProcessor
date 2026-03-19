"""Unit tests for agent/llm/openai_provider.py.

Uses pytest-httpx to mock httpx.AsyncClient without network I/O.
All async tests run via pytest-anyio (@pytest.mark.anyio).
"""
from __future__ import annotations

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

from agent.llm.base import AbstractLLMProvider, LLMProviderError
from agent.llm.openai_provider import OpenAIProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_API_KEY = "sk-test-key-abc123"
_BASE_URL = "https://api.openai.com"
_MODEL = "gpt-4o-mini"
_ENDPOINT = f"{_BASE_URL}/v1/chat/completions"
_MESSAGES = [{"role": "user", "content": "Say hello."}]


def _openai_response(content: str = "Hello from OpenAI") -> dict:
    """Minimal valid OpenAI /v1/chat/completions response payload."""
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


# ---------------------------------------------------------------------------
# Constructor / property tests  (no network)
# ---------------------------------------------------------------------------


def test_provider_name():
    p = OpenAIProvider(api_key=_API_KEY)
    assert p.provider_name == "openai"


def test_model_name():
    p = OpenAIProvider(model="gpt-4o", api_key=_API_KEY)
    assert p.model_name == "gpt-4o"


def test_model_name_default():
    p = OpenAIProvider(api_key=_API_KEY)
    assert p.model_name == "gpt-4o-mini"


def test_is_abstract_provider_subclass():
    assert issubclass(OpenAIProvider, AbstractLLMProvider)


def test_api_key_required_raises():
    with pytest.raises(ValueError, match="api_key is required"):
        OpenAIProvider(api_key="")


def test_api_key_required_no_arg():
    with pytest.raises(ValueError, match="api_key is required"):
        OpenAIProvider()


def test_base_url_trailing_slash():
    p = OpenAIProvider(base_url="https://api.openai.com/", api_key=_API_KEY)
    assert p._base_url == "https://api.openai.com"
    assert not p._base_url.endswith("/")


# ---------------------------------------------------------------------------
# Successful chat() tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_chat_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        json=_openai_response("Great response!"),
    )
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    result = await p.chat(_MESSAGES)
    assert result == "Great response!"


@pytest.mark.anyio
async def test_auth_header_always_sent(httpx_mock: HTTPXMock):
    """Authorization: Bearer header must always be present."""
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_openai_response())
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    await p.chat(_MESSAGES)
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers.get("authorization") == f"Bearer {_API_KEY}"


@pytest.mark.anyio
async def test_custom_base_url(httpx_mock: HTTPXMock):
    """Overriding base_url works (e.g. Azure OpenAI compatible endpoint)."""
    custom_base = "https://my-resource.openai.azure.com"
    custom_endpoint = f"{custom_base}/v1/chat/completions"
    httpx_mock.add_response(
        method="POST",
        url=custom_endpoint,
        json=_openai_response("Azure reply"),
    )
    p = OpenAIProvider(base_url=custom_base, model=_MODEL, api_key=_API_KEY)
    result = await p.chat(_MESSAGES)
    assert result == "Azure reply"


@pytest.mark.anyio
async def test_chat_passes_stream_false(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_openai_response())
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    await p.chat(_MESSAGES)
    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["stream"] is False


@pytest.mark.anyio
async def test_chat_passes_temperature(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_openai_response())
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    await p.chat(_MESSAGES, temperature=0.7)
    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["temperature"] == 0.7


@pytest.mark.anyio
async def test_chat_passes_max_tokens(httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=_ENDPOINT, json=_openai_response())
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
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
        json=_openai_response(content=""),
    )
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert "empty content" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_chat_http_error_401(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        status_code=401,
        text="Unauthorized",
    )
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert "401" in str(exc_info.value)
    assert exc_info.value.cause is not None
    assert isinstance(exc_info.value.cause, httpx.HTTPStatusError)


@pytest.mark.anyio
async def test_chat_http_error_429(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        status_code=429,
        text="Too Many Requests",
    )
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert "429" in str(exc_info.value)
    assert exc_info.value.cause is not None


@pytest.mark.anyio
async def test_chat_http_error_500(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        status_code=500,
        text="Internal Server Error",
    )
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert "500" in str(exc_info.value)
    assert exc_info.value.cause is not None


@pytest.mark.anyio
async def test_chat_timeout(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.TimeoutException("timed out"),
        method="POST",
        url=_ENDPOINT,
    )
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
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
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
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
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.cause is not None


# ---------------------------------------------------------------------------
# Error metadata tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_error_carries_provider_and_model(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        status_code=500,
        text="oops",
    )
    p = OpenAIProvider(base_url=_BASE_URL, model="gpt-4o", api_key=_API_KEY)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert exc_info.value.provider == "openai"
    assert exc_info.value.model == "gpt-4o"


@pytest.mark.anyio
async def test_raised_exception_is_not_httpx_type(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url=_ENDPOINT,
        status_code=500,
        text="Internal Server Error",
    )
    p = OpenAIProvider(base_url=_BASE_URL, model=_MODEL, api_key=_API_KEY)
    with pytest.raises(LLMProviderError) as exc_info:
        await p.chat(_MESSAGES)
    assert type(exc_info.value) is LLMProviderError
    assert not isinstance(exc_info.value, httpx.HTTPError)
