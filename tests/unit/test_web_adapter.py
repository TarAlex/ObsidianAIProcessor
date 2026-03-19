"""Unit tests for agent/adapters/web_adapter.py.

All network calls mocked via pytest-httpx (httpx_mock fixture).
File I/O uses pytest's tmp_path fixture for real on-disk files.
Async execution driven via anyio.run() — consistent with the rest of the test suite.
"""
from __future__ import annotations

import plistlib
import re
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import anyio
import httpx
import pytest

from agent.adapters.base import AdapterError
from agent.adapters.web_adapter import WebAdapter
from agent.core.config import AgentConfig, VaultConfig
from agent.core.models import NormalizedItem, SourceType

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_SIMPLE_HTML = """\
<html lang="en">
<head><title>Simple Title</title></head>
<body>
  <h1>Simple Article</h1>
  <p>A paragraph of readable content that will survive markdownify.</p>
</body>
</html>
"""

_RICH_HTML = """\
<html lang="fr">
<head>
  <meta property="og:title" content="OG Article Title" />
  <meta property="og:url" content="https://example.com/og-article" />
  <meta name="author" content="Jane Doe" />
  <meta property="article:published_time" content="2025-06-15T10:00:00+00:00" />
  <title>Title Tag Text</title>
</head>
<body>
  <h1>First H1 Heading</h1>
  <p>Article body content here.</p>
</body>
</html>
"""


def _make_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(vault=VaultConfig(root=str(tmp_path)))


def _run_extract(path: Path, config) -> NormalizedItem:
    """Run WebAdapter.extract synchronously via anyio (no network calls)."""
    return anyio.run(WebAdapter().extract, path, config)


def _run_extract_async(path: Path, config) -> NormalizedItem:
    """Run WebAdapter.extract synchronously via anyio (network calls present)."""
    async def _inner():
        return await WebAdapter().extract(path, config)
    return anyio.run(_inner)


# ---------------------------------------------------------------------------
# Test 1 — .url file with valid [InternetShortcut] URL → 200 HTML → NormalizedItem
# ---------------------------------------------------------------------------

def test_url_file_valid_fetch(tmp_path, httpx_mock):
    url_file = tmp_path / "article.url"
    url_file.write_text("[InternetShortcut]\nURL=https://example.com/article\n", encoding="utf-8")
    config = _make_config(tmp_path)

    httpx_mock.add_response(url="https://example.com/article", text=_SIMPLE_HTML)

    item = _run_extract_async(url_file, config)

    assert item.source_type == SourceType.ARTICLE
    assert item.raw_text.strip()
    assert item.raw_file_path == url_file
    assert item.extra_metadata["http_status"] == 200
    assert re.match(r"^SRC-\d{8}-\d{6}$", item.raw_id)


# ---------------------------------------------------------------------------
# Test 2 — .html file on disk → no network call → NormalizedItem
# ---------------------------------------------------------------------------

def test_html_file_local_no_network(tmp_path):
    html_file = tmp_path / "page.html"
    html_file.write_text(_SIMPLE_HTML, encoding="utf-8")
    config = _make_config(tmp_path)

    item = _run_extract(html_file, config)

    assert item.source_type == SourceType.ARTICLE
    assert item.extra_metadata["http_status"] is None
    assert item.extra_metadata["fetch_url"] == ""
    assert item.raw_file_path == html_file
    assert isinstance(item.file_mtime, datetime)
    assert item.file_mtime.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Test 3 — .htm extension treated identically to .html
# ---------------------------------------------------------------------------

def test_htm_extension_same_as_html(tmp_path):
    htm_file = tmp_path / "page.htm"
    htm_file.write_text(_SIMPLE_HTML, encoding="utf-8")
    config = _make_config(tmp_path)

    item = _run_extract(htm_file, config)

    assert item.source_type == SourceType.ARTICLE
    assert item.extra_metadata["http_status"] is None
    assert item.raw_text.strip()


# ---------------------------------------------------------------------------
# Test 4 — .webloc file with valid XML plist URL → fetch → NormalizedItem
# ---------------------------------------------------------------------------

def test_webloc_file_valid(tmp_path, httpx_mock):
    webloc_file = tmp_path / "article.webloc"
    webloc_file.write_bytes(plistlib.dumps({"URL": "https://mac.example.com/post"}))
    config = _make_config(tmp_path)

    httpx_mock.add_response(url="https://mac.example.com/post", text=_SIMPLE_HTML)

    item = _run_extract_async(webloc_file, config)

    assert item.source_type == SourceType.ARTICLE
    assert item.raw_text.strip()
    assert item.extra_metadata["fetch_url"] == "https://mac.example.com/post"


# ---------------------------------------------------------------------------
# Test 5 — HTML with og:title / og:url / article:published_time / author meta
# ---------------------------------------------------------------------------

def test_rich_meta_all_fields_populated(tmp_path):
    html_file = tmp_path / "rich.html"
    html_file.write_text(_RICH_HTML, encoding="utf-8")
    config = _make_config(tmp_path)

    item = _run_extract(html_file, config)

    assert item.title == "OG Article Title"
    assert item.url == "https://example.com/og-article"
    assert item.author == "Jane Doe"
    assert item.source_date == date(2025, 6, 15)
    assert item.language == "fr"


