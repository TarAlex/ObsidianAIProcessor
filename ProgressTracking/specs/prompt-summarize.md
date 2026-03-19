# Spec: prompts/summarize.md
slug: prompt-summarize
layer: prompts
phase: 1
arch_section: §9 Prompts, §6.1 Stage 4a (Summarize)

## Problem statement

Stage 4a (`s4a_summarize.py`) calls `load_prompt("summarize", ctx)` and passes the
rendered string to the LLM. The LLM must return a JSON object that maps directly to
`SummaryResult` — containing a prose summary, key ideas, action items (for meeting
content only), brief quote excerpts, and a placeholder `atom_concepts` list (always `[]`
in Phase 1).

`prompts/summarize.md` is a **static text file** authored by `dev:prompt-author`. It
defines the system role, input variable placeholders, the exact required JSON output
schema, and one few-shot example. It is local-LLM-compatible and follows the same
structural conventions as the completed `prompts/classify.md`.

---

## Module contract

**File type**: Static Markdown (loaded at runtime by `prompt_loader.py`)

**Input variables** — injected by `load_prompt("summarize", ctx)` via `str.format_map()`:

| Variable | Source | Purpose |
|---|---|---|
| `{{title}}` | `NormalizedItem.title` | Title of the source content |
| `{{source_type}}` | `NormalizedItem.source_type.value` | Format hint (youtube / article / pdf / note / ms_teams / etc.) |
| `{{language}}` | `ClassificationResult.language` | ISO 639-1 primary language — summary must match |
| `{{domain_path}}` | `ClassificationResult.domain_path` | Context for thematic focus (e.g. `"professional_dev/ai_tools"`) |
| `{{text}}` | `NormalizedItem.raw_text[:6000]` | Body content capped to avoid token overflow |
| `{{detected_people}}` | `", ".join(ClassificationResult.detected_people)` | Known persons to wikilink; empty string if none |
| `{{detected_projects}}` | `", ".join(ClassificationResult.detected_projects)` | Known projects to wikilink; empty string if none |

**LLM output** — raw JSON, no markdown fences, matching this exact schema:

```json
{
  "summary": "<2–4 sentence prose summary in {{language}}>",
  "key_ideas": ["<key idea 1>", "<key idea 2>", "<key idea 3>"],
  "action_items": ["<action item 1>"],
  "quotes": ["<brief excerpt ≤ 40 words>"],
  "atom_concepts": []
}
```

**Field-by-field mapping to `SummaryResult`:**

| JSON field | SummaryResult field | Notes |
|---|---|---|
| `summary` | `summary` | 2–4 sentences; insert `[[Name]]` wikilinks for `{{detected_people}}` and `{{detected_projects}}` when mentioned |
| `key_ideas` | `key_ideas` | 3–7 short declarative strings; no markdown inside strings |
| `action_items` | `action_items` | Non-empty **only** for meeting content (`ms_teams`) or text with explicit action language; `[]` otherwise |
| `quotes` | `quotes` | Brief excerpts enriching the summary (< 40 words each); NOT full verbatim blocks; `[]` if no notable excerpts |
| `atom_concepts` | `atom_concepts` | ALWAYS `[]` — Phase 2 only; never populated in Phase 1 |

**Explicitly excluded from LLM output** (populated by pipeline after this stage):
- `verbatim_blocks` — populated by `s4b_verbatim.py`; MUST NOT appear in this prompt's output schema

**Consumed by**: `SummaryResult` in `agent/core/models.py`

```python
SummaryResult(
    summary=data["summary"],
    key_ideas=data["key_ideas"],
    action_items=data["action_items"],
    quotes=data["quotes"],
    atom_concepts=data["atom_concepts"],   # always []
    # verbatim_blocks populated separately by s4b_verbatim
)
```

---

## Key implementation notes

### File structure (required — mirrors classify.md)

```
---
version: 1.0
task: summarize
output_format: json
---

## System
<role / persona block>

## Input variables
<table or list of {{variable}} placeholders>

## Summarization rules
<task-specific guidance sections>

## Output format
<schema block>

## Examples
### Example 1
...

## Constraints
<hard rules>
```

### Authoring constraints (from feature spec feature-tool-prompt-files.md)

1. **YAML front-matter** MUST include `version`, `task`, `output_format: json`.
2. **Variable syntax**: `{{double_braces}}` — matched by `prompt_loader.py`'s
   `str.format_map()`. Single-brace `{…}` is NOT used.
3. **Raw JSON output**: instruct the model to output ONLY the JSON object — no wrapping
   code fences, no prose before or after.
4. **Token budget**: total prompt (excluding `{{text}}` expansion) MUST stay under
   1 200 tokens. Use abbreviated few-shot examples.
5. **Local LLM compatible**: no function-calling syntax; no chain-of-thought that
   requires multi-turn context. Works on Mistral 7B / Llama 3 8B (Q4).

### Wikilink insertion

The prompt receives `{{detected_people}}` and `{{detected_projects}}` from
`ClassificationResult` (comma-separated strings). When any name from these lists appears
in the generated `summary`, the model MUST wrap it in `[[Name]]` Obsidian wikilink
syntax. Key ideas and other fields do NOT need wikilinks. If both lists are empty,
instruct the model to skip wikilink insertion entirely.

