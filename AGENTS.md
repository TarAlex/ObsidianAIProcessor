> ROUTER ONLY. Full spec in docs/. Current work queue in ProgressTracking/TRACKER.md.
---

## What this repo is

A Python 3.11+ CLI tool (`obsidian-agent`) that watches an Obsidian vault inbox,
runs a 7-stage processing pipeline (normalize → classify → date → summarize →
verbatim-extract → deduplicate → write+index → archive), and maintains
domain/subdomain _index.md files. Local-LLM-first; cloud LLMs opt-in.

Source of truth:
- Architecture: `docs/ARCHITECTURE.md` (v1.1) — never contradict it
- Requirements:  `docs/REQUIREMENTS.md`  (v1.1)
- Scope tracker: `ProgressTracking/TRACKER.md`  — check before ANY task
- Lessons:       `ProgressTracking/lessons.md`  — read at session start

---

## Absolute code constraints (never negotiate)

| Rule | Why |
|---|---|
| Python 3.11+ only | pyproject.toml target |
| All vault writes via `ObsidianVault` | vault integrity requirement |
| All LLM calls via `ProviderFactory` | privacy-first, provider-agnostic |
| `anyio` for async, not raw asyncio | cross-platform portability |
| Pydantic v2 models for all pipeline data | type safety across stages |
| No Phase 2 code in Phase 1 modules | scope discipline |
| No hardcoded vault paths or API keys | portability and security |

---

## Dev agent routing

| Task | Skill | Model |
|---|---|---|
| Generate a feature-level decomposition | `/spec` → dev:spec | opus |
| Design / spec a new module | `/plan` → dev:planner | opus |
| Implement a module from spec | `/build` → dev:builder | sonnet (forked) |
| Write or fix tests | `/test` → dev:tester | sonnet (forked) |
| Review before marking DONE | `/review` → dev:reviewer | opus |
| Write or refine a tool prompt file | `/dev-prompt-author` | opus |
| Update TRACKER / lessons only | `/done` + `/log` → dev:tracker | haiku |

Route explicitly. Do not implement and spec in the same session.

> Note: Cursor has no automatic hook lifecycle (SessionStart, PreToolUse, etc.).
> Session reminders, vault write guards, and test-gate logic are encoded in
> `.cursor/rules/session-and-hooks.mdc`. Hook scripts remain in `.cursor/hooks/`
> for agent-invoked or manual use.

---

## Pipeline stage map (read-only reference)

```
agent/stages/
  s1_normalize.py     ← SourceAdapter → NormalizedItem
  s2_classify.py      ← NormalizedItem → ClassificationResult
  s3_dates.py         ← ClassificationResult → dated NormalizedItem
  s4a_summarize.py    ← dated item → SummaryResult
  s4b_verbatim.py  ★  ← raw text → list[VerbatimBlock]
  s5_deduplicate.py   ← SummaryResult → dedup decision
  s6a_write.py        ← approved item → vault note
  s6b_index_update.py ← written note → _index.md increment  ★
  s7_archive.py       ← processed item → 05_ARCHIVE/
```

★ = added in v1.1. Each stage is stateless; pipeline.py orchestrates order.

---

## Per-session task discipline

```
0. /spec "Section"  — generate feature decomposition (once per section)
1. Check TRACKER.md — pick one TODO item in order from feature spec
2. /plan SLUG       — write module spec
3. /build SLUG      — implement + pytest green
4. /review + /done + /log — close item
```

Steps in detail:
1. Check `ProgressTracking/TRACKER.md` — pick one TODO item (follow feature spec order)
2. `/plan SLUG` — write module spec if not already in `ProgressTracking/specs/`
3. Check in with user before writing code
4. `/build SLUG` → run `pytest` → fix until green
5. Run `/review MODULE_PATH` before marking done
6. Run `/done "item name"` + `/log "lesson"` — routes to `dev:tracker`
7. Run `/clear` before next feature session

---

## Token hygiene

- This file ≤ 200 lines. Details live in docs/, ProgressTracking/, .claude/skills/
- `/dev-builder` and `/dev-tester` use forked context — implementation noise stays isolated
- `/dev-tracker` uses haiku — purely mechanical edits
- `/clear` between features — never accumulate multiple feature contexts
