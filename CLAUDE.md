# Claude Code — ObsidianAIPoweredFlow

A Python 3.11+ CLI agent (`obsidian-agent`) that processes an Obsidian vault inbox
through a 7-stage pipeline. Local-LLM-first. Full spec in `docs/`.

---

## Session start checklist

1. Read `ProgressTracking/TRACKER.md` — see current TODO/IN_PROGRESS/DONE state
2. Read `ProgressTracking/lessons.md` — avoid known mistakes
3. Skim `AGENTS.md` — routing table and pipeline stage map
4. Never start implementation without a spec in `ProgressTracking/specs/`

---

## Commands

| Command | What it does |
|---|---|
| `/spec "Section"` | Decompose a section into ordered modules → feature spec |
| `/plan SLUG` | Design one module → writes `ProgressTracking/specs/SLUG.md` |
| `/build SLUG` | Implement a module from its spec (forked context) |
| `/review PATH` | Approve or reject before marking done |
| `/test MODULE` | Write or fix pytest coverage (forked context) |
| `/done "item"` | Mark item DONE in TRACKER.md (requires prior /review APPROVED) |
| `/log "lesson"` | Append to `ProgressTracking/lessons.md` |
| `/status` | Print progress summary from TRACKER.md |

---

## Agents

| Agent | Trigger phrases | Model |
|---|---|---|
| `dev:spec` | "spec a section", "decompose a feature", "feature breakdown" | opus |
| `dev:planner` | "plan", "spec a module", "design", "before we build" | opus |
| `dev:builder` | "implement", "build", "write the code for" | sonnet (forked) |
| `dev:tester` | "write tests", "fix failing tests", "add test coverage" | sonnet (forked) |
| `dev:reviewer` | "review", "approve", before /done | opus |
| `dev:prompt-author` | "write the prompt for", "improve prompt", "fix LLM output" | opus |
| `dev:tracker` | "mark done", "update tracker", "add lesson", "log this" | haiku |

Route explicitly. Do not spec and implement in the same session.

---

## Code constraints (non-negotiable)

| Rule | Why |
|---|---|
| Python 3.11+ only | pyproject.toml target |
| All vault writes via `ObsidianVault` | vault integrity |
| All LLM calls via `ProviderFactory` | privacy-first, provider-agnostic |
| `anyio` for async, not raw `asyncio` | cross-platform portability |
| Pydantic v2 models for all pipeline data | type safety across stages |
| No Phase 2 code in Phase 1 modules | scope discipline |
| No hardcoded vault paths or API keys | portability and security |

---

## Dev cycle (4 sessions)

```
Session A — SPEC:   /spec "Section"   → feature decomposition (once per section)
Session B — PLAN:   /plan SLUG        → module spec (reads feature spec for context)
Session C — BUILD:  /build SLUG       → implement + pytest green
Session D — CLOSE:  /review PATH → /done "item" → /log "lesson" → /clear
```

Per-session task discipline:
1. Check TRACKER.md — pick one TODO in the order shown by the feature spec
2. `/plan SLUG` — write module spec (if not already done)
3. `/build SLUG` — implement
4. `/review PATH` → `/done "item"` + `/log "lesson"` — close item
5. `/clear` before next feature session

See `ProgressTracking/feature-initiation-prompts.md` for full worked examples.

---

## Key paths

| Path | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | System architecture v1.1 — never contradict |
| `docs/REQUIREMENTS.md` | Requirements v1.1 |
| `ProgressTracking/TRACKER.md` | All TODO/IN_PROGRESS/DONE items |
| `ProgressTracking/lessons.md` | Accumulated lessons (read at session start) |
| `ProgressTracking/specs/` | Module specs (SLUG.md) and feature specs (feature-SLUG.md) |
| `ProgressTracking/feature-initiation-prompts.md` | Full cycle guide with examples |
| `.claude/agents/` | Agent definitions |
| `.claude/commands/` | Slash command definitions |

---

> Token hygiene: `/build` and `/test` use forked context — noise stays isolated.
> `/tracker` uses haiku — purely mechanical edits. `/clear` between feature sessions.
