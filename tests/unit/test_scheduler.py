"""Unit tests for agent/core/scheduler.py.

All tests mock AsyncIOScheduler and task modules — no real event loop required
for the synchronous-API tests; @pytest.mark.anyio is used only for the async
job-wrapper tests.
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.core.scheduler import (
    AgentScheduler,
    _DAY_ABBR,
    _run_index_rebuild,
    _run_outdated_review,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(day: str = "monday", hour: int = 9) -> MagicMock:
    cfg = MagicMock()
    cfg.scheduler.outdated_review_day = day
    cfg.scheduler.outdated_review_hour = hour
    return cfg


def _make_vault() -> MagicMock:
    return MagicMock()


class _CapturingCronTrigger:
    """Drop-in replacement for CronTrigger that records kwargs."""

    captured: list[dict] = []

    def __init__(self, **kwargs: object) -> None:
        _CapturingCronTrigger.captured.append(kwargs)


def _make_scheduler_with_mock() -> tuple[AgentScheduler, MagicMock]:
    """Return (AgentScheduler, mock_inner) with the inner scheduler replaced."""
    sched = AgentScheduler()
    mock_inner = MagicMock()
    sched._scheduler = mock_inner
    return sched, mock_inner


# ---------------------------------------------------------------------------
# start() — job registration
# ---------------------------------------------------------------------------

class TestStartRegistersJobs:
    def _start(self, day: str = "monday", hour: int = 9) -> tuple[AgentScheduler, MagicMock]:
        sched, mock_inner = _make_scheduler_with_mock()
        sched.start(_make_vault(), _make_config(day=day, hour=hour))
        return sched, mock_inner

    def test_start_registers_two_jobs(self) -> None:
        _, mock_inner = self._start()
        assert mock_inner.add_job.call_count == 2

    def test_outdated_review_job_id(self) -> None:
        _, mock_inner = self._start()
        ids = [c.kwargs.get("id") for c in mock_inner.add_job.call_args_list]
        assert "outdated_review_job" in ids

    def test_index_rebuild_job_id(self) -> None:
        _, mock_inner = self._start()
        ids = [c.kwargs.get("id") for c in mock_inner.add_job.call_args_list]
        assert "index_rebuild_job" in ids

    def test_start_calls_scheduler_start(self) -> None:
        _, mock_inner = self._start()
        mock_inner.start.assert_called_once()


# ---------------------------------------------------------------------------
# CronTrigger arguments
# ---------------------------------------------------------------------------

class TestCronTriggerArgs:
    """Patch CronTrigger to capture its construction kwargs."""

    def _capture(self, day: str = "monday", hour: int = 9) -> list[dict]:
        _CapturingCronTrigger.captured = []
        with patch("agent.core.scheduler.CronTrigger", _CapturingCronTrigger):
            sched, mock_inner = _make_scheduler_with_mock()
            sched.start(_make_vault(), _make_config(day=day, hour=hour))
        return list(_CapturingCronTrigger.captured)

    def test_outdated_review_trigger_day_hour(self) -> None:
        calls = self._capture(day="monday", hour=9)
        assert calls[0]["day_of_week"] == "mon"
        assert calls[0]["hour"] == 9
        assert calls[0]["minute"] == 0

    def test_index_rebuild_trigger(self) -> None:
        calls = self._capture()
        assert calls[1]["hour"] == 3
        assert calls[1]["minute"] == 0
        assert "day_of_week" not in calls[1]

    def test_day_name_normalisation_monday(self) -> None:
        calls = self._capture(day="monday")
        assert calls[0]["day_of_week"] == "mon"

    def test_day_name_normalisation_uppercase(self) -> None:
        calls = self._capture(day="TUESDAY")
        assert calls[0]["day_of_week"] == "tue"

    def test_day_name_passthrough_abbr(self) -> None:
        calls = self._capture(day="fri")
        assert calls[0]["day_of_week"] == "fri"


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_when_running(self) -> None:
        sched, mock_inner = _make_scheduler_with_mock()
        mock_inner.running = True
        sched.stop()
        mock_inner.shutdown.assert_called_once_with(wait=False)

    def test_stop_when_not_running(self) -> None:
        sched, mock_inner = _make_scheduler_with_mock()
        mock_inner.running = False
        sched.stop()
        mock_inner.shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# Job wrapper — _run_outdated_review
# ---------------------------------------------------------------------------

class TestRunOutdatedReview:
    @pytest.mark.anyio
    async def test_run_outdated_review_calls_task(self) -> None:
        mock_run = AsyncMock()
        mock_module = MagicMock()
        mock_module.run = mock_run
        vault = _make_vault()
        config = _make_config()

        with patch.dict(sys.modules, {"agent.tasks.outdated_review": mock_module}):
            await _run_outdated_review(vault, config)

        mock_run.assert_awaited_once_with(vault, config)

    @pytest.mark.anyio
    async def test_run_outdated_review_error_isolation(self) -> None:
        mock_run = AsyncMock(side_effect=RuntimeError("scan failed"))
        mock_module = MagicMock()
        mock_module.run = mock_run

        with patch.dict(sys.modules, {"agent.tasks.outdated_review": mock_module}):
            # Must not raise
            await _run_outdated_review(_make_vault(), _make_config())

        mock_run.assert_awaited_once()


# ---------------------------------------------------------------------------
# Job wrapper — _run_index_rebuild
# ---------------------------------------------------------------------------

class TestRunIndexRebuild:
    @pytest.mark.anyio
    async def test_run_index_rebuild_calls_task(self) -> None:
        mock_rebuild = AsyncMock()
        mock_module = MagicMock()
        mock_module.rebuild_all_counts = mock_rebuild
        vault = _make_vault()

        with patch.dict(sys.modules, {"agent.tasks.index_updater": mock_module}):
            await _run_index_rebuild(vault)

        mock_rebuild.assert_awaited_once_with(vault)

    @pytest.mark.anyio
    async def test_run_index_rebuild_error_isolation(self) -> None:
        mock_rebuild = AsyncMock(side_effect=OSError("disk full"))
        mock_module = MagicMock()
        mock_module.rebuild_all_counts = mock_rebuild

        with patch.dict(sys.modules, {"agent.tasks.index_updater": mock_module}):
            # Must not raise
            await _run_index_rebuild(_make_vault())

        mock_rebuild.assert_awaited_once()


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------

class TestImportability:
    def test_importable_without_task_modules(self) -> None:
        """AgentScheduler is importable even when agent.tasks.* don't exist."""
        # Remove task modules from sys.modules if present
        for mod_name in (
            "agent.tasks.outdated_review",
            "agent.tasks.index_updater",
        ):
            sys.modules.pop(mod_name, None)

        # Force reload of the scheduler module — must succeed without task modules
        import agent.core.scheduler as sched_mod
        importlib.reload(sched_mod)

        assert sched_mod.AgentScheduler is not None
