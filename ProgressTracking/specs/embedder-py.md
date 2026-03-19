# Spec: embedder.py
slug: embedder-py
layer: vector
phase: 1
arch_section: §15 Vector Store

---

## Problem statement

Stage 5 (`s5_deduplicate.py`) requires a semantic similarity check before persisting a
new note. The similarity check compares the incoming content against the ChromaDB
vector store by first converting raw text into a floating-point embedding vector.
`embedder.py` is the standalone HTTP client that performs that conversion by calling
the locally-running Ollama `/api/embeddings` endpoint. It must be async, raise a typed
error on any failure, and never hard-code credentials or endpoint URLs.

**Note:** This module was implemented as a pre-built transitive dependency of
`s5_deduplicate.py`. The implementation is complete. This spec formalises the design
for `/review` → `/done`.

---

## Module contract

**File**: `agent/vector/embedder.py`

**Input**: `text: str` — raw text to embed (title + body concat from the pipeline)

**Output**: `list[float]` — normalised embedding vector returned by Ollama

**Error surface**:
- `EmbedderError(Exception)` — raised on any `httpx.HTTPStatusError` or unexpected
  exception inside `embed()`; the pipeline lets this propagate to error routing.

### Public API

```python
class EmbedderError(Exception): ...

class Embedder:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "nomic-embed-text",
    ) -> None: ...

    async def embed(self, text: str) -> list[float]: ...
```

**Constructor behaviour**:
- Reads `OLLAMA_BASE_URL` env var; falls back to constructor `base_url` parameter.
- Strips any trailing `/` from the resolved base URL.
- Stores model name as `self._model`.

**`embed()` behaviour**:
- Builds `POST <base_url>/api/embeddings` with JSON payload
  `{"model": self._model, "prompt": text}`.
- Opens a fresh `httpx.AsyncClient(timeout=30.0)` per call — no shared client state.
- Calls `response.raise_for_status()` to trigger `httpx.HTTPStatusError` on 4xx/5xx.
- Returns `response.json()["embedding"]` as `list[float]`.
- On `httpx.HTTPStatusError`: re-raises as `EmbedderError(f"HTTP {status}: ...")`.
- On any other exception: wraps and re-raises as `EmbedderError(str(exc))`.

---

## Key implementation notes

1. **Privacy-first default**: `nomic-embed-text` is a local Ollama model — no data
   leaves the machine unless the caller overrides `base_url` or `OLLAMA_BASE_URL`.

2. **No shared client state**: A new `httpx.AsyncClient` is created inside each `embed()`
   call. This avoids stale connection pool issues in long-running pipeline processes at
   the cost of a TCP handshake per call. Acceptable for per-file pipeline throughput.

3. **No `ProviderFactory` routing**: Embedding is a separate concern from text
   generation. The embedder calls Ollama directly rather than going through
   `ProviderFactory` — this is by design for Phase 1 (see Scope section).

4. **`anyio` compatibility**: The caller (`s5_deduplicate.py`) is an `async def` coroutine
   orchestrated by `anyio`. `httpx.AsyncClient` is fully compatible with any asyncio-
   backed event loop; no additional wrappers needed.

5. **`__all__`**: Exports `["Embedder", "EmbedderError"]` for clean star-import guard.

---

## Data model changes

None. `embedder.py` has no Pydantic models; it returns a plain `list[float]`.

---

## LLM prompt file needed

None. This module makes HTTP calls to an embedding endpoint, not to a text-generation
LLM via `ProviderFactory`.

---

## Tests required

**Unit**: `tests/unit/test_vector_store.py` — tests 6–8 cover embedder:

| # | Test | What it checks |
|---|------|----------------|
| 6 | `test_embedder_sends_correct_payload` | POST payload contains `"model"` and `"prompt"` keys; `"prompt"` matches input text |
| 7 | `test_embedder_raises_on_http_error` | HTTP 500 response → `EmbedderError` raised |
| 8 | `test_embedder_base_url_from_env` | `OLLAMA_BASE_URL` env var overrides constructor default |

**Test tooling**: `pytest-httpx` (`HTTPXMock`) mocks the Ollama HTTP endpoint.
Tests 6–7 are `@pytest.mark.anyio` async tests. Test 8 is synchronous (constructor only).

**Integration**: None required in Phase 1. A live Ollama integration test would require
a running Ollama instance and is deferred to `tests/integration/test_llm_ollama.py`.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Cloud embedding providers (OpenAI, Cohere, etc.) | Phase 2 only |
| Embedding model routing via `ProviderFactory` | Not wired in Phase 1 |
| Batch embedding (`embed_many`) | Not needed for single-file pipeline throughput |
| Connection pool / keep-alive `AsyncClient` | Not required at current throughput |
| Configuring `model` via `AgentConfig` YAML | Deferred; constructor default covers Phase 1 |
| Retry / backoff on transient failures | Not in Phase 1 scope |
| Embedding dimensionality validation | ChromaDB enforces consistency at upsert time |

---

## Open questions

None. Implementation is complete and matches this spec exactly.
