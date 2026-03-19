"""Unit tests for agent/tasks/index_updater.py.

All tests use a real temp vault (tmp_path fixture).
No real vault path, no LLM calls.
Async execution via anyio.run().
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import anyio
import pytest

from agent.tasks.index_updater import rebuild_all_counts
from agent.vault.vault import ObsidianVault


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(vault: ObsidianVault) -> None:
    anyio.run(rebuild_all_counts, vault)


def _write_note(vault: ObsidianVault, rel: str, fm: dict, body: str = "") -> None:
    vault.write_note(rel, fm, body)


def _write_index(
    vault: ObsidianVault,
    index_type: str,
    domain: str,
    subdomain: str | None = None,
    note_count: int = 0,
    last_updated: str = "2020-01-01",
    body: str = "",
) -> str:
    """Write a minimal _index.md and return its vault-relative path."""
    rel = vault.get_domain_index_path(domain, subdomain)
    fm: dict = {
        "index_type": index_type,
        "domain": domain,
        "note_count": note_count,
        "last_updated": last_updated,
    }
    if subdomain:
        fm["subdomain"] = subdomain
    vault.write_note(rel, fm, body)
    return rel


# ---------------------------------------------------------------------------
# Test 1 — basic subdomain count
# ---------------------------------------------------------------------------


def test_basic_subdomain_count(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    for i in range(2):
        _write_note(
            vault,
            f"02_KNOWLEDGE/professional_dev/ai_tools/note{i}.md",
            {"domain_path": "professional_dev/ai_tools", "date_modified": "2025-01-01"},
        )

    sub_rel = _write_index(vault, "subdomain", "professional_dev", "ai_tools")

    _run(vault)

    fm, _ = vault.read_note(sub_rel)
    assert fm["note_count"] == 2


# ---------------------------------------------------------------------------
# Test 2 — domain rollup
# ---------------------------------------------------------------------------


def test_domain_rollup(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    for i in range(2):
        _write_note(
            vault,
            f"02_KNOWLEDGE/professional_dev/ai_tools/note{i}.md",
            {"domain_path": "professional_dev/ai_tools", "date_modified": "2025-01-01"},
        )

    _write_index(vault, "subdomain", "professional_dev", "ai_tools")
    dom_rel = _write_index(vault, "domain", "professional_dev")

    _run(vault)

    fm, _ = vault.read_note(dom_rel)
    assert fm["note_count"] == 2


# ---------------------------------------------------------------------------
# Test 3 — corrects inflated count
# ---------------------------------------------------------------------------


def test_corrects_inflated_count(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    for i in range(2):
        _write_note(
            vault,
            f"02_KNOWLEDGE/professional_dev/ai_tools/note{i}.md",
            {"domain_path": "professional_dev/ai_tools"},
        )

    sub_rel = _write_index(
        vault, "subdomain", "professional_dev", "ai_tools", note_count=99
    )

    _run(vault)

    fm, _ = vault.read_note(sub_rel)
    assert fm["note_count"] == 2


# ---------------------------------------------------------------------------
# Test 4 — no-write when unchanged (spy on write_note)
# ---------------------------------------------------------------------------


def test_no_write_when_unchanged(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    for i in range(2):
        _write_note(
            vault,
            f"02_KNOWLEDGE/professional_dev/ai_tools/note{i}.md",
            {"domain_path": "professional_dev/ai_tools"},
        )

    _write_index(vault, "subdomain", "professional_dev", "ai_tools", note_count=0)

    with patch.object(vault, "write_note", wraps=vault.write_note) as spy:
        _run(vault)  # first run — writes because count changed 0→2
        after_first = spy.call_count

        _run(vault)  # second run — nothing changed
        after_second = spy.call_count

    assert after_first > 0, "first run must write at least one index"
    assert after_second == after_first, "second run must not trigger any additional writes"


# ---------------------------------------------------------------------------
# Test 5 — skips notes without domain_path
# ---------------------------------------------------------------------------


def test_skips_notes_without_domain_path(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    _write_note(
        vault,
        "02_KNOWLEDGE/some_domain/note.md",
        {"title": "no domain_path here"},
    )

    dom_rel = _write_index(vault, "domain", "some_domain")

    _run(vault)

    fm, _ = vault.read_note(dom_rel)
    assert fm["note_count"] == 0


# ---------------------------------------------------------------------------
# Test 6 — skips unreadable notes; rest of vault still processed
# ---------------------------------------------------------------------------


def test_skips_unreadable_notes(tmp_path: Path) -> None:
    """A file that raises on read must not crash the rebuild; the remaining
    good note must still be counted.  We use a patch so the test is immune
    to YAML-parser version differences in how malformed content is handled."""
    vault = ObsidianVault(tmp_path)

    # Two files exist so rglob finds them both.
    good_rel = "02_KNOWLEDGE/professional_dev/ai_tools/note_good.md"
    bad_rel = "02_KNOWLEDGE/professional_dev/ai_tools/note_corrupt.md"

    _write_note(vault, good_rel, {"domain_path": "professional_dev/ai_tools"})
    _write_note(vault, bad_rel, {"domain_path": "professional_dev/ai_tools"})  # content irrelevant

    sub_rel = _write_index(vault, "subdomain", "professional_dev", "ai_tools")

    original_read = vault.read_note

    def _read_with_corruption(rel: str) -> tuple:
        if rel.replace("\\", "/").endswith("note_corrupt.md"):
            raise ValueError("simulated corrupt frontmatter")
        return original_read(rel)

    with patch.object(vault, "read_note", side_effect=_read_with_corruption):
        _run(vault)  # must not raise

    fm, _ = vault.read_note(sub_rel)
    assert fm["note_count"] == 1  # only the good note is counted


# ---------------------------------------------------------------------------
# Test 7 — empty knowledge dir → all indexes get note_count: 0
# ---------------------------------------------------------------------------


def test_empty_knowledge_dir(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    # Indexes exist but no notes
    sub_rel = _write_index(vault, "subdomain", "professional_dev", "ai_tools")
    dom_rel = _write_index(vault, "domain", "professional_dev")

    _run(vault)

    sub_fm, _ = vault.read_note(sub_rel)
    dom_fm, _ = vault.read_note(dom_rel)
    assert sub_fm["note_count"] == 0
    assert dom_fm["note_count"] == 0


# ---------------------------------------------------------------------------
# Test 8 — unknown index_type: index is not written
# ---------------------------------------------------------------------------


def test_unknown_index_type_skipped(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    _write_note(
        vault,
        "02_KNOWLEDGE/professional_dev/note.md",
        {"domain_path": "professional_dev"},
    )

    idx_rel = "02_KNOWLEDGE/professional_dev/_index.md"
    vault.write_note(
        idx_rel,
        {
            "index_type": "something_else",
            "domain": "professional_dev",
            "note_count": 42,
            "last_updated": "2020-01-01",
        },
        "body",
    )

    _run(vault)

    fm, _ = vault.read_note(idx_rel)
    # unknown index_type must be left untouched
    assert fm["note_count"] == 42


# ---------------------------------------------------------------------------
# Test 9 — last_updated set to max date_modified across notes
# ---------------------------------------------------------------------------


def test_last_updated_max_date_modified(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    _write_note(
        vault,
        "02_KNOWLEDGE/professional_dev/ai_tools/old_note.md",
        {"domain_path": "professional_dev/ai_tools", "date_modified": "2025-01-01"},
    )
    _write_note(
        vault,
        "02_KNOWLEDGE/professional_dev/ai_tools/new_note.md",
        {"domain_path": "professional_dev/ai_tools", "date_modified": "2025-06-15"},
    )

    sub_rel = _write_index(vault, "subdomain", "professional_dev", "ai_tools")

    _run(vault)

    fm, _ = vault.read_note(sub_rel)
    assert fm["last_updated"] == "2025-06-15"


# ---------------------------------------------------------------------------
# Test 10 — body (Bases query block) preserved byte-for-byte after rebuild
# ---------------------------------------------------------------------------


def test_body_preserved(tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)

    original_body = (
        "```bases\nfilter: domain_path = professional_dev/ai_tools\n```\n\n"
        "Some more content that must not be touched."
    )

    _write_note(
        vault,
        "02_KNOWLEDGE/professional_dev/ai_tools/note.md",
        {"domain_path": "professional_dev/ai_tools"},
    )

    sub_rel = _write_index(
        vault, "subdomain", "professional_dev", "ai_tools", body=original_body
    )

    _, body_before = vault.read_note(sub_rel)

    _run(vault)

    _, body_after = vault.read_note(sub_rel)
    assert body_after == body_before
