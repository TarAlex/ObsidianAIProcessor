"""agent/main.py — CLI entry point for obsidian-agent.

Wires pipeline, watcher, scheduler, vault, and task modules into four Click
commands. Contains zero business logic — only imports, configures, delegates.
"""
from __future__ import annotations

from pathlib import Path

import anyio
import click

from agent.cli.configure_cmd import register_configure
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
@click.version_option("0.2.1", prog_name="obsidian-agent")
def cli() -> None:
    """Obsidian AI-powered vault inbox processor."""


register_configure(cli, DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# setup-vault — bootstrap _index.md files
# ---------------------------------------------------------------------------

@cli.command("setup-vault")
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def setup_vault_cmd(config: str, dry_run: bool) -> None:
    """Create missing domain/zone _index.md files (idempotent)."""
    from agent.tasks.vault_bootstrap import setup_vault_main  # noqa: PLC0415

    code = setup_vault_main(config, dry_run=dry_run)
    if code == 1:
        raise click.ClickException("Config load failed (see stderr).")
    if code == 2:
        raise click.ClickException("Template directory missing (see stderr).")
    if code == 3:
        raise click.ClickException("Setup finished with one or more per-file errors.")


# ---------------------------------------------------------------------------
# seed-templates — copy built-in Jinja templates into vault (install/bootstrap)
# ---------------------------------------------------------------------------

@cli.command("seed-templates")
@click.argument(
    "vault_root",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
)
def seed_templates_cmd(vault_root: Path) -> None:
    """Copy default _index templates into VAULT_ROOT/_AI_META/templates/ if missing."""
    from agent.vault.template_seed import ensure_builtin_templates  # noqa: PLC0415

    root = vault_root.resolve()
    ensure_builtin_templates(root)
    click.echo(f"[OK] templates -> {root / '_AI_META' / 'templates'}")


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
# process-inbox — batch scan (for scheduled runs)
# ---------------------------------------------------------------------------


async def _process_inbox(cfg, dry_run: bool) -> tuple[int, int]:
    """Walk 00_INBOX recursively; process each eligible file. Returns (ok, failed)."""
    from agent.core.watcher import InboxWatcher  # noqa: PLC0415

    vault = ObsidianVault(cfg.vault_root)
    inbox = vault.inbox
    if not inbox.is_dir():
        return (0, 0)

    candidates: list[Path] = []
    for path in sorted(inbox.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() in InboxWatcher.SKIP_SUFFIXES:
            continue
        candidates.append(path)

    if not candidates:
        return (0, 0)

    pipeline = KnowledgePipeline(cfg, vault, dry_run=dry_run)
    ok = failed = 0
    for path in candidates:
        try:
            record = await pipeline.process_file(path)
            out = getattr(record, "output_path", "") or ""
            click.echo(f"[OK] {path.name} -> {out}")
            ok += 1
        except Exception as exc:
            click.echo(f"[FAIL] {path}: {exc}", err=True)
            failed += 1

    return (ok, failed)


@cli.command("process-inbox")
@click.option("--config", default=DEFAULT_CONFIG, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def process_inbox_cmd(config: str, dry_run: bool) -> None:
    """Process all files under 00_INBOX/ (recursive). For use with a periodic scheduler."""
    try:
        cfg = load_config(config)
    except ConfigError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
    try:
        ok, failed = anyio.run(_process_inbox, cfg, dry_run)
        click.echo(f"process-inbox: {ok} ok, {failed} failed.")
        if failed:
            raise click.ClickException("One or more inbox files failed.")
    except click.ClickException:
        raise
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
