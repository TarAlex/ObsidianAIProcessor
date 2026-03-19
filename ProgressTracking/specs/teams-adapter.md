# Spec: TeamsAdapter
slug: teams-adapter
layer: adapters
phase: 1
arch_section: §1 (SOURCE ADAPTERS LAYER), §2 (agent/adapters/teams_adapter.py), §5 (Source Ingestion — MS Teams)

---

## Problem statement

MS Teams meeting transcripts dropped manually into `00_INBOX/` (typically
`00_INBOX/recordings/` or `00_INBOX/external_data/`) as `.vtt` (WebVTT) files
must be parsed into a `NormalizedItem` so the pipeline can classify, summarise,
and file them as source notes of type `ms_teams`.

Teams generates `.vtt` files for recorded meetings. These are plain-text files
containing timestamped cue blocks with optional `<v SpeakerName>` tags. The
adapter parses these cues into a structured `[HH:MM:SS] Speaker: text` transcript.

**Phase 1 scope: local file parsing only.** No Graph API calls, no OAuth, no
network access. Phase 2 will add automatic Graph API polling (explicitly listed
in TRACKER.md as `[ PHASE_2 ] MS Teams Graph API polling`).

---

## Module contract

```
Input:  extract(path: pathlib.Path, config: AgentConfig) -> NormalizedItem
          path   — absolute Path to a .vtt (WebVTT) Teams transcript file
          config — fully validated AgentConfig; no Teams-specific fields consumed

Output: NormalizedItem
          raw_id         str              "SRC-YYYYMMDD-HHmmss" (UTC)
          source_type    SourceType       SourceType.MS_TEAMS (always)
          raw_text       str              formatted transcript — one line per cue:
                                          "[HH:MM:SS] Speaker: text"  (speaker present)
                                          "[HH:MM:SS] text"            (no speaker tag)
                                          Lines joined with "\n"; non-empty
          title          str              path.stem, with ISO-8601 date patterns
                                          normalised (underscores → hyphens);
                                          e.g. "2026-01-15_Team_Standup" → as-is
          url            str              "" (no URL for local VTT files)
          author         str              "" (meeting has multiple speakers; see extra_metadata)
          language       str              "" (no language detection in Phase 1)
          source_date    date | None      extracted from filename stem via regex
                                          r"\d{4}[-_]\d{2}[-_]\d{2}"; None if not found
          file_mtime     datetime         datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
          raw_file_path  Path             the path argument as-is
          extra_metadata dict             {
                                            "format": "vtt",
                                            "cue_count": int,      # total parsed cues
                                            "speakers": list[str], # unique speaker names, insertion order
                                            "duration_seconds": int | None  # from last cue end timestamp
                                          }

Raises: AdapterError(message: str, path: Path)
          - path.stat() fails (OSError, PermissionError)
          - File cannot be read (OSError, PermissionError)
          - File does not start with "WEBVTT" header after stripping BOM/whitespace
          - Parsed transcript is empty (all cues have empty text after stripping)
        Never raised for missing optional VTT fields (no speaker tag → silent default).
```

---

## Key implementation notes

### Dependency footprint

`stdlib` only — `re`, `pathlib`, `datetime`. No new packages. VTT is plain text.

### Async file read — anyio

```python
import anyio

async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
    try:
        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError as exc:
        raise AdapterError(str(exc), path) from exc

    try:
        content = await anyio.Path(path).read_text(encoding="utf-8-sig")
        # utf-8-sig strips BOM silently — Teams exports sometimes include it
    except (OSError, PermissionError) as exc:
        raise AdapterError(str(exc), path) from exc
```

### WEBVTT header validation

```python
if not content.lstrip().startswith("WEBVTT"):
    raise AdapterError("File does not start with WEBVTT header", path)
```

### VTT cue parsing

WebVTT format (RFC 8216 / W3C):
```
WEBVTT
[optional metadata block ending with blank line]

[optional cue id]
HH:MM:SS.mmm --> HH:MM:SS.mmm [settings]
[<v SpeakerName>]cue text line 1
[continuation line 2]

[next cue...]
```

