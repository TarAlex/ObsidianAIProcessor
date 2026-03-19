# Spec: agent/core/scheduler.py — APScheduler periodic tasks
slug: scheduler-py
layer: core/tasks
phase: 1
arch_section: §10 (SchedulerConfig), §12 (outdated_review task interface), §13 (index_updater task interface)

---

## Problem statement

The agent needs two periodic background jobs that run independently of the
inbox watcher:

1. **Weekly outdated-review scan** — calls
   `agent.tasks.outdated_review.run(vault, config)` on a configurable weekday
   and hour (from `SchedulerConfig`).
2. **Daily index rebuild** — calls
   `agent.tasks.index_updater.rebuild_all_counts(vault)` at 03:00 local time.

Neither task module exists yet (Scheduled Tasks section is later). The scheduler
must therefore be importable and unit-testable with lazy imports and mock callables
before those modules are built.

This module provides `AgentScheduler`, a thin wrapper around APScheduler's
`AsyncIOScheduler`, with a clean `start(vault, config)` / `stop()` synchronous API.

---

## Module contract

```
Input:
  AgentScheduler.start(vault: ObsidianVault, config: AgentConfig) → None
    vault   — any object satisfying the vault interface (passed through to jobs)
    config  — AgentConfig with .scheduler.outdated_review_day (str) and
              .scheduler.outdated_review_hour (int)

  AgentScheduler.stop() → None
    — shuts down the scheduler gracefully; no-op if not running

Output: None  (side-effectful — registers jobs and starts the APScheduler loop)

Raises: nothing from start()/stop() — all job-level errors are caught inside
        the job wrapper functions and logged.
```

---

## Key implementation notes

### 1. Class skeleton

```python
# agent/core/scheduler.py
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Full weekday name → APScheduler 3.x abbreviation
_DAY_ABBR: dict[str, str] = {
    "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
}


class AgentScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def start(self, vault, config) -> None:
        """Register both periodic jobs and start the underlying scheduler."""
        ...

    def stop(self) -> None:
        """Shut down the scheduler; no-op if not running."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
```

### 2. Job registration in `start()`

```python
def start(self, vault, config) -> None:
    raw_day = config.scheduler.outdated_review_day.lower()
    day_abbr = _DAY_ABBR.get(raw_day, raw_day)   # pass-through if already abbr

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
        misfire_grace_time=3600,   # 1-hour grace if system was sleeping
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
```

`misfire_grace_time=3600`: if the system was suspended past the scheduled time,
APScheduler will still run the job within the 1-hour window. After that window
it is skipped (not accumulated).

### 3. Lazy-import job wrapper functions (module-level)

These must be module-level so APScheduler can reference them without pickling.
Imports are **deferred to call time** so `scheduler.py` remains importable before
the task modules exist.

```python
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
```

Each wrapper catches **all** exceptions, logs them, and returns normally.
APScheduler will not cancel or pause the job after a single failure.

### 4. anyio compatibility

`AsyncIOScheduler` attaches itself to the running asyncio event loop when
`start()` is called. Since anyio's asyncio backend IS the asyncio event loop,
`start()` must be called from within an async context (inside a coroutine or
anyio task group), not from a bare synchronous main.

Constraint compliance:
- Our code contains **no** direct `asyncio.*` calls.
- Job wrappers are `async def` — APScheduler awaits them natively.
- `anyio.from_thread` is not needed; APScheduler 3.x awaits coroutines on the
  same event loop.
- Note: APScheduler's `AsyncIOScheduler` is asyncio-only. Under anyio's **trio**
  backend it would not work. Since this project targets asyncio (the default
  `anyio` backend on all platforms), this is acceptable.

### 5. No hardcoded timing values

All user-configurable schedule parameters come from `config.scheduler.*`.
The index-rebuild hour (`3`) is the only constant in this module; it is not
in `SchedulerConfig` per the architecture spec (§10).

### 6. `poll_interval_minutes` is NOT used here

`SchedulerConfig.poll_interval_minutes` is for the watcher debounce; the
scheduler does not read it.

---

## Data model changes

None. `SchedulerConfig` in `agent/core/config.py` already provides:

```python
class SchedulerConfig(BaseModel):
    poll_interval_minutes: int = 15
    outdated_review_day: str = "monday"
    outdated_review_hour: int = 9
```

No new Pydantic models are needed.

---

## LLM prompt file needed

None. This module makes no LLM calls.

---

## Tests required

### unit: `tests/unit/test_scheduler.py`

All tests mock `AsyncIOScheduler` and the task modules to avoid real event loops
or missing imports. Use `pytest-mock` (`mocker` fixture) or `unittest.mock.patch`.

| Test case | What it checks |
|---|---|
| `test_start_registers_two_jobs` | `start()` calls `add_job` twice, with `id="outdated_review_job"` and `id="index_rebuild_job"` |
| `test_outdated_review_trigger_day_hour` | CronTrigger for outdated_review receives correct `day_of_week` abbr and `hour` from config |
| `test_index_rebuild_trigger` | CronTrigger for index_rebuild uses `hour=3, minute=0` regardless of config |
| `test_day_name_normalisation_monday` | config `outdated_review_day="monday"` → `day_of_week="mon"` |
| `test_day_name_normalisation_uppercase` | `"TUESDAY"` → `"tue"` |
| `test_day_name_passthrough_abbr` | `"fri"` → `"fri"` (already an abbreviation) |
| `test_start_calls_scheduler_start` | `start()` calls `self._scheduler.start()` after adding jobs |
| `test_stop_when_running` | `stop()` calls `scheduler.shutdown(wait=False)` when `running=True` |
| `test_stop_when_not_running` | `stop()` with `running=False` → no call to `shutdown`, no exception |
| `test_run_outdated_review_error_isolation` | `_run_outdated_review` catches exception from mocked `run` → logs error, does not re-raise |
| `test_run_index_rebuild_error_isolation` | `_run_index_rebuild` catches exception from mocked `rebuild_all_counts` → logs error, does not re-raise |
| `test_run_outdated_review_calls_task` | `_run_outdated_review` imports and awaits `agent.tasks.outdated_review.run` |
| `test_run_index_rebuild_calls_task` | `_run_index_rebuild` imports and awaits `agent.tasks.index_updater.rebuild_all_counts` |
| `test_importable_without_task_modules` | `from agent.core.scheduler import AgentScheduler` succeeds with empty `agent/tasks/` |

No integration tests — real APScheduler execution timing is out of scope for unit testing.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `agent.tasks.outdated_review` implementation | Separate section: Scheduled Tasks |
| `agent.tasks.index_updater` implementation | Separate section: Scheduled Tasks |
| `ObsidianVault` instantiation | Vault layer — not built in Foundations |
| `poll_interval_minutes` usage | Consumed by watcher debounce, not APScheduler jobs |
| Phase 2 tasks (`reference_linker`, etc.) | Not scheduled in Phase 1 |
| Persistent APScheduler job store (SQLAlchemy / Redis) | In-memory store is sufficient for Phase 1 |
| Arbitrary cron expression strings in YAML | Architecture specifies only `day` + `hour`; no arbitrary cron |
| Timezone configuration | Architecture does not specify TZ; system local time is used |
| `anyio.from_thread` or trio backend support | Project uses asyncio backend exclusively |

---

## Open questions

None. All decisions resolved by `feature-foundations.md §6`, `config-py.md §SchedulerConfig`,
and `ARCHITECTURE.md §10 / §12 / §13`.