### `action_items` scoping rule

Non-empty **only** when:
- `{{source_type}}` is `ms_teams`, OR
- The text contains explicit meeting-style action language (e.g. "Action:", "TODO:",
  "we agreed to", "assigned to", timestamped speaker turns)

For all other source types (article, youtube, pdf, note, audio), return `[]`.
Each action item is a short imperative sentence; no bullet marker, no trailing period.

### `quotes` scoping rule

`quotes` are **brief excerpts** (< 40 words each) that enrich the summary — notable
statistics, pithy statements, or key findings worth highlighting inline. These are NOT
full verbatim blocks; the verbatim extraction stage handles those. Return `[]` if no
short excerpt is worth highlighting.

### `atom_concepts` Phase 2 guard

`atom_concepts` MUST always be `[]` in Phase 1. The prompt MUST explicitly instruct:
> "Return an empty array for `atom_concepts`. This field is reserved for a future phase."

The few-shot example output must show `"atom_concepts": []`.

### Language constraint

`summary` and `key_ideas` MUST be written in the same language as `{{language}}`
(ISO 639-1). English is used as fallback only when `{{language}}` is empty or
unrecognised.

### Text cap and truncation note

`{{text}}` is capped at 6 000 characters by the stage code. Instruct the model to work
with whatever is provided without assuming truncation means the source is complete.

### Few-shot example requirements

- Include exactly **one complete few-shot example**: a short `TEXT`, `TITLE`,
  `SOURCE_TYPE`, `DOMAIN_PATH`, `LANGUAGE`, `DETECTED_PEOPLE`, `DETECTED_PROJECTS`
  block followed by the expected JSON output.
- The example MUST demonstrate:
  - `source_type` that is NOT `ms_teams` → `action_items: []`
  - Non-empty `key_ideas` (3+ items)
  - At least one `quotes` entry
  - `atom_concepts: []`
  - `[[wikilink]]` in `summary` for at least one detected person or project
- Example JSON must be valid, complete, contain all 5 output fields, and parse without
  error into `SummaryResult(**data)`.

---

## Data model changes (if any)

None. `SummaryResult` in `agent/core/models.py` is already complete (DONE). The
`verbatim_blocks` field remains populated exclusively by `s4b_verbatim.py` after this
stage — it is NOT produced by this prompt.

---

## LLM prompt file needed

**This spec IS the prompt file** — `prompts/summarize.md` is the deliverable.

No additional prompt file is required.

---

## Tests required

- **unit: `tests/unit/test_prompt_summarize.py`**
  - `test_prompt_file_exists` — `prompts/summarize.md` is present on disk
  - `test_frontmatter_fields` — YAML front-matter has `version`, `task`,
    `output_format: json`
  - `test_all_input_variables_present` — file contains all seven `{{…}}` placeholders:
    `title`, `source_type`, `language`, `domain_path`, `text`,
    `detected_people`, `detected_projects`
  - `test_no_verbatim_blocks_in_output_schema` — file body does NOT contain the string
    `verbatim_blocks` in the output schema / instructions section (populated by s4b, not
    this prompt)
  - `test_atom_concepts_always_empty_instruction` — file body contains text asserting
    `atom_concepts` is always `[]` or "reserved for Phase 2" (Phase 2 guard present)
  - `test_example_output_parses_to_summary_result` — extract the JSON block from the
    few-shot example and assert `SummaryResult(**data)` constructs successfully
  - `test_token_budget` — render the prompt with a 6 000-char dummy `text`, count tokens
    via `tiktoken` (or char-count ÷ 4 heuristic), assert the static portion (excluding
    `{{text}}` substitution) is ≤ 1 200 tokens
  - `test_no_markdown_fence_in_example_output` — confirm the few-shot example JSON
    output is NOT wrapped in triple-backtick fences
  - `test_wikilink_instruction_present` — file body contains `[[` or the word
    `wikilink` — ensures Obsidian link insertion is instructed
  - `test_action_items_meeting_only_instruction` — file body restricts `action_items`
    to meeting content (text contains "ms_teams" or "meeting" in the rule section)

- **integration**: none required for a static prompt file; integration coverage is
  provided by `tests/integration/test_llm_ollama.py` once `s4a_summarize.py` is built.

---

## Explicitly out of scope

- Verbatim block extraction — handled by `prompts/extract_verbatim.md` and `s4b_verbatim.py`
- Atom concept extraction — Phase 2 only; `atom_concepts` MUST be `[]`
- Hardcoding domain names — context arrives via `{{domain_path}}` at runtime
- Populating `staleness_risk`, `domain_path`, or other pipeline-computed fields in output
- Entity/people/project discovery — done at Stage 2 (classify); this prompt only uses
  the already-detected lists to insert wikilinks
- Generating summary in a different language from `{{language}}` (no translation)
- Multiple few-shot examples (token budget constraint)
- Chain-of-thought / scratchpad instructions ("think step by step")
- Function-calling or tool-use syntax
- Any Phase 2 logic (atom extraction, bi-directional link proposals)

---

## Open questions

None — all design decisions are resolved by ARCHITECTURE.md §9, REQUIREMENTS.md §6.1
(Stage 4a), `agent/core/models.py` (SummaryResult), and the completed `prompt-classify`
spec and `prompts/classify.md` as structural references.
