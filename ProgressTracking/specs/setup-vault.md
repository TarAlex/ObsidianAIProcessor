# Spec: Vault Setup Script
slug: setup-vault
layer: scripts
phase: 1
arch_section: §8, §11

## Problem statement

On a fresh vault installation none of the structural `_index.md` files exist yet.
The pipeline expects them to be present (Stage 6b `ensure_domain_index` increments
`note_count` in each index). Without an initial bootstrapper the first note written
to any domain creates a subdomain index on-the-fly, but zone-level roots
(`02_KNOWLEDGE/`, `03_PROJECTS/`, `04_PERSONAL/`, `REFERENCES/`) never receive
their indexes because there is no "first note" event for them.

`scripts/setup_vault.py` is a standalone one-shot bootstrapper that walks the
entire expected vault tree and calls `vault.ensure_domain_index()` for every
folder that should contain an `_index.md`. It is idempotent — safe to re-run any
number of times; it never overwrites a file that already exists.

---

## Module contract

```
Input:   CLI args --config PATH  (default "_AI_META/agent-config.yaml")
                  --dry-run      (report only; do not create files)

Output:  Console summary line:
           "Setup complete: N created, M skipped."   (normal)
           "Dry-run: N would be created, M already exist."  (dry-run)

Written files:
           _index.md files at the paths listed in "Folder targets" below,
           only where they are absent.

Exit codes:
  0 — success
  1 — config load failure (ConfigError)
  2 — template directory missing (FileNotFoundError)
  3 — one or more per-file errors occurred (partial run)
```

---

## Key implementation notes

### Folder targets (in traversal order)

| Relative path | index_type | domain arg | subdomain arg |
|---|---|---|---|
| `02_KNOWLEDGE/_index.md` | `"global"` | `"knowledge"` | `None` |
| `02_KNOWLEDGE/{d}/_index.md` | `"domain"` | `{d}` | `None` |
| `02_KNOWLEDGE/{d}/{s}/_index.md` | `"subdomain"` | `{d}` | `{s}` |
| `03_PROJECTS/_index.md` | `"zone"` | `"projects"` | `None` |
| `04_PERSONAL/_index.md` | `"zone"` | `"personal"` | `None` |
| `REFERENCES/_index.md` | `"zone"` | `"references"` | `None` |

**`06_ATOMS/` is explicitly skipped — Phase 2 only.**

Zone-level and global-level indexes use `domain_index.md` template (the
`ensure_domain_index` fallback when `subdomain is None`). The Bases query bodies
generated for zone indexes reference the wrong `domain_path` filter prefix by
default; this is acceptable because:
(a) these indexes are created once and humans can customise the body,
(b) `ensure_domain_index` never overwrites existing files, so any customised content
    is preserved on re-runs.
The frontmatter (`index_type`, `domain`, `note_count`, `last_updated`, `tags`) is
always correct.

### Traversal logic

```
1. ensure("02_KNOWLEDGE/_index.md", "global", "knowledge", None)
2. for each directory D under vault.knowledge/:
     ensure(f"02_KNOWLEDGE/{D.name}/_index.md", "domain", D.name, None)
     for each directory S under D/:
         ensure(f"02_KNOWLEDGE/{D.name}/{S.name}/_index.md",
                "subdomain", D.name, S.name)
3. ensure("03_PROJECTS/_index.md",  "zone", "projects",  None)
4. ensure("04_PERSONAL/_index.md",  "zone", "personal",  None)
5. ensure("REFERENCES/_index.md",   "zone", "references", None)
```

Only one level of subdomain is walked (`domain/subdomain/`). Deeper nesting is
not supported in Phase 1 (not in the vault structure spec).

### `ensure()` helper

```python
def _ensure(vault, relative_path, index_type, domain, subdomain, dry_run):
    target = vault.root / relative_path
    if target.exists():
        return "skipped"
    if dry_run:
        return "would_create"
    vault.ensure_domain_index(relative_path, index_type, domain, subdomain)
    return "created"
```

The `_ensure` helper checks existence before delegating, so the counters are
accurate. `vault.ensure_domain_index()` would also guard against overwrites
internally; the pre-check here is for the dry-run path only.

### Error handling

