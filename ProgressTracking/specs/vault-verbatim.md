# Spec: Verbatim Block Render/Parse
slug: vault-verbatim
layer: vault
phase: 1
arch_section: §7 (Verbatim Module ★ NEW)

---

## Problem statement

Pipeline stage `s4b_verbatim` extracts `VerbatimBlock` objects from source text.
`s6a_write` must embed them into note bodies as a deterministic, parseable
Markdown snippet. `outdated_review.py` (task layer) must later scan live note
bodies and reconstruct the same `VerbatimBlock` objects from those snippets.

This module provides the two pure-transform functions that close that loop:

- **render**: `VerbatimBlock` → stable Markdown string (HTML comment header +
  fenced block or blockquote)
- **parse**: Markdown body string → `list[VerbatimBlock]` (regex extraction,
  silent skip on malformed blocks)

The round-trip contract is an invariant the test suite enforces byte-for-byte.

---

## Module contract

### render_verbatim_block

```
Input:  block: VerbatimBlock
        now:   datetime | None = None   (injected for deterministic tests)
Output: str   (valid Markdown fragment, ready to embed in note body)
```

### parse_verbatim_blocks

```
Input:  body: str   (full note body, may contain 0..N verbatim blocks)
Output: list[VerbatimBlock]
```

### Round-trip invariant (tested)

```python
parse_verbatim_blocks(render_verbatim_block(block))[0].content == block.content
# byte-identical — no whitespace normalization, no newline trimming
```

---

## Key implementation notes

### Wire format (from arch §7)

```
<!-- verbatim
type: code|prompt|quote|transcript
lang: python                          ← only when non-empty
source_id: SRC-...
added_at: 2026-03-10T14:30:22
staleness_risk: high
attribution: "Author, Title, p.N"    ← only when non-empty (quotes field)
timestamp: "00:14:32"                ← only when non-empty (transcripts field)
model_target: claude-3-5-sonnet      ← only when non-empty (prompts field)
-->
```fenced or > blockquote```
```

**Field order in header is fixed** — render always emits in this order:
`type`, `lang` (if set), `source_id`, `added_at`, `staleness_risk`,
`attribution` (if set), `timestamp` (if set), `model_target` (if set), `-->`.

### Content fencing rules

| VerbatimType | Output format |
|---|---|
| `CODE` | ` ```{lang}\n{content}\n``` ` (lang may be empty → ` ``` `) |
| `PROMPT` | ` ```\n{content}\n``` ` (no lang — fence_lang = "") |
| `TRANSCRIPT` | ` ```\n{content}\n``` ` (no lang) |
| `QUOTE` | `> {line}` per line — blockquote format |

Rule from arch §7 line 705: `fence_lang = block.lang if block.type == VerbatimType.CODE else ""`

### added_at handling

- If `block.added_at` is not None → use its `.isoformat()` value
- If `block.added_at` is None → use `now.isoformat()` (caller-injected or `datetime.utcnow()`)
- After a round-trip the parsed block's `added_at` will match the rendered string;
  this means the parse must handle ISO strings both with and without timezone offset.

### Regex pattern (exact from arch §7)

```python
_VERBATIM_RE = re.compile(
    r"<!--\s*verbatim\s*\n(.*?)-->\s*\n(```[\s\S]*?```|>[\s\S]*?)(?=\n\n|\Z)",
    re.DOTALL,
)
_HEADER_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)
```

`_VERBATIM_RE` group 1 = header text, group 2 = fenced or blockquote content.
`_HEADER_FIELD_RE` parses `key: value` lines from the header.

### Parse: field stripping

- `attribution` and `timestamp` values are stored with surrounding double-quotes
  in the header; parse must `.strip('"')` when constructing `VerbatimBlock`.
- `model_target` has no surrounding quotes; store as-is.
- Default for missing fields: `lang=""`, `source_id=""`, `staleness_risk=medium`,
  `attribution=""`, `timestamp=""`, `model_target=""`, `added_at=None`.

### Content extraction

For fenced blocks (```` ``` ````) the regex match group 2 includes the fence markers.
`parse_verbatim_blocks` stores the **entire fenced block string** (including
backtick fences) as `block.content` — that is what render emits too:
```
lines.append(f"```{fence_lang}")
lines.append(block.content)
lines.append("```")
```
Wait — re-reading arch §7 carefully: `render` appends the raw `block.content`
*between* the fence lines. `parse` must therefore extract the content
**between** the fences, not the full match group 2.

**Definitive rule**:
- `render` stores `block.content` as raw text between the fence lines.
  The rendered string is ```` ```lang\n{content}\n``` ````.
- `parse` receives match group 2 = full fenced string.
  Content = strip outer fence lines to recover the inner text.
  For blockquotes: strip `> ` prefix from each line.

This is the only interpretation that satisfies the round-trip invariant
(`parse(render(b))[0].content == b.content`).

### Malformed block handling

Any `Exception` raised inside the per-match try/except is caught and the block
is silently skipped (`continue`). No re-raise, no logging inside this module.
Callers that want to log dropped blocks must compare `len(parse_verbatim_blocks(body))`
against expected count.

### Import boundary

```python
# ALLOWED
from __future__ import annotations
import re
from datetime import datetime
from agent.core.models import VerbatimBlock, VerbatimType, StatenessRisk

