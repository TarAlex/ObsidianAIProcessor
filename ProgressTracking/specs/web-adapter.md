# Spec: WebAdapter

slug: web-adapter
layer: adapters
phase: 1
arch_section: §1 (SOURCE ADAPTERS LAYER), §2 (Project Structure — agent/adapters/web_adapter.py)

---

## Problem statement

The inbox may receive web articles in two forms:
- **`.url` files** (Windows Internet Shortcut) or **`.webloc` files** (macOS) — contain a URL that must be fetched
- **`.html` / `.htm` files** — pre-downloaded pages to be converted offline

`WebAdapter` must fetch or read the HTML, convert it to clean markdown, extract
available metadata (title, author, publication date, canonical URL, language),
and return a `NormalizedItem` ready for the pipeline.

No LLM is involved. No vault writes occur here.

**Shared helpers:** `html_to_article_item()` and `fetch_url_article_item()` in the same
module build `NormalizedItem` (ARTICLE) from HTML or from a fetched URL. **`MarkdownAdapter`**
uses `fetch_url_article_item` for Obsidian-style URL-clip `.md` files so behavior stays
aligned with `.url` / HTML handling.

---

## Module contract

```
Input:  Path — one of {.url, .webloc, .html, .htm} in the inbox
        AgentConfig — provides fetch_timeout_s (default: 30)

Output: NormalizedItem
          raw_id:         SRC-YYYYMMDD-HHmmss (UTC)
          source_type:    SourceType.ARTICLE
          raw_text:       markdown body (markdownify output, stripped)
          title:          og:title → <title> → first <h1> → path.stem
          url:            canonical URL (og:url → fetched/source URL → "")
          author:         meta[name=author] → meta[property=article:author] → ""
          language:       <html lang=...> → meta[http-equiv=content-language] → ""
          source_date:    article:published_time → meta[name=date] → None
          file_mtime:     datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
          raw_file_path:  path
          extra_metadata: {"fetch_url": str, "http_status": int | None}

Raises: AdapterError if:
          - file cannot be read / URL cannot be parsed
          - network fetch fails (httpx error, non-2xx status)
          - resulting markdown body is empty after stripping
```

---

## Key implementation notes

### File dispatch

```python
_SUPPORTED_SUFFIXES = frozenset({".url", ".webloc", ".html", ".htm"})

async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
    suffix = path.suffix.lower()
    if suffix in {".url", ".webloc"}:
        url = await _read_url_from_shortcut(path)
        html, http_status = await _fetch_html(url, config)
    elif suffix in {".html", ".htm"}:
        html = await anyio.Path(path).read_text(encoding="utf-8", errors="replace")
        url = ""
        http_status = None
    else:
        raise AdapterError(f"Unsupported suffix: {suffix}", path)
```

### URL shortcut parsing

**Windows `.url`** (INI-style):
```
[InternetShortcut]
URL=https://example.com/article
```
Parse with `configparser.ConfigParser`; read `[InternetShortcut] URL`.

**macOS `.webloc`** (XML plist):
```xml
<plist><dict><key>URL</key><string>https://…</string></dict></plist>
```
Parse with stdlib `plistlib.loads()`.

Raise `AdapterError` if the key is missing or the value is not a non-empty string.

### HTTP fetch

```python
async def _fetch_html(url: str, config: AgentConfig) -> tuple[str, int]:
    timeout = getattr(config, "fetch_timeout_s", 30)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        response = await client.get(url, headers={"User-Agent": "obsidian-agent/1.0"})
    if not response.is_success:
        raise AdapterError(f"HTTP {response.status_code} for {url}", Path(url))
    return response.text, response.status_code
```

`httpx.AsyncClient` is used with `anyio`-compatible async context (httpx uses
`anyio` internally since ≥0.23). No explicit `anyio.from_thread` needed.

### HTML metadata extraction

Use stdlib `html.parser.HTMLParser` (zero extra deps) to walk the raw HTML once
and collect:

| Target field | HTML sources (priority order) |
|---|---|
| `title` | `<meta property="og:title">` → `<title>` → first `<h1>` → `path.stem` |
| `url` | `<meta property="og:url">` → fetched URL → `""` |
| `author` | `<meta name="author">` → `<meta property="article:author">` → `""` |
| `source_date` | `<meta property="article:published_time">` → `<meta name="date">` → `None` |
| `language` | `<html lang="...">` → `<meta http-equiv="content-language">` → `""` |

