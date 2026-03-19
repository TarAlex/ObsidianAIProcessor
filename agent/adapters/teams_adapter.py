"""TeamsAdapter — parses MS Teams meeting transcripts (.vtt / WebVTT files).

Phase 1 scope: local file parsing only.
No Graph API calls, no OAuth, no network access.

Supported format: WebVTT (.vtt) with optional <v SpeakerName> tags.
Output: NormalizedItem with SourceType.MS_TEAMS.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import anyio

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Compiled regexes
# ---------------------------------------------------------------------------

TIMING_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2})\.\d{3}\s*-->\s*(\d{2}:\d{2}:\d{2})\.\d{3}",
    re.MULTILINE,
)
SPEAKER_RE = re.compile(r"<v\s+([^>]+)>")
TAG_RE = re.compile(r"<[^>]+>")
DATE_RE = re.compile(r"(\d{4})[_-](\d{2})[_-](\d{2})")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _ts_to_seconds(ts: str) -> int:
    """Convert 'HH:MM:SS' to integer seconds."""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def _parse_vtt(content: str) -> tuple[list[str], list[str], int | None]:
    """Parse WebVTT content into transcript lines, speakers, and duration.

    Returns:
        transcript_lines: list of formatted "[HH:MM:SS] [Speaker: ]text" strings
        speakers_ordered: unique speaker names in insertion order
        duration_seconds: integer seconds of last cue end timestamp, or None
    """
    blocks = re.split(r"\n{2,}", content.strip())
    lines: list[str] = []
    seen_speakers: dict[str, None] = {}  # ordered set via dict keys
    last_end_seconds: int | None = None

    for block in blocks:
        m_timing = TIMING_RE.search(block)
        if not m_timing:
            continue  # header block, blank block, or cue-id-only block

        start_ts = m_timing.group(1)   # "HH:MM:SS"
        end_ts = m_timing.group(2)
        last_end_seconds = _ts_to_seconds(end_ts)

        # Cue text is everything after the timing line
        cue_text_raw = block[m_timing.end():].strip()
        if not cue_text_raw:
            continue

        speaker_m = SPEAKER_RE.search(cue_text_raw)
        speaker = speaker_m.group(1).strip() if speaker_m else ""
        if speaker:
            seen_speakers[speaker] = None

        # Strip all HTML/VTT inline tags; join continuation lines with a space
        clean_text = " ".join(TAG_RE.sub("", cue_text_raw).splitlines()).strip()
        if not clean_text:
            continue

        if speaker:
            lines.append(f"[{start_ts}] {speaker}: {clean_text}")
        else:
            lines.append(f"[{start_ts}] {clean_text}")

    return lines, list(seen_speakers), last_end_seconds


def _extract_date_from_stem(stem: str) -> date | None:
    """Extract the first ISO-8601-like date from a filename stem.

    Supports separators: hyphen or underscore.
    Returns None if no date pattern is found or the date is invalid.
    """
    m = DATE_RE.search(stem)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class TeamsAdapter(BaseAdapter):
    """Source adapter for MS Teams meeting transcripts (.vtt WebVTT files)."""

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        """Parse *path* as a WebVTT file and return a NormalizedItem.

        Raises:
            AdapterError: on stat failure, read failure, missing WEBVTT header,
                          or empty transcript.
        """
        # 1. Stat the file (fast, sync)
        try:
            file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError as exc:
            raise AdapterError(str(exc), path) from exc

        # 2. Read file content (utf-8-sig strips BOM silently)
        try:
            content = await anyio.Path(path).read_text(encoding="utf-8-sig")
        except (OSError, PermissionError) as exc:
            raise AdapterError(str(exc), path) from exc

        # 3. Validate WEBVTT header
        if not content.lstrip().startswith("WEBVTT"):
            raise AdapterError("File does not start with WEBVTT header", path)

        # 4. Parse cues
        transcript_lines, speakers, duration_seconds = _parse_vtt(content)
        if not transcript_lines:
            raise AdapterError("VTT file contains no parseable cue text", path)

        raw_text = "\n".join(transcript_lines)

        return NormalizedItem(
            raw_id=self._generate_raw_id(),
            source_type=SourceType.MS_TEAMS,
            raw_text=raw_text,
            title=path.stem,
            url="",
            author="",
            language="",
            source_date=_extract_date_from_stem(path.stem),
            file_mtime=file_mtime,
            raw_file_path=path,
            extra_metadata={
                "format": "vtt",
                "cue_count": len(transcript_lines),
                "speakers": speakers,
                "duration_seconds": duration_seconds,
            },
        )