# FORBIDDEN — will fail CI
from agent.vault.vault import ...   # any vault import
from agent.stages import ...        # any stage import
from agent.core.pipeline import ... # any pipeline import
```

---

## Data model changes

None. All models (`VerbatimBlock`, `VerbatimType`, `StatenessRisk`) exist in
`agent/core/models.py` and are stable.

---

## LLM prompt file needed

None. This module is a pure text transform; no LLM calls.

---

## Tests required

### unit: `tests/unit/test_verbatim.py`

**Round-trip cases (one per VerbatimType):**
- `test_roundtrip_code` — CODE block with `lang="python"`, `source_id`, `staleness_risk=HIGH`
- `test_roundtrip_prompt` — PROMPT block, `model_target` set, no lang
- `test_roundtrip_quote` — QUOTE block with `attribution` containing a comma and quotes
- `test_roundtrip_transcript` — TRANSCRIPT block with `timestamp` set

**Content byte-identity check:**
- Each round-trip test asserts `parsed.content == original.content` explicitly
  (not just equality of the full model)

**Multi-block body:**
- `test_parse_multiple_blocks` — body contains 3 verbatim blocks; assert `len == 3`
  and each block's type matches

**Malformed block handling:**
- `test_parse_malformed_type` — header has `type: invalid_type`; assert result is `[]`
- `test_parse_missing_end` — `-->` is absent; assert result is `[]` (no crash)
- `test_parse_empty_body` — `parse_verbatim_blocks("")` returns `[]`

**Render details:**
- `test_render_omits_empty_optional_fields` — block with empty `lang`, `attribution`,
  `timestamp`, `model_target`; rendered string must NOT contain those keys
- `test_render_now_injected` — pass explicit `now=datetime(2026,1,1,0,0,0)`;
  assert `added_at: 2026-01-01T00:00:00` in output
- `test_render_quote_blockquote_format` — QUOTE block with multi-line content;
  assert each line starts with `> `
- `test_render_code_uses_lang` — CODE block with `lang="typescript"`; assert
  fence opens with ` ```typescript `

**Parse edge cases:**
- `test_parse_attribution_strips_quotes` — attribution stored as `"Smith, p.5"`;
  parsed `attribution == "Smith, p.5"` (no surrounding double quotes)
- `test_parse_added_at_none` — block rendered with `added_at=None` (uses `now`);
  parsed `added_at` is a valid `datetime`

### integration

No integration test needed for this module (pure transform, no I/O). The
pipeline integration test `tests/integration/test_pipeline_verbatim.py` is
a separate tracker item (TODO) and is out of scope here.

---

## Explicitly out of scope

- Editing or updating existing verbatim blocks in a note (no partial-replace logic)
- Deduplication of verbatim blocks across notes
- `s4b_verbatim.py` pipeline stage (separate tracker item)
- `outdated_review.py` staleness-flagging logic
- Any vault file I/O (reads/writes via `ObsidianVault`)
- Phase 2: atom-level verbatim extraction
- Logging or metrics inside the module

---

## Open questions

None. Architecture §7 provides the exact regex, field order, and content-wrapping
rules. The round-trip invariant is unambiguous given the content-strip rule above.
