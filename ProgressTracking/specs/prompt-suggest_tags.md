# Spec: prompts/suggest_tags.md
slug: prompt-suggest_tags
layer: prompts
phase: 1
arch_section: §9 Prompts, §6.1 Stage 2 (Classify)

---

## Problem statement

Stage 2 (`s2_classify.py`) makes a supplementary LLM call after the primary classify
pass to produce a focused, taxonomy-constrained tag list. The classify prompt already
returns a preliminary `suggested_tags` array, but `suggest_tags.md` is the dedicated
prompt that concentrates solely on tag selection — constrained to the 10 allowed
namespaces, with full per-namespace guidance and the taxonomy listed inline.

`prompts/suggest_tags.md` is the **static text file** that defines: the tagger role,
input variable placeholders, the 10 allowed tag namespaces (with `verbatim/*` and
`index/*` explicitly forbidden), selection rules for each namespace, and one few-shot
example. Its output is a plain JSON array of strings consumed directly into
`ClassificationResult.suggested_tags`.

---

## Module contract

**File type**: Static Markdown (loaded at runtime by `prompt_loader.py`)

**Input variables** — injected by `load_prompt("suggest_tags", ctx)` via `str.format_map()`:

| Variable | Source in `s2_classify.py` | Purpose |
|---|---|---|
| `{{title}}` | `NormalizedItem.title` | Title of the source content |
| `{{source_type}}` | `NormalizedItem.source_type.value` | Determines `source/*` tag selection |
| `{{text_preview}}` | `NormalizedItem.raw_text[:2000]` | Content snapshot for context-aware tagging |
| `{{domain}}` | `ClassificationResult.domain` | Output of the preceding classify call |
| `{{subdomain}}` | `ClassificationResult.subdomain` | Output of the preceding classify call |
| `{{content_age}}` | `ClassificationResult.content_age.value` | Helps select `status/*` and `type/*` tags |
| `{{language}}` | `ClassificationResult.language` | ISO 639-1 code; used for `lang/*` tag |

**LLM output** — raw JSON array of strings, no markdown fences, no outer object wrapper:

```json
["domain/professional_dev", "subdomain/ai_tools", "source/youtube", "type/how-to", "lang/en"]
```

**Output schema contract:**
- Top-level value MUST be a JSON array (`[...]`), NOT an object (`{...}`)
- Every element MUST be a string in `namespace/value` format
- Allowed namespaces: `source/`, `domain/`, `subdomain/`, `proj/`, `ref/`,
  `relationship/`, `status/`, `entity/`, `type/`, `lang/`
- NEVER include `verbatim/*` or `index/*` — these are agent-assigned only
- No duplicates; no empty strings; no null values

**Field mapping:**

| Prompt output | `ClassificationResult` field | Notes |
|---|---|---|
| Array of tag strings | `suggested_tags: list[str]` | Replaces the `suggested_tags` field from the classify call |

**Calling site** (in `s2_classify.py`, after classify call completes):

```python
tags_prompt = load_prompt("suggest_tags", {
    "title": item.title,
    "source_type": item.source_type.value,
    "text_preview": item.raw_text[:2000],
    "domain": classification.domain,
    "subdomain": classification.subdomain,
    "content_age": classification.content_age.value,
    "language": classification.language,
})
tags_response = await llm.chat([
    {"role": "system", "content": "You are a knowledge tagging assistant. Respond ONLY with a valid JSON array."},
    {"role": "user", "content": tags_prompt},
], temperature=0.0)
classification.suggested_tags = json.loads(tags_response)
```

**Consumed by**: `ClassificationResult.suggested_tags` in `agent/core/models.py`

---

## Key implementation notes

### File structure (required — mirrors established pattern from classify.md)

```
---
version: 1.0
task: tag_suggestion
output_format: json
---

## System
<tagger role block>

## Input
<table of {{variable}} placeholders>

## Tag namespaces (allowed set)
<list of 10 namespaces with per-namespace guidance>

## Forbidden namespaces
<verbatim/* and index/* — never suggest these>

## Output format
<JSON array schema>

## Examples
### Example 1
<compact few-shot example>

## Constraints
<hard rules>
```

