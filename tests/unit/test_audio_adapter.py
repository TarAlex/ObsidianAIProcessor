"""Unit tests for agent/adapters/audio_adapter.py.

All Whisper I/O mocked via unittest.mock.patch.
Async execution via anyio.run() — consistent with the rest of the test suite.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import anyio
import pytest

from agent.adapters.audio_adapter import AudioAdapter, _format_timestamp
from agent.adapters.base import AdapterError
from agent.core.config import AgentConfig, VaultConfig, WhisperConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SEGMENTS = [
    {"start": 0.0, "text": "Hello world"},
    {"start": 5.0, "text": "Second segment here"},
    {"start": 10.0, "text": "Third segment text"},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(model: str = "medium", language: str | None = None) -> AgentConfig:
    return AgentConfig(
        vault=VaultConfig(root="/vault"),
        whisper=WhisperConfig(model=model, language=language),
    )


def _make_audio_file(tmp_path: Path, name: str = "recording.mp3") -> Path:
    p = tmp_path / name
    p.write_bytes(b"fake audio data")
    return p


def _make_whisper_mock(
    segments: list = _DEFAULT_SEGMENTS,
    language: str = "en",
    load_error: Exception | None = None,
    transcribe_error: Exception | None = None,
) -> MagicMock:
    """Build a mock whisper module with a mock model."""
    mock_model = MagicMock()
    if transcribe_error:
        mock_model.transcribe.side_effect = transcribe_error
    else:
        mock_model.transcribe.return_value = {"segments": segments, "language": language}

    mock_whisper = MagicMock()
    if load_error:
        mock_whisper.load_model.side_effect = load_error
    else:
        mock_whisper.load_model.return_value = mock_model

    return mock_whisper


def _run(path: Path, config: AgentConfig) -> NormalizedItem:
    """Run AudioAdapter.extract synchronously via anyio."""
    return anyio.run(AudioAdapter().extract, path, config)


# ---------------------------------------------------------------------------
# Case 1 — Valid .mp3, 3 segments with text → AUDIO source_type, [HH:MM:SS] lines
# ---------------------------------------------------------------------------


def test_valid_mp3_returns_normalized_item(tmp_path):
    path = _make_audio_file(tmp_path, "recording.mp3")
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = _run(path, config)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.AUDIO
    assert "[00:00:00]" in item.raw_text
    assert "[00:00:05]" in item.raw_text
    assert "[00:00:10]" in item.raw_text


# ---------------------------------------------------------------------------
# Case 2 — Whisper detects language "ru" → item.language == "ru"
# ---------------------------------------------------------------------------


def test_whisper_detected_language_ru(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock(language="ru")):
        item = _run(path, config)

    assert item.language == "ru"


# ---------------------------------------------------------------------------
# Case 3 — config.whisper.language = "ru" → "language" kwarg passed to transcribe
# ---------------------------------------------------------------------------


def test_language_hint_passed_to_transcribe(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config(language="ru")
    mock_whisper = _make_whisper_mock(language="ru")

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        _run(path, config)

    mock_model = mock_whisper.load_model.return_value
    assert mock_model.transcribe.call_args.kwargs.get("language") == "ru"


# ---------------------------------------------------------------------------
# Case 4 — config.whisper.language = None → "language" NOT in transcribe kwargs
# ---------------------------------------------------------------------------


def test_no_language_hint_omits_kwarg(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config(language=None)
    mock_whisper = _make_whisper_mock()

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        _run(path, config)

    mock_model = mock_whisper.load_model.return_value
    assert "language" not in mock_model.transcribe.call_args.kwargs


# ---------------------------------------------------------------------------
# Case 5 — config.whisper.model = "base" → whisper.load_model("base") called
# ---------------------------------------------------------------------------


def test_model_base_calls_load_model_base(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config(model="base")
    mock_whisper = _make_whisper_mock()

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        _run(path, config)

    mock_whisper.load_model.assert_called_once_with("base")


# ---------------------------------------------------------------------------
# Case 6 — config.whisper.model = "large" → whisper.load_model("large") called
# ---------------------------------------------------------------------------


def test_model_large_calls_load_model_large(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config(model="large")
    mock_whisper = _make_whisper_mock()

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        _run(path, config)

    mock_whisper.load_model.assert_called_once_with("large")


# ---------------------------------------------------------------------------
# Case 7 — All segments have empty "text" → AdapterError("Transcript is empty ...")
# ---------------------------------------------------------------------------


def test_all_empty_segments_raises_adapter_error(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()
    empty_segs = [{"start": 0.0, "text": ""}, {"start": 5.0, "text": "   "}]
    mock_whisper = _make_whisper_mock(segments=empty_segs)

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        with pytest.raises(AdapterError, match="Transcript is empty"):
            _run(path, config)


# ---------------------------------------------------------------------------
# Case 8 — result["segments"] absent / None → AdapterError("Transcript is empty ...")
# ---------------------------------------------------------------------------


def test_missing_segments_key_raises_adapter_error(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()
    # result has no "segments" key at all
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"language": "en"}  # no "segments" key
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        with pytest.raises(AdapterError, match="Transcript is empty"):
            _run(path, config)


def test_none_segments_raises_adapter_error(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()
    # result["segments"] is explicitly None
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"segments": None, "language": "en"}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        with pytest.raises(AdapterError, match="Transcript is empty"):
            _run(path, config)


# ---------------------------------------------------------------------------
# Case 9 — whisper.load_model() raises RuntimeError → AdapterError("Failed to load ...")
# ---------------------------------------------------------------------------


def test_load_model_error_raises_adapter_error(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config(model="base")
    mock_whisper = _make_whisper_mock(load_error=RuntimeError("CUDA not available"))

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        with pytest.raises(AdapterError, match="Failed to load Whisper model 'base'"):
            _run(path, config)


# ---------------------------------------------------------------------------
# Case 10 — model.transcribe() raises Exception → AdapterError("Whisper transcription failed ...")
# ---------------------------------------------------------------------------


def test_transcribe_error_raises_adapter_error(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()
    mock_whisper = _make_whisper_mock(transcribe_error=Exception("audio decode error"))

    with patch("agent.adapters.audio_adapter.whisper", mock_whisper):
        with pytest.raises(AdapterError, match="Whisper transcription failed"):
            _run(path, config)


# ---------------------------------------------------------------------------
# Case 11 — path.stat() raises OSError → AdapterError(str(exc), path)
# ---------------------------------------------------------------------------


def test_stat_oserror_raises_adapter_error(tmp_path):
    path = tmp_path / "missing.mp3"  # does not exist → stat() raises FileNotFoundError
    config = _make_config()

    with pytest.raises(AdapterError) as exc_info:
        _run(path, config)

    assert exc_info.value.path == path


# ---------------------------------------------------------------------------
# Case 12 — _format_timestamp(0.0) → "00:00:00"
# ---------------------------------------------------------------------------


def test_format_timestamp_zero():
    assert _format_timestamp(0.0) == "00:00:00"


# ---------------------------------------------------------------------------
# Case 13 — _format_timestamp(3661.5) → "01:01:01"
# ---------------------------------------------------------------------------


def test_format_timestamp_hours_minutes_seconds():
    assert _format_timestamp(3661.5) == "01:01:01"


# ---------------------------------------------------------------------------
# Case 14 — raw_id matches ^SRC-\d{8}-\d{6}$
# ---------------------------------------------------------------------------


def test_raw_id_format(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = _run(path, config)

    assert re.match(r"^SRC-\d{8}-\d{6}$", item.raw_id)


# ---------------------------------------------------------------------------
# Case 15 — file_mtime is UTC-aware datetime
# ---------------------------------------------------------------------------


def test_file_mtime_is_utc_aware(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = _run(path, config)

    assert isinstance(item.file_mtime, datetime)
    assert item.file_mtime.tzinfo is not None


# ---------------------------------------------------------------------------
# Case 16 — raw_file_path == path
# ---------------------------------------------------------------------------


def test_raw_file_path_equals_input(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = _run(path, config)

    assert item.raw_file_path == path


# ---------------------------------------------------------------------------
# Case 17 — item.url == "" and item.author == ""
# ---------------------------------------------------------------------------


def test_url_and_author_are_empty(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = _run(path, config)

    assert item.url == ""
    assert item.author == ""


# ---------------------------------------------------------------------------
# Case 18 — source_date is None
# ---------------------------------------------------------------------------


def test_source_date_is_none(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = _run(path, config)

    assert item.source_date is None


# ---------------------------------------------------------------------------
# Case 19 — extra_metadata["whisper_model"] matches config.whisper.model
# ---------------------------------------------------------------------------


def test_extra_metadata_whisper_model(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config(model="small")

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = _run(path, config)

    assert item.extra_metadata["whisper_model"] == "small"


# ---------------------------------------------------------------------------
# Case 20 — extra_metadata["detected_language"] matches Whisper result "language"
# ---------------------------------------------------------------------------


def test_extra_metadata_detected_language(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock(language="fr")):
        item = _run(path, config)

    assert item.extra_metadata["detected_language"] == "fr"


# ---------------------------------------------------------------------------
# Case 21 — item.title == path.stem
# ---------------------------------------------------------------------------


def test_title_equals_path_stem(tmp_path):
    path = _make_audio_file(tmp_path, "meeting_2026-03-01.mp3")
    config = _make_config()

    with patch("agent.adapters.audio_adapter.whisper", _make_whisper_mock()):
        item = _run(path, config)

    assert item.title == "meeting_2026-03-01"


# ---------------------------------------------------------------------------
# Case 22 — unexpected non-AdapterError from thread → AdapterError("Unexpected transcription error ...")
# ---------------------------------------------------------------------------


def test_unexpected_thread_exception_raises_adapter_error(tmp_path):
    path = _make_audio_file(tmp_path)
    config = _make_config()

    # Patch _transcribe to raise a non-AdapterError, bypassing its internal handlers.
    # This exercises the outer except Exception branch in extract().
    with patch(
        "agent.adapters.audio_adapter._transcribe",
        side_effect=ValueError("unexpected internal failure"),
    ):
        with pytest.raises(AdapterError, match="Unexpected transcription error"):
            _run(path, config)
