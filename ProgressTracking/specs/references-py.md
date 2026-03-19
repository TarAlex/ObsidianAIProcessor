# Spec: references.py — REFERENCES/ CRUD
slug: references-py
layer: vault
phase: 1
arch_section: §8 (Vault Layer API), §2.2 (REFERENCES Structure)

## Problem statement

Pipeline stages (s4a_summarize, s6a_write, s6c_references) need to create and
update person and project reference notes in `REFERENCES/` as named entities are
detected in source content. No other module may write to `REFERENCES/` directly.

`references.py` is the exclusive interface for all REFERENCES/ file operations:
create-or-update person notes under `REFERENCES/people/`, work project notes under
`REFERENCES/projects_work/`, and personal project notes under
`REFERENCES/projects_personal/`. All reads and writes route through `ObsidianVault`.

---

## Module contract

```
Input:
  - vault: ObsidianVault           (always first arg)
  - name: str                      (for get_person — full name, any casing)
  - ref: PersonReference           (for upsert_person)
  - ref_id: str                    (for get_project)
  - ref: ProjectReference          (for upsert_project)
  - ref_type: str                  (for list_projects — "project_work" | "project_personal")

Output:
  - get_person  → PersonReference | None
  - upsert_person → Path
  - get_project → ProjectReference | None
  - upsert_project → Path
  - list_people → list[PersonReference]
  - list_projects → list[ProjectReference]
```

---

## Key implementation notes

### 1 — Public API (six functions)

```python
def get_person(vault: ObsidianVault, name: str) -> PersonReference | None
def upsert_person(vault: ObsidianVault, ref: PersonReference) -> Path
def get_project(vault: ObsidianVault, ref_id: str) -> ProjectReference | None
def upsert_project(vault: ObsidianVault, ref: ProjectReference) -> Path
def list_people(vault: ObsidianVault) -> list[PersonReference]
def list_projects(vault: ObsidianVault, ref_type: str) -> list[ProjectReference]
```

### 2 — Path derivation

All paths are vault-relative (passed to `vault.write_note` / `vault.read_note`).
`vault.references` resolves to `vault.root / "REFERENCES"`.

| Reference type | Vault-relative path |
|---|---|
| Person | `REFERENCES/people/{slug}.md` |
| Work project | `REFERENCES/projects_work/{ref_id}.md` |
| Personal project | `REFERENCES/projects_personal/{ref_id}.md` |

Person slug: `_slug_from_name(full_name: str) -> str`
- Strip extra whitespace, split on whitespace, title-case each part, join with `-`
- `"john doe"` → `"John-Doe"`, `"María García"` → `"María-García"`
- `"alice"` → `"Alice"` (single word: no hyphen)

Project subdirectory from `ref_type`:
```python
_REF_TYPE_TO_DIR = {
    "project_work": "projects_work",
    "project_personal": "projects_personal",
}
```
Raise `ValueError` if `ref_type` is not in the map.

### 3 — upsert semantics

**Create (note does not exist):**
- Set `ref.date_added = date.today()` (only if `None`)
- Set `ref.date_modified = date.today()`
- Serialize frontmatter via `ref.model_dump(mode="json")`; filter `None` values
- Build body: `# {full_name}\n` for person, `# {project_name}\n` for project
- Call `vault.write_note(relative_path, frontmatter, body)`

**Update (note already exists):**
- Read existing note: `vault.read_note(relative_path)` → `(existing_fm, body)`
- Merge: existing_fm takes precedence for `date_added` (preserve original)
- Overlay new `ref` fields: `existing_fm.update(new_fm)` but restore `date_added`
- Set `date_modified = date.today()` always
- Re-write via `vault.write_note(relative_path, merged_fm, body)` — body unchanged

### 4 — get_* semantics

- Derive relative path from `name` / `ref_id`
- Call `vault.read_note(relative_path)` — if file missing, `read_note` raises `FileNotFoundError`
- Catch `FileNotFoundError` → return `None`
- Deserialize: `PersonReference(**frontmatter)` / `ProjectReference(**frontmatter)` — Pydantic
  ignores extra keys by default; wrap in `try/except ValidationError → return None`

### 5 — get_project path resolution

`get_project(vault, ref_id)` does not require the caller to pass `ref_type`.
Strategy: try `projects_work/{ref_id}.md` first; if not found, try
`projects_personal/{ref_id}.md`; if neither exists, return `None`.

### 6 — list_* implementations

```python
def list_people(vault):
    pattern = vault.references / "people" / "*.md"
    for path in sorted(pattern.parent.glob("*.md")):
        rel = path.relative_to(vault.root).as_posix()
        fm, _ = vault.read_note(rel)
        try:
            yield PersonReference(**fm)   # collect to list before returning
        except Exception:
            continue   # skip malformed notes silently
```

