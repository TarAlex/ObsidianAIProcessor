"""Integration tests for agent/core/watcher.py.

Uses a real tmp_path vault root with a real watchdog Observer.
Skipped unless RUN_INTEGRATION=1.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest

from agent.core.watcher import InboxWatcher


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_integration_flag() -> None:
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run integration tests")


def _make_config(vault_root: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.vault.root = str(vault_root)
    return cfg


@pytest.mark.anyio
async def test_real_md_file_dispatched(tmp_path: Path) -> None:
    """Dropping a real .md file into 00_INBOX calls pipeline.process_file within 4 s."""
    inbox = tmp_path / "00_INBOX"
    inbox.mkdir()
    cfg = _make_config(tmp_path)

    pipeline = MagicMock()
    called_paths: list[Path] = []

    async def fake_process(path: Path) -> None:
        called_paths.append(path)

    pipeline.process_file = fake_process

    watcher = InboxWatcher(cfg)
    target = inbox / "note.md"

    async def _drop_file() -> None:
        await anyio.sleep(0.5)
        target.write_text("# Hello", encoding="utf-8")
        # Wait up to 4 s for watcher to pick it up
        for _ in range(40):
            await anyio.sleep(0.1)
            if called_paths:
                return

    with anyio.move_on_after(5):
        async with anyio.create_task_group() as tg:
            tg.start_soon(watcher.run, pipeline)
            tg.start_soon(_drop_file)
            await anyio.sleep(4)
            tg.cancel_scope.cancel()

    assert called_paths, "process_file was not called for the .md file"
    assert called_paths[0] == target


@pytest.mark.anyio
async def test_tmp_file_not_dispatched(tmp_path: Path) -> None:
    """Dropping a .tmp file into 00_INBOX does NOT call pipeline.process_file."""
    inbox = tmp_path / "00_INBOX"
    inbox.mkdir()
    cfg = _make_config(tmp_path)

    pipeline = MagicMock()
    called_paths: list[Path] = []

    async def fake_process(path: Path) -> None:
        called_paths.append(path)

    pipeline.process_file = fake_process

    watcher = InboxWatcher(cfg)
    target = inbox / "download.tmp"

    async def _drop_file() -> None:
        await anyio.sleep(0.5)
        target.write_text("partial", encoding="utf-8")
        await anyio.sleep(3)

    with anyio.move_on_after(5):
        async with anyio.create_task_group() as tg:
            tg.start_soon(watcher.run, pipeline)
            tg.start_soon(_drop_file)
            await anyio.sleep(4)
            tg.cancel_scope.cancel()

    assert not called_paths, f"process_file was unexpectedly called for {called_paths}"
