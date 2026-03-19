"""Unit tests for agent/adapters/youtube_adapter.py.

All external I/O mocked:
- YouTubeTranscriptApi patched via unittest.mock.patch
- httpx.AsyncClient mocked via pytest-httpx (httpx_mock fixture)
- _fetch_watch_metadata patched directly for transcript-focused tests

Async execution driven via anyio.run() — consistent with the rest of the test suite.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import httpx
import pytest

from agent.adapters.base import AdapterError
from agent.adapters.youtube_adapter import (
    YouTubeAdapter,
    _fetch_watch_metadata,
    _format_timestamp,
)
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

try:
    from youtube_transcript_api import VideoUnavailable
except ImportError:
    from youtube_transcript_api._errors import VideoUnavailable  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DEFAULT_VIDEO_ID = "dQw4w9WgXcQ"
_DEFAULT_SEGMENTS = [
    {"start": 0.0, "duration": 5.0, "text": "Hello world"},
    {"start": 5.0, "duration": 5.0, "text": "Second line"},
    {"start": 10.0, "duration": 5.0, "text": "Third line"},
]
_NO_METADATA = AsyncMock(return_value=("", "", None))

# Patch target for the YouTubeTranscriptApi class (instance-based in 1.x+)
_API_CLASS_PATCH = "agent.adapters.youtube_adapter.YouTubeTranscriptApi"


def _patch_api(transcript_list_mock: MagicMock):
    """Return a patch context that makes YouTubeTranscriptApi().list() return tl."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    mock_instance.list.return_value = transcript_list_mock
    return patch(_API_CLASS_PATCH, mock_cls)


def _make_config() -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root="/vault"))


def _make_youtube_file(tmp_path: Path, content: str, name: str = "video.youtube") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_transcript_mock(
    segments: list,
    language_code: str = "en",
    is_generated: bool = False,
) -> MagicMock:
    """Build a mock Transcript object."""
    t = MagicMock()
    t.language_code = language_code
    t.is_generated = is_generated
    t.fetch.return_value = segments
    return t


def _make_transcript_list_mock(
    transcripts: list,
    *,
    manual: MagicMock | None = None,
    generated: MagicMock | None = None,
) -> MagicMock:
    """Build a mock TranscriptList.

    - manual=<Transcript>  → find_manually_created_transcript returns it
    - manual=None          → find_manually_created_transcript raises NoTranscriptFound
    - generated=<Transcript>  → find_generated_transcript returns it
    - generated=None          → find_generated_transcript raises NoTranscriptFound
    """
    tl = MagicMock()
    tl.__iter__ = MagicMock(side_effect=lambda: iter(transcripts))

    if manual is not None:
        tl.find_manually_created_transcript.return_value = manual
    else:
        tl.find_manually_created_transcript.side_effect = NoTranscriptFound(
            "test_vid", ["en"], []
        )

    if generated is not None:
        tl.find_generated_transcript.return_value = generated
    else:
        tl.find_generated_transcript.side_effect = NoTranscriptFound(
            "test_vid", ["en"], []
        )

    return tl


def _run(path: Path, config: AgentConfig) -> NormalizedItem:
    """Run YouTubeAdapter.extract synchronously via anyio."""
    return anyio.run(YouTubeAdapter().extract, path, config)


# ---------------------------------------------------------------------------
# Case 1 — Valid .youtube file, youtube.com/watch?v=ABC URL, 3-segment transcript
# ---------------------------------------------------------------------------


def test_valid_youtube_file_returns_normalized_item(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.YOUTUBE
    assert "[00:00:00]" in item.raw_text
    assert "[00:00:05]" in item.raw_text


# ---------------------------------------------------------------------------
# Case 2 — youtu.be/ABC short URL
# ---------------------------------------------------------------------------


def test_youtu_be_short_url_extracts_video_id(tmp_path):
    path = _make_youtube_file(tmp_path, "https://youtu.be/ABC123\n")
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ) as mock_list, patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.extra_metadata["video_id"] == "ABC123"
    mock_list.assert_called_once_with("ABC123")


