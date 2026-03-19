"""Unit tests for agent/tasks/outdated_review.py.

All file I/O uses tmp_path; date/datetime are patched to a fixed point
(TODAY = 2026-03-19) so tests are deterministic without freezegun.
"""
from __future__ import annotations

import logging
from datetime import date as real_date, datetime as real_datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import agent.tasks.outdated_review as outdated_review
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import StatenessRisk, VerbatimBlock, VerbatimType
from agent.vault.vault import ObsidianVault
from agent.vault.verbatim import render_verbatim_block

# ---------------------------------------------------------------------------
# Fixed time constants
# ---------------------------------------------------------------------------

TODAY = real_date(2026, 3, 19)
UTCNOW = real_datetime(2026, 3, 19, 0, 0, 0)
# high_risk_cutoff = UTCNOW - timedelta(days=365) ≈ 2025-03-19
# Stale verbatim: added_at before 2025-03-19  →  e.g. "2024-01-01T00:00:00"
# Fresh verbatim: added_at after  2025-03-19  →  e.g. "2026-01-01T00:00:00"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def vault_root(tmp_path: Path) -> Path:
    (tmp_path / "02_KNOWLEDGE").mkdir()
    return tmp_path


@pytest.fixture()
def vault(vault_root: Path) -> ObsidianVault:
    return ObsidianVault(vault_root)


@pytest.fixture()
def config(vault_root: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(vault_root)))


