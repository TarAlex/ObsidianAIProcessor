"""Unit tests for agent/core/watcher.py.

All tests use unittest.mock — no real Observer, no real timers,
no real filesystem (except for Path construction).
"""
from __future__ import annotations

import queue
import time
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

from agent.core.watcher import InboxWatcher, _InboxEventHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INBOX = Path("/vault/00_INBOX")


def make_handler(debounce_s: float = 0.0) -> tuple[_InboxEventHandler, queue.Queue]:
    q: queue.Queue = queue.Queue()
    handler = _InboxEventHandler(INBOX, q, debounce_s=debounce_s)
    return handler, q


def make_created_event(src_path: str, is_directory: bool = False) -> MagicMock:
    ev = MagicMock()
    ev.src_path = src_path
    ev.is_directory = is_directory
    return ev


def make_moved_event(
    src_path: str, dest_path: str, is_directory: bool = False
) -> MagicMock:
    ev = MagicMock()
    ev.src_path = src_path
    ev.dest_path = dest_path
    ev.is_directory = is_directory
    return ev


def make_config(vault_root: str = "/vault") -> MagicMock:
    cfg = MagicMock()
    cfg.vault.root = vault_root
    return cfg


# ---------------------------------------------------------------------------
# _InboxEventHandler — on_created
# ---------------------------------------------------------------------------

class TestOnCreated:
    def test_skip_suffix_on_created(self) -> None:
        """Files with .part, .tmp, .crdownload → _schedule never called."""
        handler, _ = make_handler()
        with patch.object(handler, "_schedule") as mock_sched:
            for suffix in (".part", ".tmp", ".crdownload"):
                ev = make_created_event(f"/vault/00_INBOX/file{suffix}")
                handler.on_created(ev)
            mock_sched.assert_not_called()

    def test_skip_directory_event_on_created(self) -> None:
        """Directory events are ignored."""
        handler, _ = make_handler()
        with patch.object(handler, "_schedule") as mock_sched:
            ev = make_created_event("/vault/00_INBOX/somedir", is_directory=True)
            handler.on_created(ev)
            mock_sched.assert_not_called()

    def test_on_created_valid_file_enqueued(self) -> None:
        """.md file: after debounce timer fires, path lands in the queue."""
        handler, q = make_handler(debounce_s=0.0)
        ev = make_created_event("/vault/00_INBOX/note.md")
        handler.on_created(ev)
        time.sleep(0.05)  # timer fires almost immediately at debounce_s=0
        assert not q.empty()
        assert q.get_nowait() == Path("/vault/00_INBOX/note.md")


# ---------------------------------------------------------------------------
# _InboxEventHandler — debounce
# ---------------------------------------------------------------------------

class TestDebounce:
    def test_debounce_cancels_prior_timer(self) -> None:
        """Two rapid events for same path → first timer cancelled, only one emission."""
        handler, q = make_handler(debounce_s=0.05)
        path_str = "/vault/00_INBOX/note.md"
        ev = make_created_event(path_str)

        handler.on_created(ev)
        handler.on_created(ev)  # immediately fires second; cancels first

        time.sleep(0.2)  # wait for second timer to fire

        items: list[Path] = []
        while not q.empty():
            items.append(q.get_nowait())

        assert len(items) == 1
        assert items[0] == Path(path_str)


# ---------------------------------------------------------------------------
# _InboxEventHandler — on_moved
# ---------------------------------------------------------------------------

class TestOnMoved:
    def test_on_moved_dest_outside_inbox_skipped(self) -> None:
        """dest not inside inbox_path → _schedule never called."""
        handler, _ = make_handler()
        with patch.object(handler, "_schedule") as mock_sched:
            ev = make_moved_event(
                src_path="/other/file.md",
                dest_path="/vault/02_KNOWLEDGE/note.md",
            )
            handler.on_moved(ev)
            mock_sched.assert_not_called()

    def test_on_moved_dest_inside_inbox_accepted(self) -> None:
        """dest inside inbox, .md → enqueued after debounce."""
        handler, q = make_handler(debounce_s=0.0)
        ev = make_moved_event(
            src_path="/tmp/note.md",
            dest_path="/vault/00_INBOX/note.md",
        )
        handler.on_moved(ev)
        time.sleep(0.05)
        assert not q.empty()
        assert q.get_nowait() == Path("/vault/00_INBOX/note.md")

    def test_on_moved_dest_skip_suffix(self) -> None:
        """dest inside inbox but .tmp → _schedule never called."""
        handler, _ = make_handler()
        with patch.object(handler, "_schedule") as mock_sched:
            ev = make_moved_event(
                src_path="/tmp/file",
                dest_path="/vault/00_INBOX/file.tmp",
            )
            handler.on_moved(ev)
            mock_sched.assert_not_called()

    def test_on_moved_skip_directory(self) -> None:
        """Directory move events are ignored."""
        handler, _ = make_handler()
        with patch.object(handler, "_schedule") as mock_sched:
            ev = make_moved_event(
                src_path="/tmp/dir",
                dest_path="/vault/00_INBOX/dir",
                is_directory=True,
            )
            handler.on_moved(ev)
            mock_sched.assert_not_called()


# ---------------------------------------------------------------------------
# InboxWatcher
# ---------------------------------------------------------------------------

class TestInboxWatcher:
    def test_inbox_path_construction(self) -> None:
        """_inbox_path is derived from config.vault.root."""
        cfg = make_config(vault_root="/my/vault")
        watcher = InboxWatcher(cfg)
        assert watcher._inbox_path == Path("/my/vault/00_INBOX")

    @pytest.mark.anyio
    async def test_drain_loop_dispatches_to_pipeline(self) -> None:
        """Path pushed to queue → drain loop calls pipeline.process_file."""
        cfg = make_config()
        watcher = InboxWatcher(cfg)
        pipeline = MagicMock()
        pipeline.process_file = AsyncMock(return_value=None)

        q: queue.Queue = queue.Queue()
        test_path = Path("/vault/00_INBOX/note.md")
        q.put_nowait(test_path)

        async with anyio.create_task_group() as tg:
            tg.start_soon(watcher._drain_loop, q, pipeline, tg)
            await anyio.sleep(0.2)
            tg.cancel_scope.cancel()

        pipeline.process_file.assert_called_once_with(test_path)

    @pytest.mark.anyio
    async def test_dispatch_logs_exception_does_not_raise(self) -> None:
        """process_file raises → _dispatch logs exception, does not re-raise."""
        cfg = make_config()
        watcher = InboxWatcher(cfg)
        pipeline = MagicMock()
        pipeline.process_file = AsyncMock(side_effect=RuntimeError("boom"))

        # Must not raise
        await watcher._dispatch(Path("/vault/00_INBOX/note.md"), pipeline)
        pipeline.process_file.assert_called_once()

    @pytest.mark.anyio
    async def test_observer_stop_join_called_on_cancel(self) -> None:
        """On anyio cancellation, observer.stop() and observer.join() are invoked."""
        cfg = make_config()
        watcher = InboxWatcher(cfg)
        pipeline = MagicMock()
        mock_observer = MagicMock()

        with patch("agent.core.watcher.Observer", return_value=mock_observer):
            with anyio.move_on_after(0.05):
                await watcher.run(pipeline)

        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()
