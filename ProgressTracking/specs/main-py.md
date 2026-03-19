# Spec: CLI Entry Point

slug: main-py
layer: cli
phase: 1
arch_section: §14 CLI Interface

---

## Problem statement

`agent/main.py` is the single user-facing entry point for `obsidian-agent`. It
must wire together every upstream subsystem — pipeline, watcher, scheduler,
vault, and tasks — into four Click commands that humans and automation scripts
invoke directly. The module contains **zero business logic**: it only imports,
configures, and delegates.

---

## Module contract

**Entry point registered in pyproject.toml:**
```
obsidian-agent = "agent.main:cli"
```

**Public surface — Click group + four commands:**

| Command | Signature |
|---|---|
| `obsidian-agent run` | `run [--config PATH] [--dry-run]` |
| `obsidian-agent process-file FILE` | `process_file FILE [--config PATH] [--dry-run]` |
| `obsidian-agent rebuild-indexes` | `rebuild_indexes [--config PATH] [--dry-run]` |
| `obsidian-agent outdated-review` | `outdated_review [--config PATH] [--dry-run]` |

**Global `--config` option:**
- Default: `_AI_META/agent-config.yaml`
- Passed to `load_config(config)` as a `str` before any command body executes
- All vault paths derived from the returned `AgentConfig`; no hardcoded paths

**`--dry-run` flag:**
- Present on all four commands
- When set, no vault writes are performed
- Propagated as `dry_run: bool` to `KnowledgePipeline`, `rebuild_all_counts`,
  and `run` (outdated_review) — see Key implementation notes for upstream
  API changes required

---

## Key implementation notes

### Click skeleton

```python
import anyio
import click

from agent.core.config import load_config, ConfigError
from agent.core.pipeline import KnowledgePipeline
from agent.core.watcher import InboxWatcher
from agent.core.scheduler import AgentScheduler
from agent.vault.vault import ObsidianVault
from pathlib import Path

DEFAULT_CONFIG = "_AI_META/agent-config.yaml"

@click.group()
def cli() -> None:
    """Obsidian AI-powered vault inbox processor."""

@cli.command()
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def run(config: str, dry_run: bool) -> None: ...

@cli.command("process-file")
@click.argument("file", type=click.Path(exists=False))
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def process_file(file: str, config: str, dry_run: bool) -> None: ...

@cli.command("rebuild-indexes")
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def rebuild_indexes(config: str, dry_run: bool) -> None: ...

@cli.command("outdated-review")
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def outdated_review(config: str, dry_run: bool) -> None: ...
```

### `run` command — continuous daemon

```
async def _daemon(cfg: AgentConfig, dry_run: bool) -> None:
    vault = ObsidianVault(Path(cfg.vault.root))
    pipeline = KnowledgePipeline(cfg, vault, dry_run=dry_run)
    watcher = InboxWatcher(cfg)
    scheduler = AgentScheduler()
    scheduler.start(vault, cfg)           # must be called inside running event loop
    try:
        await watcher.run(pipeline)       # blocks until anyio cancellation
    finally:
        scheduler.stop()
```

Wrap with:
```python
try:
    anyio.run(_daemon, cfg, dry_run)
except KeyboardInterrupt:
    click.echo("\n[obsidian-agent] Interrupted, shutting down.")
```

`anyio.run()` uses asyncio backend; `AsyncIOScheduler` from APScheduler 3.x
picks up the running loop from `scheduler.start()`.

### `process-file` command — one-shot

```
1. Resolve FILE as Path; raise ClickException if not found
2. load_config(config) → AgentConfig
3. vault = ObsidianVault(Path(cfg.vault.root))
4. pipeline = KnowledgePipeline(cfg, vault, dry_run=dry_run)
5. record = anyio.run(pipeline.process_file, path)
6. click.echo(f"[OK] {record.status if hasattr(record, 'status') else record.output_path}")
```

### `rebuild-indexes` command

```
1. load_config(config) → AgentConfig
2. vault = ObsidianVault(Path(cfg.vault.root))
3. from agent.tasks.index_updater import rebuild_all_counts
4. anyio.run(rebuild_all_counts, vault, dry_run)
5. click.echo("All domain indexes rebuilt.")
```

Note: `rebuild_all_counts` must accept `dry_run: bool = False` (see Upstream
API changes below).

### `outdated-review` command

```
1. load_config(config) → AgentConfig
2. vault = ObsidianVault(Path(cfg.vault.root))
3. from agent.tasks.outdated_review import run as run_outdated_review
4. anyio.run(run_outdated_review, vault, cfg, dry_run)
5. click.echo("Outdated-review report written.")
```

Note: `run_outdated_review` must accept `dry_run: bool = False` (see below).

### Graceful error handling

Every command wraps its body in `try/except` and converts known errors to
`click.ClickException`. Bare tracebacks must not reach the user:

```python
try:
    cfg = load_config(config)
except ConfigError as e:
    raise click.ClickException(str(e))
except Exception as e:
    raise click.ClickException(f"Unexpected error: {e}")
```

