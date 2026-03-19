"""Integration test for LMStudioProvider.

Requires a running LM Studio instance. Skipped in CI unless LMSTUDIO_URL is set.

Usage:
    LMSTUDIO_URL=http://localhost:1234 pytest tests/integration/test_llm_lmstudio.py -v
"""
from __future__ import annotations

import os

import pytest

from agent.llm.lmstudio_provider import LMStudioProvider

_LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "")


@pytest.mark.skipif(
    not _LMSTUDIO_URL,
    reason="LMSTUDIO_URL not set — skipped in CI",
)
@pytest.mark.anyio
async def test_lmstudio_live_smoke():
    """POST a minimal prompt to a live LM Studio instance and assert non-empty reply."""
    provider = LMStudioProvider(base_url=_LMSTUDIO_URL)
    messages = [{"role": "user", "content": "Reply with the single word: hello"}]
    result = await provider.chat(messages, temperature=0.0, max_tokens=10)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
