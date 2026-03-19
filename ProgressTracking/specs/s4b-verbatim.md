# Spec: Stage 4b — Verbatim Extraction
slug: s4b-verbatim
layer: stages
phase: 1
arch_section: §6 Stage 4b, §7 Verbatim Module

---

## Problem statement

After Stage 4a produces a summary, Stage 4b makes a second, independent LLM call to
identify passages in the raw text that must be preserved verbatim — source code, LLM
prompts, attributed quotes, and timestamped transcript segments. The stage returns a
`list[VerbatimBlock]` with **byte-identical content**. The pipeline (pipeline.py) attaches
these blocks to `SummaryResult.verbatim_blocks` and sets `record.verbatim_count`.

Key invariant (verbatim-contract skill): `VerbatimBlock.content` must be byte-identical
from extraction through to the final note body. The agent must never paraphrase, strip,
or reformat it.

---

## Module contract

```
Input:
  item:   NormalizedItem        — raw content from Stage 1
  llm:    AbstractLLMProvider   — injected (from ProviderFactory.get(config))
  config: AgentConfig           — for config.vault.max_verbatim_blocks_per_note

Output:
  list[VerbatimBlock]           — may be empty; NEVER raises (returns [] on any error)
```

Pipeline integration (pipeline.py — already written):
```python
verbatim_blocks = await s4b_verbatim.run(item, llm, config)
summary.verbatim_blocks = verbatim_blocks
record.verbatim_count = len(verbatim_blocks)
```

No vault writes. No `ObsidianVault` import. Pure LLM inference stage.

---

## Key implementation notes

### 1. Imports
```python
from __future__ import annotations

import json
import logging
from datetime import datetime

from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem, StatenessRisk, VerbatimBlock, VerbatimType
from agent.llm.base import AbstractLLMProvider
from agent.llm.prompt_loader import load_prompt
```

### 2. Module-level default staleness map

Define this constant at module level (matches REQUIREMENTS.md §3.4.2):

```python
_DEFAULT_STALENESS: dict[VerbatimType, StatenessRisk] = {
    VerbatimType.CODE:       StatenessRisk.HIGH,
    VerbatimType.PROMPT:     StatenessRisk.HIGH,
    VerbatimType.QUOTE:      StatenessRisk.LOW,
    VerbatimType.TRANSCRIPT: StatenessRisk.MEDIUM,
}
```

### 3. Priority order for cap enforcement

When LLM returns more blocks than `max_blocks`, sort by type priority before slicing:

```python
_TYPE_PRIORITY: list[VerbatimType] = [
    VerbatimType.CODE,
    VerbatimType.PROMPT,
    VerbatimType.QUOTE,
    VerbatimType.TRANSCRIPT,
]
```

Sort key: `_TYPE_PRIORITY.index(block.type)` (lower = higher priority).

### 4. Function signature

```python
async def run(
    item: NormalizedItem,
    llm: AbstractLLMProvider,
    config: AgentConfig,
) -> list[VerbatimBlock]:
```

### 5. Text cap

Slice `item.raw_text[:8000]` — matches prompt's stated limit, avoids local LLM token
overflow.

### 6. max_blocks

```python
max_blocks = config.vault.max_verbatim_blocks_per_note  # default 10
```

### 7. Prompt loading

```python
ctx = {
    "text":       item.raw_text[:8000],
    "source_id":  item.raw_id,
    "max_blocks": max_blocks,
}
prompt_text = load_prompt("extract_verbatim", ctx)
```

**Important**: `extract_verbatim.md` uses `{{var}}` notation (double-brace, Jinja-style).
`load_prompt` uses `str.format_map`, which renders `{{var}}` as literal `{var}` — the
actual values for `max_blocks` and `text` are NOT substituted into the prompt body.
The Python-side cap (`[:max_blocks]` after sorting) is therefore the **authoritative**
enforcement mechanism and must not be skipped.

### 8. LLM call

```python
response = await llm.chat(
    [
        {
            "role": "system",
            "content": "You are a content analyst for a personal knowledge management system. "
                       "Output ONLY valid JSON.",
        },
        {"role": "user", "content": prompt_text},
    ],
    temperature=0.0,
    max_tokens=2000,
)
```

### 9. JSON parsing and block construction

Expected schema from LLM:
```json
{
  "verbatim_blocks": [
    {
      "type": "code|prompt|quote|transcript",
      "content": "<exact text, whitespace preserved>",
      "lang": "<python|bash|en|ru|...>",
      "staleness_risk": "low|medium|high"
    }
  ]
}
```
Optional block fields: `attribution` (quotes only), `timestamp` (transcripts only),
`model_target` (prompts only).

Block construction for each raw dict `b` (after priority-sort and cap):

