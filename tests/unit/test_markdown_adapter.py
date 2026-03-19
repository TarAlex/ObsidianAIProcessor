"""Unit tests for agent/adapters/markdown_adapter.py.

All tests use tmp_path to create real files; no mocking of file I/O.
Async methods are driven via anyio.run().
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import anyio
import pytest

from agent.adapters.base import AdapterError
from agent.adapters.markdown_adapter import MarkdownAdapter
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path):
    """Return a minimal AgentConfig with vault.root pointing to tmp_path."""
    from agent.core.config import AgentConfig, VaultConfig
    return AgentConfig(vault=VaultConfig(root=str(tmp_path)))


def _run(coro):
    """Run a coroutine synchronously via anyio."""
    return anyio.from_thread.run_sync(lambda: None) or anyio.run(lambda: coro)


async def _extract(path: Path, tmp_path: Path) -> NormalizedItem:
    adapter = MarkdownAdapter()
    config = _make_config(tmp_path)
    return await adapter.extract(path, config)


def run_extract(path: Path, tmp_path: Path) -> NormalizedItem:
    return anyio.run(_extract, path, tmp_path)


# ---------------------------------------------------------------------------
# Test 1 — .md file with # Heading
# ---------------------------------------------------------------------------

def test_title_from_heading(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# My Title\n\nSome content here.", encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.title == "My Title"


# ---------------------------------------------------------------------------
# Test 2 — .md file with no heading → title == path.stem
# ---------------------------------------------------------------------------

def test_title_from_stem_when_no_heading(tmp_path):
    f = tmp_path / "my_note.md"
    f.write_text("Just some plain text with no heading.", encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.title == "my_note"


# ---------------------------------------------------------------------------
# Test 3 — .txt file → source_type == NOTE, title from stem
# ---------------------------------------------------------------------------

def test_txt_file_source_type_and_title(tmp_path):
    f = tmp_path / "plain_text.txt"
    f.write_text("A plain text file without headings.", encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.source_type == SourceType.NOTE
    assert item.title == "plain_text"


# ---------------------------------------------------------------------------
# Test 4 — YAML frontmatter stripped from raw_text; body preserved
# ---------------------------------------------------------------------------

def test_frontmatter_stripped_from_raw_text(tmp_path):
    content = "---\nauthor: Alice\n---\n# Body Heading\n\nBody content here."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert "author: Alice" not in item.raw_text
    assert "---" not in item.raw_text
    assert "Body content here." in item.raw_text


# ---------------------------------------------------------------------------
# Test 5 — frontmatter source_url → NormalizedItem.url
# ---------------------------------------------------------------------------

def test_source_url_from_frontmatter(tmp_path):
    content = "---\nsource_url: https://example.com\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.url == "https://example.com"


# ---------------------------------------------------------------------------
# Test 6 — frontmatter url: (alias) → NormalizedItem.url
# ---------------------------------------------------------------------------

def test_url_alias_from_frontmatter(tmp_path):
    content = "---\nurl: https://alias.com\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.url == "https://alias.com"


# ---------------------------------------------------------------------------
# Test 7 — frontmatter author → NormalizedItem.author
# ---------------------------------------------------------------------------

def test_author_from_frontmatter(tmp_path):
    content = "---\nauthor: John Doe\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.author == "John Doe"


# ---------------------------------------------------------------------------
# Test 8 — frontmatter language → NormalizedItem.language
# ---------------------------------------------------------------------------

def test_language_from_frontmatter(tmp_path):
    content = "---\nlanguage: ru\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.language == "ru"


# ---------------------------------------------------------------------------
# Test 9 — frontmatter lang: (alias) → NormalizedItem.language
# ---------------------------------------------------------------------------

def test_lang_alias_from_frontmatter(tmp_path):
    content = "---\nlang: en\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.language == "en"


# ---------------------------------------------------------------------------
# Test 10 — source_date: 2025-06-15 → date(2025, 6, 15)
# ---------------------------------------------------------------------------

def test_source_date_from_frontmatter(tmp_path):
    content = "---\nsource_date: 2025-06-15\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.source_date == date(2025, 6, 15)


# ---------------------------------------------------------------------------
# Test 11 — date: (alias) → source_date populated
# ---------------------------------------------------------------------------

def test_date_alias_from_frontmatter(tmp_path):
    content = "---\ndate: 2024-01-20\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.source_date == date(2024, 1, 20)


# ---------------------------------------------------------------------------
# Test 12 — date_created: (alias) → source_date populated
# ---------------------------------------------------------------------------

def test_date_created_alias_from_frontmatter(tmp_path):
    content = "---\ndate_created: 2023-12-31\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.source_date == date(2023, 12, 31)


# ---------------------------------------------------------------------------
# Test 13 — unparseable date string → source_date is None
# ---------------------------------------------------------------------------

def test_unparseable_date_returns_none(tmp_path):
    content = "---\nsource_date: not-a-date\n---\n# Title\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.source_date is None


# ---------------------------------------------------------------------------
# Test 14 — malformed YAML frontmatter → full content as raw_text, no error
# ---------------------------------------------------------------------------

def test_malformed_yaml_falls_back_to_full_body(tmp_path):
    # YAML with unbalanced brackets is malformed
    content = "---\nbad: [unclosed\n---\n# Heading\n\nContent."
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    # full text is treated as body — no AdapterError raised
    assert "bad: [unclosed" in item.raw_text


# ---------------------------------------------------------------------------
# Test 15 — raw_id matches SRC-YYYYMMDD-HHmmss
# ---------------------------------------------------------------------------

def test_raw_id_format(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# Title\n\nContent.", encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert re.match(r"^SRC-\d{8}-\d{6}$", item.raw_id)


# ---------------------------------------------------------------------------
# Test 16 — file_mtime is UTC-aware datetime
# ---------------------------------------------------------------------------

def test_file_mtime_is_utc_aware(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# Title\n\nContent.", encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert isinstance(item.file_mtime, datetime)
    assert item.file_mtime.tzinfo is not None
    assert item.file_mtime.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Test 17 — raw_file_path == path
# ---------------------------------------------------------------------------

def test_raw_file_path_equals_input_path(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# Title\n\nContent.", encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.raw_file_path == f


# ---------------------------------------------------------------------------
# Test 18 — source_type == SourceType.NOTE
# ---------------------------------------------------------------------------

def test_source_type_is_note(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# Title\n\nContent.", encoding="utf-8")
    item = run_extract(f, tmp_path)
    assert item.source_type == SourceType.NOTE


# ---------------------------------------------------------------------------
# Test 19 — extra frontmatter keys in extra_metadata; mapped keys absent
# ---------------------------------------------------------------------------

def test_extra_metadata_contains_unmapped_keys(tmp_path):
    content = (
        "---\n"
        "author: Jane\n"
        "source_url: https://x.com\n"
        "custom_tag: foo\n"
        "project: vault-builder\n"
        "---\n"
        "# Title\n\nContent."
    )
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    item = run_extract(f, tmp_path)
    # mapped keys must NOT appear
    assert "author" not in item.extra_metadata
    assert "source_url" not in item.extra_metadata
    # unmapped keys MUST appear
    assert item.extra_metadata.get("custom_tag") == "foo"
    assert item.extra_metadata.get("project") == "vault-builder"


# ---------------------------------------------------------------------------
# Test 20 — file with only whitespace after frontmatter → AdapterError
# ---------------------------------------------------------------------------

def test_empty_body_after_frontmatter_raises(tmp_path):
    content = "---\nauthor: Alice\n---\n   \n\t\n"
    f = tmp_path / "note.md"
    f.write_text(content, encoding="utf-8")
    with pytest.raises(AdapterError) as exc_info:
        run_extract(f, tmp_path)
    assert exc_info.value.path == f


# ---------------------------------------------------------------------------
# Test 21 — completely empty file → AdapterError
# ---------------------------------------------------------------------------

def test_completely_empty_file_raises(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("", encoding="utf-8")
    with pytest.raises(AdapterError) as exc_info:
        run_extract(f, tmp_path)
    assert exc_info.value.path == f


# ---------------------------------------------------------------------------
# Test 22 — unreadable file → AdapterError
# ---------------------------------------------------------------------------

def test_unreadable_file_raises_adapter_error(tmp_path):
    f = tmp_path / "locked.md"
    f.write_text("# Title\n\nContent.", encoding="utf-8")

    if sys.platform != "win32":
        # On Linux/macOS: chmod 000
        f.chmod(0o000)
        try:
            with pytest.raises(AdapterError) as exc_info:
                run_extract(f, tmp_path)
            assert exc_info.value.path == f
        finally:
            f.chmod(0o644)
    else:
        # On Windows: patch anyio.Path.read_text to raise OSError
        import anyio.abc

        async def _raise(*args, **kwargs):
            raise PermissionError("Access is denied")

        with patch.object(anyio.Path, "read_text", new=_raise):
            with pytest.raises(AdapterError) as exc_info:
                run_extract(f, tmp_path)
            assert exc_info.value.path == f
