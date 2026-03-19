# Spec: Stage 4a — Summarize
slug: s4a-summarize
layer: stages
phase: 1
arch_section: §6 Stage 4a (also §3.1 SummaryResult, §3.2 Source Note Frontmatter)

---

## Problem statement

After Stage 3 resolves dates, the pipeline needs a structured summary of the
content before it can be written to the vault. Stage 4a is the **second LLM
call** in the pipeline. It must:

1. Build a context dict from the `NormalizedItem` + `ClassificationResult`.
2. Render the `prompts/summarize.md` prompt via `prompt_loader.load_prompt`.
3. Call the LLM (via `AbstractLLMProvider.chat`) and parse the JSON response.
4. Return a fully-populated `SummaryResult` with `verbatim_blocks` defaulting
   to `[]` — verbatim extraction is Stage 4b's responsibility.

This stage does **not** route on `ai_confidence`, does **not** write to the
vault, and does **not** populate `verbatim_blocks`.

---

## Module contract

```
Input:  item:           NormalizedItem        — from agent.core.models
        classification: ClassificationResult  — from agent.core.models
        llm:            AbstractLLMProvider   — from agent.llm.base
        config:         AgentConfig           — from agent.core.config

Output: SummaryResult                         — from agent.core.models
```

Call signature (matches pipeline.py §5):
```python
async def run(
    item: NormalizedItem,
    classification: ClassificationResult,
    llm: AbstractLLMProvider,
    config: AgentConfig,
) -> SummaryResult
```

---

## Key implementation notes

### 1. Prompt context dict

```python
ctx = {
    "title":             item.title,
    "source_type":       item.source_type.value,
    "language":          classification.language,
    "domain_path":       classification.domain_path,
    "text":              item.raw_text[:6000],   # hard cap per prompts/summarize.md
    "detected_people":   ", ".join(classification.detected_people),
    "detected_projects": ", ".join(classification.detected_projects),
}
prompt_text = load_prompt("summarize", ctx)
```

