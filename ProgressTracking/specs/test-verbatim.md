# Spec: tests/unit/test_verbatim.py ★
slug: test-verbatim
layer: tests
phase: 1
arch_section: §7 Verbatim Module ★, §17 Testing Strategy

---

## Problem statement

`agent/vault/verbatim.py` provides the two pure-transform functions
(`render_verbatim_block` / `parse_verbatim_blocks`) whose **round-trip lossless
contract** is the correctness invariant for the entire verbatim pipeline:
`s4b_verbatim` extracts blocks; `s6a_write` renders them into notes;
`outdated_review` re-parses them later. Any drift in the render↔parse cycle
corrupts vault notes permanently.

This test module is the ★ contract enforcer: if any render or parse change
breaks byte-identical round-trip, these tests must fail first.

**Current state:** `tests/unit/test_verbatim.py` exists on disk with all 17
required test cases implemented. The `/plan` session confirms full coverage
against `vault-verbatim.md`. Proceed to `/review tests/unit/test_verbatim.py`.

---

## Module contract

Input:  `agent.vault.verbatim` — `render_verbatim_block`, `parse_verbatim_blocks`
        `agent.core.models` — `VerbatimBlock`, `VerbatimType`, `StatenessRisk`
Output: 17 passing pytest tests; `pytest tests/unit/test_verbatim.py` exits 0.

---

## Key implementation notes

### 1. Round-trip invariant (central contract)

```python
parse_verbatim_blocks(render_verbatim_block(block, now=_NOW))[0].content == block.content
```

Every `content` comparison must be byte-identical — no whitespace normalisation.

### 2. Test cases present

| Test | Group | What it verifies |
|---|---|---|
| `test_roundtrip_code` | round-trip | CODE: `lang`, `source_id`, `staleness_risk=HIGH` survive |
| `test_roundtrip_prompt` | round-trip | PROMPT: `model_target` survives; `lang == ""` |
| `test_roundtrip_quote` | round-trip | QUOTE: `attribution` with commas/quotes survives |
| `test_roundtrip_transcript` | round-trip | TRANSCRIPT: `timestamp` survives |
| `test_parse_multiple_blocks` | multi-block | 3 blocks in body → `len == 3`; correct types |
| `test_parse_malformed_type` | malformed | Invalid `type:` → returns `[]` (no crash) |
| `test_parse_missing_end` | malformed | Missing `-->` → returns `[]` (no crash) |
| `test_parse_empty_body` | malformed | Empty string → returns `[]` |
| `test_render_omits_empty_optional_fields` | render detail | Empty `lang`, `attribution`, `timestamp`, `model_target` absent from output |
| `test_render_now_injected` | render detail | `added_at=None` uses injected `now` datetime |
| `test_render_quote_blockquote_format` | render detail | Every line after `-->` starts with `> ` |
| `test_render_code_uses_lang` | render detail | CODE fence opens with ` ```typescript ` |
| `test_parse_attribution_strips_quotes` | parse edge | `"Smith, p.5"` stored → `attribution == "Smith, p.5"` (no surrounding quotes) |
| `test_parse_added_at_none` | parse edge | Block rendered with `added_at=None` → parsed `added_at` is a valid `datetime` |

### 3. Helpers

- `_NOW = datetime(2026, 1, 1, 0, 0, 0)` — fixed timestamp for deterministic renders
- `_block(**kwargs)` — thin `VerbatimBlock(...)` constructor wrapper

### 4. Cross-cutting constraints

- No I/O, no anyio, no vault imports
- All tests synchronous — no `@pytest.mark.anyio` needed
- `staleness_risk` defaults to `StatenessRisk.MEDIUM` when not provided

---

## Data model changes

None — pure test module.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_verbatim.py` (file exists — all 17 cases present)

See table above.

### integration

No integration test for this module (pure transform, no I/O). Pipeline-level
verbatim coverage is `tests/integration/test_pipeline_verbatim.py` (★, separate TODO).

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `s4b_verbatim.py` stage logic | Separate test file |
| `outdated_review.py` staleness scan | Separate test file |
| Vault file I/O with verbatim blocks | Integration test scope |
| Editing existing verbatim blocks in a note | Phase 2 |

---

## Open questions

None. `vault-verbatim.md` fully specifies the wire format, regex, and round-trip
rule. All 17 cases are present in the file.
Proceed directly to `/review tests/unit/test_verbatim.py`.