Parse strategy — split on double newlines, then for each block:
1. Skip the header block (starts with `WEBVTT`) and blank/metadata-only blocks.
2. Identify the **timing line**: matches `\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}`.
3. All lines after the timing line are cue text — join with space.
4. Extract speaker from first `<v Name>` tag in cue text; remove all `<...>` tags before logging the text.
5. Build output line: `[HH:MM:SS] Speaker: text` or `[HH:MM:SS] text`.

```python
import re

TIMING_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2})\.\d{3}\s*-->\s*(\d{2}:\d{2}:\d{2})\.\d{3}",
    re.MULTILINE,
)
SPEAKER_RE = re.compile(r"<v\s+([^>]+)>")
TAG_RE = re.compile(r"<[^>]+>")

def _parse_vtt(content: str) -> tuple[list[str], list[str], int | None]:
    """Return (transcript_lines, speakers_ordered, duration_seconds)."""
    blocks = re.split(r"\n{2,}", content.strip())
    lines: list[str] = []
    seen_speakers: dict[str, None] = {}  # ordered set
    last_end_seconds: int | None = None

    for block in blocks:
        m_timing = TIMING_RE.search(block)
        if not m_timing:
            continue  # header, blank, or cue-id-only block

        start_ts = m_timing.group(1)          # "HH:MM:SS"
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

        # Strip all HTML/VTT tags
        clean_text = TAG_RE.sub("", cue_text_raw).strip()
        if not clean_text:
            continue

        if speaker:
            lines.append(f"[{start_ts}] {speaker}: {clean_text}")
        else:
            lines.append(f"[{start_ts}] {clean_text}")

    return lines, list(seen_speakers), last_end_seconds


def _ts_to_seconds(ts: str) -> int:
    """Convert 'HH:MM:SS' to integer seconds."""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)
```

### Date extraction from filename

```python
DATE_RE = re.compile(r"(\d{4})[_-](\d{2})[_-](\d{2})")

def _extract_date_from_stem(stem: str) -> date | None:
    m = DATE_RE.search(stem)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
```

### Empty transcript guard

After `_parse_vtt`, if `transcript_lines` is empty:
```python
raise AdapterError("VTT file contains no parseable cue text", path)
```

### Full `extract()` assembly

```python
class TeamsAdapter(BaseAdapter):

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        # 1. Stat
        try:
            file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError as exc:
            raise AdapterError(str(exc), path) from exc

        # 2. Read
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
```

### Error handling summary

| Condition | Behaviour |
|---|---|
| `path.stat()` raises `OSError` | `AdapterError(str(exc), path)` |
| `anyio.Path.read_text()` raises `OSError` or `PermissionError` | `AdapterError(str(exc), path)` |
| File does not start with `WEBVTT` | `AdapterError("File does not start with WEBVTT header", path)` |
| All cues have empty text after tag stripping | `AdapterError("VTT file contains no parseable cue text", path)` |

---

## Data model changes

None. `SourceType.MS_TEAMS = "ms_teams"` already exists in `agent/core/models.py`.
`NormalizedItem` is unchanged. No new config fields required.

---

## LLM prompt file needed

None. This adapter performs no LLM calls.

---

## Tests required

### Unit: `tests/unit/test_teams_adapter.py`

Use `tmp_path` to write real VTT fixture files. Run async methods via
`anyio.run()` or `pytest-anyio` with `asyncio_mode = "auto"`.

