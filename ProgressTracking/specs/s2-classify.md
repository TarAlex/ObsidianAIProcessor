# Spec: Stage 2 — Classify
slug: s2-classify
layer: stages
phase: 1
arch_section: §6 Stage 2 (also §5 Pipeline Implementation, §3.2 Source Note Frontmatter)

---

## Problem statement

After Stage 1 produces a `NormalizedItem`, the pipeline needs to assign every
item to a knowledge domain, subdomain, and vault zone before any further
processing. Stage 2 is the **first LLM call** in the pipeline. It must:

1. Build a context dict from the `NormalizedItem` and the live config (domain
   list + tag taxonomy).
2. Render the `prompts/classify.md` prompt via `prompt_loader.load_prompt`.
3. Call the LLM (via `AbstractLLMProvider.chat`) and parse the JSON response.
4. Compute two fields the LLM does **not** return: `domain_path` (slash-joined
   `domain/subdomain`) and `staleness_risk` (derived from domain + content_age
   business rules defined in REQUIREMENTS §3.2).
5. Return a fully-populated `ClassificationResult`.

Routing decisions (confidence threshold → `to_review/`) are the pipeline
orchestrator's responsibility — Stage 2 does **not** check the threshold.

---

## Module contract

```
Input:  item:   NormalizedItem        — from agent.core.models
        llm:    AbstractLLMProvider   — from agent.llm.base
        config: AgentConfig           — from agent.core.config

Output: ClassificationResult          — from agent.core.models
```

Call signature (matches pipeline.py §5):
```python
async def run(
    item: NormalizedItem,
    llm: AbstractLLMProvider,
    config: AgentConfig,
) -> ClassificationResult
```

---

## Key implementation notes

### 1. Prompt context dict

```python
ctx = {
    "text_preview": item.raw_text[:3000],   # hard cap — avoid token overflow
    "title":        item.title,
    "url":          item.url,
    "domains":      config.domains,          # list[str] from 02_KNOWLEDGE/ dirs
    "tag_taxonomy": config.tag_taxonomy_summary,  # str, max 2000 chars
}
prompt_text = load_prompt("classify", ctx)
```

- `config.domains` is a sorted list of directory names under `vault_root/02_KNOWLEDGE/`.
- `config.tag_taxonomy_summary` is `_AI_META/tag-taxonomy.md` truncated to 2000 chars.
- Both are read fresh from disk on each pipeline run (no module-level caching in
  this stage).

### 2. LLM call

```python
response = await llm.chat(
    [
        {
            "role": "system",
            "content": "You are a knowledge classification assistant. "
                       "Respond ONLY with valid JSON.",
        },
        {"role": "user", "content": prompt_text},
    ],
    temperature=0.0,
)
```

`temperature=0.0` ensures deterministic output. `max_tokens` uses the provider
default (2000) — the JSON response is small.

### 3. JSON parsing

```python
data = json.loads(response)
```

No explicit try/except here. `json.JSONDecodeError` propagates up to
`pipeline.py`'s top-level `except Exception` block, which routes the item to
`to_review/`. Do **not** swallow parse failures.

Pydantic validation when constructing `ClassificationResult(**data, ...)` also
propagates — invalid `content_age` or missing required fields are treated as
pipeline errors.

### 4. domain_path computation

```python
domain_path = f"{data['domain']}/{data['subdomain']}"
```

The LLM is **not** asked to return `domain_path` — the classify prompt
explicitly says "Do NOT include `domain_path` or `staleness_risk`". The stage
derives it from `domain` and `subdomain`.

### 5. staleness_risk computation

```python
_STALENESS_RULES: dict[str, StatenessRisk] = {
    "professional_dev/ai_tools": StatenessRisk.HIGH,
    "professional_dev/ai_dev":   StatenessRisk.HIGH,
    "investments":               StatenessRisk.MEDIUM,
}

def _compute_staleness_risk(domain_path: str, content_age: str) -> StatenessRisk:
    if content_age == "time-sensitive":
        return StatenessRisk.HIGH
    for prefix, risk in _STALENESS_RULES.items():
        if domain_path.startswith(prefix):
            return risk
    if content_age == "evergreen":
        return StatenessRisk.LOW
    return StatenessRisk.MEDIUM   # "dated" and "personal" fall here
```

Rules (in priority order, matching REQUIREMENTS §3.2):

| Condition | staleness_risk |
|---|---|
| `content_age == "time-sensitive"` | `HIGH` |
| `domain_path` starts with `professional_dev/ai_tools` | `HIGH` |
| `domain_path` starts with `professional_dev/ai_dev` | `HIGH` |
| `domain_path` starts with `investments` | `MEDIUM` |
| `content_age == "evergreen"` (no override above) | `LOW` |
| `content_age == "dated"` or `"personal"` | `MEDIUM` |

`_STALENESS_RULES` and `_compute_staleness_risk` are module-level private
helpers (prefixed `_`). No external code imports them.

### 6. ClassificationResult construction

```python
return ClassificationResult(
    **data,
    domain_path=domain_path,
    staleness_risk=staleness_risk,
)
```

