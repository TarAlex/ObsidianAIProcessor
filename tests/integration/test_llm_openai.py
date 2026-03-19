"""Integration test for OpenAIProvider.

Requires a valid OPENAI_API_KEY environment variable.
Skipped automatically in CI where the key is absent.

Run manually:
    OPENAI_API_KEY=sk-... pytest tests/integration/test_llm_openai.py -v
"""
from __future__ import annotations

import os

import pytest

from agent.llm.openai_provider import OpenAIProvider

_SKIP = not os.environ.get("OPENAI_API_KEY")


@pytest.mark.skipif(_SKIP, reason="OPENAI_API_KEY not set")
@pytest.mark.anyio
async def test_openai_smoke():
    """Live call to OpenAI /v1/chat/completions — asserts non-empty reply."""
    api_key = os.environ["OPENAI_API_KEY"]
    provider = OpenAIProvider(api_key=api_key)
    messages = [{"role": "user", "content": "Reply with the single word: pong"}]
    result = await provider.chat(messages, max_tokens=10)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
