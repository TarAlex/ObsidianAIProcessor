# Spec: agent/core/watcher.py — InboxWatcher
slug: watcher-py
layer: core/io
phase: 1
arch_section: §1 (System Architecture Overview — INBOX WATCHER block), §5 (Pipeline Implementation)

---

## Problem statement

The agent must react to files dropped into `00_INBOX/` and route them through
`KnowledgePipeline.process_file()` automatically, without polling and without
blocking the event loop.

`watchdog`'s `Observer` runs in a background thread and delivers callbacks in that
thread — not in anyio's event loop. This module bridges watchdog's synchronous,
thread-based filesystem events into anyio's async task model using a stdlib
`queue.Queue` as the thread-safe staging buffer. A 2 s debounce per path prevents
processing partially-written or unstable files.

---

## Module contract

**Input (constructor)**
```python
InboxWatcher(config: AgentConfig)
```
Resolves `inbox_path = Path(config.vault.root) / "00_INBOX"` once at construction.
No other path is hardcoded.

**Primary entry-point**
```python
async def run(pipeline: KnowledgePipeline) -> None
```
- Starts `watchdog.Observer` watching `inbox_path` recursively.
- Drains the debounced queue and dispatches each file to `pipeline.process_file(path)`.
- Runs until cancelled (anyio cancellation). Always stops the observer in `finally`.
- Returns nothing; results are logged inside the pipeline.

**Dependencies consumed**
| Symbol | Module | Already DONE? |
|---|---|---|
| `AgentConfig` | `agent.core.config` | YES |
| `KnowledgePipeline` | `agent.core.pipeline` | YES |
| `watchdog.observers.Observer` | third-party | YES (pyproject.toml) |
| `watchdog.events.FileSystemEventHandler` | third-party | YES |

---

## Key implementation notes

### 1. Inbox path resolution

```python
self._inbox_path: Path = Path(config.vault.root) / "00_INBOX"
```

Use `config.vault.root` (the raw string from `VaultConfig.root`), wrapped in
`pathlib.Path` for cross-platform separator normalisation.

---

### 2. Unstable-file filtering

Class constant:
```python
SKIP_SUFFIXES: frozenset[str] = frozenset({".part", ".tmp", ".crdownload"})
```

Applied in the event handler before scheduling debounce — paths with these suffixes
are silently ignored.

---

### 3. `_InboxEventHandler(FileSystemEventHandler)` — private class

Handles two watchdog events:

**`on_created(event)`**
- Skip if `event.is_directory`
- Skip if `Path(event.src_path).suffix.lower() in SKIP_SUFFIXES`
- Otherwise: `self._schedule(event.src_path)`

**`on_moved(event)`**
- Skip if `event.is_directory`
- Skip if destination is **not inside** `inbox_path`:
  `not Path(event.dest_path).is_relative_to(self._inbox_path)`
- Skip if `Path(event.dest_path).suffix.lower() in SKIP_SUFFIXES`
- Otherwise: `self._schedule(event.dest_path)`

Constructor signature:
```python
def __init__(
    self,
    inbox_path: Path,
    queue: queue.Queue,   # stdlib threading queue
    debounce_s: float = 2.0,
) -> None:
```

---

### 4. Debounce mechanism

All state inside `_InboxEventHandler`:
```python
self._pending: dict[str, threading.Timer] = {}
self._lock: threading.Lock = threading.Lock()
self._debounce_s: float = debounce_s
```

`_schedule(path_str: str) → None`:
```python
with self._lock:
    if path_str in self._pending:
        self._pending[path_str].cancel()

    def _emit() -> None:
        with self._lock:
            self._pending.pop(path_str, None)
        self._queue.put_nowait(Path(path_str))

    t = threading.Timer(self._debounce_s, _emit)
    self._pending[path_str] = t
    t.start()
```

Effect: rapid events for the same path reset the 2 s countdown; only one emission
per stable file.

---

### 5. Thread-safe queue bridge

Use `queue.Queue[Path]` (stdlib `queue.Queue`, **not** `asyncio.Queue`) as the bridge.
`put_nowait` is called from a `threading.Timer` callback (background thread);
`get_nowait` is called from the anyio drain loop (event loop thread). This avoids any
`anyio.from_thread` portal complexity and is cross-backend portable.

