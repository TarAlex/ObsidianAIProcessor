# Spec: prompts/extract_verbatim.md
slug: prompt-extract-verbatim
layer: prompts
phase: 1
arch_section: §9 Prompts (extract_verbatim.md), Appendix A — Verbatim Block Decision Tree

---

## Problem statement

Stage 4b (`s4b_verbatim.py`) calls `load_prompt("extract_verbatim", ctx)` and feeds
the rendered string to the LLM. The LLM must return a JSON object with a
`verbatim_blocks` array where each element maps directly to `VerbatimBlock` fields.

`prompts/extract_verbatim.md` is the **static text file** that defines:
- The analyst role / system instruction
- Input variable placeholders (`{{text}}`, `{{source_id}}`, `{{max_blocks}}`)
- The Appendix A decision tree (embedded verbatim as a numbered decision sequence)
- Staleness-risk defaults per type (code/prompt = high, quote = low, transcript = medium)
- The exact required JSON output schema
- At least one few-shot example with multiple block types

This is the most complex of the five prompt files — it embeds a decision tree and handles
four distinct VerbatimType values, each with different optional fields.

---

## Module contract

**File type**: Static Markdown (loaded at runtime by `prompt_loader.py`)

**Input variables** — injected by `load_prompt("extract_verbatim", ctx)` via the
double-brace substitution mechanism (`{{var}}`):

| Variable | Source in `s4b_verbatim.py` | Purpose |
|---|---|---|
| `{{text}}` | `item.raw_text[:8000]` | Source content (capped at 8 000 chars) |
| `{{source_id}}` | `item.raw_id` | Context reference — not output by LLM |
| `{{max_blocks}}` | `config.vault.max_verbatim_blocks_per_note` (default 10) | Upper limit on returned blocks |

**LLM output** — raw JSON, no markdown fences, matching this exact schema:

```json
{
  "verbatim_blocks": [
    {
      "type": "code|prompt|quote|transcript",
      "content": "<exact text, whitespace preserved>",
      "lang": "<python|yaml|bash|en|ru|...>",
      "staleness_risk": "low|medium|high",
      "attribution": "<Author, Title, p.N>",
      "timestamp": "<HH:MM:SS>",
      "model_target": "<model-name>"
    }
  ]
}
```

**Field-by-field mapping to `VerbatimBlock`:**

| JSON field | VerbatimBlock field | Notes |
|---|---|---|
| `type` | `type` | VerbatimType enum: code / prompt / quote / transcript |
| `content` | `content` | Exact text; model MUST NOT paraphrase or trim |
| `lang` | `lang` | Programming language for code; ISO 639-1 for others (e.g. "en", "ru") |
| `staleness_risk` | `staleness_risk` | StatenessRisk enum: low / medium / high |
| `attribution` | `attribution` | Quotes only; omit field for code/prompt/transcript |
| `timestamp` | `timestamp` | Transcripts only (HH:MM:SS); omit for all other types |
| `model_target` | `model_target` | Prompts only (e.g. "gpt-4o"); omit if unknown or not applicable |

**Explicitly excluded from LLM output** (set in Python by `s4b_verbatim.py`):
- `source_id` — set to `item.raw_id` after parsing; must NOT appear in LLM output schema
- `added_at` — set to current datetime in pipeline; must NOT appear in LLM output schema

**Consumed by**: `VerbatimBlock` in `agent/core/models.py` via `s4b_verbatim.py`:

```python
blocks.append(VerbatimBlock(
    type=VerbatimType(b.get("type", "quote")),
    content=b["content"],
    lang=b.get("lang", ""),
    source_id=item.raw_id,                      # Python-set
    staleness_risk=StatenessRisk(risk_str),      # falls back to _DEFAULT_STALENESS[vtype]
    attribution=b.get("attribution", ""),
    timestamp=b.get("timestamp", ""),
    model_target=b.get("model_target", ""),
))
```

---

## Key implementation notes

### File structure (required — mirrors classify.md and summarize.md)

```
---
version: 1.0
task: verbatim_extraction
output_format: json
---

## System
<role / persona block>

## Input variables
<table of {{variable}} placeholders>

## Decision tree (Appendix A — embedded verbatim)
<numbered decision sequence — must be character-for-character identical to arch Appendix A>

## Verbatim block rules
<type-specific guidance, staleness defaults, lang field rules>

## Output format
<schema block>

## Examples
### Example 1
...

## Constraints
<hard rules>
```