- `ConfigError` from `load_config` → `print` to stderr, `sys.exit(1)`
- `FileNotFoundError` from a missing template directory
  (raised by `render_template` inside `ensure_domain_index`) → print to stderr,
  `sys.exit(2)`. This indicates the vault is not properly seeded with template
  files.
- Per-file `Exception` (e.g. template render fails for one domain) → log warning
  to stderr, continue traversal, increment an `errors` counter. After all targets
  are processed, if `errors > 0` exit with code 3.

### Config loading

```python
from agent.core.config import load_config, ConfigError
from agent.vault.vault import ObsidianVault

config = load_config(args.config)
vault = ObsidianVault(config.vault_root)
```

Default config path is relative to CWD (`"_AI_META/agent-config.yaml"`), matching
the convention used throughout `agent/main.py`.

### No async

`vault.ensure_domain_index()` and `vault.write_note()` are both synchronous.
No `asyncio.run()` is needed in this script (unlike `reindex.py` which wraps the
async `rebuild_all_counts`).

### CLI interface

Use `argparse` (stdlib, no extra dependency):

```
python scripts/setup_vault.py [--config PATH] [--dry-run]

Options:
  --config PATH   Path to agent-config.yaml  [default: _AI_META/agent-config.yaml]
  --dry-run       Report what would be created without writing any files
```

---

## Data model changes (if any)

None. Uses existing `DomainIndexEntry` from `agent/core/models.py` (consumed
internally by `vault.ensure_domain_index()`).

---

## LLM prompt file needed (if any)

None. This script makes no LLM calls.

---

## Tests required

- unit: `tests/unit/test_setup_vault.py`

  All unit tests use pytest's `tmp_path` fixture to create a real temporary
  directory tree. `agent.vault.templates.render_template` is patched to return a
  minimal stub string (avoids requiring actual Jinja2 template files on disk).

  Key cases:
  1. `test_creates_knowledge_root_index` — `02_KNOWLEDGE/_index.md` absent →
     created; frontmatter `index_type == "global"`, `domain == "knowledge"`.
  2. `test_creates_domain_index` — domain dir present, no `_index.md` → created
     with `index_type == "domain"`.
  3. `test_creates_subdomain_index` — subdomain dir present, no `_index.md` →
     created with `index_type == "subdomain"`, correct `domain` + `subdomain`.
  4. `test_skips_existing_index` — pre-existing `_index.md` is not touched; file
     content and mtime unchanged after setup run.
  5. `test_zone_indexes_created` — `03_PROJECTS/_index.md`, `04_PERSONAL/_index.md`,
     `REFERENCES/_index.md` all created when absent.
  6. `test_atoms_folder_skipped` — `06_ATOMS/` directory present → no `_index.md`
     created inside it.
  7. `test_dry_run_no_writes` — `--dry-run` flag: zero files written; stdout
     contains "would be created" for candidate paths.
  8. `test_idempotent_second_run` — calling `setup_vault(vault)` twice: second run
     returns `{"created": 0, "skipped": N, "errors": 0}` and does not modify files.
  9. `test_summary_counts_correct` — return dict counts match observed filesystem
     state after the run.
  10. `test_config_error_exits_1` — invalid config path → `SystemExit(1)`.
  11. `test_missing_template_dir_exits_2` — template directory absent →
      `SystemExit(2)`.

- integration: not required for Phase 1 (no LLM calls, no external I/O beyond
  the local filesystem; the vault layer already has its own tests).

---

## Explicitly out of scope

- `06_ATOMS/_index.md` creation — Phase 2
- Creating subdomain folders that do not yet exist on disk (walk-only; no mkdir)
- Creating `_index.md` for individual project subfolders under `03_PROJECTS/`
  (only the zone root is bootstrapped)
- Indexes for `00_INBOX/`, `01_PROCESSING/`, `05_ARCHIVE/` — none specified
- Generating `_AI_META/tag-taxonomy.md`, `_AI_META/ontology.md`, or any
  `_AI_META/templates/` files (these must pre-exist)
- Any LLM calls
- Any writes other than `_index.md` files

---

## Open questions

None — feature spec (`ProgressTracking/specs/feature-setup-scripts.md`) and
architecture §8 / §11 are unambiguous for Phase 1 scope.
