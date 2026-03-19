"""YouTubeAdapter — converts .youtube shortcut files into NormalizedItem.

No LLM calls, no vault writes.
Transcript fetched via youtube-transcript-api (sync, in thread pool).
Watch-page metadata fetched via httpx (async, best-effort, non-fatal).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import anyio
import httpx

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType

try:
    from youtube_transcript_api import VideoUnavailable
except ImportError:
    from youtube_transcript_api._errors import VideoUnavailable  # type: ignore[no-redef]

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_YOUTUBE_HOSTS = frozenset({
    "www.youtube.com",
    "youtube.com",
    "m.youtube.com",
})

_JSONLD_RE = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_OG_TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"')


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_url_from_file(text: str) -> str:
    """Return first non-empty, non-comment line from .youtube file content."""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""


def _extract_video_id(url: str) -> str | None:
    """Extract video ID from a YouTube URL. Returns None if unrecognised."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid or None
    if host in _YOUTUBE_HOSTS:
        qs = parse_qs(parsed.query)
        return qs.get("v", [None])[0]
    return None


def _format_timestamp(seconds: float) -> str:
    """Format float seconds as HH:MM:SS."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_transcript(segments: list) -> str:
    """Format each segment as '[HH:MM:SS] text'.

    Accepts both FetchedTranscriptSnippet dataclass objects (attribute access)
    and plain dicts (dict access) for test-mock compatibility.
    """
    lines: list[str] = []
    for seg in segments:
        try:
            start = float(seg["start"])
            text = (seg.get("text") or "").strip()
        except (TypeError, KeyError):
            start = float(seg.start)
            text = (getattr(seg, "text", "") or "").strip()
        ts = _format_timestamp(start)
        if text:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


def _fetch_transcript(
    video_id: str, path: Path
) -> tuple[list, str, bool]:
    """Sync helper — must run in a thread. Returns (segments, language_code, is_auto)."""
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
    except TranscriptsDisabled as exc:
        raise AdapterError(f"Transcripts disabled for {video_id}", path) from exc
    except VideoUnavailable as exc:
        raise AdapterError(f"Video unavailable: {video_id}", path) from exc
    except Exception as exc:
        raise AdapterError(
            f"Failed to list transcripts for {video_id}: {exc}", path
        ) from exc

    # Prefer manually-created over auto-generated; accept any available language
    all_codes = [t.language_code for t in transcript_list]
    transcript = None
    try:
        transcript = transcript_list.find_manually_created_transcript(all_codes)
    except NoTranscriptFound:
        try:
            transcript = transcript_list.find_generated_transcript(all_codes)
        except NoTranscriptFound as exc:
            raise AdapterError(
                f"No transcript found for {video_id}", path
            ) from exc

    data = transcript.fetch()
    return list(data), transcript.language_code, transcript.is_generated


async def _fetch_watch_metadata(
    video_id: str,
) -> tuple[str, str, "date | None"]:
    """Return (title, author, source_date). All empty/None on any failure."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(
                url, headers={"User-Agent": "obsidian-agent/1.0"}
            )
        if not resp.is_success:
            return "", "", None
        html = resp.text
    except Exception:
        return "", "", None

    title = ""
    author = ""
    source_date = None

    # Primary: JSON-LD VideoObject
    for match in _JSONLD_RE.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict) and data.get("@type") == "VideoObject":
                title = title or (data.get("name") or "")
                author_obj = data.get("author") or {}
                if isinstance(author_obj, dict):
                    author = author or (author_obj.get("name") or "")
                date_str = (
                    data.get("uploadDate") or data.get("datePublished") or ""
                )
                if date_str and source_date is None:
                    try:
                        source_date = date.fromisoformat(date_str[:10])
                    except ValueError:
                        pass
        except (json.JSONDecodeError, AttributeError):
            continue

    # Fallback: og:title
    if not title:
        m = _OG_TITLE_RE.search(html)
        title = m.group(1) if m else ""

    return title, author, source_date


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class YouTubeAdapter(BaseAdapter):
    """Source adapter for .youtube shortcut files in the inbox."""

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        """Extract transcript and metadata from a .youtube file at *path*.

        Raises:
            AdapterError: on read failure, bad URL, or transcript unavailability.
        """
        # 1. Read file
        try:
            raw = await anyio.Path(path).read_text(encoding="utf-8")
        except (OSError, PermissionError) as exc:
            raise AdapterError(str(exc), path) from exc

        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

        # 2. Extract URL and video ID
        url = _extract_url_from_file(raw)
        if not url:
            raise AdapterError("No YouTube URL found in file", path)

        video_id = _extract_video_id(url)
        if not video_id:
            raise AdapterError(f"Not a recognised YouTube URL: {url}", path)

        # 3. Fetch transcript (sync, in thread pool)
        try:
            segments, lang_code, is_auto = await anyio.to_thread.run_sync(
                lambda: _fetch_transcript(video_id, path), abandon_on_cancel=True
            )
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(
                f"Unexpected error fetching transcript: {exc}", path
            ) from exc

        # 4. Format transcript
        raw_text = _format_transcript(segments)
        if not raw_text.strip():
            raise AdapterError("Transcript is empty", path)

        # 5. Metadata (best-effort, non-fatal)
        title, author, source_date = await _fetch_watch_metadata(video_id)
        if not title:
            title = f"YouTube {video_id}"

        return NormalizedItem(
            raw_id=self._generate_raw_id(),
            source_type=SourceType.YOUTUBE,
            raw_text=raw_text,
            title=title,
            url=url,
            author=author,
            language=lang_code,
            source_date=source_date,
            file_mtime=file_mtime,
            raw_file_path=path,
            extra_metadata={
                "video_id": video_id,
                "language_code": lang_code,
                "is_auto_generated": is_auto,
                "fetch_url": url,
            },
        )
