# Feature Spec: Scheduled Tasks
slug: feature-scheduled-tasks
sections_covered: [ProgressTracking/tasks/07_scheduled-tasks.md]
arch_sections: [§12 Outdated Review Task, §13 Index Updater Task, §6.2 Outdated Knowledge Review, §2.2 REFERENCES]

---

## Scope

Three periodic/on-demand tasks that run outside the per-file pipeline.
All live in `agent/tasks/` and are wired to APScheduler (already DONE in
`agent/core/scheduler.py`). They are **read-heavy, write-minimal, and
human-safe** — no auto-archiving, no auto-deletion, no LLM calls.

| Task | Trigger | Output |
|---|---|---|
| `outdated_review.py` | Weekly (Monday 09:00) | `_AI_META/outdated-review.md` |
| `index_updater.py` | Daily (configurable) | In-place frontmatter edits on `_index.md` files |
| `reference_linker.py` | On-demand / weekly | In-place `[[wikilink]]` injection into note bodies |

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `agent/tasks/outdated_review.py` | `outdated-review` | vault.py ✓, verbatim.py ✓, models.py ✓, config.py ✓ | tasks |
| 2 | `agent/tasks/index_updater.py` | `index-updater` | vault.py ✓, models.py ✓, config.py ✓ | tasks |
| 3 | `agent/tasks/reference_linker.py` | `reference-linker` | vault.py ✓, references.py ✓, note.py ✓, models.py ✓ | tasks |

---

## Cross-cutting constraints

- **anyio only** — no raw `asyncio`. All `async def` entry points use `anyio`.
- **All vault writes via `ObsidianVault`** — never open vault files directly.
- **No auto-archive / no auto-delete** — tasks flag; human decides.
- **No LLM calls** — these tasks are purely structural; they read frontmatter
  and parse note bodies only.
- **Idempotent** — re-running any task must produce the same result; no
  duplicate rows, no double-increments (index_updater rebuilds from scratch,
  not from deltas).
- **Body-safe** — `index_updater` MUST NOT touch note bodies (Bases queries
  self-refresh). Only frontmatter fields `note_count` and `last_updated` are
  written.
- **Skip `_index.md` files** when scanning for content notes (outdated_review,
  reference_linker).
- **Config keys used**:
  - `vault.verbatim_high_risk_age` (int, days) — threshold for high-risk
    verbatim block flagging in outdated_review
  - `scheduler.outdated_review_day` / `scheduler.outdated_review_hour` —
    APScheduler wiring (already in config schema)
- **Pydantic v2 models** — no dataclasses or plain dicts in public interfaces.
- **Python 3.11+** — use `date.fromisoformat`, `datetime.fromisoformat`,
  `Path.rglob`, walrus operator freely.

---

## Implementation ordering rationale

1. **`outdated_review` first** — smallest surface area; depends only on
   `vault.py` and `verbatim.py` (both DONE). The output format
   (`_AI_META/outdated-review.md`) is fully specified in ARCH §12 and
   REQUIREMENTS §6.2. Straightforward to test with a mocked clock.

2. **`index_updater` second** — also has no new dependencies, but the
   rebuild-from-scratch approach must be validated before `reference_linker`
   adds any new links (to avoid double-counting). ARCH §13 gives a full
   reference implementation. Test with a fake vault tree.

3. **`reference_linker` last** — most surface area: reads every note, resolves
   entity names against `REFERENCES/people/` and `REFERENCES/projects_*/`,
   inserts `[[wikilinks]]` only when a reference file exists. Must skip notes
   that already contain the link (idempotency). Depends on `references.py`
   (DONE) and `note.py` (DONE). No ARCH reference implementation — spec must
   derive it from REQUIREMENTS §2.2.

---

## Detailed module notes

### 1. outdated_review.py (ARCH §12, REQ §6.2)

Entry point: `async def run(vault: ObsidianVault, config) -> None`

Two-pass scan over `vault.knowledge.rglob("*.md")` (skip `_index.md`):
- **Pass A — note staleness**: `review_after < date.today()` → row in
  `## Notes past review_after` table.
- **Pass B — verbatim staleness**: for each note, call
  `parse_verbatim_blocks(body)`; flag blocks where
  `staleness_risk == HIGH` AND `added_at < (now - verbatim_high_risk_age days)` →
  row in `## Verbatim blocks to review` table.

Output written atomically to `_AI_META/outdated-review.md` (overwrite on each
run — the file is a report, not an append log).

Events to emit (logging.INFO):
- `staleness.scan.started`
- `staleness.found` (count of stale notes + stale verbatim blocks)
- `staleness.scan.completed`

### 2. index_updater.py (ARCH §13)

Entry point: `async def rebuild_all_counts(vault: ObsidianVault) -> None`

Algorithm (from ARCH §13):
1. Walk all `*.md` in `vault.knowledge`, skip `_index.md`.
2. Read frontmatter; extract `domain_path`. Skip notes without it.
3. Accumulate `counts[domain_path]` and `last_modified[domain_path]`; also
   roll up to `counts[domain]` (first path component).
4. Walk all `_index.md` files; for each, determine key from
   `index_type` + `domain` + `subdomain`; if `note_count` or `last_updated`
   differs from computed value, rewrite frontmatter only (preserve body).

Only writes if values changed — avoids spurious vault activity.

### 3. reference_linker.py (REQ §2.2)

Entry point: `async def run(vault: ObsidianVault, config) -> None`

Algorithm:
1. Load all known people slugs from `REFERENCES/people/*.md` frontmatter
   (`full_name`, `nickname`).
2. Load all known project slugs from `REFERENCES/projects_work/*.md` and
   `REFERENCES/projects_personal/*.md`.
3. Walk all `*.md` under `vault.knowledge`, skip `_index.md`.
4. For each note body: for each known entity, if a plain-text mention exists
   and no `[[wikilink]]` to that reference already exists, inject the link.
   Only inject when the reference file is confirmed to exist (no dangling
   links).
5. Write updated note via `vault.write_note()` only if at least one link was
   injected. Never modify frontmatter.

Human-review safe: linker only adds links, never removes content.

---

## Excluded (Phase 2 or out of scope)

- **Prompt version migration tracking** (`model_target` superseded detection) —
  Phase 2 (REQUIREMENTS §11).
- **Birthday digest** (weekly from `REFERENCES/people/`) — Phase 2.
- **AI-generated update suggestions** for stale notes — Phase 2.
- **Auto-archive or auto-delete** of any flagged note — explicitly excluded
  (REQUIREMENTS §6.2, step 5).
- **LLM calls** inside any task in this section — none required in Phase 1.
- **Vector store interaction** — deduplication is a pipeline stage (s5), not
  a scheduled task.
