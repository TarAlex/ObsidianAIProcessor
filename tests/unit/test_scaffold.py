"""Tests for the project scaffold (pyproject-scaffold module)."""
import shutil
import subprocess
import sys

import pytest


def _cli_cmd() -> list[str]:
    """Return a command list that invokes obsidian-agent.

    Prefers the installed entry-point script when it is on PATH; falls back to
    ``python -m agent`` so the tests work on Windows user installs where the
    scripts directory is not on PATH.
    """
    if shutil.which("obsidian-agent"):
        return ["obsidian-agent"]
    return [sys.executable, "-m", "agent"]


def test_agent_importable() -> None:
    import agent

    assert agent.__version__ == "0.2.1"


def test_all_subpackages_importable() -> None:
    import agent.adapters
    import agent.core
    import agent.llm
    import agent.stages
    import agent.tasks
    import agent.vault
    import agent.vector

    # Confirm each is a proper package (has __path__)
    for pkg in (
        agent.core,
        agent.adapters,
        agent.llm,
        agent.vault,
        agent.stages,
        agent.tasks,
        agent.vector,
    ):
        assert hasattr(pkg, "__path__"), f"{pkg.__name__} is not a package"


def test_cli_help() -> None:
    result = subprocess.run(
        [*_cli_cmd(), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Obsidian" in result.stdout


def test_cli_version() -> None:
    result = subprocess.run(
        [*_cli_cmd(), "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "0.2.1" in result.stdout


@pytest.mark.xfail(
    reason="agent.core.models does not exist yet; xfail until models-py is done",
    strict=False,
)
def test_no_phase2_symbols() -> None:
    with pytest.raises(ImportError):
        from agent.core.models import AtomNote  # noqa: F401