### Authoring constraints (from feature spec feature-tool-prompt-files.md)

1. **YAML front-matter** MUST include `version: 1.0`, `task: verbatim_extraction`,
   `output_format: json`. Note: `classify.md` omits `version` from its front-matter
   (uses `prompt_name` instead) — `extract_verbatim.md` MUST use the `version` key.
2. **Variable syntax**: `{{double_braces}}` — matched by `prompt_loader.py`'s
   substitution mechanism. Single-brace `{…}` is NOT used.
3. **Raw JSON output**: instruct the model to output ONLY the JSON object — no
   wrapping code fences, no prose before or after.
4. **Token budget**: total prompt (excluding `{{text}}` expansion) MUST stay under
   1 200 tokens. Appendix A and few-shot examples together must fit this budget; use
   compact few-shot blocks (not full realistic code).
5. **Local LLM compatible**: no function-calling syntax; no chain-of-thought requiring
   multi-turn context. Works on Mistral 7B / Llama 3 8B (Q4).

### Appendix A decision tree — embedding rules

The decision tree MUST be embedded as a numbered decision sequence in a dedicated
section (e.g. `## Decision tree`). It must be logically identical to Appendix A in
`docs/ARCHITECTURE.md`:

```
1. Does the passage contain exact source code, config, or commands?
   YES → type: "code", staleness_risk: "high"
   NO → continue

2. Is it an LLM system prompt or few-shot instruction block?
   YES → type: "prompt", staleness_risk: "high"; add model_target if identifiable
   NO → continue

3. Is it directly attributed to a named author with quotation marks?
   YES → type: "quote", staleness_risk: "low"; extract attribution
   NO → continue

4. Is it a timestamped direct-speech segment from audio/video?
   YES → type: "transcript", staleness_risk: "medium"; extract timestamp
   NO → do NOT create a verbatim block; include in summary instead
```

This numbered format is preferred over the nested-YES/NO format in the arch doc
because it is more parseable by small quantised models.

### Staleness defaults and overrides

State these inline, immediately after the decision tree:

| type | staleness_risk default |
|---|---|
| code | high |
| prompt | high |
| quote | low |
| transcript | medium |

The model MAY override the default if the content signals otherwise (e.g. a timeless
quote from a foundational text about evergreen principles may warrant "low" even though
the default would not apply). Instruct the model to default to the table and only
override with a short rationale embedded in its reasoning (not in the JSON).

### max_blocks priority ordering

Instruct the model explicitly:
> If more than `{{max_blocks}}` verbatim-worthy passages exist, keep only the
> highest-signal blocks in this priority order: code > prompt > quote > transcript.

### `lang` field semantics

- For **code/prompt** blocks: use the programming language or config format name
  (e.g. `"python"`, `"yaml"`, `"bash"`, `"json"`, `"dockerfile"`, `"sql"`).
  Use `"text"` if language cannot be determined.
- For **quote/transcript** blocks: use the ISO 639-1 two-letter language code of
  the spoken/written language (e.g. `"en"`, `"ru"`, `"de"`). Default `"en"` if
  language is unclear.

### Optional field omission rules

Explicitly instruct the model:
- `attribution`: include ONLY for `type: "quote"`. Omit for all other types.
  Format: `"Author, Title, p.N"` where available; `"Author"` if page unknown.
- `timestamp`: include ONLY for `type: "transcript"`. Omit for all other types.
  Format: `"HH:MM:SS"`.
- `model_target`: include ONLY for `type: "prompt"` when a target model is
  identifiable in the text. Omit when unknown or not applicable.

All three optional fields MUST be omitted (not set to null or "") when not applicable,
to prevent null-injection into `VerbatimBlock`.

### Few-shot example requirements

Include exactly **one complete few-shot example** demonstrating:
- At least 2 distinct block types (code + quote recommended; compact blocks)
- Correct `staleness_risk` per type
- `attribution` present on the quote block, absent on the code block
- `model_target` omitted (not null) on non-prompt blocks
- Compact, realistic but short content values (≤ 3 lines each)
- The LLM output must show the top-level `{"verbatim_blocks": [...]}` wrapper
- Example JSON must be valid and parseable into `list[VerbatimBlock]`

### `content` preservation rule

Instruct the model:
> Preserve the exact text including whitespace and indentation for code/prompt blocks.
> For quote/transcript blocks, include the minimum passage that conveys the key
> insight — do not excerpt mid-sentence, and do not paraphrase.

