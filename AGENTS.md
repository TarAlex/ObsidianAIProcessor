> ROUTER ONLY. Full spec in docs/. Current work queue in .cursor/dev/TRACKER.md.
---

## What this repo is

A Python 3.11+ CLI tool (`obsidian-agent`) that watches an Obsidian vault inbox,
runs a 7-stage processing pipeline (normalize → classify → date → summarize →
verbatim-extract → deduplicate → write+index → archive), and maintains
domain/subdomain _index.md files. Local-LLM-first; cloud LLMs opt-in.

Source of truth:
- Architecture: `docs/ARCHITECTURE.md` (v1.1) — never contradict it
- Requirements:  `docs/REQUIREMENTS.md`  (v1.1)
- Scope tracker: `.cursor/dev/TRACKER.md`  — check before ANY task
- Lessons:       `.cursor/dev/lessons.md`  — read at session start

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
| Design / spec a new module | `/dev-planner` | opus |
| Implement a module from spec | `/dev-builder` | sonnet (forked) |
| Write or fix tests | `/dev-tester` | sonnet (forked) |
| Review before marking DONE | `/dev-reviewer` | opus |
| Write or refine a tool prompt file | `/dev-prompt-author` | opus |
| Update TRACKER / lessons only | `/dev-tracker` | haiku |

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

1. Check `.cursor/dev/TRACKER.md` — pick one TODO item
2. Write plan to `.cursor/dev/todo.md` — checkable items only
3. Check in with user before writing code
4. Implement → run `pytest` → fix until green
5. Run `/review MODULE_PATH` before marking done
6. Run `/done "item name"` — routes to `/dev-tracker`
7. Run `/clear` before next feature session

---

## Token hygiene

- This file ≤ 200 lines. Details live in docs/, .cursor/dev/, .cursor/skills/
- `/dev-builder` and `/dev-tester` use forked context — implementation noise stays isolated
- `/dev-tracker` uses haiku — purely mechanical edits
- `/clear` between features — never accumulate multiple feature contexts
