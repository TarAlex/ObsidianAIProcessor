"""Unit tests for agent/main.py — CLI entry point.

All upstream components are mocked with unittest.mock. anyio.run is patched
throughout so no real async execution occurs. Tests use Click's CliRunner.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest
from click.testing import CliRunner

from agent.core.config import ConfigError
from agent.main import cli, DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cfg(vault_root: str = "/vault") -> MagicMock:
    """Return a minimal AgentConfig-like mock."""
    cfg = MagicMock()
    cfg.vault.root = vault_root
    return cfg


def _make_record(output_path: str = "/out/note.md") -> SimpleNamespace:
    """Return a ProcessingRecord-like object (no .status attribute)."""
    return SimpleNamespace(output_path=output_path)


# ---------------------------------------------------------------------------
# test_all_commands_listed
# ---------------------------------------------------------------------------

def test_all_commands_listed():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "process-file" in result.output
    assert "rebuild-indexes" in result.output
    assert "outdated-review" in result.output
    assert "configure" in result.output
    assert "setup-vault" in result.output
    assert "seed-templates" in result.output
    assert "process-inbox" in result.output


# ---------------------------------------------------------------------------
# test_default_config_path
# ---------------------------------------------------------------------------

def test_default_config_path():
    runner = CliRunner()
    with patch("agent.main.load_config", side_effect=ConfigError("cfg error")) as mock_lc:
        runner.invoke(cli, ["run"])
        mock_lc.assert_called_once_with(DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------

def test_run_invokes_daemon():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg) as mock_lc:
        with patch("anyio.run") as mock_run:
            result = runner.invoke(cli, ["run", "--config", "path/config.yaml"])
    assert result.exit_code == 0
    mock_lc.assert_called_once_with("path/config.yaml")
    assert mock_run.called
    # First positional arg to anyio.run must be _daemon (a coroutine function)
    first_arg = mock_run.call_args[0][0]
    assert asyncio.iscoroutinefunction(first_arg)


def test_run_dry_run_flag_passed():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("anyio.run") as mock_run:
            result = runner.invoke(cli, ["run", "--dry-run", "--config", "cfg.yaml"])
    assert result.exit_code == 0
    # anyio.run(_daemon, cfg, dry_run) — third positional arg is dry_run
    call_args = mock_run.call_args[0]
    assert call_args[2] is True


def test_run_keyboard_interrupt_graceful():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("anyio.run", side_effect=KeyboardInterrupt()):
            result = runner.invoke(cli, ["run", "--config", "cfg.yaml"])
    assert result.exit_code == 0
    assert "Interrupted" in result.output


def test_run_config_error_exits_cleanly():
    runner = CliRunner()
    with patch("agent.main.load_config", side_effect=ConfigError("bad config")):
        result = runner.invoke(cli, ["run", "--config", "cfg.yaml"])
    assert result.exit_code == 1
    assert "bad config" in result.output


# ---------------------------------------------------------------------------
# process-file command
# ---------------------------------------------------------------------------

def test_process_file_ok(tmp_path: Path):
    test_file = tmp_path / "note.md"
    test_file.write_text("# Test")
    cfg = _make_cfg(str(tmp_path))
    record = _make_record("/out/note.md")

    runner = CliRunner()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("agent.main.ObsidianVault") as mock_vault_cls:
            with patch("agent.main.KnowledgePipeline"):
                with patch("anyio.run", return_value=record):
                    result = runner.invoke(
                        cli, ["process-file", str(test_file), "--config", "cfg.yaml"]
                    )
    assert result.exit_code == 0
    assert "[OK]" in result.output
    assert "/out/note.md" in result.output


def test_process_file_not_found():
    runner = CliRunner()
    result = runner.invoke(
        cli, ["process-file", "/nonexistent/file.md", "--config", "cfg.yaml"]
    )
    assert result.exit_code == 2
    assert "File not found" in result.output


def test_process_file_dry_run(tmp_path: Path):
    test_file = tmp_path / "note.md"
    test_file.write_text("# Test")
    cfg = _make_cfg(str(tmp_path))
    record = _make_record("/out/note.md")

    runner = CliRunner()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("agent.main.ObsidianVault") as mock_vault_cls:
            with patch("agent.main.KnowledgePipeline") as mock_pipeline_cls:
                with patch("anyio.run", return_value=record):
                    result = runner.invoke(
                        cli,
                        ["process-file", str(test_file), "--dry-run", "--config", "cfg.yaml"],
                    )
    assert result.exit_code == 0
    mock_pipeline_cls.assert_called_once_with(cfg, mock_vault_cls.return_value, dry_run=True)


# ---------------------------------------------------------------------------
# rebuild-indexes command
# ---------------------------------------------------------------------------

def test_rebuild_indexes_calls_task():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("agent.main.ObsidianVault") as mock_vault_cls:
            with patch("anyio.run") as mock_run:
                result = runner.invoke(cli, ["rebuild-indexes", "--config", "cfg.yaml"])
    assert result.exit_code == 0
    assert "All domain indexes rebuilt." in result.output
    assert mock_run.called
    call_args = mock_run.call_args[0]
    # First arg is rebuild_all_counts function
    assert call_args[0].__name__ == "rebuild_all_counts"
    assert call_args[1] is mock_vault_cls.return_value
    assert call_args[2] is False  # dry_run=False


def test_rebuild_indexes_dry_run():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("agent.main.ObsidianVault") as mock_vault_cls:
            with patch("anyio.run") as mock_run:
                result = runner.invoke(
                    cli, ["rebuild-indexes", "--dry-run", "--config", "cfg.yaml"]
                )
    assert result.exit_code == 0
    call_args = mock_run.call_args[0]
    assert call_args[0].__name__ == "rebuild_all_counts"
    assert call_args[2] is True  # dry_run=True


def test_rebuild_indexes_config_error():
    runner = CliRunner()
    with patch("agent.main.load_config", side_effect=ConfigError("no config")):
        result = runner.invoke(cli, ["rebuild-indexes", "--config", "cfg.yaml"])
    assert result.exit_code == 1
    assert "no config" in result.output


# ---------------------------------------------------------------------------
# outdated-review command
# ---------------------------------------------------------------------------

def test_outdated_review_calls_task():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("agent.main.ObsidianVault") as mock_vault_cls:
            with patch("anyio.run") as mock_run:
                result = runner.invoke(cli, ["outdated-review", "--config", "cfg.yaml"])
    assert result.exit_code == 0
    assert "Outdated-review report written." in result.output
    assert mock_run.called
    call_args = mock_run.call_args[0]
    # First arg is run_outdated_review (imported as `run` from outdated_review module)
    assert call_args[0].__module__ == "agent.tasks.outdated_review"
    assert call_args[1] is mock_vault_cls.return_value
    assert call_args[2] is cfg
    assert call_args[3] is False  # dry_run=False


def test_outdated_review_dry_run():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("agent.main.ObsidianVault") as mock_vault_cls:
            with patch("anyio.run") as mock_run:
                result = runner.invoke(
                    cli, ["outdated-review", "--dry-run", "--config", "cfg.yaml"]
                )
    assert result.exit_code == 0
    call_args = mock_run.call_args[0]
    assert call_args[0].__module__ == "agent.tasks.outdated_review"
    assert call_args[3] is True  # dry_run=True


# ---------------------------------------------------------------------------
# process-inbox command
# ---------------------------------------------------------------------------


def test_process_inbox_calls_anyio_run():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("agent.main.anyio.run", return_value=(2, 0)) as mock_run:
            result = runner.invoke(cli, ["process-inbox", "--config", "cfg.yaml"])
    assert result.exit_code == 0
    assert "2 ok, 0 failed" in result.output
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0].__name__ == "_process_inbox"


def test_process_inbox_nonzero_exit_on_failures():
    runner = CliRunner()
    cfg = _make_cfg()
    with patch("agent.main.load_config", return_value=cfg):
        with patch("agent.main.anyio.run", return_value=(0, 1)):
            result = runner.invoke(cli, ["process-inbox", "--config", "cfg.yaml"])
    assert result.exit_code != 0
