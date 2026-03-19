# Feature Initiation Guide — obsidian-agent
# Prompt Templates, Session Discipline, and Examples
#
# Rule zero: one tracker item = one implementation cycle.
# Rule one:  spec ALWAYS precedes code — never merge planning and building.
# Rule two:  /clear between every session — never accumulate context.
# Rule three: spec must read docs AND existing DONE modules before writing.

---

## THE COMPLETE DEV CYCLE

One item from `ProgressTracking/TRACKER.md` per cycle. Work in tier order
(see Part 6). Pick the next TODO item whose dependencies are all DONE.

```
╔═══════════════════════════════════════════════════════════════╗
║  Session A — SPEC / PLAN                                      ║
║                                                               ║
║  Pre-flight (before writing a single line of spec):           ║
║    1. Read docs/ARCHITECTURE.md (relevant sections)           ║
║    2. Read docs/REQUIREMENTS.md (relevant sections)           ║
║    3. Read ProgressTracking/TRACKER.md (note all DONE items)  ║
║    4. Read source of DONE dependencies (for contracts)        ║
║                                                               ║
║  → /plan   writes ProgressTracking/specs/SLUG.md             ║
║            sets item IN_PROGRESS in TRACKER.md               ║
║  → /clear                                                     ║
╠═══════════════════════════════════════════════════════════════╣
║  Session B — IMPLEMENT + TEST                                 ║
║                                                               ║
║  → /build SLUG                                                ║
║            reads ProgressTracking/specs/SLUG.md              ║
║            reads ARCHITECTURE.md relevant section            ║
║            reads interfaces of dependency modules            ║
║            writes module + tests → pytest green              ║
║  → /clear                                                     ║
╠═══════════════════════════════════════════════════════════════╣
║  Session C — REVIEW + CLOSE                                   ║
║                                                               ║
║  → /review PATH   (APPROVED or NEEDS_CHANGES)                 ║
║  → git commit     (if APPROVED)                              ║
║  → /done "item"   (flips TRACKER to DONE)                    ║
║  → /log "lesson"  (appends to ProgressTracking/lessons.md)   ║
║  → /clear                                                     ║
╚═══════════════════════════════════════════════════════════════╝
```

Never collapse sessions A+B or B+C. Context contamination between planning
and implementation is the #1 source of scope creep and hidden coupling.

---

## PART 1: THE /plan SESSION PROMPT

Open Session A fresh. This is what you type before `/plan`.
It orients the spec-writer so the interview (if interactive) is tight,
and gives the runner full context for automated execution.

### Template

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "[EXACT TEXT FROM ProgressTracking/TRACKER.md]"
- Layer: [adapters | llm | vault | stages | tasks | vector | cli | tests | skills | hooks]
- Phase: 1
- Depends on: [list DONE modules this needs, or "none"]
- Already done in this layer: [list DONE items in same layer, or "none"]

Architecture ref: docs/ARCHITECTURE.md §[section number]

Special constraints for this item (if any):
- [e.g. "must work with Ollama locally — no cloud API dependency"]
- [e.g. "verbatim blocks must be byte-identical — see .claude/skills/verbatim-contract.md"]
- [or leave blank]

Output: Write the spec to ProgressTracking/specs/[SLUG].md using the format
in .claude/agents/dev-planner.md. Do not ask the user; use the context above.
Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.

Run /plan
```

### Filled example — `VerbatimExtractorAgent`

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s4b_verbatim.py — VerbatimExtractorAgent (LLM)"
- Layer: pipeline (stages)
- Phase: 1
- Depends on: models.py (DONE), agent/llm/base.py (DONE),
              agent/llm/provider_factory.py (DONE),
              prompts/extract_verbatim.md (DONE)
- Already done in this layer: s1_normalize, s2_classify, s3_dates, s4a_summarize

Architecture ref: docs/ARCHITECTURE.md §6 Stage 4b, §7 Verbatim Module

Special constraints:
- VerbatimBlock.content must be byte-identical to source passage
- max_verbatim_blocks_per_note controls hard cap (default 10)
- staleness defaults: code/prompt=HIGH, transcript=MEDIUM, quote=LOW
- content_mismatch: drop block, emit verbatim.content_mismatch event
- Load skill: .claude/skills/verbatim-contract.md

Output: Write the spec to ProgressTracking/specs/s4b-verbatim-extractor.md
using the format in .claude/agents/dev-planner.md. Do not ask the user.
Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.

Run /plan
```