| VerbatimBlock field | Source |
|---|---|
| `type`           | `VerbatimType(b["type"])` |
| `content`        | `b["content"]` — **never modified** |
| `lang`           | `b.get("lang", "")` |
| `staleness_risk` | `StatenessRisk(b["staleness_risk"])` if present; else `_DEFAULT_STALENESS[vtype]` |
| `source_id`      | `item.raw_id` |
| `added_at`       | `datetime.utcnow()` |
| `attribution`    | `b.get("attribution", "")` |
| `timestamp`      | `b.get("timestamp", "")` |
| `model_target`   | `b.get("model_target", "")` |

### 10. Priority sort before cap

```python
blocks_raw = data.get("verbatim_blocks", [])
# Sort by type priority, then cap
def _priority(b: dict) -> int:
    try:
        return _TYPE_PRIORITY.index(VerbatimType(b.get("type", "quote")))
    except ValueError:
        return len(_TYPE_PRIORITY)  # unknown types sorted last

blocks_raw_sorted = sorted(blocks_raw, key=_priority)[:max_blocks]
```

### 11. Error handling — graceful degradation

Wrap the **entire** body (LLM call + JSON parse + block construction) in a broad
`try/except Exception`:

```python
except Exception as exc:
    logger.warning("Verbatim extraction failed for %s: %s", item.raw_id, exc)
    return []
```

Stage 4b failure must **not** abort the pipeline. Unlike s4a (which lets exceptions
propagate), s4b is non-critical — a note with no verbatim blocks is still valid.

### 12. Logging

- `logger.info` on entry: `raw_id`, `title[:60]`, `source_type`
- `logger.debug`: raw LLM response
- `logger.info` on success: `raw_id`, `len(blocks)` returned
- `logger.warning` on any exception: `raw_id`, exception text

---

## Data model changes (if any)

None. All required types already exist:
- `VerbatimBlock`, `VerbatimType`, `StatenessRisk` — `agent/core/models.py` (DONE)
- `SummaryResult.verbatim_blocks: list[VerbatimBlock]` — already in models (DONE)
- `AgentConfig.vault.max_verbatim_blocks_per_note: int = 10` — already in config (DONE)

---

## LLM prompt file needed

`prompts/extract_verbatim.md` — **already DONE**.

---

## Tests required

### unit: `tests/unit/test_s4b_verbatim.py`

All tests mock `llm.chat` (AsyncMock) and `load_prompt`.

| # | Test name | What it verifies |
|---|---|---|
| 1 | `test_happy_path_code_and_quote` | LLM returns one code + one quote block; both VerbatimBlocks have correct type, content byte-identical to LLM response, staleness_risk per defaults, `source_id == item.raw_id`, `added_at` not None |
| 2 | `test_empty_verbatim_blocks` | LLM returns `{"verbatim_blocks": []}` → returns `[]` |
| 3 | `test_llm_error_returns_empty` | `llm.chat` raises `LLMProviderError`; assert returns `[]`, no exception propagates |
| 4 | `test_json_parse_error_returns_empty` | `llm.chat` returns `"not json"` → returns `[]` |
| 5 | `test_cap_enforced_default_max` | LLM returns 15 blocks (all code); assert `len(result) == 10` |
| 6 | `test_priority_sort_on_cap` | LLM returns 12 blocks: 3 transcript + 3 quote + 3 prompt + 3 code; assert result (10) contains all 3 code, all 3 prompt, all 3 quote, 1 transcript (priority order) |
| 7 | `test_missing_staleness_uses_default` | Block has no `staleness_risk` field; CODE → HIGH, QUOTE → LOW |
| 8 | `test_text_cap_applied` | `item.raw_text` is 12 000 chars; capture `load_prompt` ctx and assert `len(ctx["text"]) == 8000` |
| 9 | `test_max_blocks_from_config` | Set `config.vault.max_verbatim_blocks_per_note = 3`; LLM returns 5 blocks; `len(result) == 3` |
| 10 | `test_optional_fields_propagate` | Quote with `attribution`, transcript with `timestamp`, prompt with `model_target`; assert all fields present on constructed blocks |
| 11 | `test_content_byte_identical` | Code block with indentation + trailing newline; assert `result[0].content == original_content` exactly |
| 12 | `test_invalid_type_skipped` | LLM returns one valid code block + one block with unknown `type`; assert only the valid block (or graceful skip) |

### integration: `tests/integration/test_pipeline_verbatim.py`

Listed in TRACKER.md as TODO — not implemented in this spec. Traceability note:
- Full pipeline test: a source with Python code block → note has `verbatim_count >= 1`
  and the code block content is byte-identical to source.

---

## Explicitly out of scope

- Attaching blocks to `SummaryResult.verbatim_blocks` — done in `pipeline.py`
- Writing vault notes — Stage 6a
- Updating `verbatim_count` / `verbatim_types` in note frontmatter — Stage 6a
- Incremental enrichment (appending to existing notes) — Stage 6a
- Staleness scanning — `outdated_review.py` (tasks layer)
- Phase 2 `atom_concepts`
- Any `VerbatimType` beyond the four in the enum

---

## Open questions

None — architecture (§6 Stage 4b), prompt (`extract_verbatim.md`), and
vault module (`verbatim.py`) are all fully specified and DONE.
