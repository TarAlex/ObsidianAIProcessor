"""ChromaDB-backed vector store for Stage 5 deduplication.

Wraps a PersistentClient with a single "knowledge_notes" collection
using cosine distance space. All public methods are async for
pipeline compatibility (the underlying chromadb calls are synchronous).
"""
from __future__ import annotations

import logging
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)

__all__ = ["VectorStore"]


class VectorStore:
    COLLECTION = "knowledge_notes"

    def __init__(self, persist_directory: str | Path) -> None:
        """Open (or create) a ChromaDB PersistentClient at persist_directory."""
        self._client = chromadb.PersistentClient(path=str(persist_directory))
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    async def add(
        self,
        doc_id: str,
        embedding: list[float],
        metadata: dict,
    ) -> None:
        """Upsert a document embedding. Silently overwrites if doc_id exists."""
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[metadata],
        )

    async def similarity_search(
        self,
        embedding: list[float],
        n_results: int = 5,
    ) -> list[dict]:
        """Return top-n similar documents.

        Each dict: {"doc_id": str, "score": float, "metadata": dict}
        score is cosine similarity [0,1]; 1 = identical.
        """
        count = self._collection.count()
        if count == 0:
            return []

        actual_n = min(n_results, count)
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=actual_n,
            include=["distances", "metadatas"],
        )

        docs = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for doc_id, distance, meta in zip(ids, distances, metadatas):
            docs.append({
                "doc_id": doc_id,
                "score": 1.0 - distance,
                "metadata": meta or {},
            })

        return docs

    async def delete(self, doc_id: str) -> None:
        """Delete document by doc_id; no-op if not found."""
        try:
            self._collection.delete(ids=[doc_id])
        except Exception:
            pass  # not found — no-op per contract
