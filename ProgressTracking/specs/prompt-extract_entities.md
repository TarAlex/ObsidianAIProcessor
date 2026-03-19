# Spec: prompts/extract_entities.md
slug: prompt-extract_entities
layer: prompts
phase: 1
arch_section: §9 Prompts (extract_entities.md), §2 Project Structure, §6.1 Stage 6c

---

## Problem statement

Stage 2 (`s2_classify.py`) extracts `detected_people` and `detected_projects` as simple
name lists from the classify prompt. That is sufficient for routing and wikilink insertion
in summaries, but not sufficient to create or update `REFERENCES/` entries, which require
relationship type, context description, and project role.

`reference_linker.py` (`agent/tasks/reference_linker.py`) calls
`load_prompt("extract_entities", ctx)` and uses the output to create or update
`PersonReference` and `ProjectReference` records in `REFERENCES/people/` and
`REFERENCES/projects_*/`.

`prompts/extract_entities.md` is the **static text file** that instructs the LLM to
return a structured JSON object containing enriched entity data for every person and
project mentioned in the source text. It is local-LLM compatible and follows the
structural conventions established by `prompts/classify.md` and
`prompts/summarize.md` (both DONE).

---

## Module contract

**File type**: Static Markdown (loaded at runtime by `prompt_loader.py`)

**Input variables** — injected by `load_prompt("extract_entities", ctx)` via the
double-brace substitution mechanism (`{{var}}`):

| Variable | Source in `reference_linker.py` | Purpose |
|---|---|---|
| `{{title}}` | `NormalizedItem.title` | Title of the source content |
| `{{text}}` | `NormalizedItem.raw_text[:4000]` | Source content (capped at 4 000 chars) |
| `{{detected_people}}` | `", ".join(ClassificationResult.detected_people)` | Names already identified by classify stage; focus enrichment on these |
| `{{detected_projects}}` | `", ".join(ClassificationResult.detected_projects)` | Project names already identified; empty string if none |

**LLM output** — raw JSON, no markdown fences, matching this exact schema:

```json
{
  "people": [
    {
      "full_name": "Jane Smith",
      "nickname": "",
      "relationship": "colleague|friend|family|mentor|client|other",
      "context": "<1–2 sentences describing who this person is in the context of this note>"
    }
  ],
  "projects": [
    {
      "project_name": "Vault Builder",
      "ref_type": "project_work|project_personal",
      "role": "<author's role or involvement, e.g. contributor, owner, stakeholder>",
      "context": "<1 sentence describing the project and its relevance to this note>"
    }
  ]
}
```

**Field-by-field mapping to `PersonReference` / `ProjectReference`:**

| JSON field | Model field | Notes |
|---|---|---|
| `people[].full_name` | `PersonReference.full_name` | Must match exactly the name in `{{detected_people}}` |
| `people[].nickname` | `PersonReference.nickname` | Empty string if no nickname is inferrable; OMIT if unknown |
| `people[].relationship` | `PersonReference.relationship` | One of: colleague, friend, family, mentor, client, other |
| `people[].context` | `PersonReference.context` | 1–2 sentences max |
| `projects[].project_name` | `ProjectReference.project_name` | Must match name in `{{detected_projects}}` |
| `projects[].ref_type` | `ProjectReference.ref_type` | `"project_work"` or `"project_personal"` |
| `projects[].role` | `ProjectReference.role` | Short role label; `"unknown"` if not determinable |
| `projects[].context` | `ProjectReference.context` (stored in `notes/`) | 1 sentence |

**Explicitly excluded from LLM output** (set in Python by `reference_linker.py`):

- `ref_id` — generated as `PERSON-YYYYMMDD-HHmmss` / `PROJ-YYYYMMDD-HHmmss`
- `date_added`, `date_modified` — set at write time
- `tags`, `linked_projects`, `team`, `domains` — set by pipeline after the LLM call
- `birthday`, `start_date`, `end_date`, `status` — not inferrable from source text

**Consumed by**: `PersonReference` and `ProjectReference` in `agent/core/models.py`
via `agent/tasks/reference_linker.py`:

```python
for p in data.get("people", []):
    PersonReference(
        ref_id=generate_ref_id("PERSON"),
        full_name=p["full_name"],
        nickname=p.get("nickname", ""),
        relationship=p.get("relationship", "other"),
        context=p.get("context", ""),
        date_added=date.today(),
        date_modified=date.today(),
    )

for proj in data.get("projects", []):
    ProjectReference(
        ref_id=generate_ref_id("PROJ"),
        project_name=proj["project_name"],
        ref_type=proj.get("ref_type", "project_work"),
        role=proj.get("role", "unknown"),
        date_added=date.today(),
        date_modified=date.today(),
    )
```

