# Spec: Reference Linker Task

slug: reference-linker
layer: tasks
phase: 1
arch_section: §2.2 REFERENCES (REQUIREMENTS.md)

---

## Problem statement

The pipeline (Stage 4a) detects people and projects by name and stores them as
plain strings in frontmatter (`related_people`, `related_projects`), but note
**bodies** are never retroactively linked to `REFERENCES/` files. Over time,
notes accumulate plain-text mentions of people (e.g. "Alice Johnson") and
projects that have confirmed reference files, yet no Obsidian wikilink connects
them. This creates a navigability gap: clicking on a person's name in a note
doesn't jump to their reference card.

`reference_linker.py` is a scheduled / on-demand task that scans every content
note under `02_KNOWLEDGE/`, finds plain-text entity mentions whose reference
files are confirmed to exist, and injects `[[wikilinks]]` for the first
occurrence of each entity in the note body — without touching frontmatter,
without removing any content, and without creating dangling links.

---

## Module contract

**Entry point:**
```python
async def run(vault: ObsidianVault, config: AgentConfig) -> None
```

- Called by `agent/core/scheduler.py` on a weekly cron (same scheduler already
  wires `outdated_review`; `reference_linker` shares the weekly slot or runs
  separately per config).
- May also be triggered on-demand via `agent/main.py` CLI.
- `config` parameter accepted for future configurability (e.g. scope filter);
  not read in Phase 1. Must remain in signature.

**Input:** `ObsidianVault` + `AgentConfig` (already constructed by caller)

**Output:** `None` — side effects are in-place body edits to existing notes via
`vault.write_note()`. Frontmatter is **never** modified.

**Internal helpers (not exported):**
```python
def _load_entity_map(vault: ObsidianVault) -> dict[str, str]:
    """Return {mention_text: wikilink_string} for all confirmed reference files.

    mention_text: full_name / nickname (people) or project_name / ref_id (projects)
    wikilink_string: the full [[vault-relative/path|display]] string to inject
    """

def _inject_links(body: str, entity_map: dict[str, str]) -> tuple[str, int]:
    """Return (updated_body, count_of_links_added).

    Replaces the first plain-text occurrence of each mention_text with its
    wikilink, only when the entity slug is not already present in any existing
    [[...]] wikilink in the body.
    """
```

---

## Key implementation notes

### 1. Load entity map

```python
from agent.vault.references import list_people, list_projects

people  = list_people(vault)
work    = list_projects(vault, "project_work")
personal = list_projects(vault, "project_personal")
```

Build `entity_map: dict[str, str]` — mapping **every mention variant** to the
wikilink string to inject:

**People:**
For each `PersonReference` ref:
- slug = `ref.full_name.strip().replace(" ", "-").title()`
  (mirrors `_slug_from_name` in `references.py` — import the private helper
   or replicate the one-liner; do **not** re-implement independently; import
   `_slug_from_name` from `agent.vault.references`)
- wikilink_path = `REFERENCES/people/{slug}` (no `.md` — Obsidian convention)
- wikilink = `[[REFERENCES/people/{slug}|{ref.full_name}]]`
- Register under `ref.full_name` as mention key.
- If `ref.nickname` is non-empty, **also** register under `ref.nickname` →
  same wikilink. Longer keys take precedence when both are present in a note
  (process longer keys first to avoid partial replacement).

**Projects:**
For each `ProjectReference` ref (work and personal combined):
- subdir = `projects_work` if `ref.ref_type == "project_work"` else
  `projects_personal`
- wikilink = `[[REFERENCES/{subdir}/{ref.ref_id}|{ref.project_name}]]`
- Register under `ref.project_name` AND `ref.ref_id` as separate mention keys.

Priority: process mention keys in **descending length order** to avoid
short substrings clobbering longer matches (e.g. nickname "Alice" must not
fire before "Alice Johnson" if both are in the map).

### 2. Walk content notes

```python
for path in vault.knowledge.rglob("*.md"):
    if path.name == "_index.md":
        continue
    rel = path.relative_to(vault.root).as_posix()
    try:
        fm, body = vault.read_note(rel)
    except Exception:
        logger.warning("reference_linker.read_error path=%s", rel)
        continue
    ...
```

### 3. Inject links into body (`_inject_links`)

For each `(mention_text, wikilink)` pair (sorted by descending `len(mention_text)`):

**Step A — already linked?**
Extract slug from wikilink path (the part between `[[` and `|`):
```python
import re
slug = re.search(r'\[\[([^\]|]+)', wikilink).group(1)
already_linked = bool(re.search(re.escape(slug), body))
```
If `already_linked`, skip this entity.

**Step B — plain-text mention present?**
```python
mention_present = mention_text in body
```
Simple substring check (case-sensitive, Phase 1). If not present, skip.

**Step C — inject first occurrence only:**
```python
body = body.replace(mention_text, wikilink, 1)
links_added += 1
```

Return `(body, links_added)`.

### 4. Write back

