# Spec: MarkdownAdapter
slug: markdown-adapter
layer: adapters
phase: 1
arch_section: §2 (Project Structure), §3 (Core Data Models — NormalizedItem), §5 (Pipeline — Stage 1 entry point)

---

## Problem statement

`agent/adapters/markdown_adapter.py` is the simplest concrete adapter in the layer.
It handles `.md` and `.txt` files dropped into `00_INBOX/raw_notes/` (and any other
inbox subfolder containing plain-text notes), converting them into a canonical
`NormalizedItem` without making any LLM calls, network requests, or vault writes.

Its role is twofold:
1. **Production**: process real personal notes and text files from the inbox.
2. **Testing fixture**: because it has no binary dependencies, it is the preferred
   source in integration tests that validate the pipeline end-to-end.

It must honour every cross-cutting constraint in the feature spec:
read-only from disk, `anyio` for async file I/O, no hardcoded paths, and
`AdapterError` on any unrecoverable failure.

---

## Module contract

```
Input:
  extract(path: pathlib.Path, config: AgentConfig) -> NormalizedItem
    path   — absolute Path to a .md or .txt file inside any inbox subfolder
    config — fully validated AgentConfig (vault.root used for path validation only)

Output:
  NormalizedItem
    raw_id         str              "SRC-YYYYMMDD-HHmmss" (UTC, from _generate_raw_id())
    source_type    SourceType       SourceType.NOTE (always)
    raw_text       str              file body, frontmatter stripped; non-empty
    title          str              first "# Heading" in body, else path.stem
    url            str              frontmatter "source_url" or "url" field; "" if absent
    author         str              frontmatter "author" field; "" if absent
    language       str              frontmatter "language" or "lang" field; "" if absent
    source_date    date | None      frontmatter "source_date", "date", or "date_created"
                                    parsed as ISO 8601 date; None if absent/unparseable
    file_mtime     datetime         datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    raw_file_path  Path             the path argument as-is
    extra_metadata dict             all remaining frontmatter keys not mapped above;
                                    empty dict if no frontmatter or no extra keys

Error path:
  AdapterError(message: str, path: Path)
    Raised when:
    - File cannot be read (PermissionError, OSError)
    - File content is empty after stripping frontmatter and whitespace
    Never raised for missing optional frontmatter fields (they silently default).
```

---

## Key implementation notes

### Async file read — anyio
```python
import anyio

async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
    try:
        raw = await anyio.Path(path).read_text(encoding="utf-8")
    except (OSError, PermissionError) as exc:
        raise AdapterError(str(exc), path) from exc
```
Must use `anyio.Path`, not `open()` or `aiofiles`, per project-wide constraint.

### YAML frontmatter parsing
Only parse frontmatter when the file starts with `---\n` (YAML front matter delimiter).
Use `pyyaml` (`import yaml`) which is already in `pyproject.toml` via `config.py`.
Do **not** add `python-frontmatter` as a new dependency.

```python
import yaml

FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)

def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text). Both may be empty."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}   # malformed frontmatter → treat as body-only
    body = text[match.end():]
    return fm if isinstance(fm, dict) else {}, body
```

If the YAML block is malformed or not a dict, silently fall back to treating the
entire file as plain text (no AdapterError — malformed frontmatter is not fatal).

### Title extraction
```python
HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

def _extract_title(body: str, path: Path) -> str:
    m = HEADING_RE.search(body)
    return m.group(1).strip() if m else path.stem
```
Uses the **first** `# Heading` line found in the body (after frontmatter removal).
Falls back to `path.stem` (filename without extension) if no heading exists.

### source_date parsing
```python
from datetime import date

def _parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None
```
Attempt `source_date` → `date` → `date_created` keys (in that order).

### file_mtime
```python
from datetime import datetime, timezone

file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
```
Must be called **after** the file read succeeds (avoids stat on unreadable files).

### Empty body guard
After stripping frontmatter and `str.strip()`, if `body == ""` raise:
```python
raise AdapterError("File is empty after stripping frontmatter", path)
```

### extra_metadata
All frontmatter keys not consumed by the field mapping above are passed through
verbatim in `extra_metadata`. This allows Stage 1 to inspect adapter-specific
supplemental data without breaking the NormalizedItem contract.

### Supported extensions
Accept `.md` and `.txt`. The adapter does NOT enforce this at runtime — the watcher
or Stage 1 is responsible for routing. The adapter processes whatever path it receives.

