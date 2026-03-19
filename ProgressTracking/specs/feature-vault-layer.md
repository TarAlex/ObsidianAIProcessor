# Feature Spec: Vault Layer
slug: feature-vault-layer
sections_covered: [ProgressTracking/tasks/05_vault-layer.md]
arch_sections: [§7, §8, §11, §2.2, §3, §6-Stage7]

---

## Scope

The Vault Layer (`agent/vault/`) is the exclusive interface between the processing
pipeline and the physical Obsidian vault on disk. No other module may read or write
vault files directly. It provides:

- Atomic file I/O for all note types (source notes, knowledge notes, index files)
- Frontmatter parse/render (via `python-frontmatter`)
- Verbatim block render/parse with round-trip losslessness guarantee
- Jinja2 template rendering for `domain_index.md` and `subdomain_index.md`
- REFERENCES/ CRUD (people, work projects, personal projects)
- Archival of processed inbox files to `05_ARCHIVE/YYYY/MM/`

All six modules in this layer are currently **TODO** (confirmed in TRACKER.md).
Dependencies `models.py`, `config.py`, and the `pyproject-scaffold` are
**DONE** or **IN_PROGRESS** and considered stable enough to build against.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `agent/vault/vault.py` | `vault-py` | `models.py`, `config.py` | vault |
| 2 | `agent/vault/note.py` | `note-py` | `models.py`, `vault.py` | vault |
| 3 | `agent/vault/verbatim.py` | `vault-verbatim` | `models.py` (VerbatimBlock, VerbatimType, StatenessRisk) | vault |
| 4 | `agent/vault/templates.py` | `templates-py` | `config.py`, `vault.py` (path helpers) | vault |
| 5 | `agent/vault/references.py` | `references-py` | `vault.py`, `models.py`, `templates.py` | vault |
| 6 | `agent/vault/archive.py` | `archive-py` | `vault.py` | vault |

---

## Module responsibilities

### 1 — vault.py (`vault-py`)
`ObsidianVault` class. Central entry point for all vault I/O.

Key methods (arch §8):
- `__init__(root: Path)` — sets all zone path properties (inbox, knowledge, processing, archive, meta, etc.)
- `write_note(relative_path, frontmatter, body) → Path` — atomic write via `.tmp` → rename
- `read_note(relative_path) → (dict, str)` — inline YAML split; returns `(frontmatter_dict, body)`
- `archive_file(source_path, date_created) → Path` — move to `05_ARCHIVE/YYYY/MM/`
- `sync_in_progress() → bool` — checks for `.sync-*` or `.syncing` lock files
- `append_log(record: ProcessingRecord)` — append to `_AI_META/processing-log.md`
- `get_domain_index_path(domain, subdomain) → str` — returns relative path for `_index.md`
- `ensure_domain_index(relative_path, index_type, domain, subdomain)` — create from template if absent; **NEVER overwrites existing**
- `increment_index_count(relative_path)` — atomically bumps `note_count` and `last_updated` in frontmatter only; **body is not touched**
- `move_to_review(path, reason)` — moves file to `01_PROCESSING/to_review/`
- `move_to_merge(path, merge_result)` — moves file to `01_PROCESSING/to_merge/`

Special constraints:
- `write_note` MUST use `.tmp` temp file then `Path.rename()` for atomicity
- `ensure_domain_index` MUST call `render_template` from `templates.py` (lazy import to avoid circular)
- `increment_index_count` reads → mutates frontmatter dict → re-writes; body is passed through unchanged
- No hardcoded vault paths; all zones derived from `root`

---

### 2 — note.py (`note-py`)
Richer frontmatter parse/render using `python-frontmatter` library.
Used by pipeline stages that need structured access to note frontmatter (e.g. s6a_write, s6b_index_update).
Vault.py uses inline YAML for its own internal operations; note.py is the public API for the pipeline.

