"""AudioAdapter — transcribes local audio files via openai-whisper (local, sync).

Supported formats: .mp3, .m4a, .wav, .ogg, .webm.
No LLM calls, no vault writes. Runs Whisper in a thread pool (CPU/GPU-bound).

Requires: pip install 'obsidian-agent[audio]'
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import anyio

from agent.adapters.base import AdapterError, BaseAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, SourceType

try:
    import whisper
except ImportError:
    whisper = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_timestamp(seconds: float) -> str:
    """Format float seconds as HH:MM:SS."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_transcript(segments: list) -> str:
    """Format each Whisper segment as '[HH:MM:SS] text'."""
    lines: list[str] = []
    for seg in segments:
        ts = _format_timestamp(float(seg["start"]))
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


def _transcribe(
    path: Path,
    model_name: str,
    language: str | None,
) -> dict:
    """Sync helper — must run in a thread. Returns raw whisper result dict."""
    if whisper is None:
        raise AdapterError(
            "openai-whisper is not installed. Install with: pip install 'obsidian-agent[audio]'",
            path,
        )

    try:
        model = whisper.load_model(model_name)
    except Exception as exc:
        raise AdapterError(
            f"Failed to load Whisper model '{model_name}': {exc}", path
        ) from exc

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


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class AudioAdapter(BaseAdapter):
    """Source adapter for local audio files (.mp3, .m4a, .wav, .ogg, .webm)."""

    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        """Transcribe *path* via local Whisper and return a NormalizedItem.

        Raises:
            AdapterError: on stat failure, model load failure, or empty transcript.
        """
        # 1. Stat the file (fast, non-async)
        try:
            file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError as exc:
            raise AdapterError(str(exc), path) from exc

        # 2. Transcribe in thread pool
        try:
            result = await anyio.to_thread.run_sync(
                lambda: _transcribe(path, config.whisper.model, config.whisper.language),
                abandon_on_cancel=True,
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
