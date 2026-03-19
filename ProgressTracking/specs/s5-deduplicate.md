# Spec: Stage 5 — Deduplicate
slug: s5-deduplicate
layer: stages
phase: 1
arch_section: §6 Stage 5, §15 Vector Store

---

## Problem statement

After Stage 4b produces verbatim blocks, Stage 5 checks whether the incoming item is
semantically similar to existing vault notes using ChromaDB cosine similarity.
Three possible decisions:

| Condition | Action |
|---|---|
| `similarity >= merge_threshold (0.80)` | `route_to_merge = True` → pipeline routes to `01_PROCESSING/to_merge/` |
| `similarity >= related_threshold (0.60)` | Record related notes, continue pipeline |
| `similarity < related_threshold` | New content, continue pipeline |

Stage 5 is **purely a decision gate**: no vault notes are written, no LLM calls are
made, no frontmatter is modified. The only side-effect is adding the new item's
embedding to ChromaDB (when not routing to merge).

**Pipeline signature (fixed in pipeline.py — DONE):**
```python
merge_result = await s5_deduplicate.run(
    item, classification, summary, self.vault, self._get_llm()
)
if merge_result.route_to_merge:
    self.vault.move_to_merge(raw_path, merge_result)
    ...
# s6a also receives merge_result:
output_paths = await s6a_write.run(item, classification, summary, merge_result, vault, config)
```

---

## Module contract

```
Input:
  item:           NormalizedItem           — raw content + metadata from S1
  classification: ClassificationResult     — domain, domain_path, staleness_risk
  summary:        SummaryResult            — summary text + key_ideas (verbatim_blocks attached)
  vault:          ObsidianVault            — used for vault.root (ChromaDB path derivation)
  llm:            AbstractLLMProvider      — accepted but unused in Phase 1

Output:
  DeduplicationResult                      — see Data model changes below
```

**Invariants:**
- Never raises; wraps all vector store I/O in `try/except Exception`
- Returns `DeduplicationResult(route_to_merge=False)` on any error (graceful pass-through)
- Never calls `vault.write_note()`, `vault.read_note()`, or any vault write
- Does not import from `agent/vault/verbatim.py` or `agent/vault/templates.py`

---

## Key implementation notes

### 1. New model required: `DeduplicationResult`

Add to `agent/core/models.py` (see Data model changes).

### 2. Text to embed

Compose from processed fields (not raw text) — captures semantic content:

```python
embed_text = (
    f"{item.title}\n"
    f"{summary.summary}\n"
    + " ".join(summary.key_ideas)
)[:2000]  # cap: embedding models have context limits
```

### 3. ChromaDB path derivation

Derive persist_directory from vault.root (no config needed):

```python
chroma_dir = vault.root / "_AI_META" / "chroma"
chroma_dir.mkdir(parents=True, exist_ok=True)
```

### 4. Vector layer interface required

s5_deduplicate.py depends on two modules that must be implemented as part of
this build (or prior to it):

**`agent/vector/embedder.py`** — `Embedder` class:
```python
class Embedder:
    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 model: str = "nomic-embed-text") -> None: ...

    async def embed(self, text: str) -> list[float]:
        """POST /api/embeddings to Ollama; return embedding vector.
        Raises EmbedderError on failure."""
```
- `base_url` defaults to `http://127.0.0.1:11434`; overridable via `OLLAMA_BASE_URL` env var
- Uses `httpx.AsyncClient` for the HTTP call
- Raises `EmbedderError(Exception)` on failure (defined in same file)

**`agent/vector/store.py`** — `VectorStore` class:
```python
class VectorStore:
    COLLECTION = "knowledge_notes"

    def __init__(self, persist_directory: str | Path) -> None:
        """Open (or create) a ChromaDB PersistentClient at persist_directory."""

    async def add(
        self,
        doc_id: str,
        embedding: list[float],
        metadata: dict,
    ) -> None:
        """Upsert a document embedding. Silently overwrites if doc_id exists."""

    async def similarity_search(
        self,
        embedding: list[float],
        n_results: int = 5,
    ) -> list[dict]:
        """Return top-n similar documents.
        Each dict: {"doc_id": str, "score": float, "metadata": dict}
        score is cosine distance in [0,1]; lower = more similar.
        Convert to similarity: similarity = 1 - distance."""

    async def delete(self, doc_id: str) -> None:
        """Delete document by doc_id; no-op if not found."""
```

**Important — ChromaDB distance vs. similarity:**
ChromaDB returns cosine *distance* (0 = identical, 2 = opposite). Convert to similarity:
```python
score = 1.0 - result["distance"]
```
Thresholds (0.80 merge, 0.60 related) apply to this converted similarity score.

