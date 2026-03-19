"""Integration test: MarkdownAdapter produces a valid NormalizedItem from a fixture file.

Validates the adapter cooperates with the NormalizedItem contract expected by Stage 1.
"""
from __future__ import annotations

from pathlib import Path

import anyio
import pytest
from pydantic import ValidationError

from agent.adapters.markdown_adapter import MarkdownAdapter
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_note.md"


def _make_config(vault_root: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(vault_root)))


async def _extract() -> NormalizedItem:
    adapter = MarkdownAdapter()
    config = _make_config(FIXTURE_PATH.parent.parent)
    return await adapter.extract(FIXTURE_PATH, config)


# ---------------------------------------------------------------------------
# Test 1 — fixture produces a NormalizedItem with non-empty, consistent fields
# ---------------------------------------------------------------------------

def test_fixture_produces_valid_item():
    item = anyio.run(_extract)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.NOTE
    assert item.title == "Sample Note for Integration Testing"
    assert item.url == "https://example.com/article"
    assert item.author == "Ada Lovelace"
    assert item.language == "en"
    assert item.raw_text.strip() != ""
    # frontmatter must not leak into raw_text
    assert "source_url:" not in item.raw_text
    assert item.raw_file_path == FIXTURE_PATH
    assert item.file_mtime is not None
    assert item.raw_id.startswith("SRC-")


# ---------------------------------------------------------------------------
# Test 2 — NormalizedItem passes Pydantic model validation
# ---------------------------------------------------------------------------

def test_fixture_item_passes_pydantic_validation():
    item = anyio.run(_extract)
    # Re-validate by round-tripping through model_validate
    try:
        NormalizedItem.model_validate(item.model_dump())
    except ValidationError as exc:
        pytest.fail(f"NormalizedItem failed Pydantic validation: {exc}")
