# Spec: agent/core/pipeline.py
slug: pipeline-py
layer: core/orchestration
phase: 1
arch_section: §5 Pipeline Implementation

---

## Problem statement

The system needs a central orchestrator that drives a raw inbox file through all
7 pipeline stages (S1→S7, with S4b and S6b sub-stages) and produces a
`ProcessingRecord`. It must handle low-confidence routing to `to_review/`, error
routing to `to_review/`, sync-lock polling before batch runs, and verbatim block
counting. The module must be importable today even though stage modules, vault,
and LLM provider are all TODO.

---

## Module contract

```
Input:   raw_path: Path  (a single inbox file, or list[Path] for batch)
         config:   AgentConfig  (already loaded by caller)
         vault:    ObsidianVault  (dependency-injected; mocked in unit tests)

Output:  ProcessingRecord  (from agent.core.models)
```

`KnowledgePipeline` is a class — callers construct it once and call
`process_file` / `process_batch` repeatedly.

---

## Key implementation notes

### 1. Importability before dependencies exist

`pipeline.py` must be importable when `agent.stages.*`, `agent.vault.vault`,
and `agent.llm.provider_factory` do not yet exist. Use one of:

```python
from __future__ import annotations   # at the top of the file
```

AND lazy runtime imports for stages and provider inside the methods that call
them (not at module level). Pattern:

```python
# At the top: only import what exists (models, config)
from agent.core.models import NormalizedItem, ProcessingRecord
from agent.core.config import AgentConfig

# Inside __init__ — lazy, so import errors happen at runtime not import time
def __init__(self, config: AgentConfig, vault: Any) -> None:
    self.config = config
    self.vault = vault
    # defer provider creation to avoid import error when llm layer missing
    self._llm: Any = None

def _get_llm(self) -> Any:
    """Lazy provider initialisation."""
    if self._llm is None:
        from agent.llm.provider_factory import get_provider  # noqa: PLC0415
        self._llm = get_provider(self.config)
    return self._llm
```

Stage functions must also be imported inside `process_file` at runtime:

```python
from agent.stages import s1_normalize, s2_classify, ...
```

This means each `process_file` call will re-import modules on first use, which
is cheap (Python caches `sys.modules`).

### 2. anyio — never asyncio

Replace every `asyncio.*` call from §5 with `anyio.*`:

| §5 (architecture) | pipeline.py (implementation) |
|---|---|
| `await asyncio.sleep(5)` | `await anyio.sleep(config.sync.sync_poll_interval_s)` |
| `asyncio.gather(*tasks)` | anyio `TaskGroup` pattern (see §batch below) |

`process_batch` pattern using `anyio.create_task_group`:

```python
async def process_batch(self, paths: list[Path]) -> list[ProcessingRecord]:
    await self._wait_for_sync_unlock()
    results: list[ProcessingRecord] = []

    async def _run(p: Path) -> None:
        results.append(await self.process_file(p))

    async with anyio.create_task_group() as tg:
        for p in paths:
            tg.start_soon(_run, p)

    return results
```

`_wait_for_sync_unlock` pattern:

```python
async def _wait_for_sync_unlock(self) -> None:
    import time
    timeout = self.config.sync.lock_wait_timeout_s
    poll   = self.config.sync.sync_poll_interval_s
    deadline = time.monotonic() + timeout
    while self.vault.sync_in_progress():
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Sync lock not released within {timeout}s"
            )
        await anyio.sleep(poll)
```

### 3. `process_file` full stage sequence

Follow the §5 code exactly, with these corrections:

a. **`config.review_threshold` does not exist** — use `self.config.vault.review_threshold`.

b. Stage sequence with low-confidence early-return:

