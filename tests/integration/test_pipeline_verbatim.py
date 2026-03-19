"""Integration test: verbatim blocks survive pipeline write and parse (round-trip).

Source with code (e.g. from tests/fixtures/sample_code_heavy.md) → s6a write
→ note body contains verbatim block(s) with byte-identical content.

Uses mocked render_template so only verbatim block rendering is under test.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import anyio
import pytest

from agent.core.models import (
    ClassificationResult,
    ContentAge,
    DeduplicationResult,
    NormalizedItem,
    SourceType,
    StatenessRisk,
    SummaryResult,
    VerbatimBlock,
    VerbatimType,
)
from agent.stages import s6a_write
from agent.vault.vault import ObsidianVault
from agent.vault.verbatim import parse_verbatim_blocks

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
CODE_CONTENT = 'def hello() -> str:\n    return "world"\n'
_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_item(raw_id: str = "SRC-20260115-120000", domain_path: str = "professional_dev/ai_tools") -> NormalizedItem:
    return NormalizedItem(
        raw_id=raw_id,
        source_type=SourceType.NOTE,
        raw_text="",
        raw_file_path=Path("/fixtures/sample_code_heavy.md"),
        title="Code-heavy sample",
        url="",
        author="",
        language="en",
        source_date=None,
        file_mtime=_NOW,
        extra_metadata={},
    )


def _make_classification(domain_path: str = "professional_dev/ai_tools") -> ClassificationResult:
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


def _make_summary_with_verbatim(verbatim_blocks: list[VerbatimBlock]) -> SummaryResult:
    return SummaryResult(
        summary="",
        key_ideas=[],
        action_items=[],
        quotes=[],
        atom_concepts=[],
        verbatim_blocks=verbatim_blocks,
    )


# ---------------------------------------------------------------------------
# Test 1 — one code block written by s6a → parse_verbatim_blocks → content byte-identical
# ---------------------------------------------------------------------------


@patch("agent.stages.s6a_write.render_template", return_value="")
def test_verbatim_code_block_roundtrip(mock_render, tmp_path: Path) -> None:
    """s6a appends verbatim block to source note body; parse recovers byte-identical content."""
    vault = ObsidianVault(tmp_path)
    item = _make_item()
    classification = _make_classification()
    block = VerbatimBlock(
        type=VerbatimType.CODE,
        content=CODE_CONTENT,
        lang="python",
        source_id=item.raw_id,
        added_at=_NOW,
        staleness_risk=StatenessRisk.HIGH,
    )
    summary = _make_summary_with_verbatim([block])
    merge_result = DeduplicationResult(route_to_merge=False)

    from agent.core.config import AgentConfig, VaultConfig
    config = AgentConfig(vault=VaultConfig(root=str(tmp_path)))

    async def _run() -> None:
        await s6a_write.run(item, classification, summary, merge_result, vault, config)

    anyio.run(_run)

    source_rel = f"02_KNOWLEDGE/{classification.domain_path}/{item.raw_id}.md"
    _, body = vault.read_note(source_rel)
    parsed = parse_verbatim_blocks(body)
    assert len(parsed) == 1
    assert parsed[0].type == VerbatimType.CODE
    assert parsed[0].content == CODE_CONTENT, "Verbatim content must be byte-identical"
    assert parsed[0].lang == "python"
    assert parsed[0].source_id == item.raw_id
