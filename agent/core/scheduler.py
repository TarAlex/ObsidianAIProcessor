"""agent/core/scheduler.py — APScheduler periodic background tasks.

Provides AgentScheduler with a synchronous start(vault, config) / stop() API.
Two periodic jobs:
  - Weekly outdated-review scan   (day/hour from SchedulerConfig)
  - Daily index rebuild            (03:00 local time, fixed)

All LLM-task imports are lazy so this module is importable before the task
modules exist.  All job-level exceptions are caught and logged; the scheduler
never crashes on a single job failure.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Full weekday name → APScheduler 3.x day_of_week abbreviation
_DAY_ABBR: dict[str, str] = {
    "monday": "mon",
    "tuesday": "tue",
    "wednesday": "wed",
    "thursday": "thu",
    "friday": "fri",
    "saturday": "sat",
    "sunday": "sun",
}


# ---------------------------------------------------------------------------
# Module-level job wrappers  (must be module-level for APScheduler pickling)
# ---------------------------------------------------------------------------

async def _run_outdated_review(vault, config) -> None:
    """APScheduler job — weekly outdated-review scan."""
    try:
        from agent.tasks.outdated_review import run as outdated_run  # lazy
        await outdated_run(vault, config)
    except Exception as exc:
        logger.error("outdated_review_job failed: %s", exc, exc_info=True)


async def _run_index_rebuild(vault) -> None:
    """APScheduler job — daily index rebuild."""
    try:
        from agent.tasks.index_updater import rebuild_all_counts  # lazy
        await rebuild_all_counts(vault)
    except Exception as exc:
        logger.error("index_rebuild_job failed: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class AgentScheduler:
    """Thin wrapper around APScheduler's AsyncIOScheduler.

    Call start() from inside a running anyio/asyncio event loop.
    Call stop() from anywhere (no-op if not running).
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def start(self, vault, config) -> None:
        """Register both periodic jobs and start the underlying scheduler.

        Must be called from within a running asyncio event loop (anyio asyncio
        backend is compatible).
        """
        raw_day = config.scheduler.outdated_review_day.lower()
        day_abbr = _DAY_ABBR.get(raw_day, raw_day)  # pass-through if already abbr

        self._scheduler.add_job(
            _run_outdated_review,
            CronTrigger(
                day_of_week=day_abbr,
                hour=config.scheduler.outdated_review_hour,
                minute=0,
            ),
            args=[vault, config],
            id="outdated_review_job",
            replace_existing=True,
            misfire_grace_time=3600,  # 1-hour grace if system was sleeping
        )

        self._scheduler.add_job(
            _run_index_rebuild,
            CronTrigger(hour=3, minute=0),
            args=[vault],
            id="index_rebuild_job",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self._scheduler.start()
        logger.info(
            "Scheduler started — outdated-review: %s %02d:00, "
            "index-rebuild: daily 03:00",
            day_abbr,
            config.scheduler.outdated_review_hour,
        )

    def stop(self) -> None:
        """Shut down the scheduler; no-op if not running."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
