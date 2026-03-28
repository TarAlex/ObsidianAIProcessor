"""Tests for GeminiProvider."""
from __future__ import annotations

import pytest

from agent.llm.gemini_provider import GeminiProvider


def test_gemini_requires_api_key() -> None:
    with pytest.raises(ValueError, match="api_key"):
        GeminiProvider(api_key="")


def test_gemini_provider_name() -> None:
    p = GeminiProvider(model="gemini-2.0-flash", api_key="x")
    assert p.provider_name == "gemini"
    assert p.model_name == "gemini-2.0-flash"