Key functions:
- `parse_note(path: Path) → (dict, str)` — uses `python-frontmatter.load()`; returns typed frontmatter and body
- `render_note(frontmatter: dict, body: str) → str` — renders full note string with YAML front block
- `build_source_frontmatter(item, classification, summary) → dict` — constructs §3.2 source note frontmatter from pipeline models
- `build_knowledge_frontmatter(classification, summary) → dict` — constructs §3.3 knowledge note frontmatter
- `compute_review_after(content_age: ContentAge, date_created: date) → str` — applies §3.1 offset rules

Special constraints:
- Uses `python-frontmatter`; not raw YAML string splitting
- No vault path writes — this module is pure parse/render
- `build_*_frontmatter` MUST populate `domain_path`, `staleness_risk`, `verbatim_count`, `verbatim_types`
- `compute_review_after` offsets from REQUIREMENTS.md §3.1: time-sensitive=+3m, dated=+12m, evergreen=+36m, personal=+6m

---

### 3 — verbatim.py (`vault-verbatim`)
Pure transform module: no vault path operations, no pipeline imports.

Key functions (arch §7):
- `render_verbatim_block(block: VerbatimBlock, now: datetime | None = None) → str`
  — renders HTML comment header + fenced block (code/prompt/transcript) or blockquote (quote)
- `parse_verbatim_blocks(body: str) → list[VerbatimBlock]`
  — regex-based extraction; malformed blocks silently skipped (no raise)

Round-trip contract (tested):
```
parse_verbatim_blocks(render_verbatim_block(block))[0].content == block.content  # byte-identical
```

Special constraints:
- Regex `_VERBATIM_RE` matches `<!-- verbatim ... -->` + fenced block or blockquote (arch §7)
- Quote type → `> line` blockquote format; all others → ` ```lang\n...\n``` ` fenced block
- `attribution`, `timestamp`, `model_target` included only when non-empty
- Malformed: `except Exception: continue` — no re-raise
- Zero imports from `agent.vault` or `agent.stages` (pure transform)

---

### 4 — templates.py (`templates-py`)
Jinja2 loader for `_AI_META/templates/`. Used by `vault.py#ensure_domain_index`
and `s6a_write` (source/knowledge note templates).

Key functions (arch §11):
- `render_template(name: str, ctx: dict) → str`
  — loads `{vault_meta_path}/templates/{name}`, renders with Jinja2 Environment
- `get_template_path(config) → Path` — derives `_AI_META/templates/` from `config.vault.root`

Templates served (Phase 1 only):
| Template | Used by |
|---|---|
| `domain_index.md` | `vault.ensure_domain_index` |
| `subdomain_index.md` | `vault.ensure_domain_index` |
| `source_base.md` | `s6a_write` |
| `source_youtube.md` | `s6a_write` |
| `source_article.md` | `s6a_write` |
| `source_course.md` | `s6a_write` |
| `source_ms_teams.md` | `s6a_write` |
| `source_pdf.md` | `s6a_write` |
| `knowledge_note.md` | `s6a_write` |

Special constraints:
- Jinja2 `Environment(autoescape=False)` — vault Markdown must not be HTML-escaped
- Paths from `config.vault.root` — no hardcoded paths
- No vault write operations (pure render)
- Template files are loaded lazily and cached in-process

---

### 5 — references.py (`references-py`)
REFERENCES/ CRUD operations for people and project references (REQUIREMENTS.md §2.2).

Key functions:
- `get_person(vault, name: str) → PersonReference | None` — reads `REFERENCES/people/{slug}.md`
- `upsert_person(vault, ref: PersonReference) → Path` — create or update person reference note
- `get_project(vault, ref_id: str) → ProjectReference | None` — reads from `REFERENCES/projects_work/` or `REFERENCES/projects_personal/`
- `upsert_project(vault, ref: ProjectReference) → Path` — create or update project reference note
- `list_people(vault) → list[PersonReference]` — scan `REFERENCES/people/`
- `list_projects(vault, ref_type: str) → list[ProjectReference]` — scan by type

