# How to Initiate Each Feature from TRACKER.md
# Prompt Templates, Session Discipline, and Examples
#
# Rule zero: one tracker item = one implementation session.
# Rule one:  always PLAN first in a separate session, then BUILD.
# Rule two:  /clear between every session — never accumulate context.

---

## THE CORE LOOP (do this for every tracker item)

```
Session A  →  /plan          (spec-writer interviews you, saves spec)
              /clear

Session B  →  /build SLUG    (builder implements from spec, runs tests)
              /clear

Session C  →  /review PATH   (reviewer checklist)
              /done "item"   (tracker-updater flips DONE)
              /clear
```

That's it. Never collapse these into one session. Context contamination
between planning and implementation is the #1 source of scope creep.

---

## PART 1: THE /plan SESSION PROMPT

This is what you type at the START of Session A, before `/plan`.
It gives the spec-writer full orientation so the interview is tight.

### Template

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "[EXACT TEXT FROM TRACKER.md]"
- Layer: [adapters | llm | vault | stages | tasks | vector | cli | tests | skills | hooks]
- Phase: 1
- Depends on: [list any modules this needs that are already DONE, or "none"]
- Already done in this layer: [list DONE items in same layer, or "none"]

Architecture ref: docs/ARCHITECTURE.md §[section number if known]

Special constraints for this item (if any):
- [e.g. "must work with Ollama locally — no cloud API dependency"]
- [e.g. "verbatim blocks must be byte-identical — see verbatim-contract skill"]
- [or leave blank]

Run /plan
```

### Filled example — `VerbatimExtractorAgent`

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s4b_verbatim.py — VerbatimExtractorAgent (LLM)"
- Layer: pipeline (stages)
- Phase: 1
- Depends on: models.py (DONE), chunk_text skill (DONE), detect_language skill (DONE),
              AbstractLLMProvider / ProviderFactory (DONE), prompts/extract_verbatim.md (DONE)
- Already done in this layer: s1_normalize, s2_classify, s3_dates, s4a_summarize

Architecture ref: docs/ARCHITECTURE.md §6 Stage 4b, §7 Verbatim Module

Special constraints:
- VerbatimBlock.content must be byte-identical to source passage (substring-match to verify)
- max_verbatim_blocks_per_note config key controls hard cap (default 10)
- staleness defaults by type: code/prompt=HIGH, transcript=MEDIUM, quote=LOW
- if content_mismatch detected: drop block, emit verbatim.content_mismatch event

Run /plan
```

---

### Filled example — `ObsidianVault` (`vault.py`)

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "vault.py — ObsidianVault: read_note, write_note, ensure_domain_index,
  update_domain_index, path helpers"
- Layer: vault
- Phase: 1
- Depends on: models.py (DONE), render_template skill (DONE)
- Already done in this layer: none (this is the foundation of the vault layer)

Architecture ref: docs/ARCHITECTURE.md §8 Vault Module

Special constraints:
- write_note must be atomic: write to .tmp → rename (never partial writes)
- ensure_domain_index must NEVER overwrite an existing _index.md
- increment_index_count must only touch frontmatter — body (Bases queries) is never modified
- All paths relative to vault root — no absolute paths hardcoded

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
- Depends on: vault.py (DONE), models.py (DONE), EventBus (DONE)
- Already done in this layer: none (first scheduled task)

Architecture ref: docs/ARCHITECTURE.md §12 Outdated Review Task, requirements.md §6.2

Special constraints:
- Two independent passes: stale notes (review_after < today) AND stale verbatim blocks
  (verbatim blocks age independently of parent note)
- Verbatim pass threshold: staleness_risk=HIGH AND added_at older than
  config.vault.verbatim_high_risk_age (default 365 days)
- Outputs to _AI_META/outdated-review.md — overwrites each run
- MUST NOT auto-archive or auto-delete anything — human review only
- Emits: staleness.scan.started, staleness.found, staleness.scan.completed

