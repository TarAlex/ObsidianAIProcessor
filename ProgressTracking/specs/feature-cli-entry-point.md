# Feature Spec: CLI Entry Point
slug: feature-cli-entry-point
sections_covered: [ProgressTracking/tasks/09_cli-entry-point.md]
arch_sections: [§2 (project structure), §14 (CLI interface)]

---

## Scope

The CLI entry point is the **single user-facing executable surface** for
`obsidian-agent`. It wires together every previously-built subsystem — pipeline,
watcher, scheduler, vault, and tasks — into four Click commands that humans and
automation scripts can invoke directly.

This section is a **thin orchestration layer**: no business logic lives here.
`agent/main.py` only imports, configures, and delegates. The `--dry-run` flag
must be propagated to every downstream component so no vault writes occur.

Phase 1 scope: four commands (`run`, `process-file`, `rebuild-indexes`,
`outdated-review`) plus a `--config` global option and a `--dry-run` flag on
commands that write. Graceful error handling via `click.ClickException`.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `agent/main.py` | `main-py` | `agent/core/pipeline.py` (DONE), `agent/core/watcher.py` (DONE), `agent/core/scheduler.py` (DONE), `agent/core/config.py` (DONE), `agent/vault/vault.py` (DONE), `agent/tasks/outdated_review.py` (IN_PROGRESS), `agent/tasks/index_updater.py` (IN_PROGRESS) | cli |

---

## Cross-cutting constraints

| Rule | Detail |
|---|---|
| Click ≥ 8.1 | Use `@click.group()` / `@cli.command()` pattern; commands registered on a single `cli` group |
| Global `--config` option | Default `_AI_META/agent-config.yaml`; passed to `load_config()` before every command body |
| `--dry-run` flag | Present on `run`, `process-file`, `rebuild-indexes`, `outdated-review`; when set, no vault writes are performed; pipeline and tasks receive it as a parameter |
| No vault writes without `ObsidianVault` | All filesystem mutations routed via the vault layer — never `Path.write_text()` directly in `main.py` |
| All LLM calls via `ProviderFactory` | `main.py` does not instantiate any provider directly; `Pipeline` and tasks handle this |
| `anyio` for async dispatch | Blocking async entry points use `anyio.run()`, not `asyncio.run()` |
| Graceful error surface | Every command wraps its body in `try/except` and raises `click.ClickException(str(e))` on unexpected failures; avoids bare tracebacks for users |
| No hardcoded paths | All paths resolved from `AgentConfig`; no literals in `main.py` |
| No Phase 2 code | `06_ATOMS/` support, atom extraction, atom-level MOC content — all excluded |

---

## Command surface (normative)

### `obsidian-agent run`
Starts the continuous inbox watcher + APScheduler periodic tasks. Blocks until
Ctrl-C. `--dry-run` passes the flag to `InboxWatcher` and `Pipeline`; no notes
are written, but processing logs still print.

```
obsidian-agent run [--config PATH] [--dry-run]
```

Internals:
1. `load_config(config)` → `AgentConfig`
2. Instantiate `Pipeline(cfg, dry_run=dry_run)`
3. Instantiate `InboxWatcher(cfg, pipeline)` and call `watcher.start()`
4. Instantiate `Scheduler(cfg, pipeline)` and call `scheduler.start()`
5. Block on `anyio.run(watcher.wait_forever)` or equivalent; catch `KeyboardInterrupt` → graceful shutdown

### `obsidian-agent process-file FILE`
One-shot processing of a single file from any path. Useful for manual re-runs
and CI testing. Prints result status to stdout.

```
obsidian-agent process-file FILE [--config PATH] [--dry-run]
```

Internals:
1. Resolve `FILE` as `Path`; raise `ClickException` if not found
2. `load_config(config)` → `AgentConfig`
3. `Pipeline(cfg, dry_run=dry_run).process_file(path)` via `anyio.run()`
4. `click.echo(f"[OK] {record.status}")` on success; `ClickException` on failure

### `obsidian-agent rebuild-indexes`
Triggers `rebuild_all_counts()` from `agent/tasks/index_updater.py` — scans
all `02_KNOWLEDGE/` domain and subdomain folders and rewrites `_index.md`
frontmatter counts from scratch.

```
obsidian-agent rebuild-indexes [--config PATH] [--dry-run]
```

Internals:
1. `load_config(config)` → `AgentConfig`
2. `ObsidianVault(Path(cfg.vault.root))`
3. `anyio.run(rebuild_all_counts, vault, dry_run=dry_run)`
4. `click.echo("All domain indexes rebuilt.")`

### `obsidian-agent outdated-review`
Runs the weekly staleness scan on demand, writing `_AI_META/outdated-review.md`.

```
obsidian-agent outdated-review [--config PATH] [--dry-run]
```

Internals:
1. `load_config(config)` → `AgentConfig`
2. `ObsidianVault(Path(cfg.vault.root))`
3. `anyio.run(run_outdated_review, vault, cfg, dry_run=dry_run)`
4. `click.echo("Outdated-review report written.")`

---

## Implementation ordering rationale

There is only one module in this section (`main.py`). Its implementation order
is strictly serial: it can only be written **after** all its dependencies are
either DONE or their public API is stable enough to import against:

- `pipeline.py` — DONE; `Pipeline(cfg, dry_run)` and `process_file()` are stable
- `watcher.py` — DONE; `InboxWatcher` public API is stable
- `scheduler.py` — DONE; `Scheduler` public API is stable
- `vault.py` — DONE; `ObsidianVault` is stable
- `outdated_review.py` — IN_PROGRESS but its `run_outdated_review(vault, cfg)` signature is specified
- `index_updater.py` — IN_PROGRESS but its `rebuild_all_counts(vault)` signature is specified

`main.py` should be implemented **last** in the overall project build order, as
it integrates all layers. The `/build` session should read the actual public APIs
of the five upstream modules before implementing the wiring.

---

## Excluded (Phase 2 or out of scope)

| Item | Reason |
|---|---|
| `scripts/setup_vault.py` | Separate TRACKER item under "Setup Scripts"; not part of this feature spec |
| `scripts/reindex.py` | Separate TRACKER item under "Setup Scripts"; not part of this feature spec |
| FastAPI Web UI / dashboard | Phase 2 (REQUIREMENTS §11) |
| MS Teams Graph API polling command | Phase 2 |
| `--verbose` / structured logging flags | Not specified in arch v1.1; keep simple |
| `06_ATOMS/` atom extraction command | Phase 2 |
| `--provider` / `--model` override flags | Resolved via config and env vars; no CLI flag in Phase 1 |
| Interactive REPL / `shell` command | Phase 2 |