---

## Key implementation notes

### File structure (required — mirrors classify.md and summarize.md)

```
---
version: 1.0
task: entity_extraction
output_format: json
---

## System
<role / persona block>

## Input variables
<table of {{variable}} placeholders>

## Entity extraction rules
<guidance on what qualifies as a person vs project, relationship types, ref_type inference>

## Output format
<schema block>

## Examples
### Example 1
...

## Constraints
<hard rules>
```

### Authoring constraints (same cross-cutting rules as other prompt files)

1. **YAML front-matter** MUST include `version: 1.0`, `task: entity_extraction`,
   `output_format: json`.
2. **Variable syntax**: `{{double_braces}}` — matched by `prompt_loader.py`'s
   substitution mechanism. Single-brace `{…}` is NOT used.
3. **Raw JSON output**: instruct the model to output ONLY the JSON object — no
   wrapping code fences, no prose before or after.
4. **Token budget**: total prompt (excluding `{{text}}` expansion) MUST stay under
   1 200 tokens. One compact few-shot example is sufficient.
5. **Local LLM compatible**: no function-calling syntax; no chain-of-thought requiring
   multi-turn context. Works on Mistral 7B / Llama 3 8B (Q4).

### Scope: people and projects only

The prompt MUST scope entity extraction to:
- **People**: named individuals mentioned in the source text who are from `{{detected_people}}`
- **Projects**: named work or personal projects from `{{detected_projects}}`

The prompt MUST NOT extract:
- Companies, organisations, or institutions (these flow via `entity/company` tags in classify)
- Tools or technologies (these flow via `suggest_tags.md`)
- Generic roles without a named person attached

### Focus on `{{detected_people}}` and `{{detected_projects}}`

Instruct the model:
> Focus exclusively on the people listed in `{{detected_people}}` and projects in
> `{{detected_projects}}`. Do not introduce new names or project names not in these lists.
> If `{{detected_people}}` is empty, return `"people": []`. If `{{detected_projects}}`
> is empty, return `"projects": []`.

This prevents the model from hallucinating additional entities and ensures the output
always aligns with the names already confirmed by the classify stage.

### `relationship` value constraints

The `relationship` field MUST be one of exactly these values:
`colleague`, `friend`, `family`, `mentor`, `client`, `other`

Instruct the model to default to `"other"` when the relationship type cannot be inferred
from context.

### `ref_type` inference rules

Instruct the model:
- `"project_work"` — professional projects: work deliverables, client engagements,
  enterprise initiatives, open-source contributions at work
- `"project_personal"` — personal projects: side projects, hobbies, home renovations,
  personal learning initiatives

Default to `"project_work"` when ambiguous.

### `nickname` omission rule

`nickname` MUST be omitted entirely (not set to null or `""`) when no nickname or
informal name is present in the source text. This prevents empty-string injection into
`PersonReference.nickname`.

Exception: if a nickname IS present in the text (e.g. "Bob (Robert Smith)"), include it.

### `context` length constraint

`context` for both people and projects MUST be 1–2 sentences maximum. Instruct the model:
> Write `context` as a factual 1–2 sentence description based only on evidence in the text.
> Do not infer biographical details not present in the source.

### Text cap note

`{{text}}` is capped at 4 000 characters by the calling code. The model should work with
whatever is provided. Entity enrichment does not require the full source text since
`{{detected_people}}` and `{{detected_projects}}` already anchor the extraction.

### Few-shot example requirements

Include exactly **one complete few-shot example** demonstrating:
- At least one person entry (with `relationship`, `context`; `nickname` omitted)
- At least one project entry (with `ref_type`, `role`, `context`)
- `relationship` value from the allowed set
- `nickname` field absent (not null, not `""`)
- `context` values ≤ 2 sentences
- The `{"people": [...], "projects": [...]}` top-level structure shown
- Example JSON must be valid and parseable into `PersonReference` / `ProjectReference`

### Empty-list handling

When `{{detected_people}}` or `{{detected_projects}}` is empty, the corresponding
array in the output MUST be `[]` (not absent, not null). Show this in the prompt instructions
and ensure the few-shot example's output structure includes both keys even when one is empty.