Run /plan
```

---

## PART 2: THE /build SESSION PROMPT

After /plan completes and you've run /clear, open a fresh session.
The spec already exists at `.claude/dev/specs/SLUG.md`.
Your prompt for Session B is minimal — the spec carries the full contract.

### Template

```
Implement the spec at .claude/dev/specs/[SLUG].md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §[relevant section]
3. Read the interfaces of these existing modules that yours depends on:
   [list the key imports, e.g. "agent/core/models.py, agent/llm/base.py"]
4. Load skill: .claude/skills/[relevant-skill].md  (if applicable)

Then implement. Run tests before returning.
```

### Filled example — VerbatimExtractorAgent

```
Implement the spec at .claude/dev/specs/s4b-verbatim-extractor.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 4b and §7 Verbatim Module
3. Read: agent/core/models.py (VerbatimBlock, VerbatimType, StatenessRisk),
         agent/llm/base.py (AbstractLLMProvider.chat signature),
         agent/skills/chunk_text.py, agent/skills/detect_language.py,
         agent/events.py (how to emit verbatim.extracted, verbatim.content_mismatch)
4. Load skill: .claude/skills/verbatim-contract.md

Then implement agent/pipeline/verbatim_extractor.py.
Run pytest tests/unit/test_verbatim.py before returning.
```

---

### Filled example — `IndexUpdaterAgent` (Stage 6b)

```
Implement the spec at .claude/dev/specs/s6b-index-updater.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 6b
3. Read: agent/core/models.py (ClassificationResult, DomainIndexEntry),
         agent/vault/vault.py (ensure_domain_index, increment_index_count),
         agent/events.py (index.updated, index.created events)
4. Load skill: .claude/skills/index-update-contract.md

Then implement agent/pipeline/index_updater.py.
Run pytest tests/unit/test_index_update.py before returning.
```

---

### Filled example — `ClassifierAgent` (Stage 2, LLM-calling)

```
Implement the spec at .claude/dev/specs/s2-classifier.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 2 and §9 Prompts (classify.md schema)
3. Read: agent/core/models.py (NormalizedItem, ClassificationResult),
         agent/llm/base.py (AbstractLLMProvider),
         agent/skills/compute_staleness.py,
         agent/skills/validate_tags.py,
         agent/events.py (llm.called, llm.failed, llm.retry, pipeline.review_queued)
4. Load skill: .claude/skills/provider-factory-pattern.md

Then implement agent/pipeline/classifier.py.
Also implement agent/skills/compute_staleness.py if not already done.
Run pytest tests/unit/test_s2_classify.py before returning.
```

---

### Filled example — A skill with no LLM (`parse_date.py`)

```
Implement the spec at .claude/dev/specs/skill-parse-date.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 3 (how DateExtractorAgent uses this skill)
3. Read: agent/core/models.py (NormalizedItem — which fields carry date metadata)

Note: this skill has NO LLM dependency and NO vault dependency.
It is a pure function. Keep it that way.

Implement agent/skills/parse_date.py.
Run pytest tests/unit/test_parse_date.py before returning.
```

---

### Filled example — A hook handler (`LLMUsageTracker`)

```
Implement the spec at .claude/dev/specs/hook-llm-usage-tracker.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §4 Hooks (event catalogue, HookHandler ABC)
3. Read: agent/events.py (HookHandler ABC, EventBus.subscribe, llm.called payload),
         agent/vault/vault.py (write_note — for appending to llm-usage.md)

Then implement agent/hooks/llm_usage_tracker.py.
Register it in agent/main.py under the llm.called event.
Run pytest tests/unit/test_hook_llm_usage.py before returning.
```

---

## PART 3: THE /review + /done SESSION PROMPT

After /clear from Session B, open Session C.
Review is always run on specific files — give exact paths.

### Template

```
/review [comma-separated list of files implemented in Session B]

