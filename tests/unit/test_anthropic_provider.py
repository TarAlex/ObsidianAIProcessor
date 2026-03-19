"""Unit tests for agent/llm/anthropic_provider.py.

Uses unittest.mock to patch anthropic.AsyncAnthropic without network I/O.
All async tests run via pytest-anyio (@pytest.mark.anyio).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import anthropic
import pytest

from agent.llm.base import AbstractLLMProvider, LLMProviderError
from agent.llm.anthropic_provider import AnthropicProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_API_KEY = "sk-ant-test-key-abc123"
_MODEL = "claude-sonnet-4-6"
_MESSAGES = [{"role": "user", "content": "Say hello."}]
_MESSAGES_WITH_SYSTEM = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Say hello."},
]
_FAKE_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _make_mock_message(text: str = "Hello from Anthropic") -> MagicMock:
    """Build a fake Anthropic Message with content[0].text set."""
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _make_mock_ctx(text: str = "Hello from Anthropic"):
    """Return (mock_client, mock_ctx_manager) pair ready for patching."""
    mock_message = _make_mock_message(text)
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_client, mock_ctx


def _make_status_error(status_code: int, cls=anthropic.APIStatusError) -> anthropic.APIStatusError:
    """Build a real APIStatusError (or subclass) instance."""
    response = httpx.Response(
        status_code,
        request=_FAKE_REQUEST,
        text="error body",
    )
    return cls(f"status {status_code}", response=response, body=None)


# ---------------------------------------------------------------------------
# Constructor / property tests  (no network)
# ---------------------------------------------------------------------------


def test_provider_name():
    p = AnthropicProvider(api_key=_API_KEY)
    assert p.provider_name == "anthropic"


def test_model_name():
    p = AnthropicProvider(model="claude-3-opus-20240229", api_key=_API_KEY)
    assert p.model_name == "claude-3-opus-20240229"


def test_model_name_default():
    p = AnthropicProvider(api_key=_API_KEY)
    assert p.model_name == "claude-sonnet-4-6"


def test_is_abstract_provider_subclass():
    assert issubclass(AnthropicProvider, AbstractLLMProvider)


def test_api_key_required_raises():
    with pytest.raises(ValueError, match="api_key is required"):
        AnthropicProvider(api_key="")


def test_api_key_required_no_arg():
    with pytest.raises(ValueError, match="api_key is required"):
        AnthropicProvider()


# ---------------------------------------------------------------------------
# Successful chat() tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_chat_success():
    _, mock_ctx = _make_mock_ctx("Great response!")
    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        result = await p.chat(_MESSAGES)
    assert result == "Great response!"


@pytest.mark.anyio
async def test_chat_system_extracted():
    """System message must be passed as system= kwarg, not in messages list."""
    mock_client, mock_ctx = _make_mock_ctx("Hi!")
    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        await p.chat(_MESSAGES_WITH_SYSTEM)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    # system= top-level param is present
    assert call_kwargs["system"] == "You are a helpful assistant."
    # messages list contains only the user message, not the system one
    assert all(m["role"] != "system" for m in call_kwargs["messages"])
    assert len(call_kwargs["messages"]) == 1


@pytest.mark.anyio
async def test_chat_no_system_message():
    """When no system message is present, system= kwarg must be absent."""
    mock_client, mock_ctx = _make_mock_ctx("Hi!")
    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        await p.chat(_MESSAGES)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "system" not in call_kwargs


@pytest.mark.anyio
async def test_temperature_and_max_tokens_passed():
    """temperature and max_tokens must be forwarded to the SDK call."""
    mock_client, mock_ctx = _make_mock_ctx()
    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        await p.chat(_MESSAGES, temperature=0.7, max_tokens=512)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["temperature"] == 0.7
    assert call_kwargs["max_tokens"] == 512


@pytest.mark.anyio
async def test_max_retries_zero():
    """SDK must be instantiated with max_retries=0 (no internal retry)."""
    _, mock_ctx = _make_mock_ctx()
    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx) as MockClass:
        p = AnthropicProvider(api_key=_API_KEY, timeout=30.0)
        await p.chat(_MESSAGES)

    MockClass.assert_called_once_with(
        api_key=_API_KEY,
        timeout=30.0,
        max_retries=0,
    )


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_chat_empty_content():
    _, mock_ctx = _make_mock_ctx(text="")
    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)
    assert "empty content" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_chat_auth_error():
    """anthropic.AuthenticationError (401) → LLMProviderError with status."""
    mock_client, mock_ctx = _make_mock_ctx()
    exc = _make_status_error(401, anthropic.AuthenticationError)
    mock_client.messages.create.side_effect = exc

    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)

    assert "401" in str(exc_info.value)
    assert exc_info.value.cause is exc


@pytest.mark.anyio
async def test_chat_rate_limit():
    """anthropic.RateLimitError (429) → LLMProviderError."""
    mock_client, mock_ctx = _make_mock_ctx()
    exc = _make_status_error(429, anthropic.RateLimitError)
    mock_client.messages.create.side_effect = exc

    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)

    assert "429" in str(exc_info.value)
    assert exc_info.value.cause is exc


@pytest.mark.anyio
async def test_chat_api_status_error():
    """Generic APIStatusError (500) → LLMProviderError."""
    mock_client, mock_ctx = _make_mock_ctx()
    exc = _make_status_error(500, anthropic.APIStatusError)
    mock_client.messages.create.side_effect = exc

    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)

    assert "500" in str(exc_info.value)
    assert exc_info.value.cause is exc


@pytest.mark.anyio
async def test_chat_connection_error():
    """anthropic.APIConnectionError → LLMProviderError."""
    mock_client, mock_ctx = _make_mock_ctx()
    exc = anthropic.APIConnectionError(request=_FAKE_REQUEST)
    mock_client.messages.create.side_effect = exc

    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)

    assert exc_info.value.cause is exc


@pytest.mark.anyio
async def test_chat_timeout_error():
    """anthropic.APITimeoutError → LLMProviderError (subclass of APIConnectionError)."""
    mock_client, mock_ctx = _make_mock_ctx()
    exc = anthropic.APITimeoutError(request=_FAKE_REQUEST)
    mock_client.messages.create.side_effect = exc

    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)

    assert exc_info.value.cause is exc


@pytest.mark.anyio
async def test_chat_malformed_response():
    """IndexError on message.content[0] → LLMProviderError."""
    mock_message = MagicMock()
    mock_message.content = []  # empty list → IndexError on [0]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)

    assert "parsing failed" in str(exc_info.value).lower()
    assert isinstance(exc_info.value.cause, IndexError)


# ---------------------------------------------------------------------------
# Error metadata tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_error_carries_provider_and_model():
    mock_client, mock_ctx = _make_mock_ctx()
    exc = _make_status_error(500, anthropic.APIStatusError)
    mock_client.messages.create.side_effect = exc

    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(model="claude-3-opus-20240229", api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)

    assert exc_info.value.provider == "anthropic"
    assert exc_info.value.model == "claude-3-opus-20240229"


@pytest.mark.anyio
async def test_raised_exception_is_not_anthropic_type():
    mock_client, mock_ctx = _make_mock_ctx()
    exc = _make_status_error(500, anthropic.APIStatusError)
    mock_client.messages.create.side_effect = exc

    with patch("anthropic.AsyncAnthropic", return_value=mock_ctx):
        p = AnthropicProvider(api_key=_API_KEY)
        with pytest.raises(LLMProviderError) as exc_info:
            await p.chat(_MESSAGES)

    assert type(exc_info.value) is LLMProviderError
    assert not isinstance(exc_info.value, anthropic.APIError)
