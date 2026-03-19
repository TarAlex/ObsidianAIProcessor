"""Integration test: pipeline respects sync lock (_wait_for_sync_unlock).

With vault root containing .syncing (or .sync-*), pipeline's _wait_for_sync_unlock
eventually proceeds when the lock is removed. Uses tmp_path as vault root.
"""
from __future__ import annotations

from pathlib import Path

import anyio
import pytest

from agent.core.config import AgentConfig, SyncConfig, VaultConfig
from agent.core.pipeline import KnowledgePipeline
from agent.vault.vault import ObsidianVault

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, poll_s: int = 1, timeout_s: int = 5) -> AgentConfig:
    return AgentConfig(
        vault=VaultConfig(root=str(tmp_path)),
        sync=SyncConfig(sync_poll_interval_s=poll_s, lock_wait_timeout_s=timeout_s),
    )


# ---------------------------------------------------------------------------
# Test 1 — no lock: _wait_for_sync_unlock returns immediately
# ---------------------------------------------------------------------------


def test_wait_for_sync_unlock_returns_immediately_when_no_lock(tmp_path: Path) -> None:
    """Vault has no lock files; _wait_for_sync_unlock completes without blocking."""
    vault = ObsidianVault(tmp_path)
    config = _make_config(tmp_path)
    pipeline = KnowledgePipeline(config=config, vault=vault)

    async def _run() -> None:
        await pipeline._wait_for_sync_unlock()

    anyio.run(_run)


# ---------------------------------------------------------------------------
# Test 2 — lock present then removed: _wait_for_sync_unlock eventually proceeds
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_wait_for_sync_unlock_proceeds_when_lock_removed(tmp_path: Path) -> None:
    """Create .syncing, start _wait_for_sync_unlock in background, remove lock after delay; wait completes."""
    vault = ObsidianVault(tmp_path)
    lock_file = tmp_path / ".syncing"
    lock_file.touch()
    config = _make_config(tmp_path, poll_s=1, timeout_s=3)
    pipeline = KnowledgePipeline(config=config, vault=vault)

    async def remove_lock_after(seconds: float) -> None:
        await anyio.sleep(seconds)
        lock_file.unlink(missing_ok=True)

    async def _run() -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(remove_lock_after, 0.15)
            await pipeline._wait_for_sync_unlock()

    anyio.run(_run)
