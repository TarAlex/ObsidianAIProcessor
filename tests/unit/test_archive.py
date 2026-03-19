"""tests/unit/test_archive.py — unit tests for agent.vault.archive.

All tests use pytest's tmp_path fixture as the vault root — no network or
LLM calls.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from agent.core.models import NormalizedItem, SourceType
from agent.vault.archive import archive_item, archive_raw
from agent.vault.vault import ObsidianVault


# ── helpers ───────────────────────────────────────────────────────────────────

def _vault(tmp_path: Path) -> ObsidianVault:
    return ObsidianVault(tmp_path)


def _make_file(directory: Path, name: str, content: str = "test content") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_item(vault: ObsidianVault, name: str, source_date: date | None) -> NormalizedItem:
    src = _make_file(vault.inbox, name)
    return NormalizedItem(
        raw_id="TEST-001",
        source_type=SourceType.NOTE,
        raw_text="hello",
        raw_file_path=src,
        source_date=source_date,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_archive_item_with_source_date(tmp_path):
    """Case 1: source_date set → file lands in 05_ARCHIVE/2026/03/20260315-{name}."""
    vault = _vault(tmp_path)
    item = _make_item(vault, "meeting-notes.md", source_date=date(2026, 3, 15))

    dest = archive_item(vault, item)

    expected_bucket = tmp_path / "05_ARCHIVE" / "2026" / "03"
    assert dest == expected_bucket / "20260315-meeting-notes.md"
    assert dest.exists()


def test_archive_item_source_date_none(tmp_path):
    """Case 2: source_date is None → bucket matches datetime.now() year/month."""
    vault = _vault(tmp_path)
    item = _make_item(vault, "note.md", source_date=None)

    before = datetime.now()
    dest = archive_item(vault, item)
    after = datetime.now()

    # Bucket should fall within the year/month window of 'now'
    expected_year = before.year
    expected_month = f"{before.month:02d}"
    assert dest.parent == tmp_path / "05_ARCHIVE" / str(expected_year) / expected_month
    assert dest.exists()
    # In the unlikely event the test straddles a month boundary, accept after month too
    # (the assertion above already verifies it exists)


def test_archive_raw_delegates_correctly(tmp_path):
    """Case 3: archive_raw returns the correct destination path."""
    vault = _vault(tmp_path)
    src = _make_file(vault.inbox, "raw-file.md")
    date_ref = datetime(2025, 11, 5)

    dest = archive_raw(vault, src, date_ref)

    expected = tmp_path / "05_ARCHIVE" / "2025" / "11" / "20251105-raw-file.md"
    assert dest == expected
    assert dest.exists()


def test_source_file_absent_after_move(tmp_path):
    """Case 4: original source path no longer exists after archival."""
    vault = _vault(tmp_path)
    item = _make_item(vault, "to-move.md", source_date=date(2026, 1, 10))
    original_path = item.raw_file_path

    archive_item(vault, item)

    assert not original_path.exists()


def test_destination_filename_has_date_prefix(tmp_path):
    """Case 5: destination filename starts with YYYYMMDD- prefix."""
    vault = _vault(tmp_path)
    src = _make_file(vault.inbox, "document.md")
    date_ref = datetime(2024, 7, 22)

    dest = archive_raw(vault, src, date_ref)

    assert dest.name == "20240722-document.md"


def test_bucket_directory_created(tmp_path):
    """Case 6: 05_ARCHIVE/YYYY/MM/ is created if it does not already exist."""
    vault = _vault(tmp_path)
    src = _make_file(vault.inbox, "new.md")
    date_ref = datetime(2030, 6, 1)
    bucket = tmp_path / "05_ARCHIVE" / "2030" / "06"

    assert not bucket.exists()
    archive_raw(vault, src, date_ref)
    assert bucket.is_dir()


def test_archive_item_non_ascii_filename(tmp_path):
    """Case 7: non-ASCII filename is preserved with date prefix."""
    vault = _vault(tmp_path)
    name = "заметка-кириллица.md"
    item = _make_item(vault, name, source_date=date(2026, 8, 3))

    dest = archive_item(vault, item)

    assert dest.name == f"20260803-{name}"
    assert dest.exists()