Pattern repeats for `FileNotFoundError` on `process-file FILE`, and top-level
`Exception` in each command body.

### `anyio.run()` usage (non-negotiable)

Use `anyio.run(coro_fn, *args)` throughout — **never** `asyncio.run()`.
The architecture §14 v1.1 snippet uses `asyncio.run()` as a placeholder; the
feature spec overrides this with `anyio.run()` per the project-wide rule.

### Upstream API changes required (minimal)

| Module | Change | Reason |
|---|---|---|
| `agent/core/pipeline.py` (DONE) | Add `dry_run: bool = False` to `KnowledgePipeline.__init__`; store as `self.dry_run`; propagate to `process_file` | `run` and `process-file` commands need it |
| `agent/tasks/index_updater.py` (IN_PROGRESS) | Add `dry_run: bool = False` to `rebuild_all_counts(vault, dry_run=False)`; skip writes when True | `rebuild-indexes --dry-run` |
| `agent/tasks/outdated_review.py` (IN_PROGRESS) | Add `dry_run: bool = False` to `run(vault, cfg, dry_run=False)`; skip report write when True; print to stdout instead | `outdated-review --dry-run` |

The change to `pipeline.py` is a **backwards-compatible default-False addition**;
all existing callers and tests remain unbroken.

### No logic in `main.py`

`main.py` must not contain:
- Business logic (filtering, scoring, formatting)
- Direct `Path.write_text()` calls
- LLM instantiation
- Direct `chromadb` / vault file operations

All mutations go through `KnowledgePipeline`, `rebuild_all_counts`, or
`run_outdated_review`.

---

## Data model changes

None. `main.py` uses `AgentConfig` (from `load_config`), `ObsidianVault`,
`KnowledgePipeline`, `InboxWatcher`, `AgentScheduler`, and the two task
functions. All Pydantic models remain unchanged.

---

## LLM prompt file needed

None. `main.py` makes no LLM calls.

---

## Tests required

### unit: `tests/unit/test_main.py`

Use `click.testing.CliRunner` for all tests. Mock upstream components with
`unittest.mock.patch` / `MagicMock`. All tests are synchronous at the Click
layer; `anyio.run` is patched to avoid real async execution.

| Test case | What it verifies |
|---|---|
| `test_run_invokes_daemon` | `run --config CFG` calls `load_config` then `anyio.run` with daemon coroutine |
| `test_run_dry_run_flag_passed` | `run --dry-run` propagates `dry_run=True` into `KnowledgePipeline.__init__` |
| `test_run_keyboard_interrupt_graceful` | `anyio.run` raising `KeyboardInterrupt` prints shutdown message and exits 0 |
| `test_run_config_error_exits_cleanly` | `load_config` raising `ConfigError` → `ClickException` message, exit code 1 |
| `test_process_file_ok` | `process-file FILE` with valid file → calls `pipeline.process_file` and prints `[OK]` |
| `test_process_file_not_found` | `process-file MISSING` → `ClickException("File not found")`, exit 2 |
| `test_process_file_dry_run` | `process-file FILE --dry-run` → `KnowledgePipeline(cfg, vault, dry_run=True)` |
| `test_rebuild_indexes_calls_task` | `rebuild-indexes` → calls `rebuild_all_counts(vault, dry_run=False)` via `anyio.run` |
| `test_rebuild_indexes_dry_run` | `rebuild-indexes --dry-run` → calls `rebuild_all_counts(vault, dry_run=True)` |
| `test_rebuild_indexes_config_error` | `load_config` raises `ConfigError` → exit 1 |
| `test_outdated_review_calls_task` | `outdated-review` → calls `run_outdated_review(vault, cfg, dry_run=False)` |
| `test_outdated_review_dry_run` | `outdated-review --dry-run` → `run_outdated_review(..., dry_run=True)` |
| `test_default_config_path` | omitting `--config` uses `_AI_META/agent-config.yaml` |
| `test_all_commands_listed` | `cli --help` output contains `run`, `process-file`, `rebuild-indexes`, `outdated-review` |

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `scripts/setup_vault.py` / `scripts/reindex.py` | Separate TRACKER items under Setup Scripts |
| FastAPI Web UI / dashboard | Phase 2 (REQUIREMENTS §11) |
| MS Teams Graph API polling command | Phase 2 |
| `--verbose` / structured logging level flags | Not in arch v1.1 |
| `--provider` / `--model` override flags | Resolved via config and env vars only |
| Interactive REPL / `shell` command | Phase 2 |
| `06_ATOMS/` atom extraction command | Phase 2 |
| `watcher.start()` / `watcher.wait_forever()` API | Actual watcher API is `watcher.run(pipeline)` — feature spec description was aspirational; use the actual source API |

---

## Open questions

None. All upstream APIs are verified against source. Feature spec and
architecture provide unambiguous guidance. Upstream `dry_run` additions are
small, backwards-compatible, and explicitly required by the feature spec.