---

## Data model changes

None. `NormalizedItem`, `SourceType`, and `AgentConfig` are all defined in DONE
modules (`agent/core/models.py`, `agent/core/config.py`). No new models required.

---

## LLM prompt file needed

None. This adapter performs no LLM calls.

---

## Tests required

### unit: `tests/unit/test_markdown_adapter.py`

All tests use `tmp_path` (pytest fixture) to create real files; no mocking of
file I/O. Use `anyio.from_thread.run_sync` / `anyio.run()` to drive async methods.

| # | Test case |
|---|-----------|
| 1 | `.md` file with `# My Title` → `NormalizedItem.title == "My Title"` |
| 2 | `.md` file with no heading → `title == path.stem` |
| 3 | `.txt` file → `source_type == SourceType.NOTE`, title from stem |
| 4 | File with YAML frontmatter → frontmatter stripped from `raw_text`; body content preserved |
| 5 | Frontmatter with `source_url: https://example.com` → `NormalizedItem.url == "https://example.com"` |
| 6 | Frontmatter with `url:` key (alias) → `NormalizedItem.url` populated |
| 7 | Frontmatter with `author: John Doe` → `NormalizedItem.author == "John Doe"` |
| 8 | Frontmatter with `language: ru` → `NormalizedItem.language == "ru"` |
| 9 | Frontmatter with `lang: en` (alias) → `NormalizedItem.language == "en"` |
| 10 | Frontmatter with `source_date: 2025-06-15` → `NormalizedItem.source_date == date(2025, 6, 15)` |
| 11 | Frontmatter with `date:` key (alias) → `source_date` populated |
| 12 | Frontmatter with `date_created:` key (alias) → `source_date` populated |
| 13 | Frontmatter with unparseable date string → `source_date is None` (no error) |
| 14 | Malformed YAML frontmatter block → falls back to full content as `raw_text`; no `AdapterError` |
| 15 | `raw_id` matches regex `^SRC-\d{8}-\d{6}$` |
| 16 | `file_mtime` is a UTC-aware `datetime` |
| 17 | `raw_file_path == path` |
| 18 | `source_type == SourceType.NOTE` |
| 19 | Extra frontmatter keys appear in `extra_metadata`; mapped keys do not |
| 20 | File with only whitespace after frontmatter strip → `AdapterError` raised with correct `path` |
| 21 | Completely empty file → `AdapterError` raised |
| 22 | Unreadable file (chmod 000 on Linux; mocked `OSError` on Windows) → `AdapterError` raised |

### integration: `tests/integration/test_pipeline_markdown.py`

Smoke-test that validates `MarkdownAdapter` cooperates with the NormalizedItem
contract expected by Stage 1. Uses a fixture `.md` file in `tests/fixtures/`.

| # | Test case |
|---|-----------|
| 1 | Load `tests/fixtures/sample_note.md` → `NormalizedItem` fields are non-empty and consistent |
| 2 | `NormalizedItem` produced passes `pydantic` model validation (no `ValidationError`) |

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `.docx`, `.html`, `.pdf` parsing | Handled by dedicated adapters (`teams_adapter`, `web_adapter`, `pdf_adapter`) |
| LLM calls inside the adapter | All LLM work is in pipeline stages §4+ |
| Vault writes | Adapters are read-only from disk |
| `00_INBOX/` path discovery | Watcher / Stage 1 responsibility |
| Routing files to `MarkdownAdapter` by extension | Stage 1 / adapter registry responsibility |
| Phase 2 features (bi-directional links, atom extraction) | Out of scope per TRACKER.md |
| Unique `raw_id` collision resolution | Stage 1 responsibility (see `adapters-base` open question #1) |
| Full round-trip verbatim block parsing | Belongs in `agent/vault/verbatim.py` |

---

## Open questions

1. **Frontmatter in `raw_text`**: Spec strips YAML frontmatter before setting
   `raw_text`. Confirm Stage 1 / downstream stages do not require the frontmatter
   text in `raw_text`. Current assumption: frontmatter fields are surfaced via
   `NormalizedItem` fields and `extra_metadata`; body-only `raw_text` is correct.

2. **`---` delimiter variants**: Some Obsidian notes use `+++` (TOML) or no
   delimiter. Phase 1 scope: support YAML `---` only. If TOML/no-delimiter is
   needed, raise a TRACKER note before building Stage 2.
