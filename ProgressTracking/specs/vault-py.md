# Spec: ObsidianVault
slug: vault-py
layer: vault
phase: 1
arch_section: §8

---

## Problem statement

The pipeline and all vault-layer modules need a single, authoritative class for all
physical I/O against the Obsidian vault. Without it every module would roll its own
file reads, writes, and path arithmetic — producing duplication, inconsistent atomicity,
and unguarded overwrite risks.

`ObsidianVault` provides:
- One canonical constructor that derives every zone path from `root`
- Atomic note writes (`.tmp` → `rename`) so a crash never leaves a half-written file
- Safe index-file management: `ensure_domain_index` creates when absent but **never
  overwrites**; `increment_index_count` touches frontmatter only — the Bases-query body
  is immutable
- Sync-lock detection, log appending, and routing to `to_review` / `to_merge`

Every other module in the vault layer (and all pipeline stages) **must** go through
this class for any file operation.

---

## Module contract

| | Type |
|---|---|
| **Input — constructor** | `root: Path` — absolute path to the vault root on disk |
| **Input — write_note** | `relative_path: str`, `frontmatter: dict`, `body: str` |
| **Input — read_note** | `relative_path: str` |
| **Output — read_note** | `tuple[dict, str]` — `(frontmatter_dict, body)` |
| **Input — archive_file** | `source_path: Path`, `date_created: datetime` |
| **Output — archive_file** | `Path` — absolute path of archived file |
| **Input — append_log** | `record: ProcessingRecord` |
| **Input — ensure_domain_index** | `relative_path: str`, `index_type: str`, `domain: str`, `subdomain: str \| None` |
| **Input — increment_index_count** | `relative_path: str` |
| **Input — move_to_review** | `path: Path`, `reason: str` |
| **Input — move_to_merge** | `path: Path`, `merge_result: str` |

No Pydantic output models — the class works at the filesystem level.
Callers hold `ProcessingRecord` / `DomainIndexEntry` models imported from
`agent.core.models`.

---

## Key implementation notes

### Constructor — zone paths
All zone `Path` attributes are set in `__init__` and derived **only** from `root`.
No hardcoded string paths anywhere in the file.

```python
self.root      = root
self.inbox     = root / "00_INBOX"
self.processing = root / "01_PROCESSING"
self.knowledge = root / "02_KNOWLEDGE"
self.projects  = root / "03_PROJECTS"
self.personal  = root / "04_PERSONAL"
self.archive   = root / "05_ARCHIVE"
self.atoms     = root / "06_ATOMS"
self.references = root / "REFERENCES"
self.meta      = root / "_AI_META"
self.merge_dir  = self.processing / "to_merge"
self.review_dir = self.processing / "to_review"
```

### `write_note` — atomic write
1. Resolve `target = self.root / relative_path`
2. `target.parent.mkdir(parents=True, exist_ok=True)`
3. Serialize: `"---\n" + yaml.dump(frontmatter, allow_unicode=True) + "---\n\n" + body`
4. Write to `tmp = target.with_suffix(".tmp")`
5. `tmp.rename(target)` — atomic on POSIX; on Windows this uses `os.replace` internally
   which is close-enough atomic within the same filesystem

**`with_suffix(".tmp")` edge case**: if `relative_path` is `foo/_index.md` the tmp file
is `foo/_index.tmp` — acceptable; it stays in the same directory.

### `read_note` — inline YAML split
```python
content = (self.root / relative_path).read_text(encoding="utf-8")
if content.startswith("---"):
    _, fm_str, body = content.split("---", 2)
    return yaml.safe_load(fm_str), body.lstrip()
return {}, content
```
`yaml.safe_load` returns `None` for empty blocks — callers should treat `None` as `{}`.

### `archive_file`
- Bucket path: `05_ARCHIVE/{year}/{month:02d}/`
- Dest filename: `{YYYYMMDD}-{source_path.name}`
- Move via `shutil.move(str(source_path), str(dest))`
- `bucket.mkdir(parents=True, exist_ok=True)` before move

### `sync_in_progress`
```python
return any(self.root.glob(".sync-*")) or (self.root / ".syncing").exists()
```

### `append_log`
- Target: `self.meta / "processing-log.md"`
- Append mode (`"a"`) — never overwrite
- Creates parent dirs if absent (`log_path.parent.mkdir(parents=True, exist_ok=True)`)
- Format matches arch §8 exactly (timestamp, raw_id, input/output paths, domain_path,
  confidence, verbatim_count, provider, model, time, errors if non-empty)

### `get_domain_index_path`
```python
def get_domain_index_path(self, domain: str, subdomain: str | None = None) -> str:
    if subdomain:
        return f"02_KNOWLEDGE/{domain}/{subdomain}/_index.md"
    return f"02_KNOWLEDGE/{domain}/_index.md"
```

### `ensure_domain_index` — never overwrites
```python
target = self.root / relative_path
if target.exists():
    return          # guard: do not overwrite
```
- After the guard: lazy-import `render_template` from `agent.vault.templates` to avoid
  circular import at module load time
- Build `DomainIndexEntry` with `note_count=0`, `last_updated=today_iso`, `tags=[f"index/{index_type}"]`
- `model_dump(exclude_none=True)` for frontmatter dict
- `template_name = "subdomain_index.md" if subdomain else "domain_index.md"`
- `body = render_template(template_name, {"domain": domain, "subdomain": subdomain, "domain_path": ...})`
- Delegate to `self.write_note(relative_path, frontmatter, body)`