```python
updated_body, count = _inject_links(body, entity_map)
if count > 0:
    vault.write_note(rel, fm, updated_body)
    notes_linked += 1
    total_links += count
    logger.info(
        "reference_linker.linked path=%s links_added=%d", rel, count
    )
```

**Never call `vault.write_note` when `count == 0`** — avoids spurious vault
activity and preserves `date_modified` semantics.

### 5. Event logging

```python
logger.info("reference_linker.scan.started")
# ... scan ...
logger.info(
    "reference_linker.scan.completed notes_scanned=%d notes_linked=%d links_added=%d",
    notes_scanned, notes_linked, total_links
)
```

Use `logging.getLogger(__name__)`.

### 6. Idempotency

Re-running the task on a vault where all links have already been injected
produces zero writes because Step A (`already_linked`) will be True for every
entity in every note. The task is safe to run repeatedly.

### 7. `anyio` note

`run()` is declared `async def` to satisfy the APScheduler async job interface.
Phase 1 body is synchronous filesystem I/O — no `await` calls required.

### 8. Error resilience

- `vault.read_note` failures → `logger.warning` + `continue` (scan continues).
- `list_people` / `list_projects` failures → let propagate (caller sees a
  structured exception; scheduler retries per its own policy).
- Empty `REFERENCES/` directories → `list_people` / `list_projects` return `[]`;
  `entity_map` is empty; scan exits with zero writes — not an error.

---

## Data model changes

None. Uses existing models from `agent.core.models`:
- `PersonReference` (fields: `full_name`, `nickname`, `ref_id`)
- `ProjectReference` (fields: `project_name`, `ref_id`, `ref_type`)

`AgentConfig` / `VaultConfig`: no new config keys in Phase 1. The `config`
parameter is accepted in the signature for forward compatibility.

---

## LLM prompt file needed

None — this task makes no LLM calls.

---

## Tests required

### unit: `tests/unit/test_reference_linker.py`

Use `tmp_path` fixture for vault root. Create minimal `REFERENCES/` tree and
`02_KNOWLEDGE/` notes as fixtures.

| Test case | What it verifies |
|---|---|
| `test_person_fullname_linked` | First occurrence of `full_name` is replaced with wikilink |
| `test_person_nickname_linked` | Nickname variant also triggers link injection |
| `test_project_name_linked` | `project_name` mention triggers project wikilink |
| `test_project_ref_id_linked` | `ref_id` mention also triggers project wikilink |
| `test_first_occurrence_only` | Only the 1st occurrence of entity name is replaced; 2nd remains plain |
| `test_existing_wikilink_not_duplicated` | If `[[REFERENCES/people/Alice-Jones]]` already in body, no new link added |
| `test_no_mention_no_write` | Note without any entity name → `vault.write_note` NOT called |
| `test_frontmatter_unchanged` | After injection, frontmatter keys are identical to pre-run values |
| `test_index_files_skipped` | `_index.md` files are never read or written |
| `test_empty_references_no_links` | Empty `REFERENCES/` dirs → scan completes, zero writes |
| `test_longer_mention_wins` | "Alice Johnson" is linked before "Alice" when both are in entity map |
| `test_multiple_entities_same_note` | Two different entities in one note → both linked in single write |
| `test_idempotent_rerun` | Second `run()` on already-linked vault → zero writes |
| `test_malformed_note_skipped` | `vault.read_note` raising `ValueError` → warning logged, scan continues |
| `test_events_emitted` | `reference_linker.scan.started` and `.scan.completed` appear in caplog |
| `test_no_dangling_links` | Entity with no file in `REFERENCES/` is not returned by `list_people` and never injected |

### integration: not required for Phase 1

The task's surface area is fully exercised by unit tests with a `tmp_path`
vault. Integration with the scheduler is tested at the scheduler layer.

---

## Explicitly out of scope

- **No frontmatter modification** — `related_people` / `related_projects` lists
  are already populated by Stage 4a; this task touches the body only.
- **No auto-delete or auto-archive** — linker only adds links, never removes
  content (REQ §2.2 constraint).
- **No LLM calls** — purely structural string matching (Phase 1).
- **No scanning outside `02_KNOWLEDGE/`** — source notes in `01_PROCESSING/`,
  project hubs in `03_PROJECTS/`, `04_PERSONAL/`, and atoms in `06_ATOMS/`
  are out of scope for Phase 1.
- **No back-link proposal** — bi-directional link suggestions are Phase 2
  (REQ §11).
- **No case-insensitive matching** — Phase 1 uses exact case. Fuzzy / case-fold
  matching is Phase 2.
- **No birthday digest** — Phase 2 (feature spec §Excluded).
- **No vector store interaction** — deduplication is pipeline Stage 5, not a
  scheduled task.
- **No `_AI_META/processing-log.md` entries** — this task is not a per-file
  pipeline run.

---

## Open questions

None — the feature spec §3 (`reference_linker.py`) fully specifies the
algorithm from REQUIREMENTS §2.2. The "first occurrence only" injection
strategy and the slug-based already-linked check are standard Obsidian
conventions and match the idempotency constraint from the feature spec's
cross-cutting constraints table.
