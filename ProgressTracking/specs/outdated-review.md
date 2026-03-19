# Spec: Outdated Review Task

slug: outdated-review
layer: tasks
phase: 1
arch_section: §12 Outdated Review Task

---

## Problem statement

The vault accumulates knowledge notes and verbatim blocks over time. Without
periodic review, stale content (past `review_after` dates or aging high-risk
verbatim blocks) remains silently in the vault with no visibility. This task
performs a weekly, fully automated scan and writes a human-readable flag report
to `_AI_META/outdated-review.md`. It never modifies or deletes notes —
human review only.

---

## Module contract

**Entry point:**
```python
async def run(vault: ObsidianVault, config: AgentConfig) -> None
```

- Called by `agent/core/scheduler.py` on the weekly APScheduler cron job
  (`scheduler.outdated_review_day` / `scheduler.outdated_review_hour`).
- May also be triggered on-demand via `agent/main.py` CLI command
  `outdated-review`.

**Input:** `ObsidianVault` + `AgentConfig` (both already constructed by caller)

**Output:** `None` — side effect is writing `_AI_META/outdated-review.md`

**Internal helper (not exported):**
```python
def _write_review_report(
    vault: ObsidianVault,
    stale_notes: list[dict],
    stale_verbatim: list[dict],
) -> None
```

---

## Key implementation notes

### Two-pass scan

Walk `vault.knowledge.rglob("*.md")`; skip any file whose `name == "_index.md"`.

**Pass A — note-level staleness**

For each note, read frontmatter via `vault.read_note(rel)`.
If `frontmatter.get("review_after")` parses as a `date` via
`date.fromisoformat()` and the result `< date.today()`, append to
`stale_notes`:

```python
{
    "path": rel,                             # vault-relative string
    "domain_path": fm.get("domain_path", ""),
    "date_created": fm.get("date_created", ""),
    "review_after": review_after_str,
    "staleness_risk": fm.get("staleness_risk", ""),
}
```

Skip notes where `review_after` is absent or unparseable (silent continue).

**Pass B — verbatim block staleness (independent of Pass A)**

For every note (including notes whose `review_after` has NOT passed), call
`parse_verbatim_blocks(body)` from `agent.vault.verbatim`. For each returned
`VerbatimBlock`, flag if **both**:
- `block.staleness_risk == StatenessRisk.HIGH`
- `block.added_at is not None` AND `block.added_at < high_risk_cutoff`

where `high_risk_cutoff = datetime.utcnow() - timedelta(days=config.vault.verbatim_high_risk_age)`.

Append to `stale_verbatim`:

```python
{
    "note_path": rel,
    "type": block.type.value,
    "lang": block.lang,
    "attribution": block.attribution or block.model_target or "",
    "added_at": block.added_at.strftime("%Y-%m-%d"),
    "preview": block.content[:120].replace("\n", " "),
}
```

### Report write

`_write_review_report` renders the Markdown report and writes it **atomically**
using a `.tmp` sidestep pattern (matching `vault.write_note` internals):

```python
report_path = vault.meta / "outdated-review.md"
tmp = report_path.with_suffix(".tmp")
tmp.write_text("\n".join(lines), encoding="utf-8")
os.replace(tmp, report_path)
```

This pattern is consistent with `vault.append_log` (which also writes meta
files directly) and avoids forcing a frontmatter wrapper on a pure report.

The report is a **full overwrite on every run** (not an append log).

Report format (matches ARCH §12 / REQ §6.2):

```markdown
# Outdated review — YYYY-MM-DD

## Notes past review_after

| Note | Domain path | date_created | review_after | staleness_risk |
|---|---|---|---|---|
| [[path]] | ... | ... | ... | ... |

## Verbatim blocks to review

| Note | Type | Attribution / target | added_at | Preview |
|---|---|---|---|---|
| [[path]] | code | ... | YYYY-MM-DD | ...… |
```

Both tables sorted ascending by date field. If a section is empty, emit
`_None._` instead of an empty table.

### Event logging

Use `logging.getLogger(__name__)` and emit at `INFO` level:

```python
logger.info("staleness.scan.started")
# ... scan ...
logger.info(
    "staleness.found stale_notes=%d stale_verbatim=%d",
    len(stale_notes), len(stale_verbatim)
)
logger.info("staleness.scan.completed")
```

### Error resilience

Wrap `vault.read_note(rel)` in `try/except Exception: continue`. Malformed or
unreadable notes are silently skipped — the scan continues to completion.

### `anyio` note

`run()` is declared `async def` to satisfy the APScheduler async job interface
and future I/O concurrency. In Phase 1 the scan body is synchronous filesystem
I/O (no `await` calls needed). Do **not** add `await anyio.sleep()` or similar.

---

## Data model changes

None. Uses existing `VerbatimBlock`, `StatenessRisk`, `VerbatimType` from
`agent.core.models`. Config keys already present in `VaultConfig`:
- `verbatim_high_risk_age: int = 365` (days)

---

## LLM prompt file needed

None — this task makes no LLM calls.

---

## Tests required

### unit: `tests/unit/test_outdated_review.py`

Use a `tmp_path` fixture for vault root. Mock `date.today()` and
`datetime.utcnow()` via `unittest.mock.patch` or `freezegun` where needed.

| Test case | What it verifies |
|---|---|
| `test_stale_note_flagged` | Note with `review_after` yesterday appears in `stale_notes` |
| `test_fresh_note_not_flagged` | Note with `review_after` tomorrow is not flagged |
| `test_note_without_review_after_skipped` | Note lacking `review_after` key is silently skipped |
| `test_malformed_review_after_skipped` | Note with non-ISO `review_after` is silently skipped |
| `test_stale_verbatim_flagged` | HIGH-risk block with `added_at` > threshold appears in `stale_verbatim` |
| `test_fresh_verbatim_not_flagged` | HIGH-risk block with `added_at` within threshold is not flagged |
| `test_medium_risk_verbatim_not_flagged` | MEDIUM-risk old block is not flagged |
| `test_verbatim_independent_of_note_staleness` | A note with fresh `review_after` but old HIGH verbatim block IS flagged in verbatim section |
| `test_index_files_skipped` | `_index.md` files are never read or flagged |
| `test_report_written_to_correct_path` | `_AI_META/outdated-review.md` is created after `run()` |
| `test_report_overwritten_on_rerun` | Second `run()` with different data replaces first report |
| `test_empty_vault_empty_tables` | No notes → report contains `_None._` for both sections |
| `test_events_emitted` | `staleness.scan.started`, `staleness.found`, `staleness.scan.completed` appear in caplog |
| `test_malformed_note_read_error_skipped` | `vault.read_note` raising an exception does not abort the scan |
| `test_tables_sorted_by_date` | stale_notes sorted by `review_after` asc; stale_verbatim sorted by `added_at` asc |

---

## Explicitly out of scope

- **No auto-archive / auto-delete** — human decides per entry (REQ §6.2 step 5)
- **No LLM calls** — purely structural; no AI-generated suggestions (Phase 2)
- **No `_AI_META/processing-log.md` entries** — this task is not a per-file
  pipeline run
- **No scanning outside `02_KNOWLEDGE/`** — source notes in `01_PROCESSING/`
  and atoms in `06_ATOMS/` are out of scope
- **No model_target superseded detection** — Phase 2 (REQ §11)
- **No email or notification** — report is file-only

---

## Open questions

None — ARCH §12 provides a complete reference implementation. Spec is
unambiguous.