```
S1  normalize    → NormalizedItem              update record.raw_id, source_type
S2  classify     → ClassificationResult        update record.domain, domain_path, confidence
    IF confidence < config.vault.review_threshold:
        vault.move_to_review(raw_path, classification)
        record.output_path = str(vault.review_dir)
        return record   ← early exit
S3  dates        → NormalizedItem (mutated)
S4a summarize    → SummaryResult
S4b verbatim     → list[VerbatimBlock]         set summary.verbatim_blocks, record.verbatim_count
S5  deduplicate  → MergeResult
    IF merge_result.route_to_merge:
        vault.move_to_merge(raw_path, merge_result)
        record.output_path = str(vault.merge_dir)
        return record   ← early exit
S6a write        → OutputPaths                 set record.output_path
S6b index_update (no return value)
S7  archive      → Path                        set record.archive_path
```

c. **Error path** — any uncaught exception in the `try` block:

```python
except Exception as e:
    logger.exception("Pipeline failed for %s: %s", raw_path, e)
    record.errors.append(str(e))
    self.vault.move_to_review(raw_path, error=str(e))
```

d. **`finally` block** always executes:

```python
finally:
    record.processing_time_s = (datetime.now() - start).total_seconds()
    self.vault.append_log(record)
```

### 4. Initial record construction

Populate `record.llm_provider` from `self._get_llm().__class__.__name__` if
the LLM is already initialised; otherwise use `"unknown"` (avoids import error
during unit tests that mock the vault and skip the LLM entirely).

### 5. Logging

Use `logging.getLogger(__name__)` — no `print()` calls. Log level:
- `logger.info(...)` for normal stage transitions
- `logger.exception(...)` in the except block (includes traceback)

---

## Data model changes

None. All types consumed and produced are already defined in `agent/core/models.py`:
- Input: `Path` (stdlib)
- Key intermediate: `NormalizedItem`, `ClassificationResult`, `SummaryResult`,
  `VerbatimBlock`
- Output: `ProcessingRecord`

---

## LLM prompt file needed

None — `pipeline.py` does not call LLM directly. It delegates to stage modules.

---

## Tests required

### unit: `tests/unit/test_pipeline.py`

All tests use `unittest.mock.AsyncMock` / `MagicMock` for stage functions and
vault. No real filesystem, no real LLM.

Key cases:

| # | Case | What to assert |
|---|------|----------------|
| 1 | `process_file` happy path (all stages succeed) | returns `ProcessingRecord` with correct `domain`, `verbatim_count`, `archive_path`; `record.errors` is empty |
| 2 | low-confidence classification | `vault.move_to_review` called; returns early; `record.output_path` == `str(vault.review_dir)` |
| 3 | merge route from S5 | `vault.move_to_merge` called; returns early |
| 4 | exception in S3 | `record.errors` contains the exception string; `vault.move_to_review` called with `error=...`; `vault.append_log` still called (finally) |
| 5 | `process_batch` with 3 paths | all 3 `ProcessingRecord`s returned; `_wait_for_sync_unlock` called once |
| 6 | `_wait_for_sync_unlock` — sync clears before deadline | no exception raised |
| 7 | `_wait_for_sync_unlock` — sync never clears | `TimeoutError` raised |
| 8 | `verbatim_count` set correctly | `record.verbatim_count == len(verbatim_blocks)` |
| 9 | `pipeline.py` is importable with no stage modules installed | `import agent.core.pipeline` succeeds even if `agent.stages` is absent |

### integration: `tests/integration/test_pipeline_integration.py`

Deferred — requires vault, stages, and LLM layer to be DONE.
Placeholder file with a single `pytest.mark.skip` test is acceptable.

---

## Explicitly out of scope

| Item | Reason |
|---|---|
| `ObsidianVault` implementation | Vault Layer section |
| Any stage implementation (`s1_*` … `s7_*`) | Pipeline Stages section |
| `agent.llm.provider_factory` implementation | LLM Provider Layer section |
| `InboxWatcher` integration | `watcher-py` module |
| CLI entry point | `agent/main.py` section |
| `AtomNote`, `06_ATOMS`, `atom_id` | Phase 2 |
| Phase 2 web UI or MS Teams hooks | Phase 2 |

---

## Open questions

None — all ambiguities resolved by feature spec §4 and architecture §5 above.
The `asyncio` → `anyio` migration and `config.review_threshold` attribute path
correction are documented as implementation decisions, not open questions.