# ---------------------------------------------------------------------------
# Test 6 — HTML missing all meta → fallback chain applies
# ---------------------------------------------------------------------------

def test_fallback_chain_when_no_meta(tmp_path):
    bare_html = "<html><body><p>Plain content with no metadata at all.</p></body></html>"
    html_file = tmp_path / "bare_page.html"
    html_file.write_text(bare_html, encoding="utf-8")
    config = _make_config(tmp_path)

    item = _run_extract(html_file, config)

    assert item.title == "bare_page"   # path.stem fallback
    assert item.url == ""
    assert item.author == ""
    assert item.source_date is None
    assert item.language == ""


# ---------------------------------------------------------------------------
# Test 7 — HTTP 404 → AdapterError raised
# ---------------------------------------------------------------------------

def test_http_404_raises_adapter_error(tmp_path, httpx_mock):
    url_file = tmp_path / "notfound.url"
    url_file.write_text(
        "[InternetShortcut]\nURL=https://example.com/404page\n", encoding="utf-8"
    )
    config = _make_config(tmp_path)

    httpx_mock.add_response(url="https://example.com/404page", status_code=404, text="Not Found")

    with pytest.raises(AdapterError) as exc_info:
        _run_extract_async(url_file, config)
    assert "404" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 8 — httpx.TimeoutException → AdapterError raised
# ---------------------------------------------------------------------------

def test_timeout_raises_adapter_error(tmp_path, httpx_mock):
    url_file = tmp_path / "slow.url"
    url_file.write_text(
        "[InternetShortcut]\nURL=https://slow.example.com/\n", encoding="utf-8"
    )
    config = _make_config(tmp_path)

    httpx_mock.add_exception(httpx.TimeoutException("connect timeout"))

    with pytest.raises(AdapterError) as exc_info:
        _run_extract_async(url_file, config)
    assert "timed out" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 9 — .url file missing URL key → AdapterError raised
# ---------------------------------------------------------------------------

def test_url_file_missing_url_key_raises(tmp_path):
    url_file = tmp_path / "broken.url"
    url_file.write_text("[InternetShortcut]\nIconIndex=0\nHotKey=0\n", encoding="utf-8")
    config = _make_config(tmp_path)

    with pytest.raises(AdapterError) as exc_info:
        _run_extract(url_file, config)
    assert exc_info.value.path == url_file


# ---------------------------------------------------------------------------
# Test 10 — HTML that markdownifies to empty string → AdapterError
# ---------------------------------------------------------------------------

def test_empty_markdown_after_conversion_raises(tmp_path):
    # markdownify's strip parameter removes tags but keeps text content;
    # truly empty body (no text nodes) produces an empty conversion result.
    empty_html = "<html><head></head><body>   \n   </body></html>"
    html_file = tmp_path / "empty_result.html"
    html_file.write_text(empty_html, encoding="utf-8")
    config = _make_config(tmp_path)

    with pytest.raises(AdapterError) as exc_info:
        _run_extract(html_file, config)
    assert "Empty content after conversion" in str(exc_info.value)
    assert exc_info.value.path == html_file


# ---------------------------------------------------------------------------
# Test 11 — .url file → redirect followed (follow_redirects=True) → NormalizedItem
# ---------------------------------------------------------------------------

def test_url_file_follows_redirect(tmp_path, httpx_mock):
    url_file = tmp_path / "redirect.url"
    url_file.write_text(
        "[InternetShortcut]\nURL=https://old.example.com/post\n", encoding="utf-8"
    )
    config = _make_config(tmp_path)

    httpx_mock.add_response(
        url="https://old.example.com/post",
        status_code=301,
        headers={"Location": "https://new.example.com/post"},
    )
    httpx_mock.add_response(url="https://new.example.com/post", text=_SIMPLE_HTML)

    item = _run_extract_async(url_file, config)

    assert item.source_type == SourceType.ARTICLE
    assert item.raw_text.strip()


# ---------------------------------------------------------------------------
# Test 12 — config.fetch_timeout_s is forwarded to httpx.AsyncClient
# ---------------------------------------------------------------------------

def test_config_fetch_timeout_respected(tmp_path):
    url_file = tmp_path / "timed.url"
    url_file.write_text(
        "[InternetShortcut]\nURL=https://example.com/timed\n", encoding="utf-8"
    )

    captured: dict = {}

    class _MockResponse:
        status_code = 200
        is_success = True
        text = _SIMPLE_HTML

    class _MockAsyncClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            return _MockResponse()

    class _CfgWithTimeout:
        """Duck-type config that carries fetch_timeout_s (not in AgentConfig yet)."""
        fetch_timeout_s = 99
        vault = VaultConfig(root=str(tmp_path))

    async def _run():
        with patch("agent.adapters.web_adapter.httpx.AsyncClient", _MockAsyncClient):
            return await WebAdapter().extract(url_file, _CfgWithTimeout())

    item = anyio.run(_run)
    assert captured.get("timeout") == 99
    assert item.source_type == SourceType.ARTICLE