---

### 6. Async drain loop

```python
async def _drain_loop(
    self,
    q: queue.Queue,
    pipeline: KnowledgePipeline,
    tg: anyio.abc.TaskGroup,
) -> None:
    while True:
        try:
            path = q.get_nowait()
            tg.start_soon(self._dispatch, path, pipeline)
        except queue.Empty:
            await anyio.sleep(0.1)
```

`_dispatch` wraps `process_file` with error isolation so one failed file does not
crash the watcher:
```python
async def _dispatch(self, path: Path, pipeline: KnowledgePipeline) -> None:
    try:
        await pipeline.process_file(path)
    except Exception:
        logger.exception("process_file failed for %s", path)
```

Each file dispatched as an independent anyio task — no head-of-line blocking.

---

### 7. `run()` structure

```python
async def run(self, pipeline: KnowledgePipeline) -> None:
    q: queue.Queue = queue.Queue()
    handler = _InboxEventHandler(self._inbox_path, q, self.DEBOUNCE_S)
    observer = Observer()
    observer.schedule(handler, str(self._inbox_path), recursive=True)
    observer.start()
    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._drain_loop, q, pipeline, tg)
    finally:
        observer.stop()
        observer.join()
```

The task group runs indefinitely (drain loop is an infinite loop).
On anyio cancellation the task group cancels `_drain_loop`; `finally` always
stops and joins the watchdog thread cleanly.

---

### 8. Cross-platform notes

- `pathlib.Path` normalises Windows `\` separators automatically.
- watchdog automatically selects `WindowsApiObserver` on Windows, `InotifyObserver`
  on Linux, `FSEventsObserver` on macOS — no platform-specific code in this module.
- `Path.is_relative_to()` is Python 3.9+; safe since project targets Python 3.11+.

---

## Data model changes

None. `InboxWatcher` introduces no new Pydantic models.

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_watcher.py`

All tests use `unittest.mock` (no real Observer, no real timers, no real filesystem).

| Test | What it verifies |
|---|---|
| `test_skip_suffix_on_created` | `.part`, `.tmp`, `.crdownload` → `_schedule` never called |
| `test_skip_directory_event_on_created` | `is_directory=True` → `_schedule` never called |
| `test_on_created_valid_file_enqueued` | `.md` file → after timer fires → path in queue |
| `test_debounce_cancels_prior_timer` | Two rapid events for same path → first timer cancelled, second fires |
| `test_on_moved_dest_outside_inbox_skipped` | dest not under inbox → `_schedule` never called |
| `test_on_moved_dest_inside_inbox_accepted` | dest inside inbox, `.md` → enqueued after debounce |
| `test_on_moved_dest_skip_suffix` | dest inside inbox but `.tmp` → skipped |
| `test_drain_loop_dispatches_to_pipeline` | Push path to queue, run drain loop one tick via `anyio.from_thread`, verify `process_file` called |
| `test_dispatch_logs_exception_does_not_raise` | `process_file` raises → `_dispatch` logs, does not re-raise |
| `test_observer_stop_join_called_on_cancel` | Simulate anyio cancellation → `observer.stop()` and `observer.join()` invoked |

### integration: `tests/integration/test_watcher_integration.py` (optional, CI-skipped)

- Marked `@pytest.mark.integration` (skip unless `RUN_INTEGRATION=1`)
- Uses real `tmp_path` as vault root (creates `00_INBOX/` subdirectory)
- Drops a real `.md` file into inbox; asserts `pipeline.process_file` called within 4 s
- Drops a `.tmp` file; asserts `pipeline.process_file` NOT called

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| Initial scan of files already in inbox at startup | Not in feature spec; separate concern |
| Back-pressure / queue size limit | Future concern; no spec for it |
| watchdog backend selection / inotify tuning | watchdog auto-selects; no code needed |
| Rate limiting concurrent `process_file` calls | Pipeline handles its own concurrency |
| `scheduler.py` integration | Separate module (`scheduler-py`) |
| Any `ObsidianVault` calls | Vault layer not yet built |
| Graceful drain-on-shutdown (finish in-flight files) | Out of Phase 1 scope |

---

## Open questions

None — all design decisions resolved by the feature spec constraints and the
existing `config.py` / `pipeline.py` interface contracts.