# ---------------------------------------------------------------------------
# Case 3 — URL with &t=42s param — video_id clean
# ---------------------------------------------------------------------------


def test_url_with_time_param_extracts_clean_video_id(tmp_path):
    url = f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}&t=42s"
    path = _make_youtube_file(tmp_path, url + "\n")
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.extra_metadata["video_id"] == _DEFAULT_VIDEO_ID
    assert "&t" not in item.extra_metadata["video_id"]


# ---------------------------------------------------------------------------
# Case 4 — m.youtube.com/watch?v=ABC
# ---------------------------------------------------------------------------


def test_mobile_youtube_url_extracts_video_id(tmp_path):
    path = _make_youtube_file(tmp_path, "https://m.youtube.com/watch?v=MOBILE1\n")
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ) as mock_list, patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.extra_metadata["video_id"] == "MOBILE1"
    mock_list.assert_called_once_with("MOBILE1")


# ---------------------------------------------------------------------------
# Case 5 — Manual transcript available → is_auto_generated == False
# ---------------------------------------------------------------------------


def test_manual_transcript_is_auto_generated_false(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS, is_generated=False)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.extra_metadata["is_auto_generated"] is False


# ---------------------------------------------------------------------------
# Case 6 — Only auto-generated transcript → is_auto_generated == True
# ---------------------------------------------------------------------------


def test_auto_generated_transcript_is_auto_generated_true(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS, is_generated=True)
    # manual raises NoTranscriptFound, generated returns t
    tl = _make_transcript_list_mock([t], manual=None, generated=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.extra_metadata["is_auto_generated"] is True


# ---------------------------------------------------------------------------
# Case 7 — TranscriptsDisabled → AdapterError with "disabled"
# ---------------------------------------------------------------------------


def test_transcripts_disabled_raises_adapter_error(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        side_effect=TranscriptsDisabled(_DEFAULT_VIDEO_ID),
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        with pytest.raises(AdapterError, match="disabled"):
            _run(path, config)


# ---------------------------------------------------------------------------
# Case 8 — VideoUnavailable → AdapterError with "unavailable"
# ---------------------------------------------------------------------------


def test_video_unavailable_raises_adapter_error(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        side_effect=VideoUnavailable(_DEFAULT_VIDEO_ID),
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        with pytest.raises(AdapterError, match="unavailable"):
            _run(path, config)


# ---------------------------------------------------------------------------
# Case 9 — NoTranscriptFound for all types → AdapterError "No transcript found"
# ---------------------------------------------------------------------------


def test_no_transcript_found_raises_adapter_error(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=None, generated=None)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        with pytest.raises(AdapterError, match="No transcript found"):
            _run(path, config)


# ---------------------------------------------------------------------------
# Case 10 — All transcript segments have empty .text → AdapterError "empty"
# ---------------------------------------------------------------------------


def test_empty_transcript_text_raises_adapter_error(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    empty_segments = [
        {"start": 0.0, "duration": 5.0, "text": ""},
        {"start": 5.0, "duration": 5.0, "text": "   "},
    ]
    t = _make_transcript_mock(empty_segments)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        with pytest.raises(AdapterError, match="Transcript is empty"):
            _run(path, config)


# ---------------------------------------------------------------------------
# Case 11 — Metadata JSON-LD VideoObject → title, author, source_date all populated
# ---------------------------------------------------------------------------


def test_metadata_jsonld_videoobject_all_fields(httpx_mock):
    html = """
<html>
<head>
<script type="application/ld+json">
{"@type": "VideoObject", "name": "My Great Video",
 "author": {"name": "Great Channel"},
 "uploadDate": "2024-06-15T00:00:00+00:00"}
</script>
</head>
<body></body>
</html>
"""
    httpx_mock.add_response(
        url=f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}",
        text=html,
    )

    async def _inner():
        return await _fetch_watch_metadata(_DEFAULT_VIDEO_ID)

    title, author, source_date = anyio.run(_inner)

    assert title == "My Great Video"
    assert author == "Great Channel"
    assert source_date == date(2024, 6, 15)


# ---------------------------------------------------------------------------
# Case 12 — JSON-LD present but not VideoObject type → og:title fallback
# ---------------------------------------------------------------------------


def test_metadata_jsonld_non_videoobject_uses_og_title(httpx_mock):
    html = """
<html>
<head>
<script type="application/ld+json">
{"@type": "WebPage", "name": "Ignored"}
</script>
<meta property="og:title" content="OG Fallback Title" />
</head>
<body></body>
</html>
"""
    httpx_mock.add_response(
        url=f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}",
        text=html,
    )

    async def _inner():
        return await _fetch_watch_metadata(_DEFAULT_VIDEO_ID)

    title, author, source_date = anyio.run(_inner)

    assert title == "OG Fallback Title"
    assert author == ""
    assert source_date is None


# ---------------------------------------------------------------------------
# Case 13 — Metadata fetch returns non-2xx → empty fallbacks
# ---------------------------------------------------------------------------


def test_metadata_non_2xx_returns_empty(httpx_mock):
    httpx_mock.add_response(
        url=f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}",
        status_code=403,
        text="Forbidden",
    )

    async def _inner():
        return await _fetch_watch_metadata(_DEFAULT_VIDEO_ID)

    title, author, source_date = anyio.run(_inner)

    assert title == ""
    assert author == ""
    assert source_date is None


# ---------------------------------------------------------------------------
# Case 14 — Metadata fetch raises httpx.RequestError → empty fallbacks, no propagation
# ---------------------------------------------------------------------------


def test_metadata_request_error_returns_empty(httpx_mock):
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url=f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}",
    )

    async def _inner():
        return await _fetch_watch_metadata(_DEFAULT_VIDEO_ID)

    title, author, source_date = anyio.run(_inner)

    assert title == ""
    assert author == ""
    assert source_date is None