### Authoring constraints (cross-cutting rules — same as all other prompt files)

1. **YAML front-matter** MUST include `version: 1.0`, `task: tag_suggestion`,
   `output_format: json`.
2. **Variable syntax**: `{{double_braces}}` — matched by `prompt_loader.py`'s
   `str.format_map()`. Single-brace `{…}` is NOT used.
3. **Raw JSON output**: instruct the model to output ONLY a JSON array — no wrapping
   code fences, no prose before or after, no outer object key.
4. **Token budget**: total prompt (excluding `{{text_preview}}` expansion) MUST stay
   under 1 200 tokens. One compact few-shot example is sufficient.
5. **Local LLM compatible**: no function-calling syntax; no chain-of-thought requiring
   multi-turn context. Works on Mistral 7B / Llama 3 8B (Q4).

### Namespace guidance (must appear in prompt body)

The prompt MUST list all 10 allowed namespaces with concrete selection guidance:

| Namespace | Selection rule |
|---|---|
| `source/` | One tag matching `{{source_type}}`: `source/youtube`, `source/pdf`, `source/article`, `source/ms_teams`, `source/note`, etc. Always include exactly one. |
| `domain/` | One tag matching `{{domain}}` (e.g. `domain/professional_dev`). Always include exactly one. |
| `subdomain/` | One tag matching `{{subdomain}}` (e.g. `subdomain/ai_tools`). Always include exactly one. |
| `proj/` | Include only if the text explicitly names a project that maps to a project reference. Omit if no project name is identifiable. |
| `ref/` | Use `ref/person`, `ref/project`, `ref/work`, `ref/personal` when the note is primarily about a reference entity. Omit otherwise. |
| `relationship/` | Include only if the source is primarily about a specific relationship (e.g. a meeting note with a colleague). Omit otherwise. |
| `status/` | Use `status/new` (default), `status/review` (if `ai_confidence < 0.7`), or `status/processed`. Default to `status/new`. |
| `entity/` | Add `entity/person`, `entity/company`, or `entity/tool` when those entities are central to the content. |
| `type/` | Select from: `type/concept`, `type/how-to`, `type/reference`, `type/meeting`, `type/reflection`. Base on note structure and `{{content_age}}`. |
| `lang/` | One tag for the primary language: `lang/en`, `lang/ru`, etc. Always include exactly one, derived from `{{language}}`. |

### Forbidden namespaces (must be stated explicitly)

The prompt MUST explicitly state:
> NEVER include `verbatim/*` tags (e.g. `verbatim/code`, `verbatim/quote`).
> These are assigned automatically by the agent after verbatim extraction (Stage 4b).
> NEVER include `index/*` tags. These are reserved for `_index.md` files only.

### Output cardinality guidance

Instruct the model:
- Minimum 3 tags (always: at least `source/*`, `domain/*`, `lang/*`)
- Maximum 10 tags
- Always include exactly one `source/*`, one `domain/*`, one `subdomain/*`, one `lang/*`
- Omit optional namespaces (`proj/`, `ref/`, `relationship/`, `entity/`) when not applicable

### Few-shot example requirements

Include exactly **one complete few-shot example** demonstrating:
- A YouTube source with domain `professional_dev`, subdomain `ai_tools`, language `en`
- Resulting array containing: `source/youtube`, `domain/professional_dev`,
  `subdomain/ai_tools`, `type/how-to`, `entity/tool`, `lang/en`, `status/new`
- Output is a bare JSON array (no wrapping key, no code fences)
- Array has between 4–8 strings

### `{{text_preview}}` cap

`{{text_preview}}` is capped at 2 000 characters by the calling code. The model must
base its tag selection on whatever is provided. Tags are primarily driven by
`{{domain}}`, `{{subdomain}}`, `{{source_type}}`, and `{{language}}` — the text
preview provides supporting context only.

---

## Data model changes (if any)

