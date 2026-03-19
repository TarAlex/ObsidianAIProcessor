# Spec: tests/unit/test_models.py
slug: test-models
layer: tests
phase: 1
arch_section: §3 Core Data Models, §17 Testing Strategy

---

## Problem statement

`agent/core/models.py` is the foundational data layer — every pipeline stage and
adapter depends on it. This test module verifies that all v1.1 models (five enums +
nine Pydantic models) construct correctly, expose the right defaults, enforce required
fields, and obey the Pydantic v2 API contract. It also serves as a Phase 2 guard
(`AtomNote` must not be importable in Phase 1).

**Current state:** The file `tests/unit/test_models.py` already exists on disk with
all 19 required test cases implemented (created as a side-effect of the models-py
/build session). The /plan session confirms full coverage; no augmentation needed.
The /review → /done cycle is required to formally close this item.

---

## Module contract

Input:  `agent.core.models` (DONE) — imported directly; no I/O, no LLM, no vault.
Output: 19 passing pytest tests; `pytest tests/unit/test_models.py` exits 0.

---

## Key implementation notes

### 1. File already exists — review only

All 19 test cases from the models-py spec §Tests Required are present:

| Test | Status |
|---|---|
| `test_all_names_importable` | present |
| `test_source_type_values` | present (9 values + len check) |
| `test_content_age_values` | present (4 values) |
| `test_processing_status_values` | present (5 values) |
| `test_stateness_risk_values` | present (3 values + len check) |
| `test_verbatim_type_values` | present (4 values + len check) |
| `test_verbatim_block_required_fields` | present (construction + 2x ValidationError) |
| `test_verbatim_block_defaults` | present (all 7 optional fields) |
| `test_verbatim_block_content_docstring` | present (checks field description or docstring) |
| `test_normalized_item_construction` | present (helper + extra_metadata default) |
| `test_classification_result_has_domain_path` | present |
| `test_summary_result_verbatim_blocks_default` | present |
| `test_domain_index_entry_construction` | present |
| `test_processing_record_has_verbatim_count` | present |
| `test_person_reference_construction` | present (all optional field defaults) |
| `test_project_reference_construction` | present (all optional field defaults) |
| `test_no_atom_note_symbol` | present (Phase 2 guard) |
| `test_model_dump_not_dict` | present (v2 API: model_dump() + deprecation warning for .dict()) |
| `test_mutable_defaults_are_independent` | present (Field default_factory isolation) |

### 2. Cross-cutting constraints satisfied

- Pydantic v2 API used throughout (`model_fields`, `model_dump()`, `ValidationError`)
- `.dict()` check correctly expects `DeprecationWarning` (not `AttributeError`) — matches Pydantic v2 behaviour
- No hardcoded vault paths (uses `Path("/tmp/note.md")` as a dummy path, acceptable for unit tests)
- No LLM calls; no vault I/O; no anyio required (all models are synchronous)
- No inline fixture data — helper functions provide minimal construction data

### 3. One potential concern to verify at review

`test_model_dump_not_dict` captures `DeprecationWarning` from `.dict()`. In some
Pydantic v2 builds the warning is `PydanticDeprecatedSince20` (a `DeprecationWarning`
subclass). The test uses `issubclass(w[0].category, DeprecationWarning)` — this is
correct and covers both the base class and the subclass.

---

## Data model changes

None — this is a pure test module.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_models.py` (file exists — all 19 cases present)

See table in Key implementation notes §1.

### integration

None — `agent/core/models.py` has no I/O or external dependencies.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `AtomNote` test coverage | Phase 2 |
| `atom_concepts` population tests | Phase 2 (field exists but never populated in Phase 1) |
| Config model tests | Separate module: `test_config.py` (not in scope for this section) |
| Integration or pipeline tests | No I/O; unit layer is sufficient |
| Serialisation round-trip to JSON/YAML | Out of scope for this spec; covered implicitly by Pydantic internals |

---

## Open questions

None. File exists, coverage is complete, spec maps 1:1 to models-py spec test table.
Proceed directly to `/review tests/unit/test_models.py`.
