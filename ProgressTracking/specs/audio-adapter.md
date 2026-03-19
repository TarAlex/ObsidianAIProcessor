# Spec: AudioAdapter
slug: audio-adapter
layer: adapters
phase: 1
arch_section: §1 (SOURCE ADAPTERS LAYER), §2 (agent/adapters/audio_adapter.py), §10 (whisper config block)

---

## Problem statement

Audio recordings dropped into `00_INBOX/recordings/` (`.mp3`, `.m4a`, `.wav`,
`.ogg`, `.webm`) must be transcribed locally and returned as a `NormalizedItem`
whose `raw_text` is a timestamped transcript. No cloud API calls, no LLM calls
inside the adapter.

`openai-whisper` (already in `pyproject.toml`) runs the Whisper ASR model
entirely on the local machine. Because the library is fully synchronous and
CPU/GPU-bound, the transcription call must run inside
`anyio.to_thread.run_sync()` — the same pattern as `PDFAdapter` and
`YouTubeAdapter`.

The model name (`"base"` by default) and optional language hint are both
configurable via `AgentConfig.whisper` (`WhisperConfig` already in
`agent/core/config.py`). All inference is local; cloud fallback is Phase 2.

---

## Module contract

```
Input:  extract(path: pathlib.Path, config: AgentConfig) -> NormalizedItem
          path   — absolute Path to an audio file; one of .mp3 .m4a .wav .ogg .webm
          config — fully validated AgentConfig; consumed fields:
                     config.whisper.model    (str, default "medium")
                     config.whisper.language (str | None — ISO 639-1 hint, e.g. "ru")

Output: NormalizedItem
          raw_id        str              "SRC-YYYYMMDD-HHmmss" (UTC)
          source_type   SourceType       SourceType.AUDIO (always)
          raw_text      str              full transcript as "[HH:MM:SS] text\n" per segment; non-empty
          title         str              path.stem (no metadata extraction from audio)
          url           str              "" (always — no URL for local recordings)
          author        str              "" (always)
          language      str              ISO 639-1 code detected by Whisper (e.g. "en", "ru")
          source_date   date | None      None (file mtime used as fallback in Stage 3)
          file_mtime    datetime         datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
          raw_file_path Path             the path argument as-is
          extra_metadata dict            {
                                           "whisper_model": str,    # e.g. "base"
                                           "detected_language": str # ISO 639-1 from Whisper
                                         }

Raises: AdapterError(message: str, path: Path)
          - File does not exist or cannot be read (OSError, PermissionError)
          - Whisper model fails to load (any exception from whisper.load_model)
          - Transcription returns None or produces empty transcript
          - Unexpected exception from whisper.transcribe()
        Never raised for unrecognised file extensions — routing is Stage 1's job.
```

---

## Key implementation notes

### Supported extensions

`.mp3`, `.m4a`, `.wav`, `.ogg`, `.webm`. The adapter does NOT validate extension
at runtime — the watcher / Stage 1 is responsible for routing. The adapter
processes whatever path it receives.

### Sync library in thread pool (mandatory)

`whisper.load_model()` and `whisper.transcribe()` are synchronous and
CPU/GPU-bound. They must run inside `anyio.to_thread.run_sync()`:

```python
import anyio
import whisper

async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
    ...
    try:
        result = await anyio.to_thread.run_sync(
            lambda: _transcribe(path, config.whisper.model, config.whisper.language),
            cancellable=True,
        )
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(f"Unexpected transcription error: {exc}", path) from exc
    ...
```

### Thread helper `_transcribe`

```python
def _transcribe(
    path: Path,
    model_name: str,
    language: str | None,
) -> dict:
    """Sync helper — must run in a thread. Returns raw whisper result dict."""
    try:
        model = whisper.load_model(model_name)
    except Exception as exc:
        raise AdapterError(f"Failed to load Whisper model '{model_name}': {exc}", path) from exc

    kwargs: dict = {"verbose": False}
    if language:
        kwargs["language"] = language

    try:
        result = model.transcribe(str(path), **kwargs)
    except Exception as exc:
        raise AdapterError(f"Whisper transcription failed: {exc}", path) from exc

    if result is None:
        raise AdapterError("Whisper returned None result", path)

    return result
```

