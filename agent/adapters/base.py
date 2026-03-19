"""Base adapter interface for all source adapters.

Zero optional dependencies — only stdlib + pydantic at module level.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem


class AdapterError(Exception):
    """Raised by any adapter on unrecoverable source failure."""

    def __init__(self, message: str, path: Path) -> None:
        super().__init__(message)
        self.path = path


class BaseAdapter(ABC):
    """Abstract base class that every source adapter must subclass."""

    @abstractmethod
    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        """Extract content from *path* and return a NormalizedItem.

        Concrete implementations must:
        - Use anyio for async file I/O (not open()).
        - Set NormalizedItem.file_mtime via:
              datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        - Raise AdapterError on any unrecoverable failure.
        """
        ...

    @staticmethod
    def _generate_raw_id() -> str:
        """Return a canonical ``SRC-YYYYMMDD-HHmmss`` identifier (UTC)."""
        return datetime.now(tz=timezone.utc).strftime("SRC-%Y%m%d-%H%M%S")
