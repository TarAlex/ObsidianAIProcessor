# Feature Spec: Vector Store
slug: feature-vector-store
sections_covered: [ProgressTracking/tasks/08_vector-store.md]
arch_sections: [§15]

---

## Scope

The vector store layer provides **semantic similarity infrastructure** for Stage 5
(deduplication). It consists of two modules: an embedding client (`embedder.py`) that
calls the Ollama `/api/embeddings` endpoint, and a ChromaDB-backed persistence layer
(`store.py`) that handles upsert, cosine-similarity search, and delete.

Both modules are already implemented as pre-built dependencies of `s5_deduplicate.py`
(which is `IN_PROGRESS`). The `/plan` sessions for this section should produce specs
that document the existing implementations so that `/review` → `/done` can close
the TRACKER items cleanly.

**Phase 1 scope only**: local Ollama embeddings + local ChromaDB. No cloud embedding
providers, no multi-collection strategy, no Phase-2 atom indexing.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `agent/vector/embedder.py` | `embedder-py` | `agent/core/config.py` (DONE) | vector |
| 2 | `agent/vector/store.py` | `store-py` | `embedder-py`, `agent/core/config.py` (DONE) | vector |

---

## Cross-cutting constraints

| Rule | Detail |
|---|---|
| Async API | All public methods are `async` — synchronous ChromaDB calls wrapped in `async def` for pipeline compatibility |
| No hardcoded paths | ChromaDB `persist_directory` always resolved from `AgentConfig`; default is `<vault_root>/.chroma` |
| No hardcoded API keys | Embedder base URL read from `OLLAMA_BASE_URL` env var (falls back to `http://127.0.0.1:11434`) |
| Privacy-first | Default embedding model is `nomic-embed-text` via local Ollama — no cloud calls |
| Single collection | One `"knowledge_notes"` collection with `hnsw:space=cosine` — no multi-collection in Phase 1 |
| Upsert semantics | `add()` silently overwrites on duplicate `doc_id` — idempotent for pipeline retries |
| Error surface | `EmbedderError` for any HTTP or parsing failure; `VectorStore` errors propagate uncaught to pipeline |
| anyio compatibility | Tests use `anyio.run(...)` — no raw `asyncio.run()` |

---

## Implementation ordering rationale

`embedder.py` must precede `store.py`: the store has no internal embedding logic and
`s5_deduplicate.py` calls `embedder.embed()` first, then passes the vector to
`store.similarity_search()`. Configuration (`config.py`) is already DONE and provides
`vault.root`, `vault.merge_threshold` (0.80), and `vault.related_threshold` (0.60)
that the deduplication stage reads — the vector modules themselves read only the
persist path from config.

Both modules were built ahead of their TRACKER items as transitive dependencies of
`s5_deduplicate.py`. The implementation is complete; this spec formalises the design
for `/review` and `/done`.

---

## Module details

### 1. `embedder-py` — Ollama embedding client

**File**: `agent/vector/embedder.py`
**Status**: Already implemented
**Public surface**:

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

**Behaviour**:
- `__init__`: reads `OLLAMA_BASE_URL` env var; falls back to constructor `base_url`
- `embed(text)`: POSTs `{"model": model, "prompt": text}` to `<base_url>/api/embeddings`;
  raises `EmbedderError` on any `httpx.HTTPStatusError` or unexpected exception
- Uses `httpx.AsyncClient(timeout=30.0)` — connection created per call (no shared client state)

**Test coverage**: `tests/unit/test_vector_store.py` tests 6–8 (payload format, HTTP 500,
env var override) via `pytest-httpx` mock.

---

### 2. `store-py` — ChromaDB vector store

**File**: `agent/vector/store.py`
**Status**: Already implemented
**Public surface**:

```python
class VectorStore:
    COLLECTION = "knowledge_notes"

    def __init__(self, persist_directory: str | Path) -> None: ...

    async def add(
        self,
        doc_id: str,
        embedding: list[float],
        metadata: dict,
    ) -> None: ...

    async def similarity_search(
        self,
        embedding: list[float],
        n_results: int = 5,
    ) -> list[dict]: ...

    async def delete(self, doc_id: str) -> None: ...
```

**Behaviour**:
- `__init__`: opens/creates `chromadb.PersistentClient` at `persist_directory`;
  calls `get_or_create_collection("knowledge_notes", metadata={"hnsw:space": "cosine"})`
- `add`: calls `collection.upsert(ids=[doc_id], embeddings=[embedding], metadatas=[metadata])` — idempotent
- `similarity_search`: guards `count == 0` → returns `[]`; clamps `n_results` to `count`;
  converts ChromaDB cosine **distance** to **similarity** via `score = 1.0 - distance`
- `delete`: catches all exceptions silently (no-op if doc_id not found)
- Each result dict: `{"doc_id": str, "score": float, "metadata": dict}`

**Test coverage**: `tests/unit/test_vector_store.py` tests 1–5 (add+search, empty store,
upsert, delete, score-is-similarity) against a real `tmp_path`-backed PersistentClient.

---

## Excluded (Phase 2 or out of scope)

| Item | Reason |
|---|---|
| Cloud embedding providers (OpenAI, Cohere) | Phase 2; `ProviderFactory` routing not wired to embedder |
| Multiple ChromaDB collections | Phase 2; atom notes (`06_ATOMS/`) not in Phase 1 |
| `model_target` superseded detection for prompt blocks | Phase 2 (TRACKER §Phase 2) |
| Embedding model config via `AgentConfig` | Not wired in Phase 1; model hardcoded to `nomic-embed-text` via constructor default |
| Batch embedding | Not needed for current single-file pipeline throughput |
| `__init__.py` public re-exports | Stub only; importers use direct module paths |