---

### Filled example — `ObsidianVault` (`vault.py`)

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "vault.py — ObsidianVault: read_note, write_note,
  ensure_domain_index, update_domain_index, path helpers"
- Layer: vault
- Phase: 1
- Depends on: models.py (DONE)
- Already done in this layer: none (this is the foundation of the vault layer)

Architecture ref: docs/ARCHITECTURE.md §8 Vault Module

Special constraints:
- write_note must be atomic: write to .tmp → rename (never partial writes)
- ensure_domain_index must NEVER overwrite an existing _index.md
- update_domain_index touches frontmatter only — body (Bases queries) untouched
- All paths relative to vault root — no absolute paths hardcoded
- Load skill: .claude/skills/index-update-contract.md

Output: Write the spec to ProgressTracking/specs/vault-py.md
using the format in .claude/agents/dev-planner.md. Do not ask the user.
Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.

Run /plan
```

---

### Filled example — `StalenessAuditorAgent` (scheduled task)

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "outdated_review.py — StalenessAuditorAgent (weekly)"
- Layer: tasks (scheduled subagents)
- Phase: 1
- Depends on: vault.py (DONE), models.py (DONE)
- Already done in this layer: none (first scheduled task)

Architecture ref: docs/ARCHITECTURE.md §12 Outdated Review Task,
                  docs/REQUIREMENTS.md §6.2

Special constraints:
- Two independent passes: stale notes AND stale verbatim blocks
- Verbatim threshold: staleness_risk=HIGH AND added_at older than
  config.vault.verbatim_high_risk_age (default 365 days)
- Outputs to _AI_META/outdated-review.md — overwrites each run
- MUST NOT auto-archive or auto-delete — human review only
- Emits: staleness.scan.started, staleness.found, staleness.scan.completed

Output: Write the spec to ProgressTracking/specs/staleness-auditor.md
using the format in .claude/agents/dev-planner.md. Do not ask the user.
Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.

Run /plan
```

---

## PART 2: THE /build SESSION PROMPT

After /plan completes and you've run /clear, open a fresh session.
The spec at `ProgressTracking/specs/SLUG.md` carries the full contract.

### Template

```
Implement the spec at ProgressTracking/specs/[SLUG].md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §[relevant section]
3. Read the interfaces of these existing modules that yours depends on:
   [list key imports, e.g. "agent/core/models.py, agent/llm/base.py"]
4. Load skill: .claude/skills/[relevant-skill].md  (if applicable)

Then implement. Run tests before returning.
```

### Filled example — VerbatimExtractorAgent

```
Implement the spec at ProgressTracking/specs/s4b-verbatim-extractor.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 4b and §7 Verbatim Module
3. Read: agent/core/models.py (VerbatimBlock, VerbatimType, StatenessRisk),
         agent/llm/base.py (AbstractLLMProvider.complete signature),
         agent/events.py (verbatim.extracted, verbatim.content_mismatch)
4. Load skill: .claude/skills/verbatim-contract.md

Implement agent/stages/s4b_verbatim.py.
Run pytest tests/unit/test_verbatim.py -v before returning.
```

---

### Filled example — `IndexUpdaterAgent` (Stage 6b)

```
Implement the spec at ProgressTracking/specs/s6b-index-updater.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 6b
3. Read: agent/core/models.py (ClassificationResult, DomainIndexEntry),
         agent/vault/vault.py (ensure_domain_index, update_domain_index),
         agent/events.py (index.updated, index.created)
4. Load skill: .claude/skills/index-update-contract.md

Implement agent/stages/s6b_index_update.py.
Run pytest tests/unit/test_index_update.py before returning.
```

---

### Filled example — `ClassifierAgent` (Stage 2, LLM-calling)

```
Implement the spec at ProgressTracking/specs/s2-classifier.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 2 and §9 Prompts
3. Read: agent/core/models.py (NormalizedItem, ClassificationResult),
         agent/llm/base.py (AbstractLLMProvider),
         agent/events.py (llm.called, llm.failed, pipeline.review_queued)
4. Load skill: .claude/skills/provider-factory-pattern.md

Implement agent/stages/s2_classify.py.
Run pytest tests/unit/test_s2_classify.py before returning.
```

