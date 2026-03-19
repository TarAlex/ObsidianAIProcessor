# Spec: YouTubeAdapter
slug: youtube-adapter
layer: adapters
phase: 1
arch_section: §1 (SOURCE ADAPTERS LAYER), §2 (agent/adapters/youtube_adapter.py)

---

## Problem statement

YouTube videos dropped into the inbox (as `.youtube` shortcut files containing a
single URL) must be converted into a `NormalizedItem` whose `raw_text` is the full
transcript with timestamps. No LLM, no OAuth, no API key.

`youtube-transcript-api` (already in `pyproject.toml`) fetches captions directly
from YouTube's caption track API. Because the library is fully synchronous (makes
HTTP requests internally), it must run inside `anyio.to_thread.run_sync()` — the
same pattern used by `PDFAdapter`.

Video metadata (title, channel, publish date) is fetched as a best-effort step via
`httpx.AsyncClient` using the watch page JSON-LD. This step is **non-fatal**: if
it fails for any reason (network, parse, non-2xx), the adapter proceeds with empty
metadata fields. The transcript itself is the only required output.

---

## Module contract

```
Input:  Path — a `.youtube` plain-text file; first non-comment line is the YouTube URL
        AgentConfig — no YouTube-specific keys consumed in Phase 1

Output: NormalizedItem
          raw_id:         SRC-YYYYMMDD-HHmmss (UTC) via _generate_raw_id()
          source_type:    SourceType.YOUTUBE
          raw_text:       transcript formatted as "[HH:MM:SS] text\n" per segment
          title:          JSON-LD name/og:title from watch page → "YouTube {video_id}"
          url:            the YouTube URL read from the .youtube file
          author:         channel name from JSON-LD → "" (non-fatal if unavailable)
          language:       ISO 639-1 / BCP-47 code from selected transcript (e.g. "en")
          source_date:    uploadDate from JSON-LD → None
          file_mtime:     datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
          raw_file_path:  path  (the .youtube shortcut file)
          extra_metadata: {
                            "video_id": str,           # e.g. "dQw4w9WgXcQ"
                            "language_code": str,       # e.g. "en", "ru-RU"
                            "is_auto_generated": bool,
                            "fetch_url": str,           # resolved YouTube URL
                          }

Raises: AdapterError if:
          - file cannot be read (OSError / PermissionError)
          - file has no non-comment, non-empty line
          - URL does not match YouTube hostname patterns
          - video_id cannot be extracted from the URL
          - TranscriptsDisabled for the video
          - VideoUnavailable
          - NoTranscriptFound (all types exhausted)
          - formatted transcript is empty after str.strip()
          - unexpected exception from transcript API
        Metadata fetch failures are silently swallowed (never AdapterError).
```

---

## Key implementation notes

### File format: `.youtube` extension

A `.youtube` file is a plain-text file whose first non-empty, non-comment line is
a YouTube URL. Lines starting with `#` are comments. Example:

```
# dropped from browser bookmarks
https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

Read with `anyio.Path(path).read_text(encoding="utf-8")`:

```python
def _extract_url_from_file(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""
```

Raise `AdapterError("No YouTube URL found in file", path)` if result is `""`.

### Video ID extraction

```python
from urllib.parse import urlparse, parse_qs

_YOUTUBE_HOSTS = frozenset({
    "www.youtube.com", "youtube.com", "m.youtube.com"
})

def _extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid or None
    if host in _YOUTUBE_HOSTS:
        qs = parse_qs(parsed.query)
        return qs.get("v", [None])[0]
    return None
```

Raise `AdapterError(f"Not a recognised YouTube URL: {url}", path)` when `None`.

### Transcript fetch — synchronous API in thread pool

`YouTubeTranscriptApi` is synchronous. Run in `anyio.to_thread.run_sync()`:

```python
import anyio
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)

# VideoUnavailable is in youtube_transcript_api._errors or the top-level package
# depending on version; import defensively:
try:
    from youtube_transcript_api import VideoUnavailable
except ImportError:
    from youtube_transcript_api._errors import VideoUnavailable


