# Spec: PDFAdapter

slug: pdf-adapter
layer: adapters
phase: 1
arch_section: §1 (SOURCE ADAPTERS LAYER), §2 (Project Structure — agent/adapters/pdf_adapter.py)

---

## Problem statement

The inbox may receive PDF files in any inbox subfolder (e.g. `00_INBOX/articles/`,
`00_INBOX/trainings/`, `00_INBOX/external_data/`). `PDFAdapter` must extract all
text content page-by-page, pull available PDF metadata (title, author, creation date),
and return a `NormalizedItem` ready for the pipeline.

No LLM is involved. No vault writes occur here. All extraction is local via `pymupdf`.

---

## Module contract

```
Input:  Path — a .pdf file in any inbox subfolder
        AgentConfig — no PDF-specific keys consumed (reserved for future config)

Output: NormalizedItem
          raw_id:         SRC-YYYYMMDD-HHmmss (UTC) via _generate_raw_id()
          source_type:    SourceType.PDF
          raw_text:       all pages joined with "\n\n---\n\n" separator, stripped
          title:          doc.metadata["title"] → path.stem (fallback)
          url:            "" (PDFs carry no canonical URL)
          author:         doc.metadata["author"] → ""
          language:       "" (language detection is Stage 2 / classifier's job)
          source_date:    parsed from doc.metadata["creationDate"] → None
          file_mtime:     datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
          raw_file_path:  path
          extra_metadata: {"page_count": int, "creator": str, "producer": str}

Raises: AdapterError if:
          - file cannot be read (OSError / PermissionError)
          - PDF is encrypted (doc.is_encrypted is True)
          - PDF is corrupt / cannot be opened by pymupdf
          - all pages yield empty text (nothing to process)
```

---

## Key implementation notes

### pymupdf is synchronous — must wrap in anyio thread pool

`fitz.open()` and page text extraction are fully synchronous (C extension).
To keep `extract()` async and anyio-compatible, run the entire pymupdf block
inside `anyio.to_thread.run_sync()`:

```python
import anyio
import fitz  # pymupdf>=1.24 ships as "fitz" alias

async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
    try:
        result = await anyio.to_thread.run_sync(
            lambda: _extract_pdf(path), cancellable=True
        )
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(f"Unexpected error reading PDF: {exc}", path) from exc
    ...
```

All `fitz` calls live in the synchronous helper `_extract_pdf(path)` which
raises `AdapterError` directly (it has no `await`).

### PDF open and encrypted check

```python
def _extract_pdf(path: Path) -> tuple[str, dict]:
    try:
        doc = fitz.open(str(path))
    except fitz.FileDataError as exc:
        raise AdapterError(f"Corrupt or unreadable PDF: {exc}", path) from exc
    except Exception as exc:
        raise AdapterError(f"Failed to open PDF: {exc}", path) from exc

    if doc.is_encrypted:
        raise AdapterError("PDF is encrypted — cannot extract text", path)
    ...
```

Use `fitz.open(str(path))` (string, not Path) for cross-platform compatibility.

### Page-by-page text extraction

```python
    pages: list[str] = []
    for page in doc:
        text = page.get_text("text").strip()
        if text:
            pages.append(text)

    raw_text = "\n\n---\n\n".join(pages)
    if not raw_text.strip():
        raise AdapterError("PDF contains no extractable text", path)
```

Empty pages are silently skipped; if all pages are empty → `AdapterError`.

### Metadata extraction

```python
    meta = doc.metadata  # dict with keys: title, author, subject, keywords,
                         # creator, producer, creationDate, modDate

    title: str = (meta.get("title") or "").strip() or path.stem
    author: str = (meta.get("author") or "").strip()
    creator: str = (meta.get("creator") or "").strip()
    producer: str = (meta.get("producer") or "").strip()
    page_count: int = doc.page_count
    source_date = _parse_pdf_date(meta.get("creationDate") or "")
```

### PDF date parsing

PDF `creationDate` is in the format `D:YYYYMMDDHHmmss[Z|+HH'mm'|-HH'mm']`,
e.g. `D:20240115143022+02'00'` or `D:20240115000000Z` or just `D:20240115`.

```python
import re
from datetime import date

_PDF_DATE_RE = re.compile(r"^D:(\d{4})(\d{2})(\d{2})")

def _parse_pdf_date(raw: str) -> date | None:
    """Parse PDF metadata date string → date, or None on failure."""
    m = _PDF_DATE_RE.match(raw.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
```

Only the date portion is extracted; time and timezone info are discarded
(pipeline uses `source_date` as a `date` field, not `datetime`).