---

### Filled example — A skill with no LLM (`parse_date.py`)

```
Implement the spec at ProgressTracking/specs/skill-parse-date.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 3 (how DateExtractorAgent uses this)
3. Read: agent/core/models.py (NormalizedItem — date metadata fields)

Note: pure function — NO LLM dependency, NO vault dependency.

Implement agent/skills/parse_date.py.
Run pytest tests/unit/test_parse_date.py before returning.
```

---

### Filled example — A hook handler

```
Implement the spec at ProgressTracking/specs/hook-llm-usage-tracker.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §4 Hooks (event catalogue, HookHandler ABC)
3. Read: agent/events.py (HookHandler ABC, EventBus.subscribe, llm.called payload),
         agent/vault/vault.py (write_note — for appending to llm-usage.md)

Implement agent/hooks/llm_usage_tracker.py.
Register it in agent/main.py under the llm.called event.
Run pytest tests/unit/test_hook_llm_usage.py before returning.
```

---

## PART 3: THE /review + /done SESSION PROMPT

After /clear from Session B, open Session C.
Give exact file paths — reviewer uses the checklist against specific code.

### Template

```
/review [comma-separated list of files implemented in Session B]

After review:
- If APPROVED:
  git commit -m "[module name]: implement [brief description]"
  /done "[exact tracker item text]"
  /log "[pattern observed — optional]"
- If NEEDS_CHANGES: list specific items and fix in a new Session B
```

### Filled example — after VerbatimExtractorAgent

```
/review agent/stages/s4b_verbatim.py, tests/unit/test_verbatim.py

After review:
- If APPROVED:
  git commit -m "s4b_verbatim: implement VerbatimExtractorAgent (LLM)"
  /done "s4b_verbatim.py — VerbatimExtractorAgent (LLM)"
  /log "content_mismatch detection requires substring check not equality —
        use 'source in output' not 'source == output'"
- If NEEDS_CHANGES: list specific items and I'll fix in next session
```

---

## PART 4: QUICK-START CHEAT SHEET

### When the item is a SKILL (no LLM, no vault)
```
Layer: agent/skills/
Prompt style: "pure function, no LLM, no vault dependency"
Test style: unit only, use fixtures
Reviewer focus: no imports of vault or LLM modules
Skill to load: none
```

### When the item is a PIPELINE STAGE (may use LLM)
```
Layer: agent/stages/
Prompt style: list all input models + LLM provider + events emitted
Test style: unit (mock LLM) + integration (real Ollama fixture if LLM-calling)
Reviewer focus: provider-factory-pattern, no direct vault writes, correct events
Skills to load: .claude/skills/ matching the stage's responsibilities
```

### When the item is a SCHEDULED TASK
```
Layer: agent/tasks/
Prompt style: "scheduled subagent, no per-file trigger, emits lifecycle events"
Test style: unit with vault fixture; mock the clock for schedule logic
Reviewer focus: idempotent (safe to run twice), no auto-delete, human-review only
```

### When the item is a HOOK HANDLER
```
Layer: agent/hooks/
Prompt style: "subscribes to [event], never raises, append-only to vault meta files"
Test style: unit — mock EventBus, assert handler appends correct log entry
Reviewer focus: handle() never raises, correct event subscription in main.py
```

### When the item is a CLI COMMAND
```
Layer: agent/main.py
Prompt style: list exact Click options, expected output format, --dry-run behaviour
Test style: integration using Click's CliRunner
Reviewer focus: --dry-run never writes, --config respected, graceful error messages
```

### When the item is a PROMPT FILE
```
Layer: prompts/
Agent: use dev:prompt-author (not dev:builder) — run /plan with that agent explicitly
Prompt style: name the target Pydantic model, list few-shot requirements,
              confirm local LLM compatibility required
Test style: manual validation via provider-check command + test_llm_ollama.py
Reviewer focus: output parses cleanly into target model, no function-calling syntax
```

---

## PART 5: FULL WORKED EXAMPLE — end to end

### Tracker item: `verbatim.py ★ — round-trip lossless`

