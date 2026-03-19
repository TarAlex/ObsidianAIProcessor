"""MarkdownAdapter — converts .md/.txt files into NormalizedItem.

No LLM calls, no vault writes, no network requests.
Uses anyio for async file I/O per project constraint.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import anyio
import yaml

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# Keys consumed by field mapping — these are NOT passed into extra_metadata
_MAPPED_KEYS: frozenset[str] = frozenset(
    {
        "source_url",
        "url",
        "author",
        "language",
        "lang",
        "source_date",
        "date",
        "date_created",
    }
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_text).

    If the file does not start with ``---\\n``, returns ({}, full text).
    Malformed YAML silently falls back to ({}, full text) — not an error.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}, text
    body = text[match.end():]
    return fm if isinstance(fm, dict) else {}, body


def _extract_title(body: str, path: Path) -> str:
    """First ``# Heading`` in body, or path.stem as fallback."""
    m = HEADING_RE.search(body)
    return m.group(1).strip() if m else path.stem


def _parse_date(value: object) -> date | None:
    """Parse a date from a YAML value (already a date, or ISO 8601 string)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _resolve_source_date(fm: dict[str, Any]) -> date | None:
    """Try source_date → date → date_created, in that order."""
    for key in ("source_date", "date", "date_created"):
        if key in fm:
            result = _parse_date(fm[key])
            if result is not None:
                return result
    return None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class MarkdownAdapter(BaseAdapter):
    """Source adapter for .md and .txt files in the inbox."""

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        """Read *path* and return a NormalizedItem.

        Raises:
            AdapterError: if the file cannot be read or is empty after
                          stripping frontmatter.
        """
        try:
            raw = await anyio.Path(path).read_text(encoding="utf-8")
        except (OSError, PermissionError) as exc:
            raise AdapterError(str(exc), path) from exc

        # stat must come after a successful read
        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        fm, body = _split_frontmatter(raw)

        if not body.strip():
            raise AdapterError("File is empty after stripping frontmatter", path)

        # Field mapping from frontmatter
        url: str = str(fm.get("source_url") or fm.get("url") or "")
        author: str = str(fm.get("author") or "")
        language: str = str(fm.get("language") or fm.get("lang") or "")
        source_date = _resolve_source_date(fm)

        # extra_metadata: all keys not consumed by the mapping above
        extra_metadata: dict[str, Any] = {
            k: v for k, v in fm.items() if k not in _MAPPED_KEYS
        }

        return NormalizedItem(
            raw_id=self._generate_raw_id(),
            source_type=SourceType.NOTE,
            raw_text=body,
            title=_extract_title(body, path),
            url=url,
            author=author,
            language=language,
            source_date=source_date,
            file_mtime=file_mtime,
            raw_file_path=path,
            extra_metadata=extra_metadata,
        )
