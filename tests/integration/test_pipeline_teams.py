"""Integration test: TeamsAdapter produces a valid NormalizedItem from a real VTT file.

Uses the fixture at tests/fixtures/sample_teams_transcript.vtt.
No mocking — pure file I/O.
"""
from __future__ import annotations

from pathlib import Path

import anyio
import pytest
from pydantic import ValidationError

from agent.adapters.teams_adapter import TeamsAdapter
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType

# Fixture path relative to this file's directory
_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_teams_transcript.vtt"


def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(tmp_path)))


# ---------------------------------------------------------------------------
# Test 1 — Real VTT fixture → NormalizedItem passes Pydantic validation
# ---------------------------------------------------------------------------


def test_teams_adapter_produces_valid_normalized_item(tmp_path):
    """Full path: real VTT file → NormalizedItem validates with no errors."""
    config = _make_config(tmp_path)

    async def _run():
        return await TeamsAdapter().extract(_FIXTURE, config)

    item = anyio.run(_run)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.MS_TEAMS

    try:
        NormalizedItem.model_validate(item.model_dump())
    except ValidationError as exc:
        pytest.fail(f"NormalizedItem failed Pydantic validation: {exc}")


# ---------------------------------------------------------------------------
# Test 2 — raw_text is non-empty; all lines start with "["
# ---------------------------------------------------------------------------


def test_teams_adapter_transcript_all_lines_start_with_bracket(tmp_path):
    """Every transcript line must start with '[' (timestamp bracket)."""
    config = _make_config(tmp_path)

    async def _run():
        return await TeamsAdapter().extract(_FIXTURE, config)

    item = anyio.run(_run)

    assert item.raw_text, "raw_text must not be empty"

    for line in item.raw_text.splitlines():
        assert line.startswith("["), f"Line does not start with '[': {line!r}"