**Session A — Plan**
```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "verbatim.py ★ — Verbatim block parse/render (round-trip lossless)"
- Layer: vault
- Phase: 1
- Depends on: models.py (DONE — VerbatimBlock, VerbatimType, StatenessRisk)
- Already done in this layer: vault.py, note.py

Architecture ref: docs/ARCHITECTURE.md §7 Verbatim Module

Special constraints:
- render_verbatim_block(block) → parse_verbatim_blocks(output)[0] must equal block
  with content field byte-identical
- Quotes rendered as blockquote (> prefix per line)
- Code/prompt/transcript rendered as fenced code block (``` with lang for code)
- parse must handle malformed blocks silently (skip, no raise)
- Zero pipeline or vault imports — this is a pure-function skill

Output: Write the spec to ProgressTracking/specs/vault-verbatim.md
using the format in .claude/agents/dev-planner.md. Do not ask the user.
Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.

Run /plan
```

/clear

**Session B — Build**
```
Implement the spec at ProgressTracking/specs/vault-verbatim.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §7 Verbatim Module
3. Read: agent/core/models.py (VerbatimBlock, VerbatimType, StatenessRisk)
         agent/vault/vault.py (how vault.py calls verbatim.py — check imports)
         agent/vault/note.py  (note rendering context)
4. Load skill: .claude/skills/verbatim-contract.md

Implement agent/vault/verbatim.py.
Write tests/unit/test_verbatim.py covering:
  - round-trip lossless for all four VerbatimType values
  - content with special chars / multiline
  - malformed comment header is skipped silently
  - content byte-identical assertion (use assertEqual, not assertIn)

Run pytest tests/unit/test_verbatim.py -v before returning.
```

/clear

**Session C — Review + Close**
```
/review agent/vault/verbatim.py, tests/unit/test_verbatim.py

If APPROVED:
  git commit -m "vault/verbatim: implement round-trip lossless parse/render"
  /done "verbatim.py ★ — Verbatim block parse/render (round-trip lossless)"
  /log "parse_verbatim_blocks silently skips malformed HTML comment headers —
        confirmed no raise on corrupt input"
```

---

## PART 6: ORDERING GUIDE — which tracker items unblock which

Work down this tier order. Starting out of order causes import errors.

```
Tier 0 — no dependencies (start here)
  models.py
  agent-config.yaml schema

Tier 1 — depends only on models.py
  All skills (compute_staleness, parse_date, detect_language, chunk_text,
              validate_tags, embed_text, transcribe, extract_pdf,
              fetch_web, fetch_youtube)
  verbatim.py (vault layer, depends only on models)

Tier 2 — depends on skills + models
  AbstractLLMProvider base + PromptLoader
  All SourceAdapters (compose skills, no LLM)
  VectorStore + Embedder (wraps embed_text skill)

Tier 3 — depends on LLM layer + vault layer
  ObsidianVault (vault.py, note.py, templates.py, references.py, archive.py)
  ProviderFactory + all provider implementations

Tier 4 — depends on vault + LLM + skills
  NormalizerAgent (S1)
  ClassifierAgent  (S2) ← needs compute_staleness, validate_tags, ProviderFactory
  DateExtractorAgent (S3) ← needs parse_date

Tier 5 — depends on S1–S3 output
  SummarizerAgent  (S4a) ← needs chunk_text, ProviderFactory
  VerbatimExtractorAgent (S4b) ← needs chunk_text, detect_language, verbatim.py
  DeduplicatorAgent (S5) ← needs similarity_search, VectorStore

Tier 6 — depends on S1–S5 output + vault
  NoteWriterAgent (S6a) ← needs render_template, validate_tags, references.py
  IndexUpdaterAgent (S6b) ← needs vault.ensure_domain_index, update_domain_index

Tier 7 — depends on full pipeline
  ArchiverAgent (S7)
  PipelineOrchestrator (pipeline.py)
  InboxWatcher (watcher.py)
  APScheduler (scheduler.py)

Tier 8 — depends on pipeline being complete
  StalenessAuditorAgent, IndexRebuilderAgent, ReferenceLinkerAgent

Tier 9 — depends on everything
  All hook handlers
  CLI commands (main.py)
  EventBus wiring

Tier 10 — standalone, can be done anytime after Tier 3
  All prompt files (prompts/*.md) — use dev:prompt-author agent
  scripts/setup_vault.py, scripts/reindex.py
```
