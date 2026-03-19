"""Unit tests for agent/adapters/teams_adapter.py.

All file I/O uses real tmp_path fixtures (no mocking needed — stdlib only).
Async execution via anyio.run().
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import anyio
import pytest

from agent.adapters.base import AdapterError
from agent.adapters.teams_adapter import (
    TeamsAdapter,
    _extract_date_from_stem,
    _parse_vtt,
    _ts_to_seconds,
)
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root="/vault"))


def _make_vtt(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _run(path: Path, config: AgentConfig | None = None) -> NormalizedItem:
    return anyio.run(TeamsAdapter().extract, path, config or _make_config())


# ---------------------------------------------------------------------------
# VTT content constants
# ---------------------------------------------------------------------------

_BASIC_VTT = """\
WEBVTT

00:00:00.000 --> 00:00:05.000
<v Alice>Hello everyone

00:00:05.000 --> 00:00:10.000
<v Bob>Good morning team

00:00:10.000 --> 00:00:15.000
<v Alice>Let us begin
"""

_NO_SPEAKER_VTT = """\
WEBVTT

00:00:00.000 --> 00:00:05.000
Hello everyone

00:00:05.000 --> 00:00:10.000
Good morning team
"""

_MIXED_VTT = """\
WEBVTT

00:00:00.000 --> 00:00:05.000
<v Alice>Hello everyone

00:00:05.000 --> 00:00:10.000
No speaker here

00:00:10.000 --> 00:00:15.000
<v Bob>Signing off
"""

_HEADER_ONLY_VTT = """\
WEBVTT

NOTE This is just a comment
"""

_MULTILINE_CUE_VTT = """\
WEBVTT

00:00:00.000 --> 00:00:10.000
<v Alice>This is line one
This is line two
"""

_COLOR_TAG_VTT = """\
WEBVTT

00:00:00.000 --> 00:00:05.000
<c.colorFF0000>Important text</c>
"""

_DURATION_VTT = """\
WEBVTT

00:00:00.000 --> 00:01:30.000
<v Alice>This is the only cue
"""


# ---------------------------------------------------------------------------
# Case 1 — Valid VTT with 3 speaker cues
# ---------------------------------------------------------------------------


def test_valid_vtt_source_type_and_transcript_lines(tmp_path):
    path = _make_vtt(tmp_path, "standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert item.source_type == SourceType.MS_TEAMS
    assert "[00:00:00] Alice: Hello everyone" in item.raw_text
    assert "[00:00:05] Bob: Good morning team" in item.raw_text
    assert "[00:00:10] Alice: Let us begin" in item.raw_text


# ---------------------------------------------------------------------------
# Case 2 — VTT cues with no <v> speaker tag → "[HH:MM:SS] text" format
# ---------------------------------------------------------------------------


def test_no_speaker_lines_formatted_without_prefix(tmp_path):
    path = _make_vtt(tmp_path, "notes.vtt", _NO_SPEAKER_VTT)
    item = _run(path)

    assert "[00:00:00] Hello everyone" in item.raw_text
    assert "[00:00:05] Good morning team" in item.raw_text
    # Must NOT have a colon after timestamp when no speaker
    for line in item.raw_text.splitlines():
        if "Hello everyone" in line or "Good morning team" in line:
            assert "] " in line
            # No speaker means the character after "] " is NOT "SpeakerName:"
            after_bracket = line.split("] ", 1)[1]
            assert not after_bracket.startswith("Alice:") and not after_bracket.startswith("Bob:")


# ---------------------------------------------------------------------------
# Case 3 — Mixed cues — some with speaker, some without
# ---------------------------------------------------------------------------


def test_mixed_cues_each_line_correct(tmp_path):
    path = _make_vtt(tmp_path, "mixed.vtt", _MIXED_VTT)
    item = _run(path)
    lines = item.raw_text.splitlines()

    assert lines[0] == "[00:00:00] Alice: Hello everyone"
    assert lines[1] == "[00:00:05] No speaker here"
    assert lines[2] == "[00:00:10] Bob: Signing off"


# ---------------------------------------------------------------------------
# Case 4 — extra_metadata["speakers"] — unique names, insertion order
# ---------------------------------------------------------------------------


def test_speakers_unique_and_insertion_order(tmp_path):
    vtt = """\
