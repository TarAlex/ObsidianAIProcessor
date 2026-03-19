# Spec: archive.py
slug: archive-py
layer: vault
phase: 1
arch_section: §6 Stage 7, §8 (ObsidianVault.archive_file)

## Problem statement

Stage 7 of the pipeline must move each processed inbox file out of `00_INBOX/`
(or `01_PROCESSING/`) into the archival zone `05_ARCHIVE/YYYY/MM/` so the
inbox stays clean and files are never silently lost.

`vault.py` already provides the low-level primitive `archive_file(source_path,
date_created)`.  `archive.py` is the thin Stage-7 facade that:

1. Derives the correct `date_created` from a `NormalizedItem` (falling back to
   `datetime.now()` when `source_date` is absent).
2. Offers a lower-level entry point for callers that already hold a bare `Path`
   + a reference `datetime` (used by `s7_archive.py` and tests).
3. Keeps all file I/O strictly inside `ObsidianVault` — no direct `shutil` or
   `Path` writes in this module.

---

## Module contract

```
Input:
  archive_item(vault: ObsidianVault, item: NormalizedItem) -> Path
    - vault   : live ObsidianVault instance (root already set)
    - item    : NormalizedItem with .raw_file_path (Path) and
                .source_date (date | None)

  archive_raw(vault: ObsidianVault, path: Path, date_ref: datetime) -> Path
    - vault    : live ObsidianVault instance
    - path     : absolute Path of the file to archive
    - date_ref : datetime used to compute YYYY/MM bucket + filename prefix

Output:
  Path — absolute path of the file at its new location inside
         05_ARCHIVE/{year}/{month:02d}/{YYYYMMDD}-{original_name}
```

---

## Key implementation notes

### 1 — `archive_item` (high-level)

```python
def archive_item(vault: ObsidianVault, item: NormalizedItem) -> Path:
    if item.source_date is not None:
        date_ref = datetime.combine(item.source_date, datetime.min.time())
    else:
        date_ref = datetime.now()
    return archive_raw(vault, item.raw_file_path, date_ref)
```

- `item.source_date` is `date | None` (models.py); must be promoted to
  `datetime` before passing to `vault.archive_file`.
- Uses `datetime.combine(..., datetime.min.time())` — zero time component,
  no timezone assumption.  The bucket path (`YYYY/MM`) is computed from this.
- Fallback: `datetime.now()` (local time) — acceptable for archival bucket
  placement when source date is unknown.

### 2 — `archive_raw` (lower-level)

```python
def archive_raw(vault: ObsidianVault, path: Path, date_ref: datetime) -> Path:
    return vault.archive_file(path, date_ref)
```

Pure delegation.  No logic of its own.  Exposed separately so `s7_archive.py`
and integration tests can archive arbitrary files without constructing a full
`NormalizedItem`.

### 3 — Destination filename (enforced by vault.archive_file)

`{date_ref.strftime('%Y%m%d')}-{path.name}`

e.g. `20260315-meeting-notes.md` → `05_ARCHIVE/2026/03/20260315-meeting-notes.md`

This is already implemented in `vault.archive_file`; `archive.py` does not
re-implement it.

### 4 — Error propagation

Neither function catches exceptions.  `shutil.move` errors (file not found,
permission denied, cross-device move) propagate to the caller
(`pipeline.py → s7_archive.py`), which logs them in `ProcessingRecord.errors`.

### 5 — No direct file I/O

This module MUST NOT call `shutil`, `os`, or `pathlib` write methods.  All I/O
routes through `vault.archive_file`.

---

## Data model changes

None.  Uses existing `NormalizedItem` (`agent/core/models.py`).

---

## LLM prompt file needed

None.  This module is pure Python logic.

---

## Tests required

### unit: `tests/unit/test_archive.py`

All tests use a tmp-dir vault root (`tmp_path` fixture).

| # | Case | What is verified |
|---|------|-----------------|
| 1 | `archive_item` with `source_date` set | File lands in `05_ARCHIVE/2026/03/20260315-{name}` |
| 2 | `archive_item` with `source_date = None` | File lands in bucket matching `datetime.now()` year/month |
| 3 | `archive_raw` | Delegates correctly; returned path == expected dest |
| 4 | Source file is absent after move | `source_path` no longer exists at original location |
| 5 | Destination filename prefix | Filename starts with `YYYYMMDD-` |
| 6 | Bucket directory created | `05_ARCHIVE/YYYY/MM/` is created if not present |
| 7 | `archive_item` — file with non-ASCII name | Filename preserved with date prefix |

All tests mock or use a real temp vault; no network or LLM calls.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Deduplication before archive | Stage 5 handles duplicates before Stage 7 |
| Logging to `_AI_META/processing-log.md` | Done by `vault.append_log` in `pipeline.py` after Stage 7 returns |
| Cleanup of `.tmp` files | Vault atomic-write pattern handles this upstream |
| Phase 2 atom archival | Phase 2 only |
| Any direct `shutil` / `os` calls | All I/O via `vault.archive_file` |
| Updating `ProcessingRecord.archive_path` | Caller (`s7_archive.py` / `pipeline.py`) responsibility |

---

## Open questions

None.  All design decisions are resolved by the feature spec, vault.py contract,
and existing models.
