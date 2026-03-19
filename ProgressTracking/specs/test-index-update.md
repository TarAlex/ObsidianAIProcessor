# Spec: tests/unit/test_index_update.py ★
slug: test-index-update
layer: tests
phase: 1
arch_section: §6 Stage 6b — Domain Index Update, §17 Testing Strategy

---

## Problem statement

`agent/stages/s6b_index_update.py` is the ★ stage that keeps `_index.md`
frontmatter (`note_count`, `last_updated`) accurate after each note write.
Incorrect index behaviour would silently corrupt domain MOC navigation in the
vault. This test module verifies call order, single- vs. two-segment domain
paths, body immutability, idempotent index creation, error isolation, and the
delegation contract (stage uses `vault.get_domain_index_path`, not hand-rolled
f-strings).

**Current state:** `tests/unit/test_index_update.py` exists on disk with all 8
required test cases implemented. The `/plan` session confirms full coverage
against `s6b-index-update.md`. Proceed to `/review tests/unit/test_index_update.py`.

---

## Module contract

Input:  `agent.stages.s6b_index_update.run(classification, vault)`
        `agent.core.models.ClassificationResult`
        `agent.vault.vault.ObsidianVault`
Output: 8 passing pytest tests; `pytest tests/unit/test_index_update.py` exits 0.

---

## Key implementation notes

### 1. Test strategy: two modes

Tests 1–3 and 7–8 use a `MagicMock(spec=ObsidianVault)` to isolate call-count
and call-order assertions from filesystem behaviour.

Tests 4–6 use a real `ObsidianVault(tmp_path)` with
`@patch("agent.vault.templates.render_template", return_value="mock body")`
to verify filesystem side-effects.

All async execution driven by `anyio.run()` via a local `_run_sync(cls, vault)` helper.

### 2. Test cases present

| # | Test | Mode | What it verifies |
|---|---|---|---|
| 1 | `test_subdomain_and_domain_both_updated` | mock | Two-segment path → `ensure_domain_index` ×2, `increment_index_count` ×2; correct args |
| 2 | `test_single_segment_domain_path_only` | mock | Single-segment path → each method called exactly once; subdomain methods not called |
| 3 | `test_ensure_called_before_increment` | mock | `ensure` precedes `increment` in mock call order (MagicMock manager attach) |
| 4 | `test_index_body_unchanged` | real vault | Pre-existing `_index.md` body is byte-identical after `run(...)` |
| 5 | `test_creates_index_if_missing` | real vault | Missing `_index.md` created; `note_count == 1` for both subdomain and domain |
| 6 | `test_increments_existing_count` | real vault | Existing `note_count: 3` → `4` after `run(...)` |
| 7 | `test_exception_does_not_propagate` | mock | `ensure_domain_index` raises `RuntimeError`; `run(...)` completes without raising |
| 8 | `test_get_domain_index_path_used` | mock | `vault.get_domain_index_path` called ≥ 2 times (delegation contract) |

### 3. Helpers

- `_make_classification(domain_path)` — builds minimal `ClassificationResult`
- `_make_mock_vault()` — `MagicMock(spec=ObsidianVault)` with `get_domain_index_path.side_effect`
- `_run_sync(cls, vault)` — `anyio.run` wrapper around the `async def run` coroutine

### 4. Cross-cutting constraints

- `anyio` used for async execution (not `asyncio.run`)
- `render_template` patched at `agent.vault.templates.render_template`
- No hardcoded vault paths in tests (all paths flow from `vault.get_domain_index_path`)

---

## Data model changes

None — pure test module.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_index_update.py` (file exists — all 8 cases present)

See table above.

### integration

`tests/integration/test_pipeline_index.py` (★, separate TODO). That file will
also cover `rebuild_all_counts` from `index_updater.py`.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `index_updater.py` rebuild_all_counts | Separate test file (`test_index_updater.py`) |
| `s6a_write.py` note rendering | Separate test file |
| Phase 2 `06_ATOMS/` index updates | Phase 2 |
| Multi-level domain hierarchies (> 2 segments) | Architecture specifies two-level only |

---

## Open questions

None. `s6b-index-update.md` §Tests required maps 1:1 to the 8 cases present.
Proceed directly to `/review tests/unit/test_index_update.py`.