**Note**: `whisper.load_model()` is called inside the thread helper on every
`extract()` call. Whisper caches the model in memory after the first load, so
subsequent calls on the same process are fast. Do NOT attempt to cache the model
object as a class attribute — this spec does not require it and would introduce
shared mutable state.

### Transcript formatting

Whisper's result dict contains `result["segments"]`, each with `"start"` (float
seconds) and `"text"` (str). Format identically to YouTubeAdapter:

```python
def _format_transcript(segments: list) -> str:
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
`AdapterError("Transcript is empty after Whisper transcription", path)`.

### Detected language

Whisper detects the dominant language and stores it in `result["language"]`
(ISO 639-1, e.g. `"en"`, `"ru"`). Always populate `NormalizedItem.language`
from this field, regardless of whether a `language` hint was passed in.

```python
detected_language: str = result.get("language") or ""
```

### `file_mtime`

Must be set from `Path.stat()` **before** entering the thread (no async I/O
needed for stat; it is a fast syscall):

```python
try:
    file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
except OSError as exc:
    raise AdapterError(str(exc), path) from exc
```

Raise `AdapterError` if `path.stat()` fails (file may not exist).

### Full `extract()` assembly

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import anyio
import whisper

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType


class AudioAdapter(BaseAdapter):

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        # 1. Stat the file (fast, non-async)
        try:
            file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError as exc:
            raise AdapterError(str(exc), path) from exc

        # 2. Transcribe in thread pool
        try:
            result = await anyio.to_thread.run_sync(
                lambda: _transcribe(path, config.whisper.model, config.whisper.language),
                cancellable=True,
            )
        except AdapterError:
            raise
        except Exception as exc:
            raise AdapterError(f"Unexpected transcription error: {exc}", path) from exc

        # 3. Format transcript
        raw_text = _format_transcript(result.get("segments") or [])
        if not raw_text.strip():
            raise AdapterError("Transcript is empty after Whisper transcription", path)

        detected_language: str = result.get("language") or ""

        return NormalizedItem(
            raw_id=self._generate_raw_id(),
            source_type=SourceType.AUDIO,
            raw_text=raw_text,
            title=path.stem,
            url="",
            author="",
            language=detected_language,
            source_date=None,
            file_mtime=file_mtime,
            raw_file_path=path,
            extra_metadata={
                "whisper_model": config.whisper.model,
                "detected_language": detected_language,
            },
        )
```

### Error handling summary

| Condition | Behaviour |
|---|---|
| `path.stat()` fails (`OSError`) | `AdapterError(str(exc), path)` |
| `whisper.load_model()` raises | `AdapterError("Failed to load Whisper model '...': ...", path)` |
| `model.transcribe()` raises | `AdapterError("Whisper transcription failed: ...", path)` |
| `result is None` | `AdapterError("Whisper returned None result", path)` |
| All segments have empty text | `AdapterError("Transcript is empty after Whisper transcription", path)` |
| Any other unexpected exception in thread | `AdapterError("Unexpected transcription error: ...", path)` |

---

## Data model changes

None. `SourceType.AUDIO = "audio"` already exists in `agent/core/models.py`.
`NormalizedItem` is unchanged. `WhisperConfig` with `model` and `language`
fields already exists in `agent/core/config.py`. `openai-whisper>=20231117`
is already declared in `pyproject.toml`.

---

## LLM prompt file needed

None. This adapter performs no LLM calls.

---

## Tests required

### Unit: `tests/unit/test_audio_adapter.py`

All Whisper I/O is mocked via `unittest.mock.patch`. Run async tests via
`anyio` (`asyncio_mode = "auto"` in `pytest.ini_options`).