Parse `source_date` via `datetime.fromisoformat()` (strips timezone suffix if
needed); fall back gracefully — `None` is acceptable.

Write a private `_MetaExtractor(HTMLParser)` class inside the module. Keep it
under ~100 lines.

### HTML → Markdown conversion

```python
from markdownify import markdownify as md

markdown_body = md(html, heading_style="ATX", strip=["script", "style", "nav",
                                                       "footer", "header", "aside"])
```

Strip leading/trailing whitespace and collapse runs of 3+ blank lines to 2.
If the resulting body is empty after stripping, raise `AdapterError`.

### AgentConfig dependency

`WebAdapter` reads one config attribute: `fetch_timeout_s: int = 30`.
The `config.py` spec must add this key. Until then, use `getattr(config,
"fetch_timeout_s", 30)` so the adapter degrades gracefully.

### Error handling

- `httpx.TimeoutException` → `AdapterError("Fetch timed out", path)`
- `httpx.RequestError` (network unreachable, DNS failure, etc.) → `AdapterError`
- Non-2xx HTTP status → `AdapterError(f"HTTP {status}", path)`
- `OSError` / `PermissionError` reading local file → `AdapterError`
- Empty markdown body after conversion → `AdapterError("Empty content after conversion", path)`

---

## Data model changes

None. `NormalizedItem` and `SourceType.ARTICLE` already exist in `models.py`.

`AgentConfig` needs `fetch_timeout_s: int = 30` added — flag to `config.py` spec author.

---

## LLM prompt file needed

None. This adapter performs no LLM calls.

---

## Tests required

### Unit: `tests/unit/test_web_adapter.py`

All network calls mocked via `respx` (httpx mock library) or `unittest.mock.AsyncMock`.

| # | Case | Expected |
|---|---|---|
| 1 | `.url` file with valid `[InternetShortcut] URL=...` → fetch returns 200 HTML | `NormalizedItem` with `source_type=ARTICLE`, non-empty `raw_text` |
| 2 | `.html` file on disk → no network call | `NormalizedItem` from local HTML, `http_status=None` in `extra_metadata` |
| 3 | `.htm` extension → treated same as `.html` | as above |
| 4 | `.webloc` file with valid XML plist URL | URL extracted, fetch mocked, `NormalizedItem` returned |
| 5 | HTML with `og:title`, `og:url`, `article:published_time`, `author` meta | All fields populated in `NormalizedItem` |
| 6 | HTML missing all meta → fallback chain | `title=path.stem`, `url=""`, `author=""`, `source_date=None` |
| 7 | HTTP 404 response | `AdapterError` raised |
| 8 | `httpx.TimeoutException` | `AdapterError` raised |
| 9 | `.url` file missing `URL` key | `AdapterError` raised |
| 10 | HTML that markdownifies to empty string | `AdapterError("Empty content after conversion", path)` |
| 11 | `.url` file read → URL has redirect (httpx `follow_redirects=True`) | Follows; `NormalizedItem` returned |
| 12 | `config.fetch_timeout_s` respected in httpx client kwargs | Verified via mock |

### Integration

Not applicable for Phase 1 (no live network calls in CI).
`tests/fixtures/sample_article.html` should be added (referenced in TRACKER.md fixtures).

---

## Explicitly out of scope

- JavaScript-rendered pages (SPAs) — no headless browser; raw HTML only
- Authentication / cookies / session management
- Paywall bypass or rate-limit handling
- RSS/Atom feed parsing
- Automatic language detection via LLM or langdetect
- Content cleaning beyond markdownify strip list
- Caching of fetched HTML
- Retry logic for transient failures (out of scope for this adapter)
- Teams adapter (separate module)

---

## Open questions

1. Should `fetch_timeout_s` be nested under a `web:` config section or flat at
   the root of `AgentConfig`? Flat is simpler given current config spec direction.
2. Is `respx` acceptable as a dev-only test dependency, or should we use
   `unittest.mock` + `httpx.MockTransport`? (Either works; `respx` is cleaner.)
   → Recommend adding `respx>=0.20` to `[project.optional-dependencies] dev`.