async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
    ...
    try:
        segments, lang_code, is_auto = await anyio.to_thread.run_sync(
            lambda: _fetch_transcript(video_id, path), cancellable=True
        )
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            f"Unexpected error fetching transcript: {exc}", path
        ) from exc
    ...
```

```python
def _fetch_transcript(
    video_id: str, path: Path
) -> tuple[list, str, bool]:
    """Sync helper — must run in a thread. Returns (segments, language_code, is_auto)."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
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
    # data items support dict-style access: item["text"], item["start"], item["duration"]
    return list(data), transcript.language_code, transcript.is_generated
```

**Note on `all_codes`**: `TranscriptList` is iterable; each item is a `Transcript`
object with `.language_code`. Passing all available codes to
`find_manually_created_transcript()` means "accept any manually-created language".

### Transcript formatting

```python
def _format_transcript(segments: list) -> str:
    """Format each segment as '[HH:MM:SS] text'."""
    lines: list[str] = []
    for seg in segments:
        ts = _format_timestamp(float(seg["start"]))
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
```

After formatting, if `raw_text.strip() == ""` raise
`AdapterError("Transcript is empty", path)`.

### Watch page metadata fetch (optional, non-fatal)

After a successful transcript fetch, attempt to retrieve video title, channel, and
publish date. Any failure returns empty/None without propagating.

```python
import httpx
import json
import re
from datetime import date

_JSONLD_RE = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_OG_TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"')


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
```

### `extract()` method assembly

```python
async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
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
            lambda: _fetch_transcript(video_id, path), cancellable=True
        )
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(f"Unexpected error fetching transcript: {exc}", path) from exc

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
```

### file_mtime

Called after a successful file read (not inside the thread helper):

```python
file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
```

### Error handling summary

| Condition | Raise |
|---|---|
| `OSError` / `PermissionError` reading file | `AdapterError(str(exc), path)` |
| File has no non-comment URL line | `AdapterError("No YouTube URL found in file", path)` |
| URL does not match YouTube host patterns | `AdapterError("Not a recognised YouTube URL: {url}", path)` |
| `TranscriptsDisabled` | `AdapterError("Transcripts disabled for {video_id}", path)` |
| `VideoUnavailable` | `AdapterError("Video unavailable: {video_id}", path)` |
| `NoTranscriptFound` (all types) | `AdapterError("No transcript found for {video_id}", path)` |
| Transcript formats to empty string | `AdapterError("Transcript is empty", path)` |
| Any other exception from transcript API | `AdapterError("Unexpected error fetching transcript: ...", path)` |
| Any failure in `_fetch_watch_metadata` | Silently returns `("", "", None)` — never raised |

---

## Data model changes

None. `SourceType.YOUTUBE = "youtube"` already exists in `models.py`.
`NormalizedItem` is unchanged. `youtube-transcript-api>=0.6` is already declared
in `pyproject.toml`.

---

## LLM prompt file needed

None. This adapter performs no LLM calls.

---

## Tests required

### Unit: `tests/unit/test_youtube_adapter.py`

All external I/O mocked:
- `youtube_transcript_api.YouTubeTranscriptApi` patched via `unittest.mock.patch`
- `httpx.AsyncClient` mocked via `pytest-httpx` (`HTTPX_MOCK` fixture) or
  `unittest.mock.AsyncMock`

Run async tests via `anyio` (project already uses `asyncio_mode = "auto"` in
`pytest.ini_options`).

| # | Case | Expected |
|---|---|---|
| 1 | Valid `.youtube` file, `youtube.com/watch?v=ABC` URL, 3-segment transcript | `NormalizedItem.source_type == YOUTUBE`, `raw_text` contains `[HH:MM:SS]` markers |
| 2 | `youtu.be/ABC` short URL | `extra_metadata["video_id"] == "ABC"` |
| 3 | URL with `&t=42s` param | `video_id` clean (no `&t` in it) |
| 4 | `m.youtube.com/watch?v=ABC` | `video_id` extracted correctly |
| 5 | Manual transcript available | `extra_metadata["is_auto_generated"] == False` |
| 6 | Only auto-generated transcript available | `extra_metadata["is_auto_generated"] == True` |
| 7 | `TranscriptsDisabled` raised | `AdapterError` with "disabled" in message |
| 8 | `VideoUnavailable` raised | `AdapterError` with "unavailable" in message |
| 9 | `NoTranscriptFound` for all types | `AdapterError` with "No transcript found" |
| 10 | All transcript segments have empty `.text` | `AdapterError("Transcript is empty", path)` |
| 11 | Metadata fetch: JSON-LD `VideoObject` with name + author + uploadDate | `title`, `author`, `source_date` all populated |
| 12 | Metadata fetch: JSON-LD present but not `VideoObject` type → og:title fallback | `title` from og:title |
| 13 | Metadata fetch returns non-2xx | `title = "YouTube {video_id}"`, `author=""`, `source_date=None` |
| 14 | Metadata fetch raises `httpx.RequestError` | Same fallbacks, no AdapterError propagated |
| 15 | `_format_timestamp(0.0)` → `"00:00:00"` | Exact string match |
| 16 | `_format_timestamp(3661.5)` → `"01:01:01"` | Exact string match |
| 17 | `raw_id` matches `^SRC-\d{8}-\d{6}$` | Regex match |
| 18 | `file_mtime` is UTC-aware `datetime` | `item.file_mtime.tzinfo is not None` |
| 19 | `raw_file_path == path` | Identity check |
| 20 | `language` set from transcript `language_code` | `item.language == "en"` (mock value) |
| 21 | Empty `.youtube` file (only whitespace) | `AdapterError("No YouTube URL found in file", path)` |
| 22 | `.youtube` file with only `#` comment lines | `AdapterError("No YouTube URL found in file", path)` |
| 23 | File contains non-YouTube URL (`https://example.com`) | `AdapterError("Not a recognised YouTube URL: ...", path)` |
| 24 | File read raises `OSError` | `AdapterError` raised with correct `path` |
| 25 | `extra_metadata` keys: `video_id`, `language_code`, `is_auto_generated`, `fetch_url` | All four present |
| 26 | `source_date` from JSON-LD `uploadDate: "2024-06-15T00:00:00"` | `source_date == date(2024, 6, 15)` |

### Integration: `tests/integration/test_pipeline_youtube.py`

All network calls mocked (no live YouTube in CI).
Uses `tests/fixtures/sample_youtube_transcript.md` as reference content
(already listed in TRACKER.md fixtures).

| # | Case | Expected |
|---|---|---|
| 1 | `.youtube` fixture file with mocked transcript → `NormalizedItem` passes Pydantic validation | No `ValidationError` |
| 2 | `raw_text` contains `[00:` timestamp markers from mocked segments | Transcript correctly formatted |

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| YouTube Data API v3 | Requires API key — forbidden per constraint |
| OAuth / login-gated videos | No authenticated requests in Phase 1 |
| Video or audio download | Handled by `audio_adapter.py` (openai-whisper) |
| LLM translation of transcript | No LLM inside adapters |
| Config-driven language preference | Phase 1: accept any available language; deferred |
| Retry logic for transient failures | Adapter layer does not retry |
| Playlist / channel / search URLs | Single video URL only |
| `.url` / `.webloc` files pointing to YouTube | Routed to `WebAdapter`; `.youtube` extension removes routing ambiguity |
| Caching of transcripts | Out of scope for Phase 1 |
| Subtitle format export (SRT, VTT) | Not needed; `raw_text` in `[HH:MM:SS] text` format is sufficient |

---

## Open questions

1. **Language preference**: Currently the adapter picks any available language
   (manual > auto-generated, any language code). Should `AgentConfig` expose
   `youtube.preferred_languages: list[str]`? Deferred — `_fetch_transcript`
   signature is written to accept a list if needed.

2. **Routing of `.url` files to YouTubeAdapter**: Current spec uses `.youtube`
   extension exclusively to avoid ambiguity with `WebAdapter`. If Stage 1
   (`s1_normalize.py`) should also route `.url` files whose URL contains
   `youtube.com` to this adapter, that is a Stage 1 / routing concern and does
   not change this spec.

3. **`youtube-transcript-api` import paths**: `VideoUnavailable` location varies
   between minor versions (`youtube_transcript_api` top-level vs.
   `youtube_transcript_api._errors`). The defensive `try/except ImportError`
   import pattern in the spec handles this; confirm against installed version.