| # | Case | Expected |
|---|---|---|
| 1 | Valid `.mp3` file, mock Whisper returns 3 segments with text | `NormalizedItem.source_type == AUDIO`, `raw_text` has `[HH:MM:SS]` lines |
| 2 | Whisper detects language `"ru"` | `item.language == "ru"` |
| 3 | `config.whisper.language = "ru"` passed to thread helper | `kwargs["language"] == "ru"` in `model.transcribe()` call |
| 4 | `config.whisper.language = None` | `"language"` key NOT in `kwargs` |
| 5 | `config.whisper.model = "base"` | `whisper.load_model("base")` called |
| 6 | `config.whisper.model = "large"` | `whisper.load_model("large")` called |
| 7 | All segments have empty `"text"` field | `AdapterError("Transcript is empty ...", path)` |
| 8 | `result["segments"]` is absent / `None` | `AdapterError("Transcript is empty ...", path)` |
| 9 | `whisper.load_model()` raises `RuntimeError` | `AdapterError("Failed to load Whisper model ...", path)` |
| 10 | `model.transcribe()` raises `Exception` | `AdapterError("Whisper transcription failed ...", path)` |
| 11 | `path.stat()` raises `OSError` (file missing) | `AdapterError(str(exc), path)` |
| 12 | `_format_timestamp(0.0)` → `"00:00:00"` | Exact string match |
| 13 | `_format_timestamp(3661.5)` → `"01:01:01"` | Exact string match |
| 14 | `raw_id` matches `^SRC-\d{8}-\d{6}$` | Regex match |
| 15 | `file_mtime` is UTC-aware `datetime` | `item.file_mtime.tzinfo is not None` |
| 16 | `raw_file_path == path` | Identity check |
| 17 | `item.url == ""` and `item.author == ""` | Both empty strings |
| 18 | `item.source_date is None` | No date extracted from audio |
| 19 | `extra_metadata["whisper_model"]` matches `config.whisper.model` | Value match |
| 20 | `extra_metadata["detected_language"]` matches Whisper result `"language"` | Value match |
| 21 | `item.title == path.stem` | e.g. `"meeting_2026-03-01"` for `meeting_2026-03-01.mp3` |
| 22 | Unexpected exception from thread raises `AdapterError("Unexpected transcription error ...")` | Correct wrapping |

### Integration: `tests/integration/test_pipeline_audio.py`

All Whisper calls mocked (no real model in CI — too slow/large).
Uses a tiny real audio fixture or a mocked `path.stat()`.

| # | Case | Expected |
|---|---|---|
| 1 | Mocked Whisper returning 2 segments → `NormalizedItem` passes Pydantic validation | No `ValidationError` |
| 2 | `raw_text` contains `[00:` timestamp markers | Transcript correctly formatted |

**CI marker**: tests that require the real Whisper model (GPU/download) should be
decorated `@pytest.mark.slow` so CI can skip them with `-m "not slow"`.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Cloud transcription (OpenAI API) | Phase 2; Phase 1 is local only per feature spec constraint |
| Model caching as class attribute | Whisper's internal cache is sufficient; shared state is out of scope |
| Audio file download / URL handling | Adapters are read-only from local disk |
| LLM calls inside the adapter | All LLM work happens in pipeline stages (§4+) |
| Vault writes | Adapters are read-only |
| Routing files to `AudioAdapter` by extension | Stage 1 / adapter registry responsibility |
| Retry on transient model load failure | Adapter layer does not retry |
| Speaker diarisation | Phase 2 / out of scope entirely |
| Video file transcription (`.mp4`) | Not in supported extension list; can be added later without spec change |
| Segment-level confidence scores | Not surfaced in Phase 1 `NormalizedItem` |

---

## Open questions

1. **Model pre-loading**: Should the agent pre-load the Whisper model on startup
   (in `pipeline.py` or `main.py`) and pass it to the adapter via config, to avoid
   re-loading per file? Current spec: no — Whisper's internal cache handles this
   efficiently for same-process calls. Revisit if profiling shows load overhead.

2. **`.mp4` / `.mkv` support**: Audio extraction from video containers is not
   listed in the feature spec. If needed, `ffmpeg` pre-processing can extract the
   audio track before passing to Whisper. Flag as a separate TRACKER item.

3. **Long file chunking**: Whisper's `transcribe()` handles long audio natively
   (sliding window). No manual chunking is required. If very large files (>1 hour)
   cause memory issues on resource-constrained machines, a `--chunk_length_s`
   option can be forwarded from `WhisperConfig`. Deferred.
