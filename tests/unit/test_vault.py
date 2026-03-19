"""tests/unit/test_vault.py — unit tests for agent.vault.vault.ObsidianVault.

All tests use pytest's tmp_path fixture as the vault root — no real vault on disk.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from agent.core.models import ProcessingRecord, SourceType
from agent.vault.vault import ObsidianVault


# ── helpers ───────────────────────────────────────────────────────────────────

def _vault(tmp_path: Path) -> ObsidianVault:
    return ObsidianVault(tmp_path)


def _record(**overrides) -> ProcessingRecord:
    defaults: dict = dict(
        raw_id="SRC-001",
        source_type=SourceType.NOTE,
        input_path="/inbox/note.md",
        output_path="/knowledge/note.md",
        archive_path="/archive/note.md",
        domain="wellbeing",
        domain_path="wellbeing/health",
        confidence=0.95,
        verbatim_count=2,
        llm_provider="ollama",
        llm_model="llama3.1:8b",
        processing_time_s=3.14,
        timestamp=datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ProcessingRecord(**defaults)


def _make_index(v: ObsidianVault, rel: str, note_count: int = 0, body: str = "bases query body") -> None:
    fm = {
        "index_type": "domain",
        "domain": "wellbeing",
        "note_count": note_count,
        "last_updated": "2026-01-01",
        "tags": ["index/domain"],
    }
    v.write_note(rel, fm, body)


# ── zone paths ────────────────────────────────────────────────────────────────

def test_zone_paths_derived_from_root(tmp_path):
    v = _vault(tmp_path)
    assert v.root == tmp_path
    assert v.inbox == tmp_path / "00_INBOX"
    assert v.processing == tmp_path / "01_PROCESSING"
    assert v.knowledge == tmp_path / "02_KNOWLEDGE"
    assert v.projects == tmp_path / "03_PROJECTS"
    assert v.personal == tmp_path / "04_PERSONAL"
    assert v.archive == tmp_path / "05_ARCHIVE"
    assert v.atoms == tmp_path / "06_ATOMS"
    assert v.references == tmp_path / "REFERENCES"
    assert v.meta == tmp_path / "_AI_META"
    assert v.review_dir == tmp_path / "01_PROCESSING" / "to_review"
    assert v.merge_dir == tmp_path / "01_PROCESSING" / "to_merge"


# ── write_note ────────────────────────────────────────────────────────────────

def test_write_note_creates_file(tmp_path):
    v = _vault(tmp_path)
    v.write_note("note.md", {"title": "Hello"}, "World")
    assert (tmp_path / "note.md").exists()


def test_write_note_frontmatter_serialized(tmp_path):
    v = _vault(tmp_path)
    v.write_note("note.md", {"key": "value"}, "body text")
    content = (tmp_path / "note.md").read_text(encoding="utf-8")
    assert "---" in content
    _, fm_str, _ = content.split("---", 2)
    fm = yaml.safe_load(fm_str)
    assert fm["key"] == "value"


def test_write_note_atomic_tmp_removed(tmp_path):
    v = _vault(tmp_path)
    v.write_note("note.md", {}, "body")
    assert not (tmp_path / "note.tmp").exists()


def test_write_note_creates_parent_dirs(tmp_path):
    v = _vault(tmp_path)
    v.write_note("nested/path/note.md", {"x": 1}, "deep note")
    assert (tmp_path / "nested" / "path" / "note.md").exists()


# ── read_note ─────────────────────────────────────────────────────────────────

def test_read_note_with_frontmatter(tmp_path):
    v = _vault(tmp_path)
    v.write_note("note.md", {"title": "Test", "count": 3}, "some body text")
    fm, body = v.read_note("note.md")
    assert fm["title"] == "Test"
    assert fm["count"] == 3
    assert body == "some body text"


def test_read_note_no_frontmatter(tmp_path):
    path = tmp_path / "plain.md"
    path.write_text("plain content", encoding="utf-8")
    v = _vault(tmp_path)
    fm, body = v.read_note("plain.md")
    assert fm == {}
    assert body == "plain content"


def test_read_note_empty_frontmatter(tmp_path):
    """yaml.safe_load of an empty/whitespace-only block returns None — documented behaviour."""
    path = tmp_path / "empty.md"
    path.write_text("---\n---\n\nbody", encoding="utf-8")
    v = _vault(tmp_path)
    fm, body = v.read_note("empty.md")
    assert fm is None


# ── archive_file ──────────────────────────────────────────────────────────────

def test_archive_file_moves_to_bucket(tmp_path):
    v = _vault(tmp_path)
    src = tmp_path / "note.md"
    src.write_text("content", encoding="utf-8")
    dt = datetime(2026, 3, 19)
    dest = v.archive_file(src, dt)
    assert dest == tmp_path / "05_ARCHIVE" / "2026" / "03" / "20260319-note.md"
    assert dest.exists()


def test_archive_file_source_removed(tmp_path):
    v = _vault(tmp_path)
    src = tmp_path / "note.md"
    src.write_text("content", encoding="utf-8")
    v.archive_file(src, datetime(2026, 3, 19))
    assert not src.exists()


def test_archive_file_bucket_created(tmp_path):
    v = _vault(tmp_path)
    src = tmp_path / "note.md"
    src.write_text("content", encoding="utf-8")
    v.archive_file(src, datetime(2025, 11, 5))
    assert (tmp_path / "05_ARCHIVE" / "2025" / "11").is_dir()


# ── sync_in_progress ──────────────────────────────────────────────────────────

def test_sync_in_progress_no_lock(tmp_path):
    v = _vault(tmp_path)
    assert v.sync_in_progress() is False


def test_sync_in_progress_sync_star(tmp_path):
    v = _vault(tmp_path)
    (tmp_path / ".sync-abc").touch()
    assert v.sync_in_progress() is True


def test_sync_in_progress_syncing(tmp_path):
    v = _vault(tmp_path)
    (tmp_path / ".syncing").touch()
    assert v.sync_in_progress() is True


# ── append_log ────────────────────────────────────────────────────────────────

def test_append_log_creates_file(tmp_path):
    v = _vault(tmp_path)
    v.append_log(_record())
    assert (tmp_path / "_AI_META" / "processing-log.md").exists()


def test_append_log_appends_not_overwrites(tmp_path):
    v = _vault(tmp_path)
    v.append_log(_record(raw_id="SRC-001"))
    v.append_log(_record(raw_id="SRC-002"))
    content = (tmp_path / "_AI_META" / "processing-log.md").read_text(encoding="utf-8")
    assert "SRC-001" in content
    assert "SRC-002" in content


def test_append_log_format_contains_raw_id(tmp_path):
    v = _vault(tmp_path)
    v.append_log(_record(raw_id="SRC-XYZ"))
    content = (tmp_path / "_AI_META" / "processing-log.md").read_text(encoding="utf-8")
    assert "SRC-XYZ" in content


# ── get_domain_index_path ─────────────────────────────────────────────────────

def test_get_domain_index_path_domain_only(tmp_path):
    v = _vault(tmp_path)
    assert v.get_domain_index_path("wellbeing") == "02_KNOWLEDGE/wellbeing/_index.md"


def test_get_domain_index_path_with_subdomain(tmp_path):
    v = _vault(tmp_path)
    assert v.get_domain_index_path("wellbeing", "health") == "02_KNOWLEDGE/wellbeing/health/_index.md"


# ── ensure_domain_index ───────────────────────────────────────────────────────

@patch("agent.vault.templates.render_template", return_value="mock body")
def test_ensure_domain_index_creates_when_absent(mock_rt, tmp_path):
    v = _vault(tmp_path)
    rel = "02_KNOWLEDGE/wellbeing/_index.md"
    v.ensure_domain_index(rel, "domain", "wellbeing", None)
    target = tmp_path / rel
    assert target.exists()
    fm, _ = v.read_note(rel)
    assert fm["note_count"] == 0
    assert "index/domain" in fm["tags"]


@patch("agent.vault.templates.render_template", return_value="mock body")
def test_ensure_domain_index_never_overwrites(mock_rt, tmp_path):
    v = _vault(tmp_path)
    rel = "02_KNOWLEDGE/wellbeing/_index.md"
    v.write_note(rel, {"sentinel": "do-not-overwrite"}, "original body")
    original = (tmp_path / rel).read_text(encoding="utf-8")
    v.ensure_domain_index(rel, "domain", "wellbeing", None)
    assert (tmp_path / rel).read_text(encoding="utf-8") == original
    mock_rt.assert_not_called()


@patch("agent.vault.templates.render_template", return_value="subdomain body")
def test_ensure_domain_index_subdomain_uses_subdomain_template(mock_rt, tmp_path):
    v = _vault(tmp_path)
    rel = "02_KNOWLEDGE/wellbeing/health/_index.md"
    v.ensure_domain_index(rel, "subdomain", "wellbeing", "health")
    mock_rt.assert_called_once()
    template_name = mock_rt.call_args[0][0]
    assert template_name == "subdomain_index.md"


@patch("agent.vault.templates.render_template", return_value="domain body")
def test_ensure_domain_index_domain_uses_domain_template(mock_rt, tmp_path):
    v = _vault(tmp_path)
    rel = "02_KNOWLEDGE/wellbeing/_index.md"
    v.ensure_domain_index(rel, "domain", "wellbeing", None)
    mock_rt.assert_called_once()
    template_name = mock_rt.call_args[0][0]
    assert template_name == "domain_index.md"


# ── increment_index_count ─────────────────────────────────────────────────────

def test_increment_index_count_increments(tmp_path):
    v = _vault(tmp_path)
    rel = "02_KNOWLEDGE/wellbeing/_index.md"
    _make_index(v, rel, note_count=0)
    v.increment_index_count(rel)
    fm, _ = v.read_note(rel)
    assert fm["note_count"] == 1


def test_increment_index_count_updates_last_updated(tmp_path):
    v = _vault(tmp_path)
    rel = "02_KNOWLEDGE/wellbeing/_index.md"
    _make_index(v, rel)
    v.increment_index_count(rel)
    fm, _ = v.read_note(rel)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert fm["last_updated"] == today


def test_increment_index_count_body_unchanged(tmp_path):
    v = _vault(tmp_path)
    rel = "02_KNOWLEDGE/wellbeing/_index.md"
    original_body = "```bases\nfilter: domain_path = test\n```"
    _make_index(v, rel, body=original_body)
    _, body_before = v.read_note(rel)
    v.increment_index_count(rel)
    _, body_after = v.read_note(rel)
    assert body_after == body_before


def test_increment_index_count_noop_when_absent(tmp_path):
    v = _vault(tmp_path)
    # Must not raise any exception
    v.increment_index_count("02_KNOWLEDGE/nonexistent/_index.md")


# ── move_to_review / move_to_merge ────────────────────────────────────────────

def test_move_to_review_moves_file(tmp_path):
    v = _vault(tmp_path)
    src = tmp_path / "note.md"
    src.write_text("content", encoding="utf-8")
    dest = v.move_to_review(src)
    assert dest == tmp_path / "01_PROCESSING" / "to_review" / "note.md"
    assert dest.exists()
    assert not src.exists()


def test_move_to_review_creates_dir(tmp_path):
    v = _vault(tmp_path)
    src = tmp_path / "note.md"
    src.write_text("content", encoding="utf-8")
    v.move_to_review(src)
    assert (tmp_path / "01_PROCESSING" / "to_review").is_dir()


def test_move_to_merge_moves_file(tmp_path):
    v = _vault(tmp_path)
    src = tmp_path / "note.md"
    src.write_text("content", encoding="utf-8")
    dest = v.move_to_merge(src)
    assert dest == tmp_path / "01_PROCESSING" / "to_merge" / "note.md"
    assert dest.exists()
    assert not src.exists()
