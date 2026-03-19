"""Unit tests for agent/stages/s6b_index_update.py.

Tests 1-3 and 7-8 use a mock vault.
Tests 4-6 use a real temp vault (render_template patched).
All async execution via anyio.run().
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

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


def _make_mock_vault() -> MagicMock:
    vault = MagicMock(spec=ObsidianVault)
    vault.get_domain_index_path.side_effect = (
        lambda d, s=None: (
            f"02_KNOWLEDGE/{d}/{s}/_index.md" if s else f"02_KNOWLEDGE/{d}/_index.md"
        )
    )
    return vault


def _run_sync(classification: ClassificationResult, vault: ObsidianVault) -> None:
    async def _coro() -> None:
        await s6b_index_update.run(classification, vault)

    anyio.run(_coro)


# ---------------------------------------------------------------------------
# Test 1 — two-segment domain_path: ensure + increment for both levels
# ---------------------------------------------------------------------------


def test_subdomain_and_domain_both_updated() -> None:
    vault = _make_mock_vault()
    cls = _make_classification("professional_dev/ai_tools")

    _run_sync(cls, vault)

    # ensure_domain_index called twice (subdomain + domain)
    assert vault.ensure_domain_index.call_count == 2
    # increment_index_count called twice (subdomain + domain)
    assert vault.increment_index_count.call_count == 2

    sub_rel = "02_KNOWLEDGE/professional_dev/ai_tools/_index.md"
    dom_rel = "02_KNOWLEDGE/professional_dev/_index.md"

    vault.ensure_domain_index.assert_any_call(sub_rel, "subdomain", "professional_dev", "ai_tools")
    vault.ensure_domain_index.assert_any_call(dom_rel, "domain", "professional_dev", None)
    vault.increment_index_count.assert_any_call(sub_rel)
    vault.increment_index_count.assert_any_call(dom_rel)


# ---------------------------------------------------------------------------
# Test 2 — single-segment domain_path: only domain index touched
# ---------------------------------------------------------------------------


def test_single_segment_domain_path_only() -> None:
    vault = _make_mock_vault()
    cls = _make_classification("personal")

    _run_sync(cls, vault)

    # ensure_domain_index called exactly once (domain only)
    assert vault.ensure_domain_index.call_count == 1
    # increment_index_count called exactly once
    assert vault.increment_index_count.call_count == 1

    dom_rel = "02_KNOWLEDGE/personal/_index.md"
    vault.ensure_domain_index.assert_called_once_with(dom_rel, "domain", "personal", None)
    vault.increment_index_count.assert_called_once_with(dom_rel)


# ---------------------------------------------------------------------------
# Test 3 — ensure_domain_index called before increment_index_count
# ---------------------------------------------------------------------------


def test_ensure_called_before_increment() -> None:
    vault = _make_mock_vault()
    cls = _make_classification("professional_dev/ai_tools")

    # Attach both methods to a manager to observe interleaved call order
    manager = MagicMock()
    manager.attach_mock(vault.ensure_domain_index, "ensure_domain_index")
    manager.attach_mock(vault.increment_index_count, "increment_index_count")

    _run_sync(cls, vault)

    calls = [c[0] for c in manager.mock_calls]  # method names only
    ensure_positions = [i for i, n in enumerate(calls) if n == "ensure_domain_index"]
    increment_positions = [i for i, n in enumerate(calls) if n == "increment_index_count"]

    # Each ensure must come before its corresponding increment
    # Pattern must be: ensure(sub), increment(sub), ensure(dom), increment(dom)
    assert len(ensure_positions) == 2
    assert len(increment_positions) == 2
    # First ensure before first increment
    assert ensure_positions[0] < increment_positions[0]
    # Second ensure before second increment
    assert ensure_positions[1] < increment_positions[1]


# ---------------------------------------------------------------------------
# Test 4 — body of existing _index.md is byte-identical after run
# ---------------------------------------------------------------------------


@patch("agent.vault.templates.render_template", return_value="mock body")
def test_index_body_unchanged(mock_rt, tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)
    domain_idx_rel = "02_KNOWLEDGE/tech/_index.md"

    original_body = "```bases\nfilter: domain_path = tech\n```\n\nSome more content."
    vault.write_note(
        domain_idx_rel,
        {"index_type": "domain", "domain": "tech", "note_count": 0, "last_updated": "2026-01-01"},
        original_body,
    )

    _, body_before = vault.read_note(domain_idx_rel)

    cls = _make_classification("tech")
    _run_sync(cls, vault)

    _, body_after = vault.read_note(domain_idx_rel)
    assert body_after == body_before


# ---------------------------------------------------------------------------
# Test 5 — creates _index.md when missing; note_count == 1
# ---------------------------------------------------------------------------


@patch("agent.vault.templates.render_template", return_value="mock body")
def test_creates_index_if_missing(mock_rt, tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)
    cls = _make_classification("tech/python")

    _run_sync(cls, vault)

    sub_rel = "02_KNOWLEDGE/tech/python/_index.md"
    dom_rel = "02_KNOWLEDGE/tech/_index.md"

    assert (tmp_path / sub_rel).exists()
    assert (tmp_path / dom_rel).exists()

    sub_fm, _ = vault.read_note(sub_rel)
    dom_fm, _ = vault.read_note(dom_rel)

    assert sub_fm["note_count"] == 1
    assert dom_fm["note_count"] == 1


# ---------------------------------------------------------------------------
# Test 6 — increments existing note_count
# ---------------------------------------------------------------------------


@patch("agent.vault.templates.render_template", return_value="mock body")
def test_increments_existing_count(mock_rt, tmp_path: Path) -> None:
    vault = ObsidianVault(tmp_path)
    dom_rel = "02_KNOWLEDGE/tech/_index.md"

    vault.write_note(
        dom_rel,
        {"index_type": "domain", "domain": "tech", "note_count": 3, "last_updated": "2026-01-01"},
        "body",
    )

    cls = _make_classification("tech")
    _run_sync(cls, vault)

    fm, _ = vault.read_note(dom_rel)
    assert fm["note_count"] == 4


# ---------------------------------------------------------------------------
# Test 7 — exception does not propagate
# ---------------------------------------------------------------------------


def test_exception_does_not_propagate() -> None:
    vault = _make_mock_vault()
    vault.ensure_domain_index.side_effect = RuntimeError("boom")

    cls = _make_classification("tech/python")

    # Must complete without raising
    _run_sync(cls, vault)


# ---------------------------------------------------------------------------
# Test 8 — get_domain_index_path is invoked (not a hand-rolled f-string)
# ---------------------------------------------------------------------------


def test_get_domain_index_path_used() -> None:
    vault = _make_mock_vault()
    cls = _make_classification("professional_dev/ai_tools")

    _run_sync(cls, vault)

    assert vault.get_domain_index_path.called
    # Called at least twice: once for subdomain, once for domain
    assert vault.get_domain_index_path.call_count >= 2
