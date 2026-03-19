"""Integration test: AudioAdapter produces a valid NormalizedItem.

All Whisper calls mocked — no real model in CI (too slow/large).
Validates the adapter cooperates with the NormalizedItem contract expected by Stage 1.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import anyio
import pytest
from pydantic import ValidationError

from agent.adapters.audio_adapter import AudioAdapter
from agent.core.config import AgentConfig, VaultConfig, WhisperConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_MOCK_SEGMENTS = [
    {"start": 0.0, "text": "Welcome to today's recording."},
    {"start": 5.5, "text": "We will cover some important topics."},
]


def _make_config(vault_root: Path) -> AgentConfig:
    return AgentConfig(
        vault=VaultConfig(root=str(vault_root)),
        whisper=WhisperConfig(model="base", language=None),
    )


def _make_whisper_mock(segments: list = _MOCK_SEGMENTS, language: str = "en") -> MagicMock:
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"segments": segments, "language": language}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    return mock_whisper


# ---------------------------------------------------------------------------
# Test 1 — Mocked Whisper, 2 segments → NormalizedItem passes Pydantic validation
# ---------------------------------------------------------------------------


def test_audio_adapter_produces_valid_normalized_item(tmp_path):
    """Full path: audio file → mocked Whisper → NormalizedItem validates."""
    audio_file = tmp_path / "meeting_2026-03-01.mp3"
    audio_file.write_bytes(b"fake mp3 content")
    config = _make_config(tmp_path)

    async def _run():
        return await AudioAdapter().extract(audio_file, config)

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = anyio.run(_run)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.AUDIO

    try:
        NormalizedItem.model_validate(item.model_dump())
    except ValidationError as exc:
        pytest.fail(f"NormalizedItem failed Pydantic validation: {exc}")


# ---------------------------------------------------------------------------
# Test 2 — raw_text contains [00: timestamp markers
# ---------------------------------------------------------------------------


def test_audio_adapter_transcript_contains_timestamp_markers(tmp_path):
    """Transcript formatting: each non-empty segment produces a [HH:MM:SS] marker."""
    audio_file = tmp_path / "lecture.wav"
    audio_file.write_bytes(b"fake wav content")
    config = _make_config(tmp_path)

    async def _run():
        return await AudioAdapter().extract(audio_file, config)

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = anyio.run(_run)

    assert "[00:00:00]" in item.raw_text
    assert "[00:00:05]" in item.raw_text
    assert "Welcome to today's recording." in item.raw_text
    assert "We will cover some important topics." in item.raw_text
