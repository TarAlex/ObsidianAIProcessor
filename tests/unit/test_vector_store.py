"""Unit tests for agent/vector/store.py and agent/vector/embedder.py.

VectorStore tests use a real PersistentClient backed by tmp_path — no mocks.
Embedder tests use pytest-httpx to mock the Ollama HTTP endpoint.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import anyio
import pytest
from pytest_httpx import HTTPXMock

from agent.vector.embedder import Embedder, EmbedderError
from agent.vector.store import VectorStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VEC_A = [1.0, 0.0, 0.0]
_VEC_B = [0.0, 1.0, 0.0]
_VEC_C = [0.7071, 0.7071, 0.0]   # 45° from A, 45° from B

_OLLAMA_URL = "http://127.0.0.1:11434/api/embeddings"


def _make_store(tmp_path: Path) -> VectorStore:
    return VectorStore(tmp_path / "chroma")


# ---------------------------------------------------------------------------
# Test 1 — add and search returns similarity ≈ 1.0
# ---------------------------------------------------------------------------


def test_add_and_search_returns_similarity(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def _go():
        await store.add("doc-1", _VEC_A, {"note": "test"})
        results = await store.similarity_search(_VEC_A, n_results=1)
        return results

    results = anyio.run(_go)
    assert len(results) == 1
    assert results[0]["doc_id"] == "doc-1"
    assert results[0]["score"] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# Test 2 — search empty store returns []
# ---------------------------------------------------------------------------


def test_search_empty_store(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    results = anyio.run(store.similarity_search, _VEC_A, 5)
    assert results == []


# ---------------------------------------------------------------------------
# Test 3 — add twice upserts (no error, 1 result)
# ---------------------------------------------------------------------------


def test_add_twice_upserts(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def _go():
        await store.add("doc-1", _VEC_A, {"v": "first"})
        await store.add("doc-1", _VEC_B, {"v": "second"})
        return await store.similarity_search(_VEC_B, n_results=5)

    results = anyio.run(_go)
    assert len(results) == 1
    assert results[0]["doc_id"] == "doc-1"


# ---------------------------------------------------------------------------
# Test 4 — delete removes doc
# ---------------------------------------------------------------------------


def test_delete_removes_doc(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def _go():
        await store.add("doc-1", _VEC_A, {"note": "test"})
        await store.delete("doc-1")
        return await store.similarity_search(_VEC_A, n_results=5)

    results = anyio.run(_go)
    assert results == []


# ---------------------------------------------------------------------------
# Test 5 — score is similarity, not distance (identical vectors ≥ 0.99)
# ---------------------------------------------------------------------------


def test_score_is_similarity_not_distance(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    async def _go():
        await store.add("doc-1", _VEC_A, {"note": "test"})
        return await store.similarity_search(_VEC_A, n_results=1)

    results = anyio.run(_go)
    assert len(results) == 1
    assert results[0]["score"] >= 0.99


# ---------------------------------------------------------------------------
# Test 6 — embedder sends correct payload (model + prompt keys)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_embedder_sends_correct_payload(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_OLLAMA_URL,
        json={"embedding": [0.1, 0.2, 0.3]},
    )
    embedder = Embedder()
    await embedder.embed("hello world")

    request = httpx_mock.get_request()
    assert request is not None
    body = json.loads(request.content)
    assert "model" in body
    assert "prompt" in body
    assert body["prompt"] == "hello world"


# ---------------------------------------------------------------------------
# Test 7 — embedder raises EmbedderError on HTTP 500
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_embedder_raises_on_http_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_OLLAMA_URL,
        status_code=500,
        text="Internal Server Error",
    )
    embedder = Embedder()
    with pytest.raises(EmbedderError):
        await embedder.embed("test text")


# ---------------------------------------------------------------------------
# Test 8 — embedder base_url from OLLAMA_BASE_URL env var
# ---------------------------------------------------------------------------


def test_embedder_base_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom:11434")
    embedder = Embedder()
    assert embedder._base_url == "http://custom:11434"
