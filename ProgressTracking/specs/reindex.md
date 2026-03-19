# Spec: Reindex Script
slug: reindex
layer: scripts
phase: 1
arch_section: §13

## Problem statement

Notes are sometimes manually added, moved, or deleted outside the agent pipeline.
When this happens the `note_count` / `last_updated` values in every `_index.md`
drift out of sync because Stage 6b only increments counts at write time.

`scripts/reindex.py` is a standalone on-demand script that triggers a full
rebuild of all domain and subdomain index counts by delegating to
`agent.tasks.index_updater.rebuild_all_counts()`. It mirrors the
`obsidian-agent rebuild-indexes` Click command in `agent/main.py` but is
intentionally kept as a script entry point (`python scripts/reindex.py`) for
users who do not have the full `obsidian-agent` package installed or who prefer
to run it without Click.

The script must be idempotent: running it multiple times on the same unmodified
vault must produce identical output.

---

## Module contract

```
Input:   CLI args --config PATH  (default "_AI_META/agent-config.yaml")
                  --dry-run      (pass dry_run=True to rebuild_all_counts;
                                  reads counts but writes nothing)

Output:  Console summary line (stdout):
           "All domain indexes rebuilt."       (normal run)
           "Dry-run: all domain indexes counted (no writes)."  (dry-run)

Exit codes:
  0 — success
  1 — config load failure (ConfigError)
  2 — unexpected error during rebuild
```

---

## Key implementation notes

### Public interface

The script wraps a single public function:

```python
# agent/tasks/index_updater.py
async def rebuild_all_counts(vault: ObsidianVault, dry_run: bool = False) -> None:
```

All business logic lives in `index_updater.py`. `reindex.py` contains only
config loading, vault construction, and `anyio.run()` invocation.

### CLI interface (argparse, stdlib only)

```
python scripts/reindex.py [--config PATH] [--dry-run]

Options:
  --config PATH   Path to agent-config.yaml  [default: _AI_META/agent-config.yaml]
  --dry-run       Count notes and report without writing any _index.md files
```

### Async invocation

`rebuild_all_counts` is `async def`. Use `anyio.run()` — consistent with the
project-wide anyio constraint and with `agent/main.py`'s `rebuild-indexes`
command:

```python
import anyio
from agent.tasks.index_updater import rebuild_all_counts

anyio.run(rebuild_all_counts, vault, dry_run)
```

### Config and vault construction

Pattern mirrors `setup_vault.py` and `agent/main.py`:

```python
from agent.core.config import ConfigError, load_config
from agent.vault.vault import ObsidianVault

try:
    config = load_config(args.config)
except ConfigError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    return 1

vault = ObsidianVault(Path(config.vault_root))
```

Note: `config.vault_root` is a `str`; wrap with `Path()`.

### Error handling

| Condition | Behaviour | Exit code |
|---|---|---|
| `ConfigError` from `load_config` | print to stderr | 1 |
| Any `Exception` from `anyio.run(...)` | print to stderr | 2 |
| Success | print summary line to stdout | 0 |

### sys.path bootstrap

Like `setup_vault.py`, insert the project root so the script runs standalone:

```python
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### No LLM calls

`rebuild_all_counts` makes no LLM calls and needs no `ProviderFactory`.

---

## Data model changes (if any)

None. `rebuild_all_counts` reads and writes `note_count` / `last_updated`
frontmatter fields in existing `_index.md` files via `ObsidianVault.write_note()`.
No new Pydantic models are introduced.

---

## LLM prompt file needed (if any)

None.

---

## Tests required

- unit: `tests/unit/test_reindex.py`

  All unit tests use pytest's `tmp_path` fixture. `rebuild_all_counts` is
  patched via `unittest.mock.patch` to avoid I/O; a minimal `agent-config.yaml`
  is written to a temp path for CLI tests.

  Key cases:
  1. `test_rebuild_called_with_vault_and_dry_run_false` — `reindex(vault)` calls
     `rebuild_all_counts(vault, False)`; no mock raises; function returns without
     error.
  2. `test_rebuild_called_with_dry_run_true` — `--dry-run` flag propagates
     `dry_run=True` to `rebuild_all_counts`.
  3. `test_success_exit_code_0` — valid config, mock succeeds → `main()` returns 0;
     stdout contains "rebuilt" or "counted".
  4. `test_dry_run_stdout_message` — `--dry-run`: stdout contains "Dry-run".
  5. `test_config_error_exits_1` — nonexistent config path → `main()` returns 1.
  6. `test_rebuild_exception_exits_2` — `rebuild_all_counts` raises `RuntimeError`
     → `main()` returns 2; error printed to stderr.
  7. `test_idempotent_multiple_calls` — calling `main()` twice with the same config
     and mock both return 0 (smoke test; idempotency contract is in
     `index_updater.py`).

- integration: not required for Phase 1 (script is a thin wrapper; vault +
  index_updater each have their own integration tests).

---

## Explicitly out of scope

- Incremental / delta reindex — only full rebuild is in scope (§13)
- Reporting per-domain counts to stdout — plain "rebuilt" summary only
- Any LLM calls or ProviderFactory usage
- Modifying or replacing the `obsidian-agent rebuild-indexes` Click command
- `06_ATOMS/` handling — Phase 2
- Web UI or API trigger — Phase 2

---

## Open questions

None — architecture §13 and feature spec (`feature-setup-scripts.md`) are
unambiguous for Phase 1 scope.
