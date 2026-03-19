# Spec: BaseAdapter ABC
slug: adapters-base
layer: adapters
phase: 1
arch_section: §2 (Project Structure), §3 (Core Data Models), §5 (Pipeline — Stage 1 entry point)

---

## Problem statement

Every source adapter (Markdown, Web, PDF, YouTube, Audio, Teams) must produce an
identical `NormalizedItem` output so Stage 1 (`s1_normalize.py`) can consume any
source type without branching.

`agent/adapters/base.py` establishes that contract as a pure abstract interface:
- `BaseAdapter(ABC)` — the class all concrete adapters inherit from
- `AdapterError` — the single exception type all adapters raise on failure
- `BaseAdapter._generate_raw_id()` — shared helper that produces the canonical
  `SRC-YYYYMMDD-HHmmss` identifier

This module must be importable with **zero optional dependencies** installed.
It contains no business logic — only the interface definition.

---

## Module contract

```
Input:
  extract(path: pathlib.Path, config: AgentConfig) -> NormalizedItem
    path   — absolute path to the raw source file (or a virtual path for URL-only inputs)
    config — fully validated AgentConfig (provides vault root, whisper settings, etc.)

Output:
  NormalizedItem  (agent/core/models.py)
    raw_id        str              "SRC-YYYYMMDD-HHmmss"
    source_type   SourceType       set by each concrete adapter
    raw_text      str              full extracted text (non-empty)
    title         str              best-effort; may be "" if unknown pre-stage-2
    url           str              populated for web/YouTube; "" otherwise
    author        str              populated when source metadata contains it; "" otherwise
    language      str              ISO 639-1 code when detected; "" otherwise
    source_date   date | None      populated from source metadata when available
    file_mtime    datetime | None  always set from Path.stat().st_mtime by the adapter
    raw_file_path Path             the path argument passed to extract()
    extra_metadata dict            adapter-specific supplemental data (e.g. page_count for PDF)

Error path:
  AdapterError(message: str, path: Path)
    Raised by any adapter on unrecoverable source failure.
    Never swallowed — propagates to pipeline error handler.
```

---

## Key implementation notes

### `AdapterError`
```python
class AdapterError(Exception):
    def __init__(self, message: str, path: Path) -> None:
        super().__init__(message)
        self.path = path
```
- Two-arg constructor: human-readable `message` + `path` for log context.
- All adapter modules import and raise only this exception; never `RuntimeError`
  or bare `Exception`.

### `BaseAdapter`
```python
from abc import ABC, abstractmethod
from pathlib import Path
from agent.core.config import AgentConfig
from agent.core.models import NormalizedItem

class BaseAdapter(ABC):
    @abstractmethod
    async def extract(self, path: Path, config: AgentConfig) -> NormalizedItem:
        ...

    @staticmethod
    def _generate_raw_id() -> str:
        from datetime import datetime, timezone
        return datetime.now(tz=timezone.utc).strftime("SRC-%Y%m%d-%H%M%S")
```

Key rules:
- `extract()` is `async` — all concrete adapters must `await` it; file I/O inside
  must use `anyio` (e.g. `await anyio.Path(path).read_text()`), not `open()`.
- `_generate_raw_id()` is a `@staticmethod` so concrete adapters call it via
  `self._generate_raw_id()` or `BaseAdapter._generate_raw_id()`.
- The method signature **must not change** — all downstream adapters depend on it.
- `NormalizedItem.file_mtime` **must** be set by every concrete adapter using
  `datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)`.
- No network, no vault, no LLM inside this module.

### Import footprint
Only stdlib + `pydantic` (already in `pyproject.toml`) may be imported at module
level. `anyio` is only used inside concrete adapter methods, not here.

---

## Data model changes

None. `NormalizedItem` and `SourceType` are already defined in `agent/core/models.py`
(DONE). `AgentConfig` is already defined in `agent/core/config.py` (DONE).

---

## LLM prompt file needed

None.

---

## Tests required

### unit: `tests/unit/test_adapters_base.py`

| # | Test case |
|---|-----------|
| 1 | `AdapterError` is a subclass of `Exception` |
| 2 | `AdapterError("msg", Path("/x"))` sets `.args[0] == "msg"` and `.path == Path("/x")` |
| 3 | `BaseAdapter` cannot be instantiated directly (raises `TypeError`) |
| 4 | A minimal concrete subclass implementing `extract()` can be instantiated |
| 5 | `_generate_raw_id()` matches regex `^SRC-\d{8}-\d{6}$` |
| 6 | Two calls to `_generate_raw_id()` return strings in `SRC-YYYYMMDD-HHmmss` format (no assertion on uniqueness — timestamps may collide in fast tests; uniqueness is a pipeline concern) |
| 7 | The module imports cleanly with only stdlib + pydantic installed (no httpx, pymupdf, whisper, etc.) |
| 8 | `extract()` is decorated with `@abstractmethod` (check via `inspect.isabstract`) |

### integration

Not applicable for this module — it is a pure ABC with no I/O.
Integration tests for the adapter layer are written alongside each concrete adapter
(e.g. `tests/integration/test_pipeline_markdown.py`).

---

## Explicitly out of scope

- Concrete adapter implementations (`markdown_adapter.py`, `web_adapter.py`, etc.)
- Any LLM calls
- Any vault writes or reads
- Network I/O
- `_generate_raw_id()` uniqueness across rapid calls (if two files arrive in the
  same second, the pipeline layer — not the adapter — is responsible for collision
  avoidance via a counter suffix or UUID; this is a Stage 1 concern)
- `anyio` file I/O (used inside concrete adapters, not in the ABC itself)
- Adapter registry / factory pattern (belongs in `s1_normalize.py`)
- Phase 2 features (Graph API, cloud Whisper, bi-directional links)

---

## Open questions

1. **Sub-second collision handling**: If two files are processed within the same
   second, two adapters produce the same `raw_id`. The feature spec places
   `_generate_raw_id()` in `BaseAdapter`; collision resolution is deferred to
   Stage 1. This spec does **not** add a counter or UUID here — confirm this is
   acceptable or raise a TRACKER note before building `s1_normalize.py`.

2. **`path` type for URL-only inputs**: Some adapters (`web_adapter`, `youtube_adapter`)
   may be invoked with a synthetic `Path` constructed from a URL rather than a real
   filesystem path. Convention TBD when building those adapters; `base.py` itself
   makes no assumptions.