### `increment_index_count` — frontmatter-only mutation
```python
target = self.root / relative_path
if not target.exists():
    return          # graceful noop — do not raise
fm, body = self.read_note(relative_path)
fm["note_count"] = fm.get("note_count", 0) + 1
fm["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
self.write_note(relative_path, fm, body)  # body passed through unchanged
```
**Critical**: `body` is **not** inspected, mutated, or re-serialised beyond passing it
straight to `write_note`. The Bases query blocks in `_index.md` bodies must never change.

### `move_to_review` / `move_to_merge`
Both use `shutil.move`. Destination dirs created with `mkdir(parents=True, exist_ok=True)`.
The `reason` / `merge_result` parameter is accepted for future sidecar logging but is
not written to disk in Phase 1.

```python
def move_to_review(self, path: Path, reason: str = "") -> Path:
    self.review_dir.mkdir(parents=True, exist_ok=True)
    dest = self.review_dir / path.name
    shutil.move(str(path), str(dest))
    return dest

def move_to_merge(self, path: Path, merge_result: str = "") -> Path:
    self.merge_dir.mkdir(parents=True, exist_ok=True)
    dest = self.merge_dir / path.name
    shutil.move(str(path), str(dest))
    return dest
```

### Imports
```python
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent.core.models import DomainIndexEntry, ProcessingRecord
```
`render_template` is imported **lazily inside** `ensure_domain_index` only.

---

## Data model changes

None. `DomainIndexEntry` and `ProcessingRecord` are already in `agent/core/models.py`
(DONE). No new models needed for `vault.py`.

---

## LLM prompt file needed

None. `vault.py` performs no LLM calls.

---

## Tests required

### unit: `tests/unit/test_vault.py`

All tests use `tmp_path` (pytest fixture) as vault root — no real vault on disk.

| Test case | What it verifies |
|---|---|
| `test_zone_paths_derived_from_root` | All 11 zone attributes equal `root / expected_suffix`; no hardcoded strings |
| `test_write_note_creates_file` | After `write_note`, file at resolved path contains frontmatter + body |
| `test_write_note_frontmatter_serialized` | YAML block present, key round-trips via `yaml.safe_load` |
| `test_write_note_atomic_tmp_removed` | `.tmp` file does not exist after successful write |
| `test_write_note_creates_parent_dirs` | `nested/path/note.md` — parent dirs created |
| `test_read_note_with_frontmatter` | Returns correct `(dict, str)` for valid YAML-frontmatter file |
| `test_read_note_no_frontmatter` | Returns `({}, full_content)` for file without `---` |
| `test_read_note_empty_frontmatter` | `yaml.safe_load("")` → `None`; caller receives `None` (documented) |
| `test_archive_file_moves_to_bucket` | File exists at `05_ARCHIVE/{year}/{month:02d}/YYYYMMDD-name.md` |
| `test_archive_file_source_removed` | Original path no longer exists after archival |
| `test_archive_file_bucket_created` | Bucket dir created when absent |
| `test_sync_in_progress_no_lock` | Returns `False` when no lock files present |
| `test_sync_in_progress_sync_star` | Returns `True` when `.sync-abc` present |
| `test_sync_in_progress_syncing` | Returns `True` when `.syncing` present |
| `test_append_log_creates_file` | First append creates `_AI_META/processing-log.md` |
| `test_append_log_appends_not_overwrites` | Second append extends file, first entry still present |
| `test_append_log_format_contains_raw_id` | Log entry contains `record.raw_id` |
| `test_get_domain_index_path_domain_only` | Returns `"02_KNOWLEDGE/wellbeing/_index.md"` |
| `test_get_domain_index_path_with_subdomain` | Returns `"02_KNOWLEDGE/wellbeing/health/_index.md"` |
| `test_ensure_domain_index_creates_when_absent` | File created; frontmatter has `note_count: 0` and correct tag |
| `test_ensure_domain_index_never_overwrites` | Pre-existing file content unchanged after call |
| `test_ensure_domain_index_subdomain_uses_subdomain_template` | `render_template` called with `"subdomain_index.md"` |
| `test_ensure_domain_index_domain_uses_domain_template` | `render_template` called with `"domain_index.md"` |
| `test_increment_index_count_increments` | `note_count` goes from 0 → 1 |
| `test_increment_index_count_updates_last_updated` | `last_updated` field changes to today's ISO date |
| `test_increment_index_count_body_unchanged` | Body string (Bases query content) is byte-identical after increment |
| `test_increment_index_count_noop_when_absent` | No exception raised when target does not exist |
| `test_move_to_review_moves_file` | File present in `01_PROCESSING/to_review/`; source gone |
| `test_move_to_review_creates_dir` | `to_review/` created when absent |
| `test_move_to_merge_moves_file` | File present in `01_PROCESSING/to_merge/`; source gone |

`render_template` should be patched via `unittest.mock.patch("agent.vault.templates.render_template")` in the `ensure_domain_index` tests to avoid pulling in the templates module before it is implemented.

### integration

Not applicable for this module in isolation. Integration coverage is provided by
`tests/integration/test_pipeline_index.py` (★) once stages `s6a_write` and
`s6b_index_update` are built.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Async file I/O (`anyio.Path`) | `vault.py` runs synchronously; async wrapper can be added later without changing the public interface |
| Conflict resolution on `move_to_review` filename collision | Phase 1 keeps it simple: overwrite; dedup is a separate concern |
| Sidecar `.meta.json` writes in `move_to_review` / `move_to_merge` | Phase 1 — reason param accepted but not persisted |
| `06_ATOMS/` path support | Phase 2 |
| Any LLM calls | This module is pure I/O |
| `note.py` parse logic (`python-frontmatter`) | That is `note-py`'s responsibility |

---

## Open questions

None. Architecture §8 provides exact method signatures and the feature spec resolves
all ambiguities about `increment_index_count` (also called `update_domain_index` in
the TRACKER item description — same method).
