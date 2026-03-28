"""CLI tests for obsidian-agent seed-templates."""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from agent.main import cli


def test_seed_templates_creates_dir(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    runner = CliRunner()
    result = runner.invoke(cli, ["seed-templates", str(vault)])
    assert result.exit_code == 0, result.output
    assert (vault / "00_INBOX" / "articles").is_dir()
    assert (vault / "01_PROCESSING" / "to_classify").is_dir()
    assert (vault / "_AI_META" / "templates" / "domain_index.md").exists()