Special constraints:
- All writes via `vault.write_note()` — never direct file I/O
- Person slug derived as `{FirstName}-{LastName}` (hyphen-joined, title-case)
- `date_modified` updated on every upsert
- Renders frontmatter from `PersonReference` / `ProjectReference` Pydantic models

---

### 6 — archive.py (`archive-py`)
Stage 7 implementation: move processed inbox files to `05_ARCHIVE/YYYY/MM/`.

Key functions:
- `archive_item(vault: ObsidianVault, item: NormalizedItem) → Path`
  — delegates to `vault.archive_file(item.raw_file_path, item.source_date or datetime.now())`
- `archive_raw(vault, path: Path, date_ref: datetime) → Path`
  — lower-level: moves a single file to `05_ARCHIVE/{year}/{month:02d}/`

Special constraints:
- Atomic move using `shutil.move()` (arch §8 `archive_file`)
- If `item.source_date` is None, falls back to `datetime.now()` for bucket path
- Does not delete originals — move only; caller responsible for error handling
- Destination filename: `{YYYYMMDD}-{original_filename}`

---

## Cross-cutting constraints

| Rule | Enforced by |
|---|---|
| All vault writes via `ObsidianVault.write_note()` | `vault.py` API; other modules must import and call it |
| `write_note` atomic: `.tmp` → `rename` | `vault.py` implementation |
| `ensure_domain_index` NEVER overwrites existing `_index.md` | Guard: `if target.exists(): return` |
| `increment_index_count` ONLY touches frontmatter — body untouched | Read-mutate-rewrite pattern |
| No Phase 2 code (`AtomNote`, `06_ATOMS`, MOC atom content) | Excluded from all 6 modules |
| No hardcoded vault paths or API keys | All paths derived from `config.vault.root` |
| Pydantic v2 models from `agent/core/models.py` | `NormalizedItem`, `VerbatimBlock`, `PersonReference`, `ProjectReference`, `DomainIndexEntry` |
| `anyio` not `asyncio` | Use `anyio.Path` or `anyio.to_thread.run_sync` if async file I/O needed |
| Python 3.11+ only | `from __future__ import annotations`; `X | Y` union syntax |
| `verbatim.py` — zero imports from vault or pipeline | Enforced by module boundary |

---

## Implementation ordering rationale

1. **vault.py first** — every other module in this layer depends on `ObsidianVault` for path resolution and atomic writes. It is the foundation; nothing else can be tested in integration without it.

2. **note.py second** — provides richer frontmatter parsing used by pipeline stages (s6a_write, etc.). Depends on vault.py for context (import of models), though note.py itself performs no writes.

3. **verbatim.py third** — pure transform with minimal dependencies (models.py only). Could be parallelised with note.py but sequential ordering matches the task file and avoids confusion. `parse_verbatim_blocks` is required by `outdated_review.py` (task layer) and `s6a_write`.

4. **templates.py fourth** — depends on vault.py (path helpers for `_AI_META/templates/`) and config. Required by `vault.ensure_domain_index` which lazy-imports it, so it must exist before vault is exercised end-to-end.

5. **references.py fifth** — depends on vault.py, models.py, and (optionally) templates.py for rendering person/project reference files from templates.

6. **archive.py last** — simplest module; thin wrapper over `vault.archive_file`. All dependencies are already in place.

---

## Excluded (Phase 2 or out of scope)

| Item | Reason |
|---|---|
| `06_ATOMS/` support | Phase 2 — `AtomNote` model not in scope |
| `atom_note.md` template rendering | Phase 2 |
| MOC atom-level content in `_index.md` body | Phase 2 — body is Bases-only, agent never writes body |
| Bi-directional link proposals | Phase 2 |
| Prompt version migration (`model_target` superseded detection) | Phase 2 |
| `_index.md` body modification of any kind | Explicitly forbidden — Bases queries self-refresh |