WEBVTT

00:00:00.000 --> 00:00:05.000
<v Alice>First

00:00:05.000 --> 00:00:10.000
<v Bob>Second

00:00:10.000 --> 00:00:15.000
<v Alice>Third (Alice again — should not duplicate)
"""
    path = _make_vtt(tmp_path, "order.vtt", vtt)
    item = _run(path)

    assert item.extra_metadata["speakers"] == ["Alice", "Bob"]


# ---------------------------------------------------------------------------
# Case 5 — extra_metadata["cue_count"] equals number of non-empty cue lines
# ---------------------------------------------------------------------------


def test_cue_count_equals_non_empty_lines(tmp_path):
    path = _make_vtt(tmp_path, "standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert item.extra_metadata["cue_count"] == 3
    assert item.extra_metadata["cue_count"] == len(item.raw_text.splitlines())


# ---------------------------------------------------------------------------
# Case 6 — extra_metadata["duration_seconds"] from last cue end timestamp
# ---------------------------------------------------------------------------


def test_duration_seconds_from_last_cue(tmp_path):
    path = _make_vtt(tmp_path, "long.vtt", _DURATION_VTT)
    item = _run(path)

    assert item.extra_metadata["duration_seconds"] == 90  # 00:01:30


# ---------------------------------------------------------------------------
# Case 7 — VTT with no timing lines → AdapterError("no parseable cue text")
# ---------------------------------------------------------------------------


def test_header_only_vtt_raises_adapter_error(tmp_path):
    path = _make_vtt(tmp_path, "empty.vtt", _HEADER_ONLY_VTT)

    with pytest.raises(AdapterError, match="no parseable cue text"):
        _run(path)


# ---------------------------------------------------------------------------
# Case 8 — File with BOM is parsed successfully
# ---------------------------------------------------------------------------


def test_bom_vtt_parsed_successfully(tmp_path):
    path = tmp_path / "bom.vtt"
    # Write UTF-8 with BOM
    path.write_bytes("\ufeff".encode("utf-8") + _BASIC_VTT.encode("utf-8"))

    item = _run(path)
    assert item.source_type == SourceType.MS_TEAMS
    assert item.raw_text  # non-empty


# ---------------------------------------------------------------------------
# Case 9 — File not starting with WEBVTT → AdapterError("WEBVTT header")
# ---------------------------------------------------------------------------


def test_non_vtt_file_raises_adapter_error(tmp_path):
    path = _make_vtt(tmp_path, "plain.txt", "This is not a VTT file\nsome text here\n")

    with pytest.raises(AdapterError, match="WEBVTT header"):
        _run(path)


# ---------------------------------------------------------------------------
# Case 10 — path.stat() raises OSError → AdapterError with correct path
# ---------------------------------------------------------------------------


def test_stat_oserror_raises_adapter_error(tmp_path):
    path = tmp_path / "missing.vtt"  # does not exist

    with pytest.raises(AdapterError) as exc_info:
        _run(path)

    assert exc_info.value.path == path


# ---------------------------------------------------------------------------
# Case 11 — File unreadable (OSError from read) → AdapterError raised
# ---------------------------------------------------------------------------


def test_read_oserror_raises_adapter_error(tmp_path):
    path = _make_vtt(tmp_path, "unreadable.vtt", _BASIC_VTT)

    with patch(
        "agent.adapters.teams_adapter.anyio.Path.read_text",
        side_effect=OSError("permission denied"),
    ):
        with pytest.raises(AdapterError):
            _run(path)


# ---------------------------------------------------------------------------
# Case 12 — Filename with hyphen date → source_date extracted
# ---------------------------------------------------------------------------


def test_source_date_from_hyphen_filename(tmp_path):
    path = _make_vtt(tmp_path, "2026-01-15_Team_Standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert item.source_date == date(2026, 1, 15)


# ---------------------------------------------------------------------------
# Case 13 — Filename with underscore date → source_date extracted
# ---------------------------------------------------------------------------


def test_source_date_from_underscore_filename(tmp_path):
    path = _make_vtt(tmp_path, "2026_01_15_meeting.vtt", _BASIC_VTT)
    item = _run(path)

    assert item.source_date == date(2026, 1, 15)


# ---------------------------------------------------------------------------
# Case 14 — Filename with no date → source_date is None
# ---------------------------------------------------------------------------


def test_no_date_in_filename_gives_none(tmp_path):
    path = _make_vtt(tmp_path, "standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert item.source_date is None


# ---------------------------------------------------------------------------
# Case 15 — raw_id matches ^SRC-\d{8}-\d{6}$
# ---------------------------------------------------------------------------


def test_raw_id_format(tmp_path):
    path = _make_vtt(tmp_path, "standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert re.match(r"^SRC-\d{8}-\d{6}$", item.raw_id)


# ---------------------------------------------------------------------------
# Case 16 — file_mtime is UTC-aware datetime
# ---------------------------------------------------------------------------


def test_file_mtime_is_utc_aware(tmp_path):
    path = _make_vtt(tmp_path, "standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert isinstance(item.file_mtime, datetime)
    assert item.file_mtime.tzinfo is not None


# ---------------------------------------------------------------------------
# Case 17 — raw_file_path == path
# ---------------------------------------------------------------------------


def test_raw_file_path_equals_input(tmp_path):
    path = _make_vtt(tmp_path, "standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert item.raw_file_path == path


# ---------------------------------------------------------------------------
# Case 18 — url, author, language are all empty strings
# ---------------------------------------------------------------------------


def test_url_author_language_are_empty(tmp_path):
    path = _make_vtt(tmp_path, "standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert item.url == ""
    assert item.author == ""
    assert item.language == ""


# ---------------------------------------------------------------------------
# Case 19 — title equals path.stem
# ---------------------------------------------------------------------------


def test_title_equals_path_stem(tmp_path):
    path = _make_vtt(tmp_path, "2026-01-15_standup.vtt", _BASIC_VTT)
    item = _run(path)

    assert item.title == "2026-01-15_standup"


# ---------------------------------------------------------------------------
# Case 20 — _ts_to_seconds helper
# ---------------------------------------------------------------------------


def test_ts_to_seconds():
    assert _ts_to_seconds("01:02:03") == 3723


def test_ts_to_seconds_zero():
    assert _ts_to_seconds("00:00:00") == 0


def test_ts_to_seconds_hours():
    assert _ts_to_seconds("02:00:00") == 7200


# ---------------------------------------------------------------------------
# Case 21 — Multi-line cue text joined with space
# ---------------------------------------------------------------------------


def test_multiline_cue_text_joined_with_space(tmp_path):
    path = _make_vtt(tmp_path, "multi.vtt", _MULTILINE_CUE_VTT)
    item = _run(path)

    assert "This is line one This is line two" in item.raw_text


# ---------------------------------------------------------------------------
# Case 22 — Non-speaker VTT tag stripped, text preserved
# ---------------------------------------------------------------------------


def test_color_tag_stripped_text_preserved(tmp_path):
    path = _make_vtt(tmp_path, "color.vtt", _COLOR_TAG_VTT)
    item = _run(path)

    assert "Important text" in item.raw_text
    assert "<c" not in item.raw_text
    assert "</c>" not in item.raw_text


# ---------------------------------------------------------------------------
# Additional: _extract_date_from_stem directly
# ---------------------------------------------------------------------------


def test_extract_date_from_stem_hyphen():
    assert _extract_date_from_stem("2026-01-15_standup") == date(2026, 1, 15)


def test_extract_date_from_stem_underscore():
    assert _extract_date_from_stem("2026_01_15_meeting") == date(2026, 1, 15)


def test_extract_date_from_stem_no_date():
    assert _extract_date_from_stem("weekly_standup") is None


def test_extract_date_from_stem_invalid_date():
    assert _extract_date_from_stem("2026-13-99_meeting") is None


# ---------------------------------------------------------------------------
# Additional: _parse_vtt with duration_seconds = None when no cues
# ---------------------------------------------------------------------------


def test_parse_vtt_no_timing_blocks_returns_none_duration():
    lines, speakers, duration = _parse_vtt("WEBVTT\n\nNOTE just a comment\n")
    assert lines == []
    assert speakers == []
    assert duration is None
