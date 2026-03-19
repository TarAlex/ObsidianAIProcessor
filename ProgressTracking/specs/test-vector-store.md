# Spec: tests/unit/test_vector_store.py
slug: test-vector-store
layer: tests
phase: 1
arch_section: §15 Vector Store, §14 Embedder, §17 Testing Strategy

---

## Problem statement

`agent/vector/store.py` (`VectorStore`) and `agent/vector/embedder.py`
(`Embedder`) form the deduplication backing for Stage 5. `VectorStore` wraps
ChromaDB; `Embedder` wraps the Ollama embeddings HTTP endpoint. Both need
isolated unit tests that verify the public contract without requiring a live
Ollama or ChromaDB server.

**Current state:** `tests/unit/test_vector_store.py` exists on disk with all 8
required test cases (5 for `VectorStore`, 3 for `Embedder`). The `/plan`
session confirms full coverage against `store-py.md` and `embedder-py.md`.
Proceed to `/review tests/unit/test_vector_store.py`.

---

## Module contract

Inputs:
- `agent.vector.store.VectorStore` (DONE) — PersistentClient backed by `tmp_path`
- `agent.vector.embedder.Embedder`, `EmbedderError` (DONE) — mocked via `pytest-httpx`

Output: 8 passing pytest tests; `pytest tests/unit/test_vector_store.py` exits 0.

---

## Key implementation notes

### 1. Test strategy: two isolation modes

**VectorStore (tests 1–5)** — real `PersistentClient` backed by `tmp_path / "chroma"`.
No mocks for the store itself; ChromaDB operates against an on-disk directory that
pytest cleans up automatically. All async calls driven by `anyio.run(...)`.

**Embedder (tests 6–8)** — `pytest-httpx` (`HTTPXMock`) mocks the Ollama HTTP
endpoint at `http://127.0.0.1:11434/api/embeddings`. Tests 6–7 use
`@pytest.mark.anyio`; test 8 is synchronous (constructor-only inspection).

### 2. Test vectors

```python
_VEC_A = [1.0, 0.0, 0.0]   # unit vector along X
_VEC_B = [0.0, 1.0, 0.0]   # unit vector along Y
_VEC_C = [0.7071, 0.7071, 0.0]  # 45° from A and B
```

Cosine similarity of identical unit vectors = 1.0; orthogonal = 0.0.

### 3. Test cases present

| # | Test | Component | What it verifies |
|---|---|---|---|
| 1 | `test_add_and_search_returns_similarity` | VectorStore | `add` + `similarity_search` same vec → `score ≈ 1.0`, `doc_id` matches |
| 2 | `test_search_empty_store` | VectorStore | Fresh store returns `[]` without raising |
| 3 | `test_add_twice_upserts` | VectorStore | `add(same_id)` twice → no error, exactly 1 result |
| 4 | `test_delete_removes_doc` | VectorStore | `add` → `delete` → `similarity_search` returns `[]` |
| 5 | `test_score_is_similarity_not_distance` | VectorStore | Identical vec → `score >= 0.99` (similarity, not raw distance) |
| 6 | `test_embedder_sends_correct_payload` | Embedder | HTTP POST body contains `model` and `prompt` keys; `prompt == "hello world"` |
| 7 | `test_embedder_raises_on_http_error` | Embedder | HTTP 500 → raises `EmbedderError` |
| 8 | `test_embedder_base_url_from_env` | Embedder | `OLLAMA_BASE_URL` env var sets `_base_url` on constructor |

### 4. Key assertions

- Test 5 specifically checks `score >= 0.99` (not `== 1.0`) to allow for ChromaDB
  floating-point precision tolerance.
- Test 1 uses `pytest.approx(1.0, abs=0.01)` for the same reason.
- Tests 6–7 use `@pytest.mark.anyio` because `Embedder.embed` is `async def`.

### 5. Cross-cutting constraints

- `pytest-httpx` required (`pip install pytest-httpx`); listed in `pyproject.toml` dev deps
- `anyio` used for VectorStore sync wrappers and `@pytest.mark.anyio` for Embedder
- No hardcoded Ollama URL in test assertions beyond `_OLLAMA_URL` constant
- `monkeypatch.setenv` used for env-var test (test 8) — no `os.environ` mutation

---

## Data model changes

None — pure test module.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_vector_store.py` (file exists — all 8 cases present)

See table above.

### integration

`tests/integration/test_pipeline_dedup.py` — live ChromaDB + Ollama (deferred,
not in current tracker). `test_pipeline_youtube.py` and `test_pipeline_pdf.py`
provide end-to-end coverage of Stage 5 deduplication path.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `s5_deduplicate.py` stage logic | Separate test file (`test_s5_deduplicate.py`) |
| Multiple ChromaDB collections | Phase 2 |
| `anyio.to_thread` wrapping | Not required at single-file throughput |
| Embedder model configuration (non-env) | Config-driven provider selection is `provider_factory.py` scope |

---

## Open questions

None. `store-py.md` §Tests required maps 1:1 to tests 1–5; `embedder-py.md`
covers tests 6–8. All 8 cases are present in the file.
Proceed directly to `/review tests/unit/test_vector_store.py`.
