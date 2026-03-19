"""agent/core/watcher.py — Filesystem inbox watcher.

Bridges watchdog's thread-based file events into anyio's task group
using a stdlib queue.Queue as a thread-safe staging buffer.
A 2 s debounce per path prevents processing partially-written files.
"""
from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path

import anyio
import anyio.abc
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agent.core.config import AgentConfig
from agent.core.pipeline import KnowledgePipeline

logger = logging.getLogger(__name__)


class _InboxEventHandler(FileSystemEventHandler):
    """Watchdog event handler that debounces filesystem events into a stdlib queue."""

    def __init__(
        self,
        inbox_path: Path,
        queue: queue.Queue,
        debounce_s: float = 2.0,
    ) -> None:
        super().__init__()
        self._inbox_path = inbox_path
        self._queue = queue
        self._debounce_s = debounce_s
        self._pending: dict[str, threading.Timer] = {}
        self._lock: threading.Lock = threading.Lock()

    def on_created(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        if Path(event.src_path).suffix.lower() in InboxWatcher.SKIP_SUFFIXES:
            return
        self._schedule(event.src_path)

    def on_moved(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        dest = Path(event.dest_path)
        if not dest.is_relative_to(self._inbox_path):
            return
        if dest.suffix.lower() in InboxWatcher.SKIP_SUFFIXES:
            return
        self._schedule(event.dest_path)

    def _schedule(self, path_str: str) -> None:
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


class InboxWatcher:
    """Watches 00_INBOX/ for new files and dispatches them to KnowledgePipeline.

    Uses watchdog for event delivery (background thread) and a stdlib queue.Queue
    as a thread-safe bridge into anyio's task model.
    """

    SKIP_SUFFIXES: frozenset[str] = frozenset({".part", ".tmp", ".crdownload"})
    DEBOUNCE_S: float = 2.0

    def __init__(self, config: AgentConfig) -> None:
        self._inbox_path: Path = Path(config.vault.root) / "00_INBOX"

    async def run(self, pipeline: KnowledgePipeline) -> None:
        """Start watching 00_INBOX/ and dispatch stable files to pipeline.process_file().

        Runs until anyio cancellation. Always stops and joins the watchdog Observer
        in the finally block.
        """
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

    async def _dispatch(self, path: Path, pipeline: KnowledgePipeline) -> None:
        try:
            await pipeline.process_file(path)
        except Exception:
            logger.exception("process_file failed for %s", path)
