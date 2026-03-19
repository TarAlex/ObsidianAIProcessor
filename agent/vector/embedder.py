"""Ollama embedding client for Stage 5 deduplication.

Sends text to the Ollama /api/embeddings endpoint and returns the
embedding vector. Base URL is overridable via OLLAMA_BASE_URL env var.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

__all__ = ["Embedder", "EmbedderError"]


class EmbedderError(Exception):
    """Raised by Embedder on any HTTP or parsing failure."""


class Embedder:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "nomic-embed-text",
    ) -> None:
        self._base_url = os.environ.get("OLLAMA_BASE_URL", base_url).rstrip("/")
        self._model = model

    async def embed(self, text: str) -> list[float]:
        """POST /api/embeddings to Ollama; return embedding vector.

        Raises:
            EmbedderError: on any HTTP or parsing failure.
        """
        url = f"{self._base_url}/api/embeddings"
        payload = {"model": self._model, "prompt": text}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["embedding"]
        except httpx.HTTPStatusError as exc:
            raise EmbedderError(
                f"HTTP {exc.response.status_code}: {exc}"
            ) from exc
        except Exception as exc:
            raise EmbedderError(str(exc)) from exc
