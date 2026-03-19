"""Unit tests for agent/adapters/pdf_adapter.py.

All fitz.open calls patched via unittest.mock.patch.
Async execution driven via anyio.run() — consistent with the rest of the test suite.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import anyio
import fitz
import pytest

from agent.adapters.base import AdapterError
from agent.adapters.pdf_adapter import PDFAdapter, _parse_pdf_date
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root="/vault"))


def _make_mock_doc(
    *,
    pages: list[str],
    is_encrypted: bool = False,
    metadata: dict | None = None,
    page_count: int | None = None,
) -> MagicMock:
    """Build a minimal fitz document mock."""
    doc = MagicMock()
    doc.is_encrypted = is_encrypted

    mock_pages = []
    for text in pages:
        p = MagicMock()
        p.get_text.return_value = text
        mock_pages.append(p)
    doc.__iter__ = MagicMock(return_value=iter(mock_pages))

    doc.metadata = metadata or {}
    doc.page_count = page_count if page_count is not None else len(pages)
    return doc


def _run(path: Path, config: AgentConfig) -> NormalizedItem:
    """Run PDFAdapter.extract synchronously via anyio."""
    return anyio.run(PDFAdapter().extract, path, config)


# ---------------------------------------------------------------------------
# Unit tests for _parse_pdf_date (synchronous)
# ---------------------------------------------------------------------------


def test_parse_pdf_date_full():
    assert _parse_pdf_date("D:20240115143022+02'00'") == date(2024, 1, 15)


def test_parse_pdf_date_utc_suffix():
    assert _parse_pdf_date("D:20240115000000Z") == date(2024, 1, 15)


def test_parse_pdf_date_date_only():
    assert _parse_pdf_date("D:20240115") == date(2024, 1, 15)


def test_parse_pdf_date_empty_returns_none():
    assert _parse_pdf_date("") is None


def test_parse_pdf_date_malformed_returns_none():
    assert _parse_pdf_date("not-a-date") is None


def test_parse_pdf_date_impossible_date_returns_none():
    # month 13 — should not raise, just return None
    assert _parse_pdf_date("D:20241332") is None


# ---------------------------------------------------------------------------
# Unit tests for PDFAdapter.extract
# ---------------------------------------------------------------------------


# Case 1 — Normal multi-page PDF with title + author metadata
def test_normal_pdf_returns_normalized_item(tmp_path):
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(
        pages=["Page one text.", "Page two text."],
        metadata={
            "title": "My Document",
            "author": "Alice",
            "creator": "Word",
            "producer": "Acrobat",
            "creationDate": "D:20240115143022",
        },
        page_count=2,
    )
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.PDF
    assert item.title == "My Document"
    assert item.author == "Alice"
    assert item.extra_metadata["page_count"] == 2
    assert item.raw_text != ""


# Case 2 — Pages joined with "\n\n---\n\n" separator
def test_pages_joined_with_separator(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["First page", "Second page"])
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.raw_text == "First page\n\n---\n\nSecond page"


# Case 3 — No title metadata → fallback to path.stem
def test_no_title_falls_back_to_stem(tmp_path):
    pdf_path = tmp_path / "my_report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(
        pages=["Some content"],
        metadata={"title": "", "author": "Bob", "creator": "", "producer": ""},
    )
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.title == "my_report"


# Case 4 — creationDate in D:YYYYMMDD... format → source_date populated
def test_creation_date_parsed(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(
        pages=["Content"],
        metadata={"creationDate": "D:20230701120000Z"},
    )
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.source_date == date(2023, 7, 1)


# Case 5 — Missing creationDate → source_date is None
def test_missing_creation_date_is_none(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["Content"], metadata={})
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.source_date is None


# Case 6 — Malformed creationDate → source_date is None (no exception)
def test_malformed_creation_date_is_none(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(
        pages=["Content"],
        metadata={"creationDate": "garbage-value"},
    )
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.source_date is None


# Case 7 — Encrypted PDF raises AdapterError
def test_encrypted_pdf_raises(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=[], is_encrypted=True)
    with patch("fitz.open", return_value=doc):
        with pytest.raises(AdapterError, match="encrypted"):
            _run(pdf_path, config)


# Case 8 — fitz.open raises FileDataError (corrupt PDF)
def test_corrupt_pdf_raises(tmp_path):
    pdf_path = tmp_path / "corrupt.pdf"
    pdf_path.write_bytes(b"not a pdf")
    config = _make_config()

    with patch("fitz.open", side_effect=fitz.FileDataError("bad data")):
        with pytest.raises(AdapterError, match="Corrupt"):
            _run(pdf_path, config)


# Case 9 — All pages yield empty text → AdapterError
def test_all_empty_pages_raises(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["   ", "  \n  "])
    with patch("fitz.open", return_value=doc):
        with pytest.raises(AdapterError, match="no extractable text"):
            _run(pdf_path, config)


# Case 10 — Mixed empty/non-empty pages → empty ones skipped
def test_empty_pages_skipped(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["  ", "Real content", "   ", "More content"])
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.raw_text == "Real content\n\n---\n\nMore content"


# Case 11 — file_mtime is a UTC datetime
def test_file_mtime_is_utc_datetime(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["Content"])
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert isinstance(item.file_mtime, datetime)
    assert item.file_mtime.tzinfo == timezone.utc


# Case 12 — raw_file_path equals input Path
def test_raw_file_path_equals_input(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["Content"])
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.raw_file_path == pdf_path


# Case 13 — extra_metadata contains page_count, creator, producer
def test_extra_metadata_keys(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(
        pages=["Content"],
        metadata={"creator": "LibreOffice", "producer": "Cairo"},
        page_count=3,
    )
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.extra_metadata["page_count"] == 3
    assert item.extra_metadata["creator"] == "LibreOffice"
    assert item.extra_metadata["producer"] == "Cairo"


# Case 14 — raw_id matches SRC-YYYYMMDD-HHmmss pattern
def test_raw_id_format(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["Content"])
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert re.match(r"SRC-\d{8}-\d{6}", item.raw_id)


# Extra — url is always empty string
def test_url_is_empty(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["Content"])
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.url == ""


# Extra — language is always empty string
def test_language_is_empty(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    config = _make_config()

    doc = _make_mock_doc(pages=["Content"])
    with patch("fitz.open", return_value=doc):
        item = _run(pdf_path, config)

    assert item.language == ""
