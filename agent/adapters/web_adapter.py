"""WebAdapter — converts .url, .webloc, .html, .htm files into NormalizedItem.

No LLM calls, no vault writes.
Network I/O via httpx (anyio-compatible since httpx uses anyio internally ≥0.23).
"""
from __future__ import annotations

import configparser
import plistlib
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import anyio
import httpx
from markdownify import markdownify as md

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType

_SUPPORTED_SUFFIXES = frozenset({".url", ".webloc", ".html", ".htm"})
_BLANK_RUN_RE = re.compile(r"\n{3,}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _read_url_from_shortcut(path: Path) -> str:
    """Extract URL from a .url (Windows) or .webloc (macOS) shortcut file."""
    try:
        raw_bytes = await anyio.Path(path).read_bytes()
    except (OSError, PermissionError) as exc:
        raise AdapterError(str(exc), path) from exc

    suffix = path.suffix.lower()

    if suffix == ".url":
        # Windows INI-style: [InternetShortcut]\nURL=https://...
        text = raw_bytes.decode("utf-8", errors="replace")
        cp = configparser.ConfigParser()
        cp.read_string(text)
        try:
            url = cp.get("InternetShortcut", "URL")
        except (configparser.NoSectionError, configparser.NoOptionError) as exc:
            raise AdapterError(
                f"Missing [InternetShortcut] URL key in {path.name}", path
            ) from exc
        if not url.strip():
            raise AdapterError(f"Empty URL in {path.name}", path)
        return url.strip()

    # .webloc — macOS XML plist
    try:
        plist = plistlib.loads(raw_bytes)
    except Exception as exc:
        raise AdapterError(f"Failed to parse .webloc plist: {exc}", path) from exc

    url = plist.get("URL", "") if isinstance(plist, dict) else ""
    if not url or not isinstance(url, str):
        raise AdapterError(f"Missing URL key in .webloc plist: {path.name}", path)
    return url.strip()


async def _fetch_html(url: str, config: AgentConfig, path: Path) -> tuple[str, int]:
    """Fetch *url* and return (html_text, status_code).

    Raises AdapterError on timeout, network error, or non-2xx status.
    Uses *path* (the shortcut file) for AdapterError context.
    """
    timeout = getattr(config, "fetch_timeout_s", 30)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url, headers={"User-Agent": "obsidian-agent/1.0"})
    except httpx.TimeoutException as exc:
        raise AdapterError("Fetch timed out", path) from exc
    except httpx.RequestError as exc:
        raise AdapterError(f"Network error fetching {url}: {exc}", path) from exc

    if not response.is_success:
        raise AdapterError(f"HTTP {response.status_code} for {url}", path)
    return response.text, response.status_code


def _collapse_blank_lines(text: str) -> str:
    """Collapse runs of 3+ blank lines to exactly 2."""
    return _BLANK_RUN_RE.sub("\n\n", text)


# ---------------------------------------------------------------------------
# HTML metadata extractor
# ---------------------------------------------------------------------------