@pytest.fixture()
def mock_dates():
    """Freeze date.today() → TODAY and datetime.utcnow() → UTCNOW."""
    mock_date = MagicMock()
    mock_date.today.return_value = TODAY
    mock_date.fromisoformat = real_date.fromisoformat

    mock_dt = MagicMock()
    mock_dt.utcnow.return_value = UTCNOW

    with (
        patch("agent.tasks.outdated_review.date", mock_date),
        patch("agent.tasks.outdated_review.datetime", mock_dt),
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_note(vault: ObsidianVault, rel_path: str, fm: dict, body: str = "") -> None:
    (vault.root / rel_path).parent.mkdir(parents=True, exist_ok=True)
    vault.write_note(rel_path, fm, body)


def _make_verbatim_body(
    type_: str,
    staleness_risk: str,
    added_at_str: str,
    lang: str = "",
    attribution: str = "",
    model_target: str = "",
) -> str:
    """Build a note body containing one correctly-formatted verbatim block."""
    block = VerbatimBlock(
        type=VerbatimType(type_),
        content="test verbatim content",
        lang=lang,
        source_id="SRC-TEST",
        added_at=real_datetime.fromisoformat(added_at_str),
        staleness_risk=StatenessRisk(staleness_risk),
        attribution=attribution,
        model_target=model_target,
    )
    return render_verbatim_block(block)


def _read_report(vault: ObsidianVault) -> str:
    return (vault.meta / "outdated-review.md").read_text(encoding="utf-8")


def _notes_section(report: str) -> str:
    """Extract the Notes past review_after section from the report."""
    return report.split("## Notes past review_after")[1].split("## Verbatim")[0]


def _verbatim_section(report: str) -> str:
    """Extract the Verbatim blocks to review section from the report."""
    return report.split("## Verbatim blocks to review")[1]


# ---------------------------------------------------------------------------
# Pass A — note-level staleness
# ---------------------------------------------------------------------------


class TestStaleNoteDetection:
    @pytest.mark.anyio
    async def test_stale_note_flagged(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        _write_note(vault, "02_KNOWLEDGE/old.md", {"review_after": "2026-03-18"})
        await outdated_review.run(vault, config)
        assert "old.md" in _notes_section(_read_report(vault))

    @pytest.mark.anyio
    async def test_fresh_note_not_flagged(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        _write_note(vault, "02_KNOWLEDGE/new.md", {"review_after": "2026-03-20"})
        await outdated_review.run(vault, config)
        assert "new.md" not in _notes_section(_read_report(vault))

    @pytest.mark.anyio
    async def test_note_without_review_after_skipped(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        _write_note(vault, "02_KNOWLEDGE/no_date.md", {"domain_path": "tech/python"})
        await outdated_review.run(vault, config)
        assert "_None._" in _notes_section(_read_report(vault))

    @pytest.mark.anyio
    async def test_malformed_review_after_skipped(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        _write_note(vault, "02_KNOWLEDGE/bad_date.md", {"review_after": "not-a-date"})
        await outdated_review.run(vault, config)
        assert "_None._" in _notes_section(_read_report(vault))


# ---------------------------------------------------------------------------
# Pass B — verbatim block staleness
# ---------------------------------------------------------------------------


class TestStaleVerbatimDetection:
    @pytest.mark.anyio
    async def test_stale_verbatim_flagged(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        body = _make_verbatim_body("code", "high", "2024-01-01T00:00:00", lang="python")
        _write_note(vault, "02_KNOWLEDGE/note.md", {}, body)
        await outdated_review.run(vault, config)
        assert "note.md" in _verbatim_section(_read_report(vault))

    @pytest.mark.anyio
    async def test_fresh_verbatim_not_flagged(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        body = _make_verbatim_body("code", "high", "2026-01-01T00:00:00", lang="python")
        _write_note(vault, "02_KNOWLEDGE/fresh.md", {}, body)
        await outdated_review.run(vault, config)
        assert "fresh.md" not in _verbatim_section(_read_report(vault))

    @pytest.mark.anyio
    async def test_medium_risk_verbatim_not_flagged(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        body = _make_verbatim_body("code", "medium", "2024-01-01T00:00:00", lang="python")
        _write_note(vault, "02_KNOWLEDGE/medium.md", {}, body)
        await outdated_review.run(vault, config)
        assert "medium.md" not in _verbatim_section(_read_report(vault))

    @pytest.mark.anyio
    async def test_verbatim_independent_of_note_staleness(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        """Fresh note (review_after in future) with old HIGH verbatim block:
        note NOT in stale notes, but block IS in stale verbatim."""
        body = _make_verbatim_body("code", "high", "2024-01-01T00:00:00", lang="python")
        _write_note(
            vault,
            "02_KNOWLEDGE/indep.md",
            {"review_after": "2027-01-01"},
            body,
        )
        await outdated_review.run(vault, config)
        report = _read_report(vault)
        assert "indep.md" not in _notes_section(report)
        assert "indep.md" in _verbatim_section(report)


# ---------------------------------------------------------------------------
# Index file skipping
# ---------------------------------------------------------------------------


class TestIndexFilesSkipped:
    @pytest.mark.anyio
    async def test_index_files_skipped(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        # _index.md with stale review_after — must not appear in report
        _write_note(
            vault,
            "02_KNOWLEDGE/_index.md",
            {"review_after": "2020-01-01"},
        )
        await outdated_review.run(vault, config)
        report = _read_report(vault)
        assert "_index.md" not in report


# ---------------------------------------------------------------------------
# Report output
# ---------------------------------------------------------------------------


class TestReportOutput:
    @pytest.mark.anyio
    async def test_report_written_to_correct_path(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        await outdated_review.run(vault, config)
        assert (vault.meta / "outdated-review.md").exists()

    @pytest.mark.anyio
    async def test_report_overwritten_on_rerun(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        _write_note(vault, "02_KNOWLEDGE/first.md", {"review_after": "2026-03-18"})
        await outdated_review.run(vault, config)
        assert "first.md" in _read_report(vault)

        # Remove first note; add a different one — second run must replace report
        (vault.knowledge / "first.md").unlink()
        _write_note(vault, "02_KNOWLEDGE/second.md", {"review_after": "2026-03-18"})
        await outdated_review.run(vault, config)
        report = _read_report(vault)
        assert "second.md" in report
        assert "first.md" not in report

    @pytest.mark.anyio
    async def test_empty_vault_empty_tables(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        await outdated_review.run(vault, config)
        report = _read_report(vault)
        assert report.count("_None._") == 2

    @pytest.mark.anyio
    async def test_tables_sorted_by_date(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        # Two stale notes: beta has later review_after → must appear second
        _write_note(vault, "02_KNOWLEDGE/beta.md", {"review_after": "2026-02-01"})
        _write_note(vault, "02_KNOWLEDGE/alpha.md", {"review_after": "2026-01-01"})

        # Two stale verbatim: gamma is older → must appear first
        body_old = _make_verbatim_body("code", "high", "2023-01-01T00:00:00", lang="python")
        body_new = _make_verbatim_body("code", "high", "2024-06-01T00:00:00", lang="python")
        _write_note(vault, "02_KNOWLEDGE/gamma.md", {}, body_old)
        _write_note(vault, "02_KNOWLEDGE/delta.md", {}, body_new)

        await outdated_review.run(vault, config)
        report = _read_report(vault)

        # Notes sorted ascending by review_after
        notes_sec = _notes_section(report)
        assert notes_sec.index("2026-01-01") < notes_sec.index("2026-02-01")

        # Verbatim sorted ascending by added_at
        verb_sec = _verbatim_section(report)
        assert verb_sec.index("2023-01-01") < verb_sec.index("2024-06-01")


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------


class TestEventsEmitted:
    @pytest.mark.anyio
    async def test_events_emitted(
        self,
        vault: ObsidianVault,
        config: AgentConfig,
        mock_dates: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO, logger="agent.tasks.outdated_review"):
            await outdated_review.run(vault, config)

        messages = " ".join(caplog.messages)
        assert "staleness.scan.started" in messages
        assert "staleness.found" in messages
        assert "staleness.scan.completed" in messages


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------


class TestErrorResilience:
    @pytest.mark.anyio
    async def test_malformed_note_read_error_skipped(
        self, vault: ObsidianVault, config: AgentConfig, mock_dates: None
    ) -> None:
        # Plant a .md file so rglob finds it; read_note will raise for it
        (vault.knowledge / "bad.md").write_text("content", encoding="utf-8")

        with patch.object(vault, "read_note", side_effect=OSError("disk error")):
            # Must not raise; report must still be written
            await outdated_review.run(vault, config)

        assert (vault.meta / "outdated-review.md").exists()
        assert _read_report(vault).count("_None._") == 2