None. `ClassificationResult.suggested_tags: list[str]` already exists in
`agent/core/models.py` (IN_PROGRESS spec). No new Pydantic model is introduced.
The output is a plain `list[str]` parsed from the JSON array.

---

## LLM prompt file needed

**This spec IS the prompt file** — `prompts/suggest_tags.md` is the deliverable.
No additional prompt file is required.

---

## Tests required

- **unit: `tests/unit/test_prompt_suggest_tags.py`**
  - `test_prompt_file_exists` — `prompts/suggest_tags.md` is present on disk
  - `test_frontmatter_fields` — YAML front-matter has `version`, `task: tag_suggestion`,
    `output_format: json`
  - `test_all_input_variables_present` — file body contains all seven `{{…}}`
    placeholders: `title`, `source_type`, `text_preview`, `domain`, `subdomain`,
    `content_age`, `language`
  - `test_all_allowed_namespaces_listed` — file body mentions all 10 allowed namespace
    prefixes: `source/`, `domain/`, `subdomain/`, `proj/`, `ref/`, `relationship/`,
    `status/`, `entity/`, `type/`, `lang/`
  - `test_forbidden_namespaces_stated` — file body explicitly mentions `verbatim/` and
    `index/` as NEVER-suggest namespaces
  - `test_output_is_array_not_object` — the output schema section in the file instructs
    the model to return a JSON array (not an object); file does NOT show `{"tags": [...]}`
    in the output schema
  - `test_example_output_is_valid_json_array` — extract the few-shot example JSON from
    the file; assert `json.loads(example)` returns a `list`
  - `test_example_output_has_required_namespaces` — example array contains at least one
    `source/*`, one `domain/*`, one `subdomain/*`, one `lang/*` tag
  - `test_example_output_no_forbidden_tags` — example array contains no `verbatim/*` or
    `index/*` tags
  - `test_example_output_all_strings` — every element in the example array is a string
    in `namespace/value` format (matches regex `r'^[a-z_]+/[a-z0-9_\-]+$'`)
  - `test_no_markdown_fence_in_example_output` — the example JSON array is NOT wrapped
    in triple-backtick fences in the LLM output section
  - `test_cardinality_instructions` — file body states the minimum (3) and maximum (10)
    tag count guidance
  - `test_token_budget` — render prompt with 2 000-char dummy `text_preview`, count
    tokens via `tiktoken` (or char-count ÷ 4 heuristic), assert static portion
    (excluding `{{text_preview}}`) is ≤ 1 200 tokens

- **integration**: none required for a static prompt file; integration coverage is
  provided by `tests/integration/test_llm_ollama.py` once `s2_classify.py` is built.

---

## Explicitly out of scope

- Suggesting `verbatim/*` or `index/*` tags — forbidden; agent-assigned only
- Outputting a JSON object with a `"tags"` key — output MUST be a bare array
- Hardcoding domain or subdomain values — they come from `{{domain}}` / `{{subdomain}}`
- Suggesting tags for Phase 2 namespaces (atom types, bi-directional links)
- Entity extraction or summarisation — scope of `extract_entities.md` / `summarize.md`
- Classification of domain / subdomain — scope of `classify.md`
- Verbatim block identification — scope of `extract_verbatim.md`
- Multiple few-shot examples (token budget constraint; one is sufficient)
- Chain-of-thought / scratchpad instructions ("think step by step")
- Function-calling or tool-use syntax

---

## Open questions

None — all design decisions are resolved by:
- `docs/REQUIREMENTS.md` §4 (Tag Taxonomy — namespace list and forbidden namespaces)
- `docs/ARCHITECTURE.md` §9 (Prompts — `suggest_tags.md` output feeds `ClassificationResult.suggested_tags`)
- `ProgressTracking/specs/feature-tool-prompt-files.md` (cross-cutting constraints and
  tag taxonomy extra constraints)
- `agent/core/models.py` spec (`ClassificationResult.suggested_tags: list[str]`)
- `prompts/classify.md` (DONE) — establishes the upstream classification context that
  this prompt receives as `{{domain}}`, `{{subdomain}}`, `{{language}}`