`data` from JSON contains the 9 LLM-assigned fields:
`domain`, `subdomain`, `vault_zone`, `content_age`, `suggested_tags`,
`detected_people`, `detected_projects`, `language`, `confidence`.

`domain_path` and `staleness_risk` are injected by the stage — they are NOT
in the LLM output.

### 7. Logging

Log at `INFO`:
- prompt context summary (raw_id, title truncated to 60 chars, domain resolved)
- LLM response: domain, subdomain, confidence

Log at `DEBUG`:
- full prompt context dict (for local dev debugging)
- raw LLM response string

Do **not** log `raw_text` at INFO or higher (may contain PII).

### 8. No vault access

`ObsidianVault` is **not** imported or used. Stage 2 is a pure LLM inference
step. No files are written or read beyond what `prompt_loader` does (reads from
`prompts/`).

---

## Data model changes

None. `ClassificationResult` from `agent/core/models.py` already includes
`domain_path: str` and `staleness_risk: StatenessRisk` per architecture v1.1.

---

## LLM prompt file needed

`prompts/classify.md` — **already DONE** (see TRACKER §Tool Prompt Files).

The prompt instructs the LLM to return JSON without `domain_path` or
`staleness_risk` — those are computed here. Template variables used:
`{text_preview}`, `{title}`, `{url}`, `{domains}`, `{tag_taxonomy}`.

---

## Tests required

### unit: `tests/unit/test_s2_classify.py`

All tests patch `llm` with `unittest.mock.AsyncMock` — no real LLM calls.
All tests use a minimal `AgentConfig` (temp vault root with `02_KNOWLEDGE/`).

| Case | Description |
|---|---|
| `test_run_returns_classification_result` | Valid JSON from LLM → returns `ClassificationResult` with all fields set |
| `test_domain_path_is_domain_slash_subdomain` | `domain="wellbeing"`, `subdomain="nutrition"` → `domain_path="wellbeing/nutrition"` |
| `test_staleness_high_for_time_sensitive` | `content_age="time-sensitive"` → `staleness_risk=HIGH` regardless of domain |
| `test_staleness_high_for_ai_tools` | `domain_path="professional_dev/ai_tools"`, `content_age="dated"` → `HIGH` |
| `test_staleness_high_for_ai_dev` | `domain_path="professional_dev/ai_dev"`, `content_age="evergreen"` → `HIGH` |
| `test_staleness_medium_for_investments` | `domain_path="investments/shares"`, `content_age="evergreen"` → `MEDIUM` |
| `test_staleness_low_for_evergreen_no_override` | `domain_path="wellbeing/nutrition"`, `content_age="evergreen"` → `LOW` |
| `test_staleness_medium_for_dated_default` | `domain_path="hobbies/gaming"`, `content_age="dated"` → `MEDIUM` |
| `test_staleness_medium_for_personal` | `content_age="personal"`, neutral domain → `MEDIUM` |
| `test_text_preview_capped_at_3000_chars` | `item.raw_text` is 5000 chars → `load_prompt` ctx key `text_preview` is ≤ 3000 chars |
| `test_llm_called_with_temperature_zero` | Verify `llm.chat` called with `temperature=0.0` |
| `test_llm_called_with_system_message` | System message content contains `"Respond ONLY with valid JSON"` |
| `test_json_decode_error_propagates` | `llm.chat` returns `"not json"` → `json.JSONDecodeError` raised |
| `test_llm_provider_error_propagates` | `llm.chat` raises `LLMProviderError` → propagates to caller |
| `test_pydantic_validation_error_propagates` | JSON missing required field `"domain"` → `ValidationError` raised |
| `test_confidence_preserved_from_llm` | LLM returns `confidence=0.85` → `result.confidence == 0.85` |
| `test_language_preserved_from_llm` | LLM returns `language="ru"` → `result.language == "ru"` |
| `test_load_prompt_called_with_classify` | Verify `load_prompt` called with `"classify"` as first argument |

All LLM mock return values are minimal valid JSON strings matching the schema
in `prompts/classify.md`.

### integration: `tests/integration/test_pipeline_s2.py` _(low priority)_

- Build a `NormalizedItem` from a short text fixture.
- Wire a `FakeLLMProvider` that returns a hardcoded valid JSON string.
- Call `s2_classify.run(item, fake_llm, config)`.
- Assert `ClassificationResult.domain`, `domain_path`, and `staleness_risk`
  all match expected values.
- No real LLM; no real vault.

---

## Explicitly out of scope

- Confidence threshold routing — handled by `pipeline.py`
- Multiple classification attempts / retry on low confidence
- Writing anything to `01_PROCESSING/` or any vault path
- Detecting language independently (language is inferred by the LLM)
- Resolving `detected_people` or `detected_projects` to REFERENCES/ entries (Stage 6)
- Tag taxonomy validation (tags accepted as-is from LLM)
- Phase 2 fields (atom concepts, cross-domain links)
- Parallel classification of multiple items (pipeline handles concurrency)

---

## Open questions

None. All design decisions resolved from architecture §6, requirements §3.2,
pipeline.py §5, and the DONE `prompts/classify.md` file.
