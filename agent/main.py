"""agent/main.py — CLI entry point for obsidian-agent.

Wires pipeline, watcher, scheduler, vault, and task modules into four Click
commands. Contains zero business logic — only imports, configures, delegates.
"""
from __future__ import annotations

from pathlib import Path

import anyio
import click

from agent.core.config import ConfigError, load_config
from agent.core.pipeline import KnowledgePipeline
from agent.core.scheduler import AgentScheduler
from agent.core.watcher import InboxWatcher
from agent.vault.vault import ObsidianVault

DEFAULT_CONFIG = "_AI_META/agent-config.yaml"


# ---------------------------------------------------------------------------
# Daemon coroutine — module-level for testability
# ---------------------------------------------------------------------------

async def _daemon(cfg, dry_run: bool) -> None:
    """Continuous daemon: watch inbox and process files as they arrive."""
    vault = ObsidianVault(Path(cfg.vault.root))
    pipeline = KnowledgePipeline(cfg, vault, dry_run=dry_run)
    watcher = InboxWatcher(cfg)
    scheduler = AgentScheduler()
    scheduler.start(vault, cfg)
    try:
        await watcher.run(pipeline)
    finally:
        scheduler.stop()


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """Obsidian AI-powered vault inbox processor."""


# ---------------------------------------------------------------------------
# run — continuous daemon
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def run(config: str, dry_run: bool) -> None:
    """Watch 00_INBOX/ and process new files continuously."""
    try:
        cfg = load_config(config)
    except ConfigError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
    try:
        anyio.run(_daemon, cfg, dry_run)
    except KeyboardInterrupt:
        click.echo("\n[obsidian-agent] Interrupted, shutting down.")
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# process-file — one-shot
# ---------------------------------------------------------------------------

@cli.command("process-file")
@click.argument("file", type=click.Path(exists=False))
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def process_file(file: str, config: str, dry_run: bool) -> None:
    """Process a single FILE through the full pipeline."""
    path = Path(file)
    if not path.exists():
        raise click.UsageError(f"File not found: {file}")
    try:
        cfg = load_config(config)
    except ConfigError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
    try:
        vault = ObsidianVault(Path(cfg.vault.root))
        pipeline = KnowledgePipeline(cfg, vault, dry_run=dry_run)
        record = anyio.run(pipeline.process_file, path)
        click.echo(f"[OK] {record.status if hasattr(record, 'status') else record.output_path}")
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# rebuild-indexes
# ---------------------------------------------------------------------------

@cli.command("rebuild-indexes")
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def rebuild_indexes(config: str, dry_run: bool) -> None:
    """Rebuild all domain/subdomain _index.md note counts from scratch."""
    try:
        cfg = load_config(config)
    except ConfigError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
    try:
        from agent.tasks.index_updater import rebuild_all_counts  # noqa: PLC0415
        vault = ObsidianVault(Path(cfg.vault.root))
        anyio.run(rebuild_all_counts, vault, dry_run)
        click.echo("All domain indexes rebuilt.")
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# outdated-review
# ---------------------------------------------------------------------------

@cli.command("outdated-review")
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def outdated_review(config: str, dry_run: bool) -> None:
    """Scan vault for stale notes and write an outdated-review report."""
    try:
        cfg = load_config(config)
    except ConfigError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
    try:
        from agent.tasks.outdated_review import run as run_outdated_review  # noqa: PLC0415
        vault = ObsidianVault(Path(cfg.vault.root))
        anyio.run(run_outdated_review, vault, cfg, dry_run)
        click.echo("Outdated-review report written.")
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
