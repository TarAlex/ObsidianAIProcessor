"""Unit tests for agent/adapters/markitdown_adapter.py.

All markitdown.MarkItDown calls patched via unittest.mock.patch.
Async execution driven via anyio.run() — consistent with the rest of the test suite.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import anyio
import pytest

from agent.adapters.base import AdapterError
from agent.adapters.markitdown_adapter import MarkItDownAdapter
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root="/vault"))


def _make_convert_result(*, text_content: str, title: str | None = None) -> MagicMock:
    """Build a minimal markitdown conversion result mock."""
    result = MagicMock()
    result.text_content = text_content
    result.title = title
    return result


def _run(path: Path, config: AgentConfig) -> NormalizedItem:
    """Run MarkItDownAdapter.extract synchronously via anyio."""
    return anyio.run(MarkItDownAdapter().extract, path, config)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


# Case 1 — Happy path DOCX: returns NormalizedItem with correct fields
def test_docx_happy_path(tmp_path):
    doc_path = tmp_path / "report.docx"
    doc_path.write_bytes(b"fake docx content")
    config = _make_config()

    result = _make_convert_result(
        text_content="This is the document content.",
        title="My Report",
    )
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        item = _run(doc_path, config)

    assert isinstance(item, NormalizedItem)
    assert item.source_type == SourceType.ARTICLE
    assert item.raw_text == "This is the document content."
    assert item.title == "My Report"
    assert item.url == ""
    assert item.author == ""
    assert item.language == ""
    assert item.source_date is None


# Case 2 — Title fallback to path.stem when markitdown title is empty
def test_title_fallback_to_stem(tmp_path):
    doc_path = tmp_path / "my_presentation.pptx"
    doc_path.write_bytes(b"fake pptx content")
    config = _make_config()

    result = _make_convert_result(text_content="Slide content here.", title=None)
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        item = _run(doc_path, config)

    assert item.title == "my_presentation"


# Case 3 — Title fallback when title is empty string
def test_title_empty_string_falls_back_to_stem(tmp_path):
    doc_path = tmp_path / "budget.xlsx"
    doc_path.write_bytes(b"fake xlsx content")
    config = _make_config()

    result = _make_convert_result(text_content="Revenue data.", title="")
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        item = _run(doc_path, config)

    assert item.title == "budget"


# Case 4 — Empty text_content raises AdapterError
def test_empty_content_raises_adapter_error(tmp_path):
    doc_path = tmp_path / "empty.docx"
    doc_path.write_bytes(b"fake content")
    config = _make_config()

    result = _make_convert_result(text_content="   ", title="Empty Doc")
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        with pytest.raises(AdapterError, match="no extractable text"):
            _run(doc_path, config)


# Case 5 — None text_content raises AdapterError
def test_none_content_raises_adapter_error(tmp_path):
    doc_path = tmp_path / "broken.docx"
    doc_path.write_bytes(b"fake content")
    config = _make_config()

    result = _make_convert_result(text_content=None, title="Broken")
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        with pytest.raises(AdapterError):
            _run(doc_path, config)


# Case 6 — markitdown raises an exception → AdapterError propagated
def test_markitdown_exception_raises_adapter_error(tmp_path):
    doc_path = tmp_path / "corrupt.docx"
    doc_path.write_bytes(b"garbage")
    config = _make_config()

    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.side_effect = RuntimeError("unsupported format")
        with pytest.raises(AdapterError, match="unsupported format"):
            _run(doc_path, config)


# Case 7 — raw_file_path equals the input path
def test_raw_file_path_equals_input(tmp_path):
    doc_path = tmp_path / "notes.docx"
    doc_path.write_bytes(b"fake content")
    config = _make_config()

    result = _make_convert_result(text_content="Notes content.", title="Notes")
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        item = _run(doc_path, config)

    assert item.raw_file_path == doc_path


# Case 8 — extra_metadata contains original_format with lowercase extension
def test_extra_metadata_original_format(tmp_path):
    doc_path = tmp_path / "slides.PPTX"
    doc_path.write_bytes(b"fake content")
    config = _make_config()

    result = _make_convert_result(text_content="Slide text.", title="Slides")
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        item = _run(doc_path, config)

    assert item.extra_metadata["original_format"] == ".pptx"


# Case 9 — file_mtime is a UTC datetime
def test_file_mtime_is_utc_datetime(tmp_path):
    doc_path = tmp_path / "doc.docx"
    doc_path.write_bytes(b"fake content")
    config = _make_config()

    result = _make_convert_result(text_content="Content.", title="Doc")
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        item = _run(doc_path, config)

    assert isinstance(item.file_mtime, datetime)
    assert item.file_mtime.tzinfo == timezone.utc


# Case 10 — raw_id matches SRC-YYYYMMDD-HHmmss pattern
def test_raw_id_format(tmp_path):
    doc_path = tmp_path / "doc.xlsx"
    doc_path.write_bytes(b"fake content")
    config = _make_config()

    result = _make_convert_result(text_content="Spreadsheet data.", title="Data")
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        item = _run(doc_path, config)

    assert re.match(r"SRC-\d{8}-\d{6}", item.raw_id)


# Case 11 — EPUB format handled correctly
def test_epub_format(tmp_path):
    doc_path = tmp_path / "book.epub"
    doc_path.write_bytes(b"fake epub content")
    config = _make_config()

    result = _make_convert_result(text_content="Chapter one text.", title="My Book")
    with patch("markitdown.MarkItDown") as MockMD:
        MockMD.return_value.convert.return_value = result
        item = _run(doc_path, config)

    assert item.source_type == SourceType.ARTICLE
    assert item.extra_metadata["original_format"] == ".epub"
    assert item.title == "My Book"
