# Spec: tests/unit/test_vault.py
slug: test-vault
layer: tests
phase: 1
arch_section: §8 Vault Layer, §17 Testing Strategy

---

## Problem statement

`agent/vault/vault.py` is the single gatekeeper for all physical vault I/O.
Every pipeline stage depends on it. This test module verifies the full public
API of `ObsidianVault`: zone path derivation, atomic writes, round-trip reads,
archive routing, sync-lock detection, log appending, domain-index management,
and file routing helpers.

**Current state:** `tests/unit/test_vault.py` exists on disk with all 30
required test cases implemented. The `/plan` session confirms full coverage
against the `vault-py.md` spec. Proceed directly to `/review tests/unit/test_vault.py`.

---

## Module contract

Input:  `agent.vault.vault.ObsidianVault` (DONE) — all tests via `tmp_path`.
Output: 30 passing pytest tests; `pytest tests/unit/test_vault.py` exits 0.

---

## Key implementation notes

### 1. Fixture strategy

- All tests use `pytest`'s `tmp_path` fixture as the vault root — no real vault.
- `render_template` is patched via
  `@patch("agent.vault.templates.render_template", return_value="mock body")`
  in the `ensure_domain_index` tests to avoid pulling in Jinja2 before
  `templates.py` is implemented.
- A `_make_index(vault, rel, note_count, body)` helper seeds pre-existing
  `_index.md` files for increment tests.

### 2. Test cases present

| Test | Group | What it verifies |
|---|---|---|
| `test_zone_paths_derived_from_root` | zone paths | All 11 zone attributes equal `root / expected_suffix` |
| `test_write_note_creates_file` | write_note | File exists after write |
| `test_write_note_frontmatter_serialized` | write_note | YAML block present; key survives `yaml.safe_load` round-trip |
| `test_write_note_atomic_tmp_removed` | write_note | `.tmp` file absent after successful write |
| `test_write_note_creates_parent_dirs` | write_note | Nested path directories created |
| `test_read_note_with_frontmatter` | read_note | Returns correct `(dict, str)` for frontmatter file |
| `test_read_note_no_frontmatter` | read_note | Returns `({}, full_content)` for plain file |
| `test_read_note_empty_frontmatter` | read_note | Empty `---\n---` block returns `{}` |
| `test_archive_file_moves_to_bucket` | archive_file | File at `05_ARCHIVE/{year}/{month:02d}/YYYYMMDD-name.md` |
| `test_archive_file_source_removed` | archive_file | Source path gone after archive |
| `test_archive_file_bucket_created` | archive_file | Bucket directory created when absent |
| `test_sync_in_progress_no_lock` | sync | Returns `False` with no lock files |
| `test_sync_in_progress_sync_star` | sync | Returns `True` with `.sync-abc` present |
| `test_sync_in_progress_syncing` | sync | Returns `True` with `.syncing` present |
| `test_append_log_creates_file` | append_log | Creates `_AI_META/processing-log.md` on first call |
| `test_append_log_appends_not_overwrites` | append_log | Two calls → both raw_ids in file |
| `test_append_log_format_contains_raw_id` | append_log | Log entry contains `record.raw_id` |
| `test_get_domain_index_path_domain_only` | path helper | Returns `"02_KNOWLEDGE/wellbeing/_index.md"` |
| `test_get_domain_index_path_with_subdomain` | path helper | Returns `"02_KNOWLEDGE/wellbeing/health/_index.md"` |
| `test_ensure_domain_index_creates_when_absent` | ensure | File created; `note_count: 0` and tag `index/domain` |
| `test_ensure_domain_index_never_overwrites` | ensure | Pre-existing file byte-identical; `render_template` not called |
| `test_ensure_domain_index_subdomain_uses_subdomain_template` | ensure | `render_template` called with `"subdomain_index.md"` |
| `test_ensure_domain_index_domain_uses_domain_template` | ensure | `render_template` called with `"domain_index.md"` |
| `test_increment_index_count_increments` | increment | `note_count` 0 → 1 |
| `test_increment_index_count_updates_last_updated` | increment | `last_updated` field set to today's ISO date |
| `test_increment_index_count_body_unchanged` | increment | Bases-query body string byte-identical after increment |
| `test_increment_index_count_noop_when_absent` | increment | No exception when target does not exist |
| `test_move_to_review_moves_file` | routing | File in `to_review/`; source gone |
| `test_move_to_review_creates_dir` | routing | `to_review/` directory created |
| `test_move_to_merge_moves_file` | routing | File in `to_merge/`; source gone |

### 3. Cross-cutting constraints

- No LLM calls, no anyio, no real vault paths
- `ProcessingRecord` and `SourceType` imported from `agent.core.models`
- `_record(**overrides)` helper builds minimal `ProcessingRecord` for log tests

---

## Data model changes

None — pure test module.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_vault.py` (file exists — all 30 cases present)

See table in §Key implementation notes.

### integration

Covered by `tests/integration/test_pipeline_index.py` (★, separate TODO item).

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `note.py` parse logic | `test_note.py` exists separately |
| `templates.py` rendering | `test_templates.py` exists separately |
| Async vault I/O | Phase 1 vault is synchronous |
| Phase 2 `06_ATOMS/` paths | Phase 2 |

---

## Open questions

None. File exists, all 30 cases match the `vault-py.md` test table.
Proceed directly to `/review tests/unit/test_vault.py`.