# ---------------------------------------------------------------------------
# Case 15 — _format_timestamp(0.0) → "00:00:00"
# ---------------------------------------------------------------------------


def test_format_timestamp_zero():
    assert _format_timestamp(0.0) == "00:00:00"


# ---------------------------------------------------------------------------
# Case 16 — _format_timestamp(3661.5) → "01:01:01"
# ---------------------------------------------------------------------------


def test_format_timestamp_hours_minutes_seconds():
    assert _format_timestamp(3661.5) == "01:01:01"


# ---------------------------------------------------------------------------
# Case 17 — raw_id matches ^SRC-\d{8}-\d{6}$
# ---------------------------------------------------------------------------


def test_raw_id_format(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert re.match(r"^SRC-\d{8}-\d{6}$", item.raw_id)


# ---------------------------------------------------------------------------
# Case 18 — file_mtime is UTC-aware datetime
# ---------------------------------------------------------------------------


def test_file_mtime_is_utc_aware(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert isinstance(item.file_mtime, datetime)
    assert item.file_mtime.tzinfo is not None


# ---------------------------------------------------------------------------
# Case 19 — raw_file_path == path
# ---------------------------------------------------------------------------


def test_raw_file_path_equals_input(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.raw_file_path == path


# ---------------------------------------------------------------------------
# Case 20 — language set from transcript language_code
# ---------------------------------------------------------------------------


def test_language_set_from_transcript(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS, language_code="en")
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.language == "en"


# ---------------------------------------------------------------------------
# Case 21 — Empty .youtube file (only whitespace) → AdapterError
# ---------------------------------------------------------------------------


def test_empty_file_raises_adapter_error(tmp_path):
    path = _make_youtube_file(tmp_path, "   \n  \n  ")
    config = _make_config()

    with pytest.raises(AdapterError, match="No YouTube URL found in file"):
        _run(path, config)


# ---------------------------------------------------------------------------
# Case 22 — .youtube file with only # comment lines → AdapterError
# ---------------------------------------------------------------------------


def test_comment_only_file_raises_adapter_error(tmp_path):
    path = _make_youtube_file(tmp_path, "# This is a comment\n# Another comment\n")
    config = _make_config()

    with pytest.raises(AdapterError, match="No YouTube URL found in file"):
        _run(path, config)


# ---------------------------------------------------------------------------
# Case 23 — Non-YouTube URL → AdapterError
# ---------------------------------------------------------------------------


def test_non_youtube_url_raises_adapter_error(tmp_path):
    path = _make_youtube_file(tmp_path, "https://example.com/some-video\n")
    config = _make_config()

    with pytest.raises(AdapterError, match="Not a recognised YouTube URL"):
        _run(path, config)


# ---------------------------------------------------------------------------
# Case 24 — File read raises OSError → AdapterError
# ---------------------------------------------------------------------------


def test_file_read_oserror_raises_adapter_error(tmp_path):
    path = tmp_path / "video.youtube"
    path.write_text("placeholder", encoding="utf-8")
    config = _make_config()

    mock_path_instance = AsyncMock()
    mock_path_instance.read_text.side_effect = OSError("permission denied")

    with patch(
        "agent.adapters.youtube_adapter.anyio.Path",
        return_value=mock_path_instance,
    ):
        with pytest.raises(AdapterError) as exc_info:
            _run(path, config)

    assert exc_info.value.path == path


# ---------------------------------------------------------------------------
# Case 25 — extra_metadata keys: video_id, language_code, is_auto_generated, fetch_url
# ---------------------------------------------------------------------------


def test_extra_metadata_has_all_required_keys(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    keys = item.extra_metadata.keys()
    assert "video_id" in keys
    assert "language_code" in keys
    assert "is_auto_generated" in keys
    assert "fetch_url" in keys


# ---------------------------------------------------------------------------
# Case 26 — source_date from JSON-LD uploadDate: "2024-06-15T00:00:00"
# ---------------------------------------------------------------------------


def test_metadata_upload_date_parsed_to_source_date(httpx_mock):
    html = """
<html>
<head>
<script type="application/ld+json">
{"@type": "VideoObject", "name": "Test", "uploadDate": "2024-06-15T00:00:00"}
</script>
</head>
<body></body>
</html>
"""
    httpx_mock.add_response(
        url=f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}",
        text=html,
    )

    async def _inner():
        return await _fetch_watch_metadata(_DEFAULT_VIDEO_ID)

    _, _, source_date = anyio.run(_inner)

    assert source_date == date(2024, 6, 15)


# ---------------------------------------------------------------------------
# Extra — title falls back to "YouTube {video_id}" when metadata unavailable
# ---------------------------------------------------------------------------


def test_title_fallback_when_no_metadata(tmp_path):
    path = _make_youtube_file(
        tmp_path, f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.title == f"YouTube {_DEFAULT_VIDEO_ID}"


# ---------------------------------------------------------------------------
# Extra — url field equals the URL read from the .youtube file
# ---------------------------------------------------------------------------


def test_url_field_matches_file_content(tmp_path):
    expected_url = f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}"
    path = _make_youtube_file(tmp_path, expected_url + "\n")
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    assert item.url == expected_url
    assert item.extra_metadata["fetch_url"] == expected_url


# ---------------------------------------------------------------------------
# Extra — comment lines before URL are skipped
# ---------------------------------------------------------------------------


def test_comment_lines_before_url_are_skipped(tmp_path):
    content = (
        "# dropped from browser bookmarks\n"
        f"https://www.youtube.com/watch?v={_DEFAULT_VIDEO_ID}\n"
    )
    path = _make_youtube_file(tmp_path, content)
    config = _make_config()
    t = _make_transcript_mock(_DEFAULT_SEGMENTS)
    tl = _make_transcript_list_mock([t], manual=t)

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi.list_transcripts",
        return_value=tl,
    ) as mock_list, patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        _NO_METADATA,
    ):
        item = _run(path, config)

    mock_list.assert_called_once_with(_DEFAULT_VIDEO_ID)
    assert item.extra_metadata["video_id"] == _DEFAULT_VIDEO_ID
