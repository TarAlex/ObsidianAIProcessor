"""Integration test: YouTubeAdapter produces a valid NormalizedItem.

All network calls mocked — no live YouTube in CI.
Validates adapter cooperates with the NormalizedItem contract expected by Stage 1.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from pydantic import ValidationError

from agent.adapters.youtube_adapter import YouTubeAdapter
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_VIDEO_ID = "dQw4w9WgXcQ"
_MOCK_SEGMENTS = [
    {"start": 0.0, "duration": 5.0, "text": "Hello and welcome to this video."},
    {"start": 5.0, "duration": 5.0, "text": "Today we will cover an important topic."},
    {"start": 10.0, "duration": 5.0, "text": "Let's get started with the fundamentals."},
]


def _make_config(vault_root: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(vault_root)))


def _make_transcript_mock(segments: list) -> MagicMock:
    t = MagicMock()
    t.language_code = "en"
    t.is_generated = False
    t.fetch.return_value = segments
    return t


def _make_transcript_list_mock(transcript: MagicMock) -> MagicMock:
    tl = MagicMock()
    tl.__iter__ = MagicMock(side_effect=lambda: iter([transcript]))
    tl.find_manually_created_transcript.return_value = transcript
    return tl


# ---------------------------------------------------------------------------
# Test 1 — .youtube fixture with mocked transcript → NormalizedItem passes Pydantic validation
# ---------------------------------------------------------------------------


def test_youtube_adapter_produces_valid_normalized_item(tmp_path):
    """Full pipeline: .youtube file → mocked transcript → NormalizedItem validates."""
    youtube_file = tmp_path / "sample.youtube"
    youtube_file.write_text(
        f"# sample fixture\nhttps://www.youtube.com/watch?v={_VIDEO_ID}\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path)

    t = _make_transcript_mock(_MOCK_SEGMENTS)
    tl = _make_transcript_list_mock(t)

    async def _run():
        return await YouTubeAdapter().extract(youtube_file, config)

    mock_api = MagicMock()
    mock_api.return_value.list.return_value = tl

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi",
        mock_api,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        AsyncMock(return_value=("Test Video Title", "Test Channel", None)),
    ):
        item = anyio.run(_run)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.YOUTUBE

    try:
        NormalizedItem.model_validate(item.model_dump())
    except ValidationError as exc:
        pytest.fail(f"NormalizedItem failed Pydantic validation: {exc}")


# ---------------------------------------------------------------------------
# Test 2 — raw_text contains [00: timestamp markers from mocked segments
# ---------------------------------------------------------------------------


def test_youtube_adapter_transcript_contains_timestamp_markers(tmp_path):
    """Transcript formatting: every non-empty segment produces a [HH:MM:SS] marker."""
    youtube_file = tmp_path / "sample.youtube"
    youtube_file.write_text(
        f"https://www.youtube.com/watch?v={_VIDEO_ID}\n",
        encoding="utf-8",
    )
    config = _make_config(tmp_path)

    t = _make_transcript_mock(_MOCK_SEGMENTS)
    tl = _make_transcript_list_mock(t)

    async def _run():
        return await YouTubeAdapter().extract(youtube_file, config)

    mock_api = MagicMock()
    mock_api.return_value.list.return_value = tl

    with patch(
        "agent.adapters.youtube_adapter.YouTubeTranscriptApi",
        mock_api,
    ), patch(
        "agent.adapters.youtube_adapter._fetch_watch_metadata",
        AsyncMock(return_value=("", "", None)),
    ):
        item = anyio.run(_run)

    # Every segment should have a [HH:MM:SS] marker
    assert "[00:00:00]" in item.raw_text
    assert "[00:00:05]" in item.raw_text
    assert "[00:00:10]" in item.raw_text
    assert "Hello and welcome to this video." in item.raw_text
