"""Integration tests for:
  - agent/stages/s6b_index_update.py  (pipeline stage, end-to-end)
  - agent/tasks/index_updater.py       (daily rebuild task, end-to-end)
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

import anyio
import pytest

from agent.core.models import (
    ClassificationResult,
    ContentAge,
    StatenessRisk,
)
from agent.stages import s6b_index_update
from agent.tasks.index_updater import rebuild_all_counts
from agent.vault.vault import ObsidianVault


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_classification(domain_path: str) -> ClassificationResult:
    parts = domain_path.split("/", 1)
    return ClassificationResult(
        domain=parts[0],
        subdomain=parts[1] if len(parts) > 1 else "",
        domain_path=domain_path,
        vault_zone="02_KNOWLEDGE",
        content_age=ContentAge.EVERGREEN,
        staleness_risk=StatenessRisk.LOW,
        suggested_tags=[],
        detected_people=[],
        detected_projects=[],
        language="en",
        confidence=0.9,
    )


def _run_sync(classification: ClassificationResult, vault: ObsidianVault) -> None:
    async def _coro() -> None:
        await s6b_index_update.run(classification, vault)

    anyio.run(_coro)


def _run_rebuild(vault: ObsidianVault) -> None:
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
) -> str:
    rel = vault.get_domain_index_path(domain, subdomain)
    fm: dict = {
        "index_type": index_type,
        "domain": domain,
        "note_count": note_count,
        "last_updated": last_updated,
    }
    if subdomain:
        fm["subdomain"] = subdomain
    vault.write_note(rel, fm, "")
    return rel


# ---------------------------------------------------------------------------
# s6b stage — end-to-end
# ---------------------------------------------------------------------------


@patch("agent.vault.templates.render_template", return_value="mock body")
def test_full_pipeline_index_update(mock_rt, tmp_path: Path) -> None:
    """Both _index.md files must exist with note_count=1 and a refreshed last_updated."""
    vault = ObsidianVault(tmp_path)
    cls = _make_classification("professional_dev/ai_tools")

    _run_sync(cls, vault)

    sub_rel = "02_KNOWLEDGE/professional_dev/ai_tools/_index.md"
    dom_rel = "02_KNOWLEDGE/professional_dev/_index.md"

    assert (tmp_path / sub_rel).exists(), "subdomain _index.md must be created"
    assert (tmp_path / dom_rel).exists(), "domain _index.md must be created"

    sub_fm, _ = vault.read_note(sub_rel)
    dom_fm, _ = vault.read_note(dom_rel)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    assert sub_fm["note_count"] == 1
    assert sub_fm["last_updated"] == today

    assert dom_fm["note_count"] == 1
    assert dom_fm["last_updated"] == today


# ---------------------------------------------------------------------------
# index_updater task — integration case 1: three notes → count 3
# ---------------------------------------------------------------------------


def test_three_notes_count_three(tmp_path: Path) -> None:
    """Write 3 notes to professional_dev/ai_tools/; run rebuild_all_counts;
    verify note_count: 3 in both subdomain and domain _index.md."""
    vault = ObsidianVault(tmp_path)

    for i in range(3):
        _write_note(
            vault,
            f"02_KNOWLEDGE/professional_dev/ai_tools/note{i}.md",
            {"domain_path": "professional_dev/ai_tools", "date_modified": "2025-03-01"},
        )

    sub_rel = _write_index(vault, "subdomain", "professional_dev", "ai_tools")
    dom_rel = _write_index(vault, "domain", "professional_dev")

    _run_rebuild(vault)

    sub_fm, _ = vault.read_note(sub_rel)
    dom_fm, _ = vault.read_note(dom_rel)

    assert sub_fm["note_count"] == 3, "subdomain index must reflect 3 notes"
    assert dom_fm["note_count"] == 3, "domain index must reflect 3 notes"


# ---------------------------------------------------------------------------
# index_updater task — integration case 2: multi-domain isolation
# ---------------------------------------------------------------------------


def test_multi_domain_isolation(tmp_path: Path) -> None:
    """2 notes in professional_dev/ai_tools, 1 in mindset/resilience;
    each domain/subdomain gets an independent correct count."""
    vault = ObsidianVault(tmp_path)

    for i in range(2):
        _write_note(
            vault,
            f"02_KNOWLEDGE/professional_dev/ai_tools/note{i}.md",
            {"domain_path": "professional_dev/ai_tools"},
        )

    _write_note(
        vault,
        "02_KNOWLEDGE/mindset/resilience/note0.md",
        {"domain_path": "mindset/resilience"},
    )

    pd_sub_rel = _write_index(vault, "subdomain", "professional_dev", "ai_tools")
    pd_dom_rel = _write_index(vault, "domain", "professional_dev")
    ms_sub_rel = _write_index(vault, "subdomain", "mindset", "resilience")
    ms_dom_rel = _write_index(vault, "domain", "mindset")

    _run_rebuild(vault)

    pd_sub_fm, _ = vault.read_note(pd_sub_rel)
    pd_dom_fm, _ = vault.read_note(pd_dom_rel)
    ms_sub_fm, _ = vault.read_note(ms_sub_rel)
    ms_dom_fm, _ = vault.read_note(ms_dom_rel)

    assert pd_sub_fm["note_count"] == 2, "professional_dev/ai_tools subdomain: 2 notes"
    assert pd_dom_fm["note_count"] == 2, "professional_dev domain: 2 notes"
    assert ms_sub_fm["note_count"] == 1, "mindset/resilience subdomain: 1 note"
    assert ms_dom_fm["note_count"] == 1, "mindset domain: 1 note"
