"""MarkdownAdapter — converts .md/.txt files into NormalizedItem.

No LLM calls, no vault writes. Optional HTTP fetch for Obsidian-style URL clips
(frontmatter ``type: url`` etc.), reusing the same HTML pipeline as WebAdapter.
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
from agent.adapters.web_adapter import fetch_url_article_item
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_MD_LINK_URL_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s\)>]+")

# Frontmatter ``type`` values that mean "fetch body URL like Web Clipper"
_CLIP_TYPES = frozenset({"url", "bookmark", "web"})

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
        "type",
        "fetch_content",
        "title",
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


def _truthy_fetch_content(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return False


def _should_fetch_url_clip(fm: dict[str, Any]) -> bool:
    """True when frontmatter asks to download page content (Obsidian Web Clipper-style)."""
    t = fm.get("type")
    if isinstance(t, str) and t.strip().lower() in _CLIP_TYPES:
        return True
    return _truthy_fetch_content(fm.get("fetch_content"))


def _normalize_url_candidate(s: str) -> str:
    u = s.strip().strip('"').strip("'")
    return u.rstrip(").,;]")


def _resolve_clip_url(fm: dict[str, Any], body: str) -> str:
    """Resolve http(s) URL: frontmatter url → source_url → markdown link → bare URL."""
    for key in ("url", "source_url"):
        v = fm.get(key)
        if isinstance(v, str) and v.strip().lower().startswith(("http://", "https://")):
            return _normalize_url_candidate(v)

    m = _MD_LINK_URL_RE.search(body)
    if m:
        return _normalize_url_candidate(m.group(1))

    m2 = _BARE_URL_RE.search(body)
    if m2:
        return _normalize_url_candidate(m2.group(0))

    return ""


def _strip_leading_url_from_body(body: str, url: str) -> str:
    """Remove leading blank lines and lines that only repeat the clipped URL."""
    url_n = url.rstrip("/")
    lines = body.split("\n")
    i = 0
    while i < len(lines):
        line_stripped = lines[i].strip()
        if not line_stripped:
            i += 1
            continue
        if line_stripped.rstrip(").,;]") == url.rstrip(").,;]"):
            i += 1
            continue
        m = re.match(r"^\[[^\]]*\]\((https?://[^)]+)\)\s*$", line_stripped)
        if m:
            inner = _normalize_url_candidate(m.group(1)).rstrip("/")
            if inner == url_n or inner.rstrip("/") == url_n.rstrip("/"):
                i += 1
                continue
        break
    return "\n".join(lines[i:]).strip()


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

        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        fm, body = _split_frontmatter(raw)

        if not body.strip():
            raise AdapterError("File is empty after stripping frontmatter", path)

        if path.suffix.lower() == ".md" and _should_fetch_url_clip(fm):
            return await self._extract_url_clip(path, config, fm, body, file_mtime)

        return self._extract_local_note(path, fm, body, file_mtime)

    async def _extract_url_clip(
        self,
        path: Path,
        config: AgentConfig,
        fm: dict[str, Any],
        body: str,
        file_mtime: datetime,
    ) -> NormalizedItem:
        url = _resolve_clip_url(fm, body)
        if not url:
            raise AdapterError(
                "URL clip (type/fetch_content) requires url, source_url, or http(s) link in body",
                path,
            )

        item = await fetch_url_article_item(
            url,
            path,
            config,
            file_mtime,
            self._generate_raw_id(),
        )

        fm_title = fm.get("title")
        if isinstance(fm_title, str) and fm_title.strip():
            item = item.model_copy(update={"title": fm_title.strip()})

        fm_author = str(fm.get("author") or "").strip()
        if fm_author:
            item = item.model_copy(update={"author": fm_author})

        fm_lang = str(fm.get("language") or fm.get("lang") or "").strip()
        if fm_lang:
            item = item.model_copy(update={"language": fm_lang})

        fm_date = _resolve_source_date(fm)
        if fm_date is not None:
            item = item.model_copy(update={"source_date": fm_date})

        notes = _strip_leading_url_from_body(body, url)
        if notes:
            new_text = item.raw_text + "\n\n---\n\n## Inbox notes\n\n" + notes
            item = item.model_copy(update={"raw_text": new_text})

        extra = {k: v for k, v in fm.items() if k not in _MAPPED_KEYS}
        merged_extra = {**extra, **item.extra_metadata}
        item = item.model_copy(update={"extra_metadata": merged_extra})

        return item

    def _extract_local_note(
        self,
        path: Path,
        fm: dict[str, Any],
        body: str,
        file_mtime: datetime,
    ) -> NormalizedItem:
        url: str = str(fm.get("source_url") or fm.get("url") or "")
        author: str = str(fm.get("author") or "")
        language: str = str(fm.get("language") or fm.get("lang") or "")
        source_date = _resolve_source_date(fm)

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
