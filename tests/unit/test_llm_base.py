"""Unit tests for agent/llm/base.py (AbstractLLMProvider + LLMProviderError)."""
from __future__ import annotations

import inspect

import pytest

from agent.llm.base import AbstractLLMProvider, LLMProviderError


# ---------------------------------------------------------------------------
# Helpers — minimal concrete stub used across multiple tests
# ---------------------------------------------------------------------------


class _ConcreteStub(AbstractLLMProvider):
    """Fully-implemented stub — satisfies the entire ABC contract."""

    @property
    def model_name(self) -> str:
        return "stub-model"

    @property
    def provider_name(self) -> str:
        return "stub"

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        return "stub reply"


# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------


def test_abstract_class_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractLLMProvider()  # type: ignore[abstract]


def test_subclass_missing_chat_raises():
    class _NoChatProvider(AbstractLLMProvider):
        @property
        def model_name(self) -> str:
            return "x"

        @property
        def provider_name(self) -> str:
            return "x"

    with pytest.raises(TypeError):
        _NoChatProvider()


def test_subclass_missing_model_name_raises():
    class _NoModelName(AbstractLLMProvider):
        @property
        def provider_name(self) -> str:
            return "x"

        async def chat(self, messages, temperature=0.0, max_tokens=2000) -> str:
            return ""

    with pytest.raises(TypeError):
        _NoModelName()


def test_subclass_missing_provider_name_raises():
    class _NoProviderName(AbstractLLMProvider):
        @property
        def model_name(self) -> str:
            return "x"

        async def chat(self, messages, temperature=0.0, max_tokens=2000) -> str:
            return ""

    with pytest.raises(TypeError):
        _NoProviderName()


# ---------------------------------------------------------------------------
# Valid concrete subclass
# ---------------------------------------------------------------------------


def test_minimal_concrete_subclass_valid():
    stub = _ConcreteStub()
    assert isinstance(stub.model_name, str)
    assert isinstance(stub.provider_name, str)
    assert inspect.iscoroutinefunction(stub.chat)


def test_chat_is_coroutine_function():
    assert inspect.iscoroutinefunction(_ConcreteStub.chat)


# ---------------------------------------------------------------------------
# LLMProviderError
# ---------------------------------------------------------------------------


def test_llm_provider_error_is_exception():
    assert issubclass(LLMProviderError, Exception)


def test_llm_provider_error_stores_fields():
    cause = ValueError("underlying")
    err = LLMProviderError("msg", provider="ollama", model="llama3", cause=cause)

    assert str(err) == "msg"
    assert err.provider == "ollama"
    assert err.model == "llama3"
    assert err.cause is cause


def test_llm_provider_error_defaults():
    err = LLMProviderError("bare message")
    assert err.provider == ""
    assert err.model == ""
    assert err.cause is None
