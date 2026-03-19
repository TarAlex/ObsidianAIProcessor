"""tests/unit/test_setup_vault.py — unit tests for scripts/setup_vault.py.

All tests use pytest's tmp_path fixture as the vault root.
agent.vault.templates.render_template is patched to return a minimal stub
string — avoids requiring actual Jinja2 template files on disk.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# Make scripts/ importable without modifying pyproject.toml.
_SCRIPTS_DIR = str(Path(__file__).parent.parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from setup_vault import main, setup_vault  # noqa: E402

from agent.vault.note import parse_note
from agent.vault.vault import ObsidianVault

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

STUB_BODY = "## stub\n"
RENDER_TARGET = "agent.vault.templates.render_template"


def _vault(root: Path) -> ObsidianVault:
    return ObsidianVault(root)


def _read_fm(vault: ObsidianVault, rel: str) -> dict:
    fm, _ = parse_note((vault.root / rel).read_text(encoding="utf-8"))
    return fm


def _write_config(cfg_path: Path, vault_root: Path) -> None:
    """Write a minimal agent-config.yaml at cfg_path."""
    cfg_path.write_text(
        f"vault:\n  root: {vault_root.as_posix()}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Test 1 — knowledge root index created
# ---------------------------------------------------------------------------

def test_creates_knowledge_root_index(tmp_path):
    vault = _vault(tmp_path)
    with patch(RENDER_TARGET, return_value=STUB_BODY):
        counts = setup_vault(vault)

    index_path = tmp_path / "02_KNOWLEDGE" / "_index.md"
    assert index_path.exists(), "_index.md not created under 02_KNOWLEDGE/"
    fm = _read_fm(vault, "02_KNOWLEDGE/_index.md")
    assert fm["index_type"] == "global"
    assert fm["domain"] == "knowledge"
    assert counts["created"] >= 1


# ---------------------------------------------------------------------------
# Test 2 — domain index created
# ---------------------------------------------------------------------------

def test_creates_domain_index(tmp_path):
    vault = _vault(tmp_path)
    domain_dir = tmp_path / "02_KNOWLEDGE" / "science"
    domain_dir.mkdir(parents=True)

    with patch(RENDER_TARGET, return_value=STUB_BODY):
        counts = setup_vault(vault)

    index_path = domain_dir / "_index.md"
    assert index_path.exists()
    fm = _read_fm(vault, "02_KNOWLEDGE/science/_index.md")
    assert fm["index_type"] == "domain"
    assert fm["domain"] == "science"
    assert counts["created"] >= 2  # at least knowledge-root + domain


# ---------------------------------------------------------------------------
# Test 3 — subdomain index created
# ---------------------------------------------------------------------------

def test_creates_subdomain_index(tmp_path):
    vault = _vault(tmp_path)
    sub_dir = tmp_path / "02_KNOWLEDGE" / "science" / "physics"
    sub_dir.mkdir(parents=True)

    with patch(RENDER_TARGET, return_value=STUB_BODY):
        counts = setup_vault(vault)

    index_path = sub_dir / "_index.md"
    assert index_path.exists()
    fm = _read_fm(vault, "02_KNOWLEDGE/science/physics/_index.md")
    assert fm["index_type"] == "subdomain"
    assert fm["domain"] == "science"
    assert fm["subdomain"] == "physics"
    assert counts["errors"] == 0


# ---------------------------------------------------------------------------
# Test 4 — existing index not overwritten
# ---------------------------------------------------------------------------

def test_skips_existing_index(tmp_path):
    vault = _vault(tmp_path)
    index_path = tmp_path / "02_KNOWLEDGE" / "_index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    original_content = "---\nindex_type: global\n---\n\noriginal body"
    index_path.write_text(original_content, encoding="utf-8")

    original_mtime = index_path.stat().st_mtime
    # Small sleep to ensure mtime would differ if file were rewritten
    time.sleep(0.05)

    with patch(RENDER_TARGET, return_value=STUB_BODY):
        counts = setup_vault(vault)

    assert index_path.read_text(encoding="utf-8") == original_content
    assert index_path.stat().st_mtime == original_mtime
    assert counts["skipped"] >= 1


# ---------------------------------------------------------------------------
# Test 5 — zone indexes created
# ---------------------------------------------------------------------------

def test_zone_indexes_created(tmp_path):
    vault = _vault(tmp_path)

    with patch(RENDER_TARGET, return_value=STUB_BODY):
        counts = setup_vault(vault)

    for rel in (
        "03_PROJECTS/_index.md",
        "04_PERSONAL/_index.md",
        "REFERENCES/_index.md",
    ):
        assert (tmp_path / rel).exists(), f"Missing: {rel}"

    assert counts["errors"] == 0


# ---------------------------------------------------------------------------
# Test 6 — 06_ATOMS/ explicitly skipped
# ---------------------------------------------------------------------------

def test_atoms_folder_skipped(tmp_path):
    vault = _vault(tmp_path)
    atoms_dir = tmp_path / "06_ATOMS"
    atoms_dir.mkdir()

    with patch(RENDER_TARGET, return_value=STUB_BODY):
        setup_vault(vault)

    assert not (atoms_dir / "_index.md").exists()


# ---------------------------------------------------------------------------
# Test 7 — dry-run: no writes, stdout contains "would be created"
# ---------------------------------------------------------------------------

def test_dry_run_no_writes(tmp_path, capsys):
    vault = _vault(tmp_path)
    # Add a domain dir so there are candidates beyond the three zone indexes
    (tmp_path / "02_KNOWLEDGE" / "tech").mkdir(parents=True)

    config_file = tmp_path / "agent-config.yaml"
    _write_config(config_file, tmp_path)

    with patch(RENDER_TARGET, return_value=STUB_BODY):
        exit_code = main(["--config", str(config_file), "--dry-run"])

    assert exit_code == 0

    # No _index.md files should have been written
    created = list(tmp_path.rglob("_index.md"))
    assert created == [], f"Unexpected files created: {created}"

    captured = capsys.readouterr()
    assert "would be created" in captured.out


# ---------------------------------------------------------------------------
# Test 8 — idempotent: second run creates nothing new
# ---------------------------------------------------------------------------

def test_idempotent_second_run(tmp_path):
    vault = _vault(tmp_path)
    (tmp_path / "02_KNOWLEDGE" / "health").mkdir(parents=True)

    with patch(RENDER_TARGET, return_value=STUB_BODY):
        first = setup_vault(vault)
        second = setup_vault(vault)

    assert second["created"] == 0
    assert second["skipped"] == first["created"] + first["skipped"]
    assert second["errors"] == 0


# ---------------------------------------------------------------------------
# Test 9 — summary counts match filesystem state
# ---------------------------------------------------------------------------

def test_summary_counts_correct(tmp_path):
    vault = _vault(tmp_path)
    # Pre-create one index to get a skipped count
    existing = tmp_path / "03_PROJECTS" / "_index.md"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("---\nindex_type: zone\n---\n\nbody", encoding="utf-8")

    # Add a domain so there are 2 new knowledge indexes (root + domain)
    (tmp_path / "02_KNOWLEDGE" / "tech").mkdir(parents=True)

    with patch(RENDER_TARGET, return_value=STUB_BODY):
        counts = setup_vault(vault)

    # Verify counts against actual filesystem
    actual_created = list(tmp_path.rglob("_index.md"))
    # Exclude the pre-created one from "created"
    expected_total = len(actual_created)
    assert counts["created"] + counts["skipped"] == expected_total
    assert counts["skipped"] == 1
    assert counts["errors"] == 0


# ---------------------------------------------------------------------------
# Test 10 — bad config path → exit code 1
# ---------------------------------------------------------------------------

def test_config_error_exits_1(tmp_path):
    result = main(["--config", str(tmp_path / "nonexistent.yaml")])
    assert result == 1


# ---------------------------------------------------------------------------
# Test 11 — missing template dir → exit code 2
# ---------------------------------------------------------------------------

def test_missing_template_dir_exits_2(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    config_file = tmp_path / "agent-config.yaml"
    _write_config(config_file, vault_root)

    def _raise_fnf(name, ctx, template_dir):
        raise FileNotFoundError(f"Template directory does not exist: {template_dir}")

    with patch(RENDER_TARGET, side_effect=_raise_fnf):
        result = main(["--config", str(config_file)])

    assert result == 2
