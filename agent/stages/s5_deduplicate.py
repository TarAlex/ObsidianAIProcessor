"""Stage 5 — Deduplicate.

Checks whether the incoming item is semantically similar to existing
vault notes using ChromaDB cosine similarity. Three outcomes:

  similarity >= 0.80  → route_to_merge=True  (pipeline routes to 01_PROCESSING/to_merge/)
  similarity >= 0.60  → record related notes, continue pipeline
  similarity <  0.60  → new content, continue pipeline

This stage is a pure decision gate: no vault writes, no LLM calls,
no frontmatter modifications. The only side-effect is adding the
new item's embedding to ChromaDB (when not routing to merge).
"""
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

logger = logging.getLogger(__name__)

_MERGE_THRESHOLD: float = 0.80    # mirrors VaultConfig.merge_threshold
_RELATED_THRESHOLD: float = 0.60  # mirrors VaultConfig.related_threshold
_N_RESULTS: int = 5               # neighbours to retrieve


def _build_embed_text(item: NormalizedItem, summary: SummaryResult) -> str:
    return (
        f"{item.title}\n"
        f"{summary.summary}\n"
        + " ".join(summary.key_ideas)
    )[:2000]


async def run(
    item: NormalizedItem,
    classification: ClassificationResult,
    summary: SummaryResult,
    vault: Any,                    # ObsidianVault (typed as Any to avoid circular import)
    llm: AbstractLLMProvider,      # unused in Phase 1; accepted for pipeline compatibility
) -> DeduplicationResult:
    logger.info(
        "S5 dedup: raw_id=%s title=%.60s source_type=%s",
        item.raw_id,
        item.title,
        item.source_type.value,
    )

    try:
        embed_text = _build_embed_text(item, summary)
        chroma_dir = Path(vault.root) / "_AI_META" / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)

        embedder = Embedder()
        store = VectorStore(chroma_dir)

        embedding = await embedder.embed(embed_text)

        neighbours = await store.similarity_search(embedding, n_results=_N_RESULTS)

        best_score = 0.0
        best_path = ""
        related_paths: list[str] = []

        for n in neighbours:
            score = n["score"]
            if score > best_score:
                best_score = score
                best_path = n["metadata"].get("vault_path", "")
            if _RELATED_THRESHOLD <= score < _MERGE_THRESHOLD:
                related_paths.append(n["metadata"].get("vault_path", ""))

        if best_score >= _MERGE_THRESHOLD:
            logger.info(
                "S5 dedup: route_to_merge=True for %s (score=%.3f, similar=%s)",
                item.raw_id,
                best_score,
                best_path,
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
            item.raw_id,
            best_score,
            len(related_paths),
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