Same pattern for `list_projects` — filter by subdirectory using `_REF_TYPE_TO_DIR`.
Both return `list[...]` (not generator).

### 7 — No template dependency for body

Body is a minimal markdown heading. This makes the module independent of
`templates.py` status (currently IN_PROGRESS). The body from existing notes is
preserved verbatim on updates (read body → re-write unchanged body).

### 8 — No `_index.md` updates

`REFERENCES/_index.md` is a Bases self-refreshing view. This module does NOT call
`vault.ensure_domain_index` or `vault.increment_index_count` for REFERENCES.
Index management for REFERENCES is the responsibility of `scripts/setup_vault.py`.

### 9 — Tags

On create, apply minimal standard tags:
- Person: `["ref/person", f"relationship/{ref.relationship}"]` (skip relationship tag if empty)
- Work project: `["ref/project", "ref/work"]`
- Personal project: `["ref/project", "ref/personal"]`

If `ref.tags` is non-empty, merge rather than overwrite. On update, preserve existing tags.

---

## Data model changes

None. Both `PersonReference` and `ProjectReference` are already defined in
`agent/core/models.py` and are used directly.

---

## LLM prompt file needed

None. This module is pure CRUD with no LLM calls.

---

## Tests required

**Unit: `tests/unit/test_references.py`**

All tests use `tmp_path` (pytest fixture) to create a minimal fake vault;
a real `ObsidianVault(tmp_path)` is used (not mocked) so writes hit the filesystem.

| Test | What it proves |
|---|---|
| `test_slug_from_name_two_words` | `"john doe"` → `"John-Doe"` |
| `test_slug_from_name_single_word` | `"Alice"` → `"Alice"` |
| `test_slug_from_name_extra_whitespace` | `"  john  doe  "` → `"John-Doe"` |
| `test_upsert_person_creates_file` | File written at correct path; frontmatter round-trips |
| `test_upsert_person_sets_dates_on_create` | `date_added` and `date_modified` both set |
| `test_upsert_person_update_preserves_date_added` | Second upsert keeps original `date_added` |
| `test_upsert_person_update_updates_date_modified` | Second upsert updates `date_modified` |
| `test_upsert_person_preserves_body_on_update` | Body text unchanged after second upsert |
| `test_get_person_returns_model` | Existing note deserialized to `PersonReference` |
| `test_get_person_missing_returns_none` | Non-existent name → `None` (no exception) |
| `test_upsert_project_work_creates_in_projects_work` | Path is `REFERENCES/projects_work/…` |
| `test_upsert_project_personal_creates_in_projects_personal` | Path is `REFERENCES/projects_personal/…` |
| `test_upsert_project_invalid_ref_type_raises` | `ValueError` for unknown `ref_type` |
| `test_get_project_work` | Finds a work project by `ref_id` |
| `test_get_project_personal` | Finds a personal project by `ref_id` |
| `test_get_project_checks_both_dirs` | Searches work dir first, falls back to personal |
| `test_get_project_missing_returns_none` | Non-existent `ref_id` → `None` |
| `test_list_people_empty` | Empty `REFERENCES/people/` → `[]` |
| `test_list_people_returns_all` | Three person notes → list of 3 `PersonReference` |
| `test_list_people_skips_malformed` | One malformed note → silently skipped |
| `test_list_projects_filters_by_type` | Only work projects returned when `ref_type="project_work"` |
| `test_all_writes_use_vault_write_note` | Monkey-patch `vault.write_note`; assert called on upsert |

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `REFERENCES/_index.md` creation / updates | Self-refreshing Bases view; setup_vault.py responsibility |
| Wikilink injection into other notes | Pipeline stage s6c_references / s4a_summarize |
| Template-based body rendering | Templates IN_PROGRESS; inline markdown body is sufficient |
| Birthday reminder / weekly digest | Phase 2 (REQUIREMENTS.md §11) |
| `model_target` migration for prompt references | Phase 2 |
| Search / fuzzy match on person names | Not required for Phase 1 CRUD |
| Bulk import from external CRM or contact list | Out of scope |

---

## Open questions

1. **Case normalization for slug**: the `_slug_from_name` uses `.title()` which works
   for ASCII names but may not be correct for names with unicode (e.g. `mcnamara` →
   `Mcnamara` not `McNamara`). Phase 1: use `.title()` as-is, flag as known limitation.

2. **ref_id format for projects**: `ProjectReference.ref_id` is a plain string.
   Convention (`project-slug-2026`) should be documented but is not enforced by this
   module — the caller (stage s6c or reference_linker) is responsible.

3. **Conflict on `get_project` when same `ref_id` exists in both directories**: unlikely
   but theoretically possible. Implementation: first match wins (work dir first).
   Log a warning but do not raise.
