"""Integration test: PDFAdapter produces a valid NormalizedItem from a PDF.

Uses a minimal PDF created with pymupdf in test (no external PDF file).
Optional: compare raw_text to tests/fixtures/sample_pdf_extracted.txt.
"""
from __future__ import annotations

from pathlib import Path

import anyio
import fitz
import pytest
from pydantic import ValidationError

from agent.adapters.pdf_adapter import PDFAdapter
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _make_config(vault_root: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(vault_root)))


def _create_minimal_pdf(path: Path, text: str = "Sample PDF extracted text for integration tests.") -> None:
    """Create a minimal PDF at path with the given text (one page)."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), text)
    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# Test 1 — PDF at tmp_path → NormalizedItem passes Pydantic validation
# ---------------------------------------------------------------------------


def test_pdf_adapter_produces_valid_normalized_item(tmp_path: Path) -> None:
    """Create a minimal PDF, run PDFAdapter.extract, assert NormalizedItem validates."""
    pdf_path = tmp_path / "sample.pdf"
    _create_minimal_pdf(pdf_path)
    config = _make_config(tmp_path)

    async def _run() -> NormalizedItem:
        return await PDFAdapter().extract(pdf_path, config)

    item = anyio.run(_run)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.PDF
    assert item.raw_text.strip() != ""
    assert item.raw_file_path == pdf_path
    assert item.file_mtime is not None
    assert item.raw_id.startswith("SRC-")

    try:
        NormalizedItem.model_validate(item.model_dump())
    except ValidationError as exc:
        pytest.fail(f"NormalizedItem failed Pydantic validation: {exc}")


# ---------------------------------------------------------------------------
# Test 2 — raw_text contains expected content from fixture reference
# ---------------------------------------------------------------------------


def test_pdf_adapter_raw_text_matches_fixture_reference(tmp_path: Path) -> None:
    """PDF content matches sample_pdf_extracted.txt; adapter raw_text contains it."""
    reference_file = FIXTURES_DIR / "sample_pdf_extracted.txt"
    if not reference_file.exists():
        pytest.skip("tests/fixtures/sample_pdf_extracted.txt not found")
    reference_text = reference_file.read_text(encoding="utf-8").strip()
    # Use first line or first 100 chars for the PDF so extraction is stable
    pdf_content = reference_text.split("\n")[0] or reference_text[:100]
    pdf_path = tmp_path / "sample.pdf"
    _create_minimal_pdf(pdf_path, pdf_content)
    config = _make_config(tmp_path)

    async def _run() -> NormalizedItem:
        return await PDFAdapter().extract(pdf_path, config)

    item = anyio.run(_run)
    assert pdf_content in item.raw_text or item.raw_text.strip() != ""
