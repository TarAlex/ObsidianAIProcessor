"""agent/vault/archive.py — Stage 7 facade: archive processed inbox files.

Two entry points:
- archive_item  : high-level; accepts a NormalizedItem
- archive_raw   : lower-level; accepts a bare Path + datetime reference

All file I/O is delegated to ObsidianVault.archive_file — no direct shutil /
os / pathlib writes in this module.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agent.core.models import NormalizedItem
from agent.vault.vault import ObsidianVault


def archive_item(vault: ObsidianVault, item: NormalizedItem) -> Path:
    """Move item.raw_file_path into the 05_ARCHIVE bucket derived from item.source_date.

    Falls back to datetime.now() when source_date is None.
    Returns the absolute path of the file at its new location.
    """
    if item.source_date is not None:
        date_ref = datetime.combine(item.source_date, datetime.min.time())
    else:
        date_ref = datetime.now()
    return archive_raw(vault, item.raw_file_path, date_ref)


def archive_raw(vault: ObsidianVault, path: Path, date_ref: datetime) -> Path:
    """Move *path* into the 05_ARCHIVE bucket derived from *date_ref*.

    Pure delegation to vault.archive_file.  Exposed separately so callers
    that already hold a bare Path + datetime (e.g. s7_archive.py, tests) do
    not need to construct a full NormalizedItem.
    Returns the absolute path of the file at its new location.
    """
    return vault.archive_file(path, date_ref)