class _MetaExtractor(HTMLParser):
    """Walk the HTML once and collect title/author/url/language/date.

    Priority order per field (first non-empty wins):
      title    : og:title → <title> → first <h1> → path.stem
      url      : og:url → fallback (caller-supplied)
      author   : meta[name=author] → meta[property=article:author]
      language : <html lang> → meta[http-equiv=content-language]
      date     : article:published_time → meta[name=date]
    """

    def __init__(self) -> None:
        super().__init__()
        self.og_title: str = ""
        self.og_url: str = ""
        self.title_tag: str = ""
        self.first_h1: str = ""
        self.author: str = ""
        self.article_author: str = ""
        self.published_time: str = ""
        self.meta_date: str = ""
        self.language: str = ""
        self.content_language: str = ""
        self._in_title: bool = False
        self._in_h1: bool = False
        self._h1_done: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        t = tag.lower()

        if t == "html":
            self.language = attr.get("lang") or ""
        elif t == "title":
            self._in_title = True
        elif t == "h1" and not self._h1_done:
            self._in_h1 = True
        elif t == "meta":
            name = (attr.get("name") or "").lower()
            prop = (attr.get("property") or "").lower()
            content = attr.get("content") or ""
            http_equiv = (attr.get("http-equiv") or "").lower()

            if prop == "og:title" and not self.og_title:
                self.og_title = content
            elif prop == "og:url" and not self.og_url:
                self.og_url = content
            elif name == "author" and not self.author:
                self.author = content
            elif prop == "article:author" and not self.article_author:
                self.article_author = content
            elif prop == "article:published_time" and not self.published_time:
                self.published_time = content
            elif name == "date" and not self.meta_date:
                self.meta_date = content
            elif http_equiv == "content-language" and not self.content_language:
                self.content_language = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        elif tag.lower() == "h1":
            self._in_h1 = False
            self._h1_done = True

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.title_tag:
            self.title_tag = data.strip()
        elif self._in_h1 and not self._h1_done:
            self.first_h1 += data

    # ------------------------------------------------------------------
    # Resolved properties (call after feed())
    # ------------------------------------------------------------------

    def resolved_title(self, path: Path) -> str:
        return self.og_title or self.title_tag or self.first_h1.strip() or path.stem

    def resolved_url(self, fallback: str) -> str:
        return self.og_url or fallback

    def resolved_author(self) -> str:
        return self.author or self.article_author

    def resolved_language(self) -> str:
        return self.language or self.content_language

    def resolved_source_date(self) -> date | None:
        raw = self.published_time or self.meta_date
        if not raw:
            return None
        # Python 3.11+ fromisoformat handles timezone offsets like +00:00
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass
        # Date-only fallback (e.g. "2025-06-15")
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def html_to_article_item(
    html: str,
    *,
    path: Path,
    file_mtime: datetime,
    source_url: str,
    http_status: int | None,
    raw_id: str,
    extra_metadata: dict | None = None,
) -> NormalizedItem:
    """Build a NormalizedItem from HTML (shared by WebAdapter and MarkdownAdapter URL clips)."""
    extractor = _MetaExtractor()
    extractor.feed(html)

    markdown_body = md(
        html,
        heading_style="ATX",
        strip=["script", "style", "nav", "footer", "header", "aside"],
    )
    markdown_body = _collapse_blank_lines(markdown_body.strip())

    if not markdown_body:
        raise AdapterError("Empty content after conversion", path)

    meta = dict(extra_metadata) if extra_metadata else {}
    if "fetch_url" not in meta and source_url:
        meta["fetch_url"] = source_url
    if "http_status" not in meta and http_status is not None:
        meta["http_status"] = http_status

    return NormalizedItem(
        raw_id=raw_id,
        source_type=SourceType.ARTICLE,
        raw_text=markdown_body,
        title=extractor.resolved_title(path),
        url=extractor.resolved_url(source_url),
        author=extractor.resolved_author(),
        language=extractor.resolved_language(),
        source_date=extractor.resolved_source_date(),
        file_mtime=file_mtime,
        raw_file_path=path,
        extra_metadata=meta,
    )


async def fetch_url_article_item(
    url: str,
    path: Path,
    config: AgentConfig,
    file_mtime: datetime,
    raw_id: str,
    extra_metadata: dict | None = None,
) -> NormalizedItem:
    """GET *url*, convert HTML to article NormalizedItem (for .url clips and markdown URL clips)."""
    html, http_status = await _fetch_html(url, config, path)
    base_meta = dict(extra_metadata) if extra_metadata else {}
    base_meta.setdefault("fetch_url", url)
    base_meta["http_status"] = http_status
    return html_to_article_item(
        html,
        path=path,
        file_mtime=file_mtime,
        source_url=url,
        http_status=http_status,
        raw_id=raw_id,
        extra_metadata=base_meta,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class WebAdapter(BaseAdapter):
    """Source adapter for .url, .webloc, .html, and .htm files in the inbox."""

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        """Extract content from *path* and return a NormalizedItem.

        Raises:
            AdapterError: on unsupported suffix, read failure, network error,
                          non-2xx HTTP status, or empty markdown body.
        """
        suffix = path.suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            raise AdapterError(f"Unsupported suffix: {suffix}", path)

        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        http_status: int | None = None
        source_url: str = ""

        if suffix in {".url", ".webloc"}:
            source_url = await _read_url_from_shortcut(path)
            return await fetch_url_article_item(
                source_url,
                path,
                config,
                file_mtime,
                self._generate_raw_id(),
            )

        # .html / .htm — local file
        try:
            html = await anyio.Path(path).read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            raise AdapterError(str(exc), path) from exc

        return html_to_article_item(
            html,
            path=path,
            file_mtime=file_mtime,
            source_url=source_url,
            http_status=http_status,
            raw_id=self._generate_raw_id(),
            extra_metadata={"fetch_url": source_url, "http_status": http_status},
        )
