# Spec: store.py
slug: store-py
layer: vector
phase: 1
arch_section: §15 Vector Store

---

## Problem statement

Stage 5 (`s5_deduplicate.py`) needs a persistent local vector store to:
1. Query for semantically similar existing notes before deciding to merge or continue.
2. Persist the new note's embedding once it is confirmed as novel content.
3. Delete stale embeddings when a note is removed (cleanup path).

`store.py` is the ChromaDB wrapper that satisfies all three. It must:
- Persist embeddings across process restarts (PersistentClient).
- Use cosine similarity consistently (explicit `hnsw:space: cosine`).
- Convert ChromaDB's distance output to similarity scores so the caller works in the
  [0, 1] range where 1 = identical.
- Never raise on an empty collection or a missing doc_id (guard both edge cases).
- Expose an `async` API even though the underlying ChromaDB calls are synchronous
  (pipeline compatibility — s5_deduplicate is an `async def` coroutine under `anyio`).

**Note:** This module was pre-built as a transitive dependency of `s5_deduplicate.py`.
The implementation is complete. This spec formalises the design for `/review` → `/done`.

---

## Module contract

**File**: `agent/vector/store.py`

**Input / Output per method:**

| Method | Input | Output |
|---|---|---|
| `__init__(persist_directory)` | `str \| Path` — absolute path to ChromaDB directory | Creates/opens `PersistentClient`; no return value |
| `add(doc_id, embedding, metadata)` | `str`, `list[float]`, `dict` | `None` — upserts silently |
| `similarity_search(embedding, n_results)` | `list[float]`, `int = 5` | `list[dict]` — see schema below |
| `delete(doc_id)` | `str` | `None` — no-op if not found |

**`similarity_search` return schema:**
```python
[
    {
        "doc_id":   str,    # ChromaDB document ID (= NormalizedItem.raw_id)
        "score":    float,  # cosine similarity ∈ [0, 1]; 1 = identical
        "metadata": dict,   # metadata dict stored at add() time
    },
    ...
]
```

**Error surface:**
- `__init__` may raise `chromadb` exceptions if the directory is not writable —
  these propagate to the caller (s5_deduplicate wraps everything in `try/except`).
- `add` / `similarity_search` / `delete` do not define additional error types;
  ChromaDB errors propagate upward.
- `delete` is the exception: it silently swallows **all** exceptions (no-op contract).

### Public API

```python
class VectorStore:
    COLLECTION: str = "knowledge_notes"

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

**`__all__`**: `["VectorStore"]`

---

## Key implementation notes

### 1. PersistentClient initialisation

```python
self._client = chromadb.PersistentClient(path=str(persist_directory))
self._collection = self._client.get_or_create_collection(
    name=self.COLLECTION,
    metadata={"hnsw:space": "cosine"},
)
```

- `path` is cast to `str` — ChromaDB does not accept `Path` objects.
- `get_or_create_collection` is idempotent: on process restart it attaches to the
  existing collection without data loss.
- `metadata={"hnsw:space": "cosine"}` is set at creation time and ignored on
  subsequent opens. It ensures consistent cosine distance throughout.

### 2. `add` — upsert semantics

```python
self._collection.upsert(
    ids=[doc_id],
    embeddings=[embedding],
    metadatas=[metadata],
)
```

Uses ChromaDB `upsert` (not `add`) so calling `add` twice with the same `doc_id`
silently overwrites rather than raising a duplicate-key error.

### 3. `similarity_search` — empty-collection guard

ChromaDB raises `ValueError` when `n_results > count`. Guard:

```python
count = self._collection.count()
if count == 0:
    return []
actual_n = min(n_results, count)
```

Query only returns `distances` and `metadatas` (not documents/data) to minimise
payload size:

```python
results = self._collection.query(
    query_embeddings=[embedding],
    n_results=actual_n,
    include=["distances", "metadatas"],
)
```

### 4. Distance-to-similarity conversion

ChromaDB cosine distance ∈ [0, 2] where 0 = identical vectors. Convert:

```python
score = 1.0 - distance
```

This maps identical → 1.0, orthogonal → 0.0, opposite → −1.0. Callers
(s5_deduplicate) apply thresholds of 0.80 (merge) and 0.60 (related) on this
converted score. Negative scores are valid but never meet any threshold.

### 5. Safe result unpacking

ChromaDB query results are nested lists; use `.get()` with empty-list defaults:

```python
ids = results.get("ids", [[]])[0]
distances = results.get("distances", [[]])[0]
metadatas = results.get("metadatas", [[]])[0]
```

`meta or {}` guards against `None` entries in the metadatas list.

### 6. `delete` — silent no-op

```python
async def delete(self, doc_id: str) -> None:
    try:
        self._collection.delete(ids=[doc_id])
    except Exception:
        pass  # not found — no-op per contract
