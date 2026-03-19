"""Integration test for AnthropicProvider.

Requires a valid ANTHROPIC_API_KEY environment variable.
Skipped automatically in CI where the key is absent.

Run manually:
    ANTHROPIC_API_KEY=sk-ant-... pytest tests/integration/test_llm_anthropic.py -v
"""
from __future__ import annotations

import os

import pytest

from agent.llm.anthropic_provider import AnthropicProvider

_SKIP = not os.environ.get("ANTHROPIC_API_KEY")


@pytest.mark.skipif(_SKIP, reason="ANTHROPIC_API_KEY not set")
@pytest.mark.anyio
async def test_anthropic_smoke():
    """Live call to Anthropic Messages API — asserts non-empty reply."""
    api_key = os.environ["ANTHROPIC_API_KEY"]
    provider = AnthropicProvider(api_key=api_key)
    messages = [{"role": "user", "content": "Reply with the single word: pong"}]
    result = await provider.chat(messages, max_tokens=10)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
