"""MarkItDownAdapter — converts Office documents into NormalizedItem.

Supports DOCX, DOC, PPTX, PPT, XLSX, XLS, EPUB and any other format
that markitdown can handle.

No LLM calls, no vault writes.
Conversion via markitdown (sync) run in anyio thread pool.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import anyio

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType


def _convert_document(path: Path) -> tuple[str, str]:
    """Run markitdown conversion synchronously.

    Returns (raw_text, title).
    Raises AdapterError on any failure or empty result.
    This function is fully synchronous — always call via anyio thread pool.
    """
    try:
        from markitdown import MarkItDown  # noqa: PLC0415
        result = MarkItDown().convert(str(path))
    except Exception as exc:
        raise AdapterError(str(exc), path) from exc

    raw_text = (result.text_content or "").strip()
    if not raw_text:
        raise AdapterError("Document contains no extractable text", path)

    title = (result.title or "").strip()
    return raw_text, title


class MarkItDownAdapter(BaseAdapter):
    """Source adapter for Office documents and other markitdown-supported formats."""

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        """Extract text and metadata from an Office document at *path*.

        Raises:
            AdapterError: on read failure, unsupported format, or empty text.
        """
        try:
            raw_text, title = await anyio.to_thread.run_sync(
                lambda: _convert_document(path), abandon_on_cancel=True
            )
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"Unexpected error reading document: {exc}", path) from exc

        if not title:
            title = path.stem

        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        return NormalizedItem(
            raw_id=self._generate_raw_id(),
            source_type=SourceType.ARTICLE,
            raw_text=raw_text,
            title=title,
            url="",
            author="",
            language="",
            source_date=None,
            file_mtime=file_mtime,
            raw_file_path=path,
            extra_metadata={"original_format": path.suffix.lower()},
        )
