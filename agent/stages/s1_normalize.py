"""Stage 1 — Normalize

Dispatches a raw inbox file to the correct source adapter, extracts content
into a NormalizedItem, and writes a staging copy to 01_PROCESSING/to_classify/.

Contract:
    Input:  raw_path: Path, config: AgentConfig
    Output: NormalizedItem

No LLM calls. No ObsidianVault usage. Stateless.
"""
from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

import anyio

from agent.adapters.base import AdapterError, BaseAdapter
from agent.adapters.audio_adapter import AudioAdapter
from agent.adapters.markdown_adapter import MarkdownAdapter
from agent.adapters.pdf_adapter import PDFAdapter
from agent.adapters.teams_adapter import TeamsAdapter
from agent.adapters.web_adapter import WebAdapter
from agent.adapters.youtube_adapter import YouTubeAdapter
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dispatch table — built lazily so module-level names can be patched in tests
# ---------------------------------------------------------------------------

def _build_ext_map() -> dict[str, type[BaseAdapter]]:
    """Return the extension → adapter class mapping.

    Built on each call so that monkeypatching the module-level names in tests
    (e.g. ``patch("agent.stages.s1_normalize.MarkdownAdapter")``) takes effect.
    """
    return {
        ".md":     MarkdownAdapter,
        ".txt":    MarkdownAdapter,
        ".pdf":    PDFAdapter,
        ".mp3":    AudioAdapter,
        ".m4a":    AudioAdapter,
        ".wav":    AudioAdapter,
        ".ogg":    AudioAdapter,
        ".flac":   AudioAdapter,
        ".vtt":    TeamsAdapter,
        ".html":   WebAdapter,
        ".htm":    WebAdapter,
        ".url":    WebAdapter,    # sidecar URL files — YouTube handled in adapter
        ".webloc": WebAdapter,
    }


def _select_adapter(raw_path: Path) -> BaseAdapter:
    """Return the correct adapter instance for *raw_path*.

    Resolution order:
    1. Extension lookup in the dispatch map (case-insensitive).
    2. MIME sniff for unknown/missing extensions.
    3. MarkdownAdapter fallback (treats unknown files as plain text).
    """
    ext = raw_path.suffix.lower()
    ext_map = _build_ext_map()

    if ext in ext_map:
        cls = ext_map[ext]
        logger.info(
            "Adapter selected: %s for %s",
            getattr(cls, "__name__", repr(cls)),
            raw_path.name,
        )
        return cls()

    # MIME sniff fallback for absent or unrecognised extensions
    mime_type, _ = mimetypes.guess_type(str(raw_path))
    if mime_type and mime_type.startswith("audio/"):
        logger.warning(
            "MIME sniff fallback triggered for %s → AudioAdapter (mime=%s)",
            raw_path.name,
            mime_type,
        )
        return AudioAdapter()

    logger.info(
        "Adapter selected: MarkdownAdapter (fallback) for %s", raw_path.name
    )
    return MarkdownAdapter()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run(raw_path: Path, config: AgentConfig) -> NormalizedItem:
    """Normalise a single inbox file and write a staging copy.

    Args:
        raw_path: Absolute path to the inbox file.
        config:   Agent configuration (provides vault root path).

    Returns:
        NormalizedItem with raw_file_path set to the original inbox path.

    Raises:
        AdapterError: propagated unchanged from the selected adapter.
    """
    adapter = _select_adapter(raw_path)

    # AdapterError propagates up to the pipeline orchestrator — not caught here.
    item: NormalizedItem = await adapter.extract(raw_path, config)

    # Write staging copy — plain anyio write, no ObsidianVault involved.
    staging_dir = Path(config.vault.root) / "01_PROCESSING" / "to_classify"
    staging_path = staging_dir / f"raw_{item.raw_id}.md"

    await anyio.Path(staging_dir).mkdir(parents=True, exist_ok=True)
    await anyio.Path(staging_path).write_text(item.raw_text, encoding="utf-8")

    logger.info(
        "Staging file written: %s  (raw_id=%s)", staging_path, item.raw_id
    )

    return item
