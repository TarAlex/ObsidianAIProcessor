"""Integration tests for OllamaProvider against a real Ollama instance.

Marked @pytest.mark.integration.
Auto-skipped if Ollama is not reachable at http://localhost:11434.

Run with:
    pytest tests/integration/test_llm_ollama.py -v -m integration
"""
from __future__ import annotations

import json

import httpx
import pytest
import anyio

from agent.llm.ollama_provider import OllamaProvider

_BASE_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Fixture: skip all tests if Ollama is not reachable
# ---------------------------------------------------------------------------


def _ollama_reachable() -> bool:
    try:
        resp = httpx.get(f"{_BASE_URL}/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def require_ollama():
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable at http://localhost:11434 — skipping integration tests")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ollama_reachable():
    """Smoke test: GET /api/tags returns 200."""
    resp = httpx.get(f"{_BASE_URL}/api/tags", timeout=5.0)
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_chat_returns_nonempty_string():
    p = OllamaProvider(base_url=_BASE_URL)
    result = await p.chat([{"role": "user", "content": "Say hello."}])
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.anyio
async def test_chat_returns_parseable_json_for_classify_system_prompt():
    p = OllamaProvider(base_url=_BASE_URL)
    messages = [
        {"role": "system", "content": "Respond ONLY with valid JSON. No other text."},
        {"role": "user", "content": 'Return exactly: {"status": "ok"}'},
    ]
    result = await p.chat(messages, temperature=0.0)
    # Result should be parseable as JSON (or at least contain JSON)
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_provider_name_and_model_name_populated():
    p = OllamaProvider(base_url=_BASE_URL)
    assert p.provider_name == "ollama"
    assert isinstance(p.model_name, str)
    assert len(p.model_name) > 0