### AgentConfig dependency

No PDF-specific config keys consumed in Phase 1. Use `getattr(config, ...)` with
defaults if any are added later. The `path` parameter is always caller-provided.

### file_mtime

Must be set from `path.stat().st_mtime` in the `extract()` async method (not inside
`_extract_pdf`), after the thread call returns:

```python
    file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
```

### Error handling summary

| Condition | Raise |
|---|---|
| `OSError` / `PermissionError` opening file | `AdapterError(str(exc), path)` |
| `fitz.FileDataError` (corrupt PDF) | `AdapterError("Corrupt or unreadable PDF: ...", path)` |
| `doc.is_encrypted` | `AdapterError("PDF is encrypted — cannot extract text", path)` |
| All pages yield empty text | `AdapterError("PDF contains no extractable text", path)` |
| Any other unexpected exception from fitz | `AdapterError("Unexpected error reading PDF: ...", path)` |

---

## Data model changes

None. `SourceType.PDF = "pdf"` already exists in `models.py`.
`NormalizedItem` is unchanged.

---

## LLM prompt file needed

None. This adapter performs no LLM calls.

---

## Tests required

### Unit: `tests/unit/test_pdf_adapter.py`

All `fitz.open` calls patched via `unittest.mock.patch("fitz.open")`.

| # | Case | Expected |
|---|---|---|
| 1 | Normal multi-page PDF with title + author metadata | `NormalizedItem` with `source_type=PDF`, non-empty `raw_text`, title/author populated, `page_count` in `extra_metadata` |
| 2 | Pages joined with `\n\n---\n\n` separator | `raw_text` contains the separator between page texts |
| 3 | PDF metadata has no title → fallback to `path.stem` | `title == path.stem` |
| 4 | PDF metadata has `creationDate` in `D:YYYYMMDD...` format | `source_date` is a `date` matching the date portion |
| 5 | PDF `creationDate` is empty / missing → `source_date = None` | `source_date is None` |
| 6 | PDF `creationDate` has malformed value | `source_date is None` (no exception) |
| 7 | Encrypted PDF (`doc.is_encrypted = True`) | `AdapterError` raised with "encrypted" in message |
| 8 | `fitz.open` raises `fitz.FileDataError` (corrupt) | `AdapterError` raised with "Corrupt" in message |
| 9 | All pages return empty text | `AdapterError("PDF contains no extractable text", path)` |
| 10 | Empty pages interspersed with non-empty pages | Empty pages skipped; non-empty pages joined correctly |
| 11 | `file_mtime` set from `path.stat().st_mtime` | `file_mtime` is a UTC `datetime` |
| 12 | `raw_file_path` is the input `Path` | `raw_file_path == path` |
| 13 | `extra_metadata` contains `page_count`, `creator`, `producer` | All three keys present |
| 14 | `raw_id` matches `SRC-YYYYMMDD-HHmmss` pattern | `re.match(r"SRC-\d{8}-\d{6}", item.raw_id)` |

### Integration: `tests/integration/test_pipeline_pdf.py`

Referenced in TRACKER.md. Uses `tests/fixtures/sample_pdf_extracted.txt` as
reference text for round-trip comparison. Full integration is deferred until
the pipeline stage (`s1_normalize.py`) is implemented.

At minimum, add a fixture: `tests/fixtures/sample_pdf.pdf` — a minimal real PDF
(or generated via `fpdf2` / `reportlab` in the test setup) so the integration
test can run without network access.

---

## Explicitly out of scope

- OCR for image-only / scanned PDFs (no Tesseract or similar in Phase 1)
- PDF form field extraction
- Embedded image extraction
- PDF password decryption (encrypted PDFs raise `AdapterError`)
- Multi-column layout detection or reflow
- Table extraction
- Annotation / comment extraction
- Streaming large PDFs (entire doc loaded into memory)
- PDF/A compliance checking
- Language detection (belongs to Stage 2 classifier)
- LLM-assisted metadata enrichment inside the adapter

---

## Open questions

1. Should `_extract_pdf` be a module-level function or a static method on `PDFAdapter`?
   → Module-level function is preferred (consistent with `web_adapter.py` helpers
   `_fetch_html`, `_read_url_from_shortcut`).

2. Is `fitz.open(str(path))` preferred over `fitz.open(path)` on Windows?
   → Use `str(path)` — pymupdf's C layer is more reliable with string paths
   cross-platform.

3. Should `anyio.to_thread.run_sync(..., cancellable=True)` be used?
   → Yes. `cancellable=True` allows anyio to cancel the thread if the task is
   cancelled, preventing zombie threads on timeout/cancellation.