### 5. Threshold constants (module-level)

Config is not in the stage signature (pipeline.py is DONE). Use module-level constants
that mirror `VaultConfig` defaults:

```python
_MERGE_THRESHOLD: float = 0.80    # mirrors VaultConfig.merge_threshold
_RELATED_THRESHOLD: float = 0.60  # mirrors VaultConfig.related_threshold
_N_RESULTS: int = 5               # neighbours to retrieve
```

### 6. Function signature

```python
async def run(
    item: NormalizedItem,
    classification: ClassificationResult,
    summary: SummaryResult,
    vault: Any,                    # ObsidianVault (typed as Any to avoid circular import)
    llm: AbstractLLMProvider,      # unused in Phase 1; accepted for pipeline compatibility
) -> DeduplicationResult:
```

### 7. Core algorithm

```python
async def run(...) -> DeduplicationResult:
    try:
        embed_text = _build_embed_text(item, summary)
        chroma_dir = Path(vault.root) / "_AI_META" / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)

        embedder = Embedder()                          # defaults to Ollama localhost
        store = VectorStore(chroma_dir)

        embedding = await embedder.embed(embed_text)

        # Search for neighbours
        neighbours = await store.similarity_search(embedding, n_results=_N_RESULTS)

        # Evaluate
        best_score = 0.0
        best_path = ""
        related_paths: list[str] = []

        for n in neighbours:
            score = n["score"]          # already converted to similarity in VectorStore
            if score > best_score:
                best_score = score
                best_path = n["metadata"].get("vault_path", "")
            if score >= _RELATED_THRESHOLD and score < _MERGE_THRESHOLD:
                related_paths.append(n["metadata"].get("vault_path", ""))

        if best_score >= _MERGE_THRESHOLD:
            logger.info(
                "S5 dedup: route_to_merge=True for %s (score=%.3f, similar=%s)",
                item.raw_id, best_score, best_path,
            )
            return DeduplicationResult(
                route_to_merge=True,
                similar_note_path=best_path,
                similarity_score=best_score,
                related_note_paths=[],
            )

        # Not a duplicate — add to vector store
        await store.add(
            doc_id=item.raw_id,
            embedding=embedding,
            metadata={
                "raw_id": item.raw_id,
                "domain_path": classification.domain_path,
                "source_type": item.source_type.value,
                "title": item.title,
                "vault_path": "",   # not yet written; s6a will supply via separate call if needed
            },
        )

        logger.info(
            "S5 dedup: new content for %s (best_score=%.3f, related=%d)",
            item.raw_id, best_score, len(related_paths),
        )
        return DeduplicationResult(
            route_to_merge=False,
            similar_note_path=best_path if best_score >= _RELATED_THRESHOLD else "",
            similarity_score=best_score,
            related_note_paths=related_paths,
        )

    except Exception as exc:
        logger.warning("S5 dedup failed for %s (pass-through): %s", item.raw_id, exc)
        return DeduplicationResult(route_to_merge=False)
```

### 8. Logging

- `logger.info` on entry: `raw_id`, `title[:60]`, `source_type`
- `logger.info` on result: `raw_id`, `route_to_merge`, `best_score`, `similar_note_path`
- `logger.warning` on exception: `raw_id`, exception message

### 9. Imports

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.core.models import (
    ClassificationResult,
    DeduplicationResult,
    NormalizedItem,
    SummaryResult,
)
from agent.llm.base import AbstractLLMProvider
from agent.vector.embedder import Embedder
from agent.vector.store import VectorStore
```

---

## Data model changes

Add `DeduplicationResult` to `agent/core/models.py`:

```python
class DeduplicationResult(BaseModel):
    """Output of Stage 5 — deduplication decision."""

    route_to_merge: bool = False
    similar_note_path: str = ""           # vault-relative path of closest existing note
    similarity_score: float = 0.0         # cosine similarity [0,1]; 1 = identical
    related_note_paths: list[str] = Field(default_factory=list)