---

## Data model changes (if any)

None. `PersonReference` and `ProjectReference` in `agent/core/models.py` are already
specified (IN_PROGRESS models-py spec). No new Pydantic model is introduced; the prompt
output maps directly to existing model fields. The `ref_id`, `date_added`, `date_modified`,
`tags`, `linked_projects`, `team`, `domains`, and `status` fields are all Python-set.

---

## LLM prompt file needed

**This spec IS the prompt file** — `prompts/extract_entities.md` is the deliverable.
No additional prompt file is required.

---

## Tests required

- **unit: `tests/unit/test_prompt_extract_entities.py`**
  - `test_prompt_file_exists` — `prompts/extract_entities.md` is present on disk
  - `test_frontmatter_fields` — YAML front-matter contains `version`, `task`,
    `output_format: json`
  - `test_all_input_variables_present` — file body contains all four `{{…}}`
    placeholders: `title`, `text`, `detected_people`, `detected_projects`
  - `test_output_schema_has_people_and_projects` — file body contains both
    `"people"` and `"projects"` keys in the output schema section
  - `test_relationship_values_listed` — file body lists all six allowed relationship
    values: `colleague`, `friend`, `family`, `mentor`, `client`, `other`
  - `test_ref_type_values_listed` — file body mentions both `"project_work"` and
    `"project_personal"` ref_type values
  - `test_no_excluded_fields_in_schema` — file body does NOT contain `ref_id`,
    `date_added`, `date_modified`, `birthday`, `start_date`, or `end_date` in the
    output schema section (those are Python-set)
  - `test_nickname_omit_instruction` — file body instructs to OMIT (not null, not
    empty string) the `nickname` field when not present in source
  - `test_focus_on_detected_lists_instruction` — file body instructs to use ONLY
    names from `{{detected_people}}` / `{{detected_projects}}`
  - `test_empty_list_handling` — file body instructs to return `[]` (not absent)
    when either detected list is empty
  - `test_example_output_parses_to_models` — extract the JSON block from the
    few-shot example; assert each person entry contains at minimum `full_name`,
    `relationship`, `context`; assert each project entry contains at minimum
    `project_name`, `ref_type`, `role`, `context`
  - `test_example_has_both_people_and_projects` — few-shot JSON contains at least
    one entry in `people` and one entry in `projects`
  - `test_token_budget` — render the prompt with a 4 000-char dummy `text`, count
    tokens via `tiktoken` (or char-count ÷ 4 heuristic), assert the static portion
    (excluding `{{text}}` substitution) is ≤ 1 200 tokens
  - `test_no_markdown_fence_in_example_output` — confirm the few-shot example
    JSON output is NOT wrapped in triple-backtick fences
  - `test_context_length_instruction` — file body instructs `context` to be 1–2
    sentences maximum

- **integration**: none required for a static prompt file; integration coverage is
  provided once `agent/tasks/reference_linker.py` is built.

---

## Explicitly out of scope

- Extracting company, organisation, or institution entities — flow via `entity/company`
  tags in `prompts/classify.md`
- Extracting tool or technology entities — scope of `prompts/suggest_tags.md`
- Setting `ref_id`, `date_added`, `date_modified`, `birthday`, `status` in LLM output
  (all Python-set)
- Introducing new entity names not in `{{detected_people}}` or `{{detected_projects}}`
- Verbatim block extraction — scope of `prompts/extract_verbatim.md`
- Summarisation — scope of `prompts/summarize.md`
- Classification or domain assignment — scope of `prompts/classify.md`
- Tag suggestions — scope of `prompts/suggest_tags.md`
- Phase 2 atom extraction or bi-directional link proposals
- Multiple few-shot examples (token budget constraint; one is sufficient)
- Chain-of-thought / scratchpad instructions ("think step by step")
- Function-calling or tool-use syntax

---

## Open questions

None — all design decisions are resolved by:
- `docs/REQUIREMENTS.md` §2.2 (PersonReference, ProjectReference schemas) and §6.1
  (Stage 6c — references & links)
- `agent/core/models.py` spec (`PersonReference`, `ProjectReference` model fields)
- `prompts/classify.md` (DONE) — establishes the `detected_people` / `detected_projects`
  upstream contract that this prompt enriches
- Feature-layer structural precedent from `prompt-classify.md`, `prompt-summarize.md`,
  and `prompt-extract_verbatim.md` (all DONE or IN_PROGRESS)
