"""Integration tests for agent/stages/s6b_index_update.py.

End-to-end tests against a real temp vault (render_template patched).
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


# ---------------------------------------------------------------------------
# Test 1 — end-to-end: both _index.md files created with correct metadata
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
# Test 2 — rebuild_all_counts corrects inflated counts (DEFERRED)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Requires agent/tasks/index_updater.py — deferred to index_updater spec")
def test_rebuild_all_counts_corrects_inflation(tmp_path: Path) -> None:
    """TODO: manually set note_count=99 in a subdomain index, then call
    index_updater.rebuild_all_counts() and verify the count is corrected.
    This test requires agent/tasks/index_updater.py to be implemented first.
    """
    pass