### Text cap note

`{{text}}` is capped at 8 000 characters by the stage code. Instruct the model to
work with whatever is provided without assuming truncation means the source is complete.

### Source ID usage

`{{source_id}}` is provided as context so the model can reference the source when
identifying transcript timestamps or attribution. It is NOT part of the output schema —
the model MUST NOT include it in any block.

---

## Data model changes (if any)

None. `VerbatimBlock`, `VerbatimType`, and `StatenessRisk` in `agent/core/models.py`
are already specified (IN_PROGRESS models-py spec). The prompt file does not add or
modify any Pydantic model.

---

## LLM prompt file needed

**This spec IS the prompt file** — `prompts/extract_verbatim.md` is the deliverable.
No additional prompt file is required.

---

## Tests required

- **unit: `tests/unit/test_prompt_extract_verbatim.py`**
  - `test_prompt_file_exists` — `prompts/extract_verbatim.md` is present on disk
  - `test_frontmatter_fields` — YAML front-matter contains `version`, `task`,
    `output_format: json`
  - `test_all_input_variables_present` — file body contains all three `{{…}}`
    placeholders: `text`, `source_id`, `max_blocks`
  - `test_decision_tree_embedded` — file body contains all four decision nodes
    (look for substrings: `"code"`, `"prompt"`, `"quote"`, `"transcript"` in a
    decision-sequence section)
  - `test_staleness_defaults_stated` — file body contains "code" with "high",
    "quote" with "low", "transcript" with "medium" (confirms defaults table)
  - `test_priority_ordering_instruction` — file body mentions priority order
    (look for substring "code > prompt > quote > transcript" or equivalent)
  - `test_no_excluded_fields_in_schema` — file body does NOT contain `source_id`
    or `added_at` in the output schema section (those are Python-set)
  - `test_optional_fields_omit_instruction` — file body instructs to OMIT
    (not null) `attribution`, `timestamp`, `model_target` when not applicable
  - `test_example_output_parses_to_verbatim_blocks` — extract the JSON block
    from the few-shot example and assert each element can construct
    `VerbatimBlock(**block_data | {"source_id": "test"})` without error
  - `test_example_has_multiple_block_types` — the few-shot JSON example contains
    at least 2 distinct `type` values
  - `test_token_budget` — render the prompt with an 8 000-char dummy `text`,
    count tokens via `tiktoken` (or char-count ÷ 4 heuristic), assert the static
    portion (excluding `{{text}}` substitution) is ≤ 1 200 tokens
  - `test_no_markdown_fence_in_example_output` — confirm the few-shot example
    JSON output is NOT wrapped in triple-backtick fences
  - `test_verbatim_blocks_wrapper_present` — output schema shows top-level
    `"verbatim_blocks"` key (not a bare array)

- **integration**: none required for a static prompt file; integration coverage is
  provided by `tests/integration/test_pipeline_verbatim.py` once `s4b_verbatim.py`
  is built.

---

## Explicitly out of scope

- Any logic from `s4b_verbatim.py` (Python post-processing, staleness fallback logic)
- Setting `source_id` or `added_at` in LLM output — Python-only fields
- Phase 2 atom extraction or bi-directional link proposals
- Hardcoding `max_blocks` — MUST come from `{{max_blocks}}` at runtime
- Chain-of-thought / scratchpad instructions ("think step by step")
- Function-calling or tool-use syntax
- Generating a summary or key ideas — scope of `prompts/summarize.md`
- Entity/people extraction — scope of `prompts/extract_entities.md`
- Tag suggestions — scope of `prompts/suggest_tags.md`
- Multiple few-shot examples (token budget constraint; one is sufficient)
- `verbatim/*` or `index/*` tags — these are agent-assigned, not LLM-output

---

## Open questions

None — all design decisions are resolved by:
- `docs/ARCHITECTURE.md` §9 (extract_verbatim.md prompt draft) and Appendix A
  (decision tree)
- `agent/core/models.py` spec (`VerbatimBlock`, `VerbatimType`, `StatenessRisk`)
- `agent/stages/s4b_verbatim.py` reference code in ARCHITECTURE.md §6.2
- `feature-tool-prompt-files.md` (cross-cutting constraints and verbatim-specific rules)
- Structural precedent from `prompts/classify.md` and `prompts/summarize.md` (DONE)
