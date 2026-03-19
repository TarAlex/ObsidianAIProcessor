"""tests/unit/test_reindex.py — unit tests for scripts/reindex.py.

All tests use pytest's tmp_path fixture as the vault root.
anyio.run is patched throughout so no real async execution occurs.
A minimal agent-config.yaml is written to a temp path for CLI tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make scripts/ importable without modifying pyproject.toml.
_SCRIPTS_DIR = str(Path(__file__).parent.parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from reindex import main  # noqa: E402

from agent.vault.vault import ObsidianVault  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(cfg_path: Path, vault_root: Path) -> None:
    """Write a minimal agent-config.yaml at cfg_path."""
    cfg_path.write_text(
        f"vault:\n  root: {vault_root.as_posix()}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Test 1 — rebuild_all_counts called with vault and dry_run=False
# ---------------------------------------------------------------------------

def test_rebuild_called_with_vault_and_dry_run_false(tmp_path):
    config_file = tmp_path / "agent-config.yaml"
    _write_config(config_file, tmp_path)

    with patch("anyio.run") as mock_run:
        result = main(["--config", str(config_file)])

    assert result == 0
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0]
    # anyio.run(rebuild_all_counts, vault, dry_run)
    assert call_args[0].__name__ == "rebuild_all_counts"
    assert isinstance(call_args[1], ObsidianVault)
    assert call_args[2] is False  # dry_run=False


# ---------------------------------------------------------------------------
# Test 2 — --dry-run flag propagates dry_run=True
# ---------------------------------------------------------------------------

def test_rebuild_called_with_dry_run_true(tmp_path):
    config_file = tmp_path / "agent-config.yaml"
    _write_config(config_file, tmp_path)

    with patch("anyio.run") as mock_run:
        result = main(["--config", str(config_file), "--dry-run"])

    assert result == 0
    call_args = mock_run.call_args[0]
    assert call_args[0].__name__ == "rebuild_all_counts"
    assert call_args[2] is True  # dry_run=True


# ---------------------------------------------------------------------------
# Test 3 — success exit code 0; stdout contains "rebuilt" or "counted"
# ---------------------------------------------------------------------------

def test_success_exit_code_0(tmp_path, capsys):
    config_file = tmp_path / "agent-config.yaml"
    _write_config(config_file, tmp_path)

    with patch("anyio.run"):
        result = main(["--config", str(config_file)])

    assert result == 0
    captured = capsys.readouterr()
    assert "rebuilt" in captured.out or "counted" in captured.out


# ---------------------------------------------------------------------------
# Test 4 — dry-run stdout message contains "Dry-run"
# ---------------------------------------------------------------------------

def test_dry_run_stdout_message(tmp_path, capsys):
    config_file = tmp_path / "agent-config.yaml"
    _write_config(config_file, tmp_path)

    with patch("anyio.run"):
        result = main(["--config", str(config_file), "--dry-run"])

    assert result == 0
    captured = capsys.readouterr()
    assert "Dry-run" in captured.out


# ---------------------------------------------------------------------------
# Test 5 — nonexistent config path → exit code 1
# ---------------------------------------------------------------------------

def test_config_error_exits_1(tmp_path):
    result = main(["--config", str(tmp_path / "nonexistent.yaml")])
    assert result == 1


# ---------------------------------------------------------------------------
# Test 6 — rebuild raises RuntimeError → exit code 2; error on stderr
# ---------------------------------------------------------------------------

def test_rebuild_exception_exits_2(tmp_path, capsys):
    config_file = tmp_path / "agent-config.yaml"
    _write_config(config_file, tmp_path)

    with patch("anyio.run", side_effect=RuntimeError("unexpected boom")):
        result = main(["--config", str(config_file)])

    assert result == 2
    captured = capsys.readouterr()
    assert "ERROR" in captured.err


# ---------------------------------------------------------------------------
# Test 7 — idempotent: two successive calls both return 0
# ---------------------------------------------------------------------------

def test_idempotent_multiple_calls(tmp_path):
    config_file = tmp_path / "agent-config.yaml"
    _write_config(config_file, tmp_path)

    with patch("anyio.run"):
        first = main(["--config", str(config_file)])
        second = main(["--config", str(config_file)])

    assert first == 0
    assert second == 0
