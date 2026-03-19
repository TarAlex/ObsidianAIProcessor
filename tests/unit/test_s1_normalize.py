"""Unit tests for agent/stages/s1_normalize.py.

All adapters are patched via AsyncMock — no real file parsing.
Uses tmp_path fixtures; no real vault needed.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

from agent.adapters.base import AdapterError
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType
from agent.stages import s1_normalize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(tmp_path)))


def _make_item(raw_id: str = "SRC-20240101-120000", raw_path: Path | None = None) -> NormalizedItem:
    return NormalizedItem(
        raw_id=raw_id,
        source_type=SourceType.NOTE,
        raw_text="test content",
        raw_file_path=raw_path or Path("/inbox/test.md"),
    )


async def _run(raw_path: Path, config: AgentConfig) -> NormalizedItem:
    return await s1_normalize.run(raw_path, config)


# ---------------------------------------------------------------------------
# test_dispatch_md — .md → MarkdownAdapter
# ---------------------------------------------------------------------------

def test_dispatch_md(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "note.md"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.MarkdownAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        result = anyio.run(_run, fake_path, config)

    MockAdapter.assert_called_once()
    assert result.raw_id == item.raw_id


# ---------------------------------------------------------------------------
# test_dispatch_pdf — .pdf → PDFAdapter
# ---------------------------------------------------------------------------

def test_dispatch_pdf(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "doc.pdf"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.PDFAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        anyio.run(_run, fake_path, config)

    MockAdapter.assert_called_once()


# ---------------------------------------------------------------------------
# test_dispatch_audio_mp3 — .mp3 → AudioAdapter
# ---------------------------------------------------------------------------

def test_dispatch_audio_mp3(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "recording.mp3"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.AudioAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        anyio.run(_run, fake_path, config)

    MockAdapter.assert_called_once()


# ---------------------------------------------------------------------------
# test_dispatch_vtt — .vtt → TeamsAdapter
# ---------------------------------------------------------------------------

def test_dispatch_vtt(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "meeting.vtt"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.TeamsAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        anyio.run(_run, fake_path, config)

    MockAdapter.assert_called_once()


# ---------------------------------------------------------------------------
# test_dispatch_html — .html → WebAdapter
# ---------------------------------------------------------------------------

def test_dispatch_html(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "page.html"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.WebAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        anyio.run(_run, fake_path, config)

    MockAdapter.assert_called_once()


# ---------------------------------------------------------------------------
# test_dispatch_txt_fallback — unknown extension → MarkdownAdapter
# ---------------------------------------------------------------------------

def test_dispatch_txt_fallback(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "notes.xyz"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.MarkdownAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        anyio.run(_run, fake_path, config)

    MockAdapter.assert_called_once()


# ---------------------------------------------------------------------------
# test_staging_file_written — staging file exists with correct content
# ---------------------------------------------------------------------------

def test_staging_file_written(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "note.md"
    raw_id = "SRC-20240101-120000"
    item = _make_item(raw_id=raw_id, raw_path=fake_path)

    with patch("agent.stages.s1_normalize.MarkdownAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        anyio.run(_run, fake_path, config)

    staging_path = tmp_path / "01_PROCESSING" / "to_classify" / f"raw_{raw_id}.md"
    assert staging_path.exists(), f"Staging file not found: {staging_path}"
    assert staging_path.read_text(encoding="utf-8") == "test content"


# ---------------------------------------------------------------------------
# test_staging_dir_autocreated — staging dir created if absent
# ---------------------------------------------------------------------------

def test_staging_dir_autocreated(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "note.md"
    item = _make_item(raw_path=fake_path)

    staging_dir = tmp_path / "01_PROCESSING" / "to_classify"
    assert not staging_dir.exists()

    with patch("agent.stages.s1_normalize.MarkdownAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        anyio.run(_run, fake_path, config)

    assert staging_dir.is_dir()


# ---------------------------------------------------------------------------
# test_raw_file_path_preserved — raw_file_path == original inbox path
# ---------------------------------------------------------------------------

def test_raw_file_path_preserved(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "original.md"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.MarkdownAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        result = anyio.run(_run, fake_path, config)

    assert result.raw_file_path == fake_path


# ---------------------------------------------------------------------------
# test_raw_id_format — raw_id matches SRC-YYYYMMDD-HHmmss
# ---------------------------------------------------------------------------

def test_raw_id_format(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "note.md"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.MarkdownAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        result = anyio.run(_run, fake_path, config)

    assert re.fullmatch(r"SRC-\d{8}-\d{6}", result.raw_id), (
        f"raw_id '{result.raw_id}' does not match SRC-YYYYMMDD-HHmmss"
    )


# ---------------------------------------------------------------------------
# test_adapter_error_propagates — AdapterError re-raised unchanged
# ---------------------------------------------------------------------------

def test_adapter_error_propagates(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "bad.md"

    with patch("agent.stages.s1_normalize.MarkdownAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(
            side_effect=AdapterError("file unreadable", fake_path)
        )
        MockAdapter.return_value = mock_inst

        with pytest.raises(AdapterError, match="file unreadable"):
            anyio.run(_run, fake_path, config)


# ---------------------------------------------------------------------------
# test_normalized_item_fields — returned item has non-empty raw_text, correct source_type
# ---------------------------------------------------------------------------

def test_normalized_item_fields(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "note.md"
    item = NormalizedItem(
        raw_id="SRC-20240101-120000",
        source_type=SourceType.NOTE,
        raw_text="Some meaningful content",
        raw_file_path=fake_path,
    )

    with patch("agent.stages.s1_normalize.MarkdownAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        result = anyio.run(_run, fake_path, config)

    assert result.raw_text != ""
    assert result.source_type == SourceType.NOTE


# ---------------------------------------------------------------------------
# test_case_insensitive_extension — .PDF dispatches to PDFAdapter
# ---------------------------------------------------------------------------

def test_case_insensitive_extension(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    fake_path = tmp_path / "DOC.PDF"
    item = _make_item(raw_path=fake_path)

    with patch("agent.stages.s1_normalize.PDFAdapter") as MockAdapter:
        mock_inst = MagicMock()
        mock_inst.extract = AsyncMock(return_value=item)
        MockAdapter.return_value = mock_inst

        anyio.run(_run, fake_path, config)

    MockAdapter.assert_called_once()