After review:
- If APPROVED: /done "[exact tracker item text]"
- If NEEDS_CHANGES: fix inline or restart Session B with the specific items

Any lesson to capture? Run: /log "[pattern observed]"
```

### Filled example — after VerbatimExtractorAgent

```
/review agent/pipeline/verbatim_extractor.py, tests/unit/test_verbatim.py

After review:
- If APPROVED: /done "s4b_verbatim.py — VerbatimExtractorAgent (LLM)"
- If NEEDS_CHANGES: list specific items and I'll fix in next session

Possible lesson to capture: any edge case discovered during verbatim
content_mismatch handling.
```

---

## PART 4: QUICK-START CHEAT SHEET

### When the item is a SKILL (no LLM, no vault)
```
Layer: agent/skills/
Prompt style: "pure function, no LLM, no vault dependency"
Test style: unit only, use fixtures
Reviewer focus: no imports of vault or LLM modules
Skill to load: none (skills are primitive — they don't load other skills)
```

### When the item is a PIPELINE SUBAGENT (may use LLM)
```
Layer: agent/pipeline/
Prompt style: list all input models + LLM provider + events emitted
Test style: unit (mock LLM) + integration (real Ollama fixture if LLM-calling)
Reviewer focus: provider-factory-pattern, no direct vault writes, correct events emitted
Skills to load: relevant skills from .claude/skills/ matching the subagent's responsibilities
```

### When the item is a SCHEDULED TASK
```
Layer: agent/tasks/
Prompt style: "scheduled subagent, no per-file trigger, emits lifecycle events"
Test style: unit with vault fixture; mock the clock for schedule logic
Reviewer focus: idempotent (safe to run twice), no auto-delete, human-review only outputs
```

### When the item is a HOOK HANDLER
```
Layer: agent/hooks/
Prompt style: "subscribes to [event], never raises, append-only to vault meta files"
Test style: unit — mock EventBus, assert handler appends correct log entry
Reviewer focus: handler.handle() never raises, correct event subscription in main.py
```

### When the item is a CLI COMMAND
```
Layer: agent/main.py
Prompt style: list exact Click options, expected output format, --dry-run behaviour
Test style: integration using Click's test runner (CliRunner)
Reviewer focus: --dry-run never writes, --config respected, graceful error messages
```

### When the item is a PROMPT FILE
```
Layer: prompts/
Agent: use dev:prompt-author (not dev:builder)
Prompt style: name the target Pydantic model, list few-shot requirements,
              confirm local LLM compatibility required
Test style: manual validation via provider-check command, then add to test_llm_ollama.py
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
- This is a skill consumed by NoteWriterAgent and VerbatimExtractorAgent
  — it must have zero pipeline or vault imports

Run /plan
```

/clear

**Session B — Build**
```
Implement the spec at .claude/dev/specs/vault-verbatim.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §7 Verbatim Module (full code listing is there)
3. Read agent/core/models.py: VerbatimBlock, VerbatimType, StatenessRisk
4. Load skill: .claude/skills/verbatim-contract.md

Implement agent/vault/verbatim.py.
Write tests/unit/test_verbatim.py covering:
  - round-trip lossless for all four VerbatimType values
  - content with special chars / multiline
  - malformed comment header is skipped silently
  - content byte-identical assertion

Run pytest tests/unit/test_verbatim.py -v before returning.
```

/clear

**Session C — Review + Close**
```
/review agent/vault/verbatim.py, tests/unit/test_verbatim.py

If APPROVED:
/done "verbatim.py ★ — Verbatim block parse/render (round-trip lossless)"
/log "parse_verbatim_blocks silently skips malformed headers — confirmed no raise on corrupt HTML comment"
```

---

## PART 6: ORDERING GUIDE — which tracker items unblock which

Work down this order. Starting out of order causes import errors.

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
  IndexUpdaterAgent (S6b) ← needs vault.ensure_domain_index, vault.increment_index_count

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