| # | Case | Expected |
|---|---|---|
| 1 | Valid VTT with 3 speaker cues | `source_type == SourceType.MS_TEAMS`, `raw_text` has `[HH:MM:SS] Speaker: text` lines |
| 2 | VTT cues with no `<v>` speaker tag | Lines formatted as `[HH:MM:SS] text` (no speaker prefix) |
| 3 | Mixed cues — some with speaker, some without | Each line correct independently |
| 4 | `extra_metadata["speakers"]` contains unique names in insertion order | Deduplication and order preserved |
| 5 | `extra_metadata["cue_count"]` equals number of non-empty cue lines | Integer match |
| 6 | `extra_metadata["duration_seconds"]` derived from last cue's end timestamp | e.g. `00:01:30.000` → `90` |
| 7 | VTT with no timing lines (only header) | `AdapterError("VTT file contains no parseable cue text", path)` |
| 8 | File with BOM (`\ufeffWEBVTT...`) parsed successfully | BOM stripped by `utf-8-sig`; no `AdapterError` |
| 9 | File not starting with `WEBVTT` (e.g. plain `.txt`) | `AdapterError("File does not start with WEBVTT header", path)` |
| 10 | `path.stat()` raises `OSError` | `AdapterError` with correct `path` |
| 11 | File unreadable (`OSError` from read) | `AdapterError` raised |
| 12 | Filename `2026-01-15_Team_Standup.vtt` → `source_date == date(2026, 1, 15)` | Date extracted |
| 13 | Filename with underscore date `2026_01_15_meeting.vtt` → `source_date == date(2026, 1, 15)` | Underscore separator supported |
| 14 | Filename with no date pattern → `source_date is None` | None, no error |
| 15 | `raw_id` matches `^SRC-\d{8}-\d{6}$` | Regex match |
| 16 | `file_mtime` is UTC-aware `datetime` | `item.file_mtime.tzinfo is not None` |
| 17 | `raw_file_path == path` | Identity check |
| 18 | `item.url == ""` and `item.author == ""` and `item.language == ""` | All empty |
| 19 | `item.title == path.stem` | e.g. `"2026-01-15_standup"` |
| 20 | `_ts_to_seconds("01:02:03")` → `3723` | Unit test on helper directly |
| 21 | `_parse_vtt` with multi-line cue text (two text lines after timing) | Lines joined with space correctly |
| 22 | Cue with `<c.colorFF0000>text</c>` (non-speaker tag) | Tag stripped; text preserved |

### Integration: `tests/integration/test_pipeline_teams.py`

Uses a fixture VTT file at `tests/fixtures/sample_teams_transcript.vtt`.

| # | Case | Expected |
|---|---|---|
| 1 | Load `sample_teams_transcript.vtt` → `NormalizedItem` passes Pydantic validation | No `ValidationError` |
| 2 | `raw_text` is non-empty; all lines start with `[` | Transcript correctly formatted |

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| MS Graph API polling for new meeting transcripts | Phase 2 — explicitly in `TRACKER.md` as `[ PHASE_2 ]` |
| OAuth / MSAL token acquisition | Phase 2 |
| `.docx` or `.html` Teams meeting exports | Different format; use `web_adapter` / future `docx_adapter` |
| `.txt` plain Teams transcript pastes | Handled by `MarkdownAdapter` (`SourceType.NOTE`) |
| Language detection | No stdlib language detection; add if needed in a future pass |
| Speaker diarisation beyond `<v>` tag extraction | Whisper-level diarisation is an Audio concern |
| Vault writes | Adapters are read-only from disk |
| Routing `.vtt` files to `TeamsAdapter` | Stage 1 / adapter registry responsibility |
| Retry on transient file read failure | Adapter layer does not retry |
| Real-time meeting capture | Phase 2 / out of scope entirely |

---

## Open questions

1. **`.vtt` extension routing**: Stage 1 (`s1_normalize.py`) will need to route
   `.vtt` files to `TeamsAdapter`. There is currently no extension-to-adapter
   registry defined — confirm this is acceptable as a Stage 1 concern before
   building Stage 1, or raise a TRACKER note.

2. **Multi-line cue text joining**: This spec joins continuation lines with a
   single space. If preserving paragraph breaks within a cue is important for
   downstream summarization quality, change the join separator to `"\n"`. Low
   priority for Phase 1.

3. **Teams `.vtt` encoding edge cases**: Teams-generated VTT files are typically
   UTF-8 with BOM. Spec uses `utf-8-sig` to handle this. If non-UTF-8 files
   appear (e.g. UTF-16 from older Teams exports), fallback encoding detection is
   a future concern.
