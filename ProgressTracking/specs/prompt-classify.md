# Spec: prompts/classify.md
slug: prompt-classify
layer: prompts
phase: 1
arch_section: §9 Prompts (classify.md schema)

## Problem statement

Stage 2 (`s2_classify.py`) calls `load_prompt("classify", ctx)` and feeds the result
to the LLM. The LLM must return a single JSON object that can be parsed and passed
directly to `ClassificationResult(**data, domain_path=…, staleness_risk=…)`.

`prompts/classify.md` is the **static text file** that defines the task instruction,
the input variable placeholders, the exact required JSON output schema, and at least
one few-shot example. It is not Python code; it is authored by `dev:prompt-author`.

---

## Module contract

**File type**: Static Markdown (loaded at runtime by `prompt_loader.py`)

**Input variables** — injected by `load_prompt("classify", ctx)` via `str.format_map()`:

| Variable | Source | Purpose |
|---|---|---|
| `{{title}}` | `NormalizedItem.title` | Note / article title |
| `{{url}}` | `NormalizedItem.url` | Source URL (empty string if none) |
| `{{text_preview}}` | `NormalizedItem.raw_text[:3000]` | Content snippet for classification |
| `{{domains}}` | `config.domains` | Newline-separated list of allowed domain names |
| `{{tag_taxonomy}}` | `config.tag_taxonomy_summary` | Abbreviated tag namespace list |

**LLM output** — raw JSON, no markdown fences, matching this exact schema:

```json
{
  "domain": "<one of {{domains}}>",
  "subdomain": "<specific subdomain within that domain>",
  "vault_zone": "job | personal",
  "content_age": "time-sensitive | dated | evergreen | personal",
  "suggested_tags": ["tag1", "tag2"],
  "detected_people": ["Full Name"],
  "detected_projects": ["project name"],
  "language": "<ISO 639-1 code>",
  "confidence": 0.85
}
```

**Explicitly excluded from LLM output** (computed in Python by `s2_classify.py`):
- `domain_path` — constructed as `f"{domain}/{subdomain}"`
- `staleness_risk` — computed from `domain_path` + `content_age` via `_compute_staleness_risk()`

**Consumed by**: `ClassificationResult` in `agent/core/models.py`

```python
ClassificationResult(
    domain=data["domain"],
    subdomain=data["subdomain"],
    domain_path=f"{data['domain']}/{data['subdomain']}",
    vault_zone=data["vault_zone"],
    content_age=ContentAge(data["content_age"]),
    staleness_risk=_compute_staleness_risk(domain_path, data["content_age"]),
    suggested_tags=data["suggested_tags"],
    detected_people=data["detected_people"],
    detected_projects=data["detected_projects"],
    language=data["language"],
    confidence=data["confidence"],
)
```

---

## Key implementation notes

### File structure (required)

```
---
version: 1.0
task: classification
output_format: json
---

<role / system instruction block>

<input section with {{variables}}>

<output schema section>

<few-shot example>
```

### Authoring constraints (from feature spec)

1. **YAML front-matter** MUST include `version`, `task`, `output_format: json`.
2. **Variable syntax**: `{{double_braces}}` — matched by `prompt_loader.py`'s
   `str.format_map()`. Single-brace `{…}` is NOT used.
3. **Raw JSON output**: instruct the model to output ONLY the JSON object — no
   wrapping code fences, no prose before or after.
4. **Token budget**: total prompt (excluding `{{text_preview}}` expansion) MUST stay
   under 1 200 tokens. Use abbreviated few-shot examples.
5. **Local LLM compatible**: no function-calling syntax; no chain-of-thought that
   requires multi-turn context. Works on Mistral 7B / Llama 3 8B (Q4).

### Domains reference

Known domains (from vault structure in REQUIREMENTS.md §2.1; passed dynamically via
`{{domains}}` at runtime, so the prompt does NOT hardcode them):

```
wellbeing, self_development, family_friends, investments, professional_dev
```
(and others as the vault grows — always consumed from config, never hardcoded).

### Content-age values (must match `ContentAge` enum exactly)

```
time-sensitive | dated | evergreen | personal
```

### Tag taxonomy guidance (abbreviated, for `suggested_tags`)

Allowed prefixes: `source/`, `domain/`, `subdomain/`, `proj/`, `ref/`,
`relationship/`, `status/`, `entity/`, `type/`, `lang/`

NEVER suggest `verbatim/*` or `index/*` tags — those are agent-assigned only.

### few-shot example requirements

- Include exactly **one complete few-shot example**: a short `TEXT`, `TITLE`, `URL`
  triplet followed by the expected JSON output.
- The example must cover a case with `detected_people`, `suggested_tags`, and a
  `confidence` value < 1.0 to teach the model to be calibrated.
- Example JSON must be valid, complete, and contain all 9 output fields.

### Confidence scoring guidance

Instruct the model:
- `0.9–1.0`: title and text clearly indicate domain
- `0.7–0.89`: reasonable match, some ambiguity
- `< 0.7`: domain unclear — still pick best match, lower confidence

---

## Data model changes (if any)

None. `ClassificationResult` in `agent/core/models.py` is already complete (DONE).
`domain_path` and `staleness_risk` remain Python-computed fields — not requested
from the LLM.

---

## LLM prompt file needed

**This spec IS the prompt file** — `prompts/classify.md` is the deliverable.

No additional prompt file is required.

---

## Tests required

- **unit: `tests/unit/test_prompt_classify.py`**
  - `test_prompt_file_exists` — `prompts/classify.md` is present on disk
  - `test_frontmatter_fields` — YAML front-matter has `version`, `task`,
    `output_format: json`
  - `test_all_input_variables_present` — file contains all five `{{…}}` placeholders:
    `title`, `url`, `text_preview`, `domains`, `tag_taxonomy`
  - `test_no_excluded_fields_in_schema` — file body does NOT contain the strings
    `domain_path` or `staleness_risk` (those must not be requested from LLM)
  - `test_example_output_parses_to_classification_result` — extract the JSON block
    from the few-shot example and assert it can construct `ClassificationResult`
    (after computing `domain_path`/`staleness_risk` in Python)
  - `test_token_budget` — render the prompt with a 3000-char dummy text, count
    tokens with `tiktoken` (or char-count heuristic ÷ 4), assert ≤ 1 200 tokens
    for the static portion (excluding `{{text_preview}}` substitution)
  - `test_no_markdown_fence_in_example` — confirm the example JSON block is NOT
    wrapped in triple-backtick fences in the LLM output instruction
  - `test_content_age_enum_values_listed` — all four `ContentAge` values
    (`time-sensitive`, `dated`, `evergreen`, `personal`) appear in the prompt body

- **integration**: none required for a static prompt file; integration coverage is
  provided by `tests/integration/test_llm_ollama.py` (tests the full
  classify stage end-to-end once that module is built).

---

## Explicitly out of scope

- Hardcoding domain names — they MUST come from `{{domains}}` at runtime
- `staleness_risk` or `domain_path` in the LLM output schema
- Multiple few-shot examples (token budget constraint; one is sufficient)
- Chain-of-thought / scratchpad instructions ("think step by step")
- Function-calling or tool-use syntax
- `verbatim/*` or `index/*` tag suggestions
- Any logic from Phase 2 (e.g., atom extraction, bi-directional link proposals)

---

## Open questions

None — all design decisions are resolved by ARCHITECTURE.md §9, REQUIREMENTS.md §4,
and `agent/core/models.py` (ClassificationResult, ContentAge enums).
