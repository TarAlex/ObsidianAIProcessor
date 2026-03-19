# Spec: Index Updater Task
slug: index-updater
layer: tasks
phase: 1
arch_section: §13

## Problem statement

`_index.md` frontmatter fields `note_count` and `last_updated` can drift from
reality whenever notes are manually added, moved, deleted, or when the pipeline's
incremental `increment_index_count()` call is skipped due to an error. A daily
rebuild-from-scratch task corrects any such drift without human intervention.

This module is the authoritative source-of-truth recount for all domain and
subdomain indexes. It replaces whatever counts exist with freshly computed ones,
then writes only if a change is detected (to avoid spurious vault activity).

---

## Module contract

```
Input:  vault: ObsidianVault  (all vault I/O goes through this)
Output: None  (side effects: frontmatter of _index.md files may be updated)
```

Public API surface (one async function):

```python
async def rebuild_all_counts(vault: ObsidianVault) -> None: ...
```

Called by:
- `agent/core/scheduler.py` — daily APScheduler job
- `agent/main.py` — `rebuild-indexes` CLI command

No `AgentConfig` parameter — the task needs only the vault root, not config
settings. (Contrast with `outdated_review.run()` which needs
`verbatim_high_risk_age` from config.)

---

## Key implementation notes

### Algorithm (two-pass, rebuild-from-scratch)

**Pass 1 — count notes**

Walk `vault.knowledge.rglob("*.md")`; skip `_index.md` files.
For each note:
1. Read frontmatter via `vault.read_note(rel)`. Skip on any exception (corrupt /
   unreadable file).
2. Extract `domain_path` from frontmatter. Skip notes without it.
3. Accumulate:
   - `counts[domain_path] += 1`
   - `last_modified[domain_path] = max(last_modified[domain_path], mtime)`
     where `mtime = fm.get("date_modified", "")`.
4. Roll up to domain level:
   - `domain = domain_path.split("/")[0]`
   - `counts[domain] += 1`
   - `last_modified[domain] = max(last_modified[domain], mtime)`

`last_modified` comparison uses ISO date string lexicographic order
(`"2025-01-02" > "2025-01-01"` holds). Missing `date_modified` → empty string
(never beats an existing date).

**Pass 2 — update indexes**

Walk `vault.knowledge.rglob("_index.md")`.
For each index:
1. Read frontmatter + body via `vault.read_note(rel)`. Skip on exception.
2. Determine lookup key:
   - `index_type == "subdomain"` → `key = f"{fm['domain']}/{fm['subdomain']}"`
   - `index_type == "domain"` → `key = fm["domain"]`
   - Any other value → skip (unknown index type; do not corrupt).
3. Compute:
   - `new_count = counts.get(key, 0)` — 0 if no notes tagged to this domain
   - `new_mtime = last_modified.get(key, date.today().isoformat())`
4. **Write-only-if-changed**: if `fm.get("note_count") != new_count` OR
   `fm.get("last_updated") != new_mtime`:
   - `fm["note_count"] = new_count`
   - `fm["last_updated"] = new_mtime`
   - `vault.write_note(rel, fm, body)` — body passed through unchanged
   - `logger.debug("index.updated rel=%s count=%d", rel, new_count)`

Body (Obsidian Bases query blocks) is **never touched** — pass the original
`body` string unmodified to `write_note()`.

### Logging events (INFO level unless noted)

| Event constant | Level | Meaning |
|---|---|---|
| `"index.rebuild.started"` | INFO | Entry point called |
| `"index.updated rel=... count=..."` | DEBUG | Single index written |
| `"index.rebuild.complete indexes_written=N"` | INFO | Run finished |

### Idempotency

Rebuild-from-scratch guarantees idempotency: re-running on the same vault
produces identical frontmatter. The write-only-if-changed guard prevents
redundant vault activity on a second run.

### Sync-safety

The task does NOT acquire the sync lock — it is a read-mostly operation and
writes are atomic (vault.write_note uses `.tmp` + `os.replace`). The scheduler
already avoids running during active Obsidian Sync lock
(`vault.sync_in_progress()` guard lives in `scheduler.py`).

### anyio

The entry point is `async def`. The implementation uses only synchronous I/O
(`vault.read_note` / `vault.write_note` are synchronous) wrapped in an `async
def` to fit the APScheduler async job contract. No `asyncio.run()` inside this
module. Do not call `anyio.to_thread.run_sync` unless profiling shows the walk is
a bottleneck (it won't be in Phase 1 vault sizes).

---

## Data model changes

None. Uses existing `DomainIndexEntry` model (defined in `agent/core/models.py`)
only for reference — the frontmatter dict is read and written directly via
`vault.read_note` / `vault.write_note`, matching the ARCH §13 reference
implementation. No new Pydantic models required.

---

## LLM prompt file needed

None. This task is purely structural; no LLM calls.

---

## Tests required

### unit: `tests/unit/test_index_updater.py`

All tests use a fake vault tree (tmp_path fixture). Do **not** use a real vault.

| # | Case | What to assert |
|---|---|---|
| 1 | **basic subdomain count** | 2 notes with `domain_path: professional_dev/ai_tools` → subdomain index gets `note_count: 2` |
| 2 | **domain rollup** | same 2 notes → domain index `professional_dev` gets `note_count: 2` |
| 3 | **corrects inflated count** | subdomain index pre-seeded with `note_count: 99` → after rebuild it is `2` |
| 4 | **no-write when unchanged** | run twice; `vault.write_note` called only on first run (use mock / spy) |
| 5 | **skips notes without domain_path** | note missing `domain_path` key not counted |
| 6 | **skips unreadable notes** | corrupt note (raises `Exception` on read) → no crash, rest of vault processed |
| 7 | **empty knowledge dir** | no notes → all indexes get `note_count: 0` |
| 8 | **unknown index_type skipped** | `_index.md` with `index_type: something_else` → not written |
| 9 | **last_updated set to max date_modified** | two notes, dates `2025-01-01` and `2025-06-15` → index `last_updated: 2025-06-15` |
| 10 | **body preserved** | existing index body containing Bases query block is byte-for-byte identical after rebuild |

### integration: `tests/integration/test_pipeline_index.py`

Requires a real (tmp_path) vault tree with note fixtures.

| # | Case | What to assert |
|---|---|---|
| 1 | **three notes → count 3** | Write 3 notes to `professional_dev/ai_tools/`; run `rebuild_all_counts`; verify `note_count: 3` in both subdomain and domain `_index.md` |
| 2 | **multi-domain isolation** | 2 notes in `professional_dev/ai_tools`, 1 in `mindset/resilience`; verify each domain/subdomain gets correct independent count |

---

## Explicitly out of scope

- Modifying note bodies — only `note_count` and `last_updated` frontmatter keys
  are touched; Bases query block bodies are passed through unchanged.
- Counting notes outside `02_KNOWLEDGE/` (inbox, processing, archive, atoms).
- Creating missing `_index.md` files — that is `ensure_domain_index()`'s job
  (called by `s6b_index_update.py`). If an index doesn't exist, skip it.
- Delta / incremental counting (counts[key] += delta) — always rebuild from
  scratch for correctness.
- LLM calls of any kind.
- Phase 2 features (06_ATOMS counting, MOC atom-level content).
- Config parameter — no `AgentConfig` needed; vault root is sufficient.

---

## Open questions

None. ARCH §13 provides a complete reference implementation. All edge cases
(missing `domain_path`, unknown `index_type`, corrupt notes) are covered above.