```

ChromaDB raises when attempting to delete a non-existent ID; swallowing the
exception upholds the no-op contract and prevents error routing on cleanup paths.

### 7. Async wrapper rationale

All three mutating/query methods are `async def` even though ChromaDB's Python
client is synchronous. This is intentional:
- s5_deduplicate is an `async def` coroutine orchestrated by `anyio`.
- Wrapping as `async` avoids blocking the event loop on long queries if ChromaDB
  is later replaced with an async-native backend.
- For Phase 1 throughput (single file at a time), the synchronous-in-async call
  is acceptable — no `anyio.to_thread` wrapping is needed.

### 8. Persist directory — no hardcoded paths

`VectorStore.__init__` accepts any `persist_directory` from the caller.
The canonical path is derived by s5_deduplicate:

```python
chroma_dir = Path(vault.root) / "_AI_META" / "chroma"
chroma_dir.mkdir(parents=True, exist_ok=True)
store = VectorStore(chroma_dir)
```

`store.py` itself never references vault paths, config keys, or environment variables.

---

## Data model changes

None. `store.py` has no Pydantic models and introduces no new types in
`agent/core/models.py`. The `DeduplicationResult` model required by s5 is
specified in `ProgressTracking/specs/s5-deduplicate.md`.

---

## LLM prompt file needed

None. `store.py` makes no LLM calls.

---

## Tests required

**Unit**: `tests/unit/test_vector_store.py` — tests 1–5 cover `VectorStore`
(tests 6–8 cover `Embedder`, per the embedder spec):

| # | Test name | What it verifies |
|---|---|---|
| 1 | `test_add_and_search_returns_similarity` | `add` one doc then `similarity_search` with same embedding → `score ≈ 1.0`, `doc_id` matches |
| 2 | `test_search_empty_store` | Fresh store → `similarity_search` returns `[]` without raising |
| 3 | `test_add_twice_upserts` | `add(same_id, ...)` twice does not raise; `similarity_search` returns exactly 1 result |
| 4 | `test_delete_removes_doc` | `add` then `delete` then `similarity_search` → returns `[]` |
| 5 | `test_score_is_similarity_not_distance` | After `add` + `similarity_search` with identical vector → `score >= 0.99` (not raw distance) |

**Test tooling**: Use `chromadb.EphemeralClient` (in-memory) for unit tests — no
`tmp_path` or PersistentClient needed. All tests are synchronous (call
`asyncio.run(...)` or use `@pytest.mark.anyio`).

**Integration**: None in Phase 1. A live ChromaDB + Ollama integration test is
deferred to `tests/integration/test_pipeline_dedup.py`.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Multiple ChromaDB collections (per-domain) | Single `knowledge_notes` collection in Phase 1; multi-collection is Phase 2 |
| Async-native ChromaDB (`chromadb.AsyncClient`) | Not available in `chromadb>=0.5`; revisit if backend changes |
| `anyio.to_thread` wrapping for blocking ChromaDB calls | Not required at single-file pipeline throughput |
| Updating `vault_path` metadata after s6a writes | Out of scope for store.py; s5 or a future cleanup task |
| Removing embeddings on vault note deletion | Phase 2 |
| Config-driven persist_directory (via `AgentConfig`) | Caller (s5_deduplicate) derives path from `vault.root`; no config parameter needed |
| Dimensionality validation of embedding vectors | ChromaDB enforces consistency at upsert time — error propagates naturally |
| Batch add / bulk import | Not required for single-file pipeline throughput |

---

## Open questions

1. **Distance metric on existing collection**: If a ChromaDB collection was created
   without `hnsw:space: cosine` (e.g., during early testing), the metric cannot be
   changed in-place. Callers should delete the `_AI_META/chroma` directory to force
   recreation if similarity scores appear wrong. A warning log on first-create could
   be added to the constructor in a future session.

2. **`vault_path` metadata is empty at add time**: s5_deduplicate stores
   `"vault_path": ""` because s6a has not yet written the note. This is a known
   limitation accepted for Phase 1 (ChromaDB is advisory-only). A cleanup sweep
   could be added to the daily `index_updater` task in Phase 2.
