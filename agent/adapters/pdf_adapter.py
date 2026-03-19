"""PDFAdapter — converts PDF files into NormalizedItem.

No LLM calls, no vault writes.
PDF parsing via pymupdf (fitz). Sync fitz calls run in anyio thread pool.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import anyio
import fitz  # pymupdf>=1.24

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType

_PDF_DATE_RE = re.compile(r"^D:(\d{4})(\d{2})(\d{2})")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_pdf_date(raw: str) -> date | None:
    """Parse a PDF metadata date string (D:YYYYMMDDHHmmss...) → date or None."""
    m = _PDF_DATE_RE.match(raw.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _extract_pdf(path: Path) -> tuple[str, dict]:
    """Open *path* with fitz, extract text and metadata.

    Returns (raw_text, metadata_dict).
    Raises AdapterError on any unrecoverable failure.
    This function is fully synchronous — always call via anyio thread pool.
    """
    try:
        doc = fitz.open(str(path))
    except fitz.FileDataError as exc:
        raise AdapterError(f"Corrupt or unreadable PDF: {exc}", path) from exc
    except (OSError, PermissionError) as exc:
        raise AdapterError(str(exc), path) from exc
    except Exception as exc:
        raise AdapterError(f"Failed to open PDF: {exc}", path) from exc

    if doc.is_encrypted:
        raise AdapterError("PDF is encrypted — cannot extract text", path)

    pages: list[str] = []
    for page in doc:
        text = page.get_text("text").strip()
        if text:
            pages.append(text)

    raw_text = "\n\n---\n\n".join(pages)
    if not raw_text.strip():
        raise AdapterError("PDF contains no extractable text", path)

    meta = doc.metadata  # keys: title, author, subject, creator, producer, creationDate, …
    return raw_text, {
        "title": (meta.get("title") or "").strip(),
        "author": (meta.get("author") or "").strip(),
        "creator": (meta.get("creator") or "").strip(),
        "producer": (meta.get("producer") or "").strip(),
        "page_count": doc.page_count,
        "creation_date_raw": (meta.get("creationDate") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PDFAdapter(BaseAdapter):
    """Source adapter for PDF files in the inbox."""

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        """Extract text and metadata from a PDF file at *path*.

        Raises:
            AdapterError: on read failure, encryption, corruption, or empty text.
        """
        try:
            raw_text, meta = await anyio.to_thread.run_sync(
                lambda: _extract_pdf(path), abandon_on_cancel=True
            )
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"Unexpected error reading PDF: {exc}", path) from exc

        title: str = meta["title"] or path.stem
        author: str = meta["author"]
        source_date = _parse_pdf_date(meta["creation_date_raw"])
        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        return NormalizedItem(
            raw_id=self._generate_raw_id(),
            source_type=SourceType.PDF,
            raw_text=raw_text,
            title=title,
            url="",
            author=author,
            language="",
            source_date=source_date,
            file_mtime=file_mtime,
            raw_file_path=path,
            extra_metadata={
                "page_count": meta["page_count"],
                "creator": meta["creator"],
                "producer": meta["producer"],
            },
        )
