"""Tests for obsidian-agent configure."""
from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from agent.main import cli


def test_configure_non_interactive_ollama(tmp_path: Path) -> None:
    vault = tmp_path / "myvault"
    vault.mkdir()
    cfg = vault / "_AI_META" / "agent-config.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "configure",
            "--non-interactive",
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--provider",
            "ollama",
            "--ollama-model",
            "llama3.2",
        ],
    )
    assert result.exit_code == 0, result.output
    assert cfg.exists()
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["llm"]["providers"]["ollama"]["default_model"] == "llama3.2"