```

Also add `"DeduplicationResult"` to `__all__` in models.py.

**No other model changes.** All other required types exist:
- `NormalizedItem`, `ClassificationResult`, `SummaryResult` — DONE
- `AbstractLLMProvider` — DONE
- `AgentConfig`, `VaultConfig` — DONE (thresholds accessed via module-level constants, not config)

---

## LLM prompt file needed

None. Stage 5 uses vector similarity only — no LLM calls in Phase 1.

---

## Tests required

### unit: `tests/unit/test_s5_deduplicate.py`

All tests mock `Embedder.embed` (AsyncMock) and `VectorStore.similarity_search` / `VectorStore.add` (AsyncMock). `vault.root` is a `tmp_path` fixture.

| # | Test name | What it verifies |
|---|---|---|
| 1 | `test_new_content_below_related_threshold` | similarity_search returns score 0.40 → `route_to_merge=False`, `related_note_paths=[]`, `store.add` called once |
| 2 | `test_related_content_between_thresholds` | score 0.70 → `route_to_merge=False`, `related_note_paths` has the note path, `store.add` called once |
| 3 | `test_duplicate_above_merge_threshold` | score 0.85 → `route_to_merge=True`, `similar_note_path` populated, `similarity_score=0.85`, `store.add` NOT called |
| 4 | `test_multiple_neighbours_best_selected` | 3 neighbours with scores [0.50, 0.82, 0.65]; assert `route_to_merge=True`, `similarity_score=0.82` |
| 5 | `test_embed_error_returns_passthrough` | `Embedder.embed` raises `EmbedderError`; assert returns `DeduplicationResult(route_to_merge=False)`, no exception propagates |
| 6 | `test_chromadb_error_returns_passthrough` | `VectorStore.similarity_search` raises `Exception`; assert pass-through |
| 7 | `test_empty_neighbours_is_new_content` | `similarity_search` returns `[]`; assert `route_to_merge=False`, `similarity_score=0.0`, `store.add` called |
| 8 | `test_embed_text_caps_at_2000_chars` | `item.raw_text` irrelevant; title + summary > 2000 chars; capture arg to `Embedder.embed` and assert `len(text) <= 2000` |
| 9 | `test_llm_param_not_used` | `llm` is a MagicMock; assert `llm.chat` never called |
| 10 | `test_chroma_dir_created` | `vault.root / "_AI_META" / "chroma"` does not exist before call; after call it exists (mkdir called) |

### unit: `tests/unit/test_vector_store.py`

Tests for `agent/vector/store.py` and `agent/vector/embedder.py` — exercised with a
real in-memory ChromaDB client and a mocked httpx for the embedder.

| # | Test name | What it verifies |
|---|---|---|
| 1 | `test_add_and_search_returns_similarity` | Add one doc; search with same embedding → score ≈ 1.0 |
| 2 | `test_search_empty_store` | Fresh store → returns `[]` |
| 3 | `test_add_twice_upserts` | `add(same_id, ...)` twice does not raise; search returns 1 result |
| 4 | `test_delete_removes_doc` | Add then delete; search returns `[]` |
| 5 | `test_score_is_similarity_not_distance` | Score for identical vectors should be ≥ 0.99 |
| 6 | `test_embedder_sends_correct_payload` | Mock httpx; assert POST body has `model` and `prompt` keys |
| 7 | `test_embedder_raises_on_http_error` | httpx returns 500 → `EmbedderError` raised |
| 8 | `test_embedder_base_url_from_env` | Set `OLLAMA_BASE_URL=http://custom:11434`; assert Embedder uses it |

### integration: none in Phase 1

Full integration test (pipeline with real ChromaDB + Ollama) is deferred to
`tests/integration/test_pipeline_dedup.py` (not in TRACKER — Phase 2 candidate).

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| LLM-based merge suggestion (what to keep/drop) | Phase 2 — human decides in to_merge/ |
| Updating `vault_path` in ChromaDB after s6a writes | Out of scope; s6a or a separate updater task |
| Multi-collection / per-domain ChromaDB collections | Single `knowledge_notes` collection in Phase 1 |
| Semantic merge logic (combining two notes) | Human-only in Phase 1 |
| `agent/vector/embedder.py` LM Studio / OpenAI fallback | Phase 1 Ollama only; env var for base_url |
| Removing embedding on vault note deletion | Phase 2 |
| Config-driven thresholds (merge_threshold, related_threshold) | Pipeline signature is DONE; Phase 1 uses module-level constants matching VaultConfig defaults |

---

## Open questions

1. **`vault_path` in ChromaDB metadata**: s5 adds an embedding before s6a writes the note. The `vault_path` in metadata will be `""` until s6a completes. If s6a later fails, the embedding is orphaned. For Phase 1 this is acceptable (ChromaDB is advisory-only). A cleanup sweep could be added to the daily index_updater task in Phase 2.

2. **Distance metric**: ChromaDB defaults to `cosine` distance. The spec assumes this. If the collection was created with a different metric, scores will be wrong. The `VectorStore` constructor should explicitly set `metadata={"hnsw:space": "cosine"}` when creating the collection.