- Text cap is **6 000 chars** (specified in `prompts/summarize.md` — "up to 6 000
  characters").
- `detected_people` and `detected_projects` are comma-separated strings; empty
  lists become `""` which the prompt treats as "skip wikilink insertion".
- `source_type` is the enum `.value` (e.g. `"youtube"`, `"article"`).

### 2. LLM call

```python
response = await llm.chat(
    [
        {
            "role": "system",
            "content": "You are a knowledge summarisation assistant. "
                       "Respond ONLY with valid JSON.",
        },
        {"role": "user", "content": prompt_text},
    ],
    temperature=0.0,
)
```

`temperature=0.0` for deterministic output. `max_tokens` uses the provider
default (2 000) — the JSON response is small.

### 3. JSON parsing

```python
data = json.loads(response)
```

No explicit try/except. `json.JSONDecodeError` propagates to `pipeline.py`'s
top-level exception handler, which routes the item to `to_review/`. Do **not**
swallow parse failures.

Pydantic validation when constructing `SummaryResult(**data)` also propagates —
missing required fields (`summary`, `key_ideas`) are treated as pipeline errors.

### 4. SummaryResult construction

```python
return SummaryResult(**data)
```

The LLM output schema (from `prompts/summarize.md`) maps directly to
`SummaryResult` fields:

| JSON key        | SummaryResult field | Notes                              |
|-----------------|---------------------|------------------------------------|
| `summary`       | `summary`           | 2–4 sentence prose                 |
| `key_ideas`     | `key_ideas`         | 3–7 short strings                  |
| `action_items`  | `action_items`      | `[]` unless `ms_teams` or meeting  |
| `quotes`        | `quotes`            | brief excerpts < 40 words, or `[]` |
| `atom_concepts` | `atom_concepts`     | always `[]` in Phase 1             |

`verbatim_blocks` is absent from the LLM output; Pydantic fills it with `[]`
via `Field(default_factory=list)`. Stage 4b populates it separately.

### 5. Logging

Log at `INFO`:
- `raw_id`, `title` (truncated to 60 chars), `source_type`
- `len(key_ideas)`, `len(action_items)` from result

Log at `DEBUG`:
- Full prompt context dict (for local dev debugging)
- Raw LLM response string

Do **not** log `raw_text` at INFO or higher (may contain PII).

### 6. No vault access

`ObsidianVault` is **not** imported or used. Stage 4a is a pure LLM inference
step. No files are written or read beyond what `prompt_loader` does (reads
`prompts/summarize.md`).

### 7. Imports

```python
import json
import logging

from agent.core.config import AgentConfig
from agent.core.models import ClassificationResult, NormalizedItem, SummaryResult
from agent.llm.base import AbstractLLMProvider
from agent.llm.prompt_loader import load_prompt
```

---

## Data model changes

None. `SummaryResult` in `agent/core/models.py` already contains all required
fields: `summary`, `key_ideas`, `action_items`, `quotes`, `atom_concepts`,
`verbatim_blocks`. No model changes needed.

---

## LLM prompt file needed

`prompts/summarize.md` — **already DONE** (see TRACKER §Tool Prompt Files).

Template variables used: `{{title}}`, `{{source_type}}`, `{{language}}`,
`{{domain_path}}`, `{{text}}`, `{{detected_people}}`, `{{detected_projects}}`.

---

## Tests required

### unit: `tests/unit/test_s4a_summarize.py`

All tests patch `llm` with `unittest.mock.AsyncMock` — no real LLM calls.
All tests use a minimal `AgentConfig` stub and pre-built fixture models.

| Case | Description |
|---|---|
| `test_run_returns_summary_result` | Valid JSON from LLM → returns `SummaryResult` with all fields populated |
| `test_verbatim_blocks_default_empty` | LLM JSON has no `verbatim_blocks` key → `result.verbatim_blocks == []` |
| `test_text_capped_at_6000_chars` | `item.raw_text` is 8 000 chars → `load_prompt` ctx key `text` is ≤ 6 000 chars |
| `test_source_type_value_passed` | `item.source_type = SourceType.YOUTUBE` → ctx `source_type == "youtube"` |
| `test_detected_people_comma_joined` | `classification.detected_people = ["Alice", "Bob"]` → ctx `detected_people == "Alice, Bob"` |
| `test_detected_people_empty_string_when_none` | `classification.detected_people = []` → ctx `detected_people == ""` |
| `test_detected_projects_comma_joined` | `classification.detected_projects = ["Vault Builder"]` → ctx `detected_projects == "Vault Builder"` |
| `test_llm_called_with_temperature_zero` | Verify `llm.chat` called with `temperature=0.0` |
| `test_llm_called_with_system_message` | System message content contains `"Respond ONLY with valid JSON"` |
| `test_load_prompt_called_with_summarize` | Verify `load_prompt` called with `"summarize"` as first arg |
| `test_action_items_empty_for_article` | LLM returns `action_items: []`, source is `article` → `result.action_items == []` |
| `test_action_items_populated_for_ms_teams` | LLM returns non-empty `action_items`, source is `ms_teams` → items preserved |
| `test_atom_concepts_always_empty` | LLM returns `atom_concepts: []` → `result.atom_concepts == []` |
| `test_json_decode_error_propagates` | `llm.chat` returns `"not json"` → `json.JSONDecodeError` raised |
| `test_llm_provider_error_propagates` | `llm.chat` raises `LLMProviderError` → propagates to caller |
| `test_pydantic_validation_error_propagates` | JSON missing required field `"summary"` → `ValidationError` raised |
| `test_language_from_classification_used` | `classification.language = "ru"` → ctx `language == "ru"` |
| `test_domain_path_from_classification_used` | `classification.domain_path = "wellbeing/nutrition"` → ctx `domain_path == "wellbeing/nutrition"` |
| `test_quotes_returned_when_present` | LLM returns `quotes: ["excerpt"]` → `result.quotes == ["excerpt"]` |
| `test_quotes_empty_when_none` | LLM returns `quotes: []` → `result.quotes == []` |

All LLM mock return values are minimal valid JSON strings matching the output
schema in `prompts/summarize.md`.

### integration: `tests/integration/test_pipeline_s4a.py` _(low priority)_

- Build a `NormalizedItem` from a short text fixture and a `ClassificationResult`
  with `domain_path="professional_dev/ai_tools"`, `language="en"`.
- Wire a `FakeLLMProvider` that returns a hardcoded valid JSON string.
- Call `s4a_summarize.run(item, classification, fake_llm, config)`.
- Assert `SummaryResult.summary` is non-empty, `verbatim_blocks == []`.
- No real LLM; no real vault.

---

## Explicitly out of scope

- Populating `verbatim_blocks` — handled by Stage 4b (`s4b_verbatim.py`)
- Populating `atom_concepts` — Phase 2 only; always returns `[]`
- Routing on LLM confidence — handled by `pipeline.py`
- Retry logic on LLM failure — handled by `_FallbackProvider` in `provider_factory.py`
- Writing anything to `01_PROCESSING/` or any vault path
- Wikilink validation (links accepted as-is from LLM output)
- Truncation strategies beyond `raw_text[:6000]` (chunking, summarization of chunks)
- Phase 2 fields (cross-domain links, atom note creation)

---

## Open questions

None. All design decisions resolved from architecture §6 (Stage 4a), requirements
§6.1, `prompts/summarize.md` (DONE), `SummaryResult` in `models.py` (DONE), and
the s2-classify.md spec (established LLM-stage pattern).
