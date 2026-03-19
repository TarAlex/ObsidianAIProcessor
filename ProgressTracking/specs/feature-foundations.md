# Feature Spec: Foundations
slug: feature-foundations
sections_covered: [ProgressTracking/tasks/01_foundations.md]
arch_sections: [§1, §2, §3, §5, §10, §12, §13, §16, REQUIREMENTS §5.3]

---

## Scope

Stand up the entire project skeleton and the six core infrastructure modules that
every other section depends on. After this section is DONE the repo is installable
(`pip install -e .`), the package structure is valid, all v1.1 Pydantic models
exist, config loads cleanly, and the pipeline orchestrator + inbox watcher +
scheduler are wired together (stages are stub-imported at this point).

No business logic beyond what is specified below. No stage implementations.
No vault writes. No LLM calls.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `pyproject.toml` + directory skeleton + `__init__.py` files | `pyproject-scaffold` | none | scaffold |
| 2 | `agent/core/models.py` — all v1.1 Pydantic models | `models-py` | `pyproject-scaffold` | core/models |
| 3 | `agent/core/config.py` — YAML + `.env` loading, `AgentConfig` Pydantic model | `config-py` | `pyproject-scaffold`, `models-py` | core/config |
| 4 | `agent/core/pipeline.py` — `KnowledgePipeline` stage orchestrator | `pipeline-py` | `models-py`, `config-py` | core/orchestration |
| 5 | `agent/core/watcher.py` — `watchdog`-based `InboxWatcher` | `watcher-py` | `config-py`, `pipeline-py` | core/io |
| 6 | `agent/core/scheduler.py` — `APScheduler` periodic tasks (weekly + daily) | `scheduler-py` | `config-py` | core/scheduler |

---

## Cross-cutting constraints

All modules in this section MUST obey:

| Rule | Rationale |
|---|---|
| Python 3.11+ syntax only | `pyproject.toml` target (`requires-python = ">=3.11"`) |
| `anyio` for all async primitives — never `asyncio` directly | Cross-platform portability (§ code constraints) |
| Pydantic v2 for every model (`model_dump`, not `.dict()`) | Type safety across pipeline stages |
| All paths read from `AgentConfig` — zero hardcoded paths or API keys | Portability and security |
| No Phase 2 symbols (`AtomNote`, `06_ATOMS`, `extract_atoms`, `atom_id`) | Scope discipline |
| All vault writes go via `ObsidianVault` — but `ObsidianVault` is NOT built in this section | No vault code in Foundations modules |
| Stage imports in `pipeline.py` may be lazy/conditional until stage modules exist | Dependency ordering |

---

## Module notes (what each spec must cover)

### 1. `pyproject-scaffold` (pyproject.toml + project skeleton)

- `pyproject.toml` with `[project]` metadata from ARCHITECTURE §16 (all deps pinned to minimum versions listed there)
- `[project.scripts]` entry: `obsidian-agent = "agent.main:cli"` (stub `main.py` OK here)
- Dev deps: `pytest`, `pytest-anyio`, `pytest-cov`
- All package directories with `__init__.py`: `agent/`, `agent/core/`, `agent/adapters/`, `agent/llm/`, `agent/vault/`, `agent/stages/`, `agent/tasks/`, `agent/vector/`
- `.env.example` with all config env-var keys, values redacted
- `README.md` (one paragraph) and `.gitignore`
- Must pass `pip install -e .` and `python -c "import agent"` without errors

### 2. `models-py` (agent/core/models.py)

Implement all v1.1 models exactly as specified in ARCHITECTURE §3:

| Model | Key v1.1 additions |
|---|---|
| `SourceType`, `ContentAge`, `ProcessingStatus` | Enums, unchanged |
| `StatenessRisk` ★ | NEW enum: `low / medium / high` |
| `VerbatimType` ★ | NEW enum: `code / prompt / quote / transcript` |
| `VerbatimBlock` ★ | NEW model: `type`, `content`, `lang`, `source_id`, `added_at`, `staleness_risk`, `attribution`, `timestamp`, `model_target` |
| `NormalizedItem` | Unchanged from §3 |
| `ClassificationResult` | Added: `domain_path: str`, `staleness_risk: StatenessRisk` |
| `SummaryResult` | Added: `verbatim_blocks: list[VerbatimBlock]` |
| `DomainIndexEntry` ★ | NEW model: `index_type`, `domain`, `subdomain`, `note_count`, `last_updated`, `tags` |
| `ProcessingRecord` | Added: `domain_path: str`, `verbatim_count: int` |
| `PersonReference`, `ProjectReference` | Unchanged from §3 |

All fields must match §3 exactly — no extra fields, no renamed fields.
`VerbatimBlock.content` docstring must state "agent must not modify".

### 3. `config-py` (agent/core/config.py)

- `AgentConfig` Pydantic v2 model matching the full YAML schema in ARCHITECTURE §10
- Sub-models: `VaultConfig` (includes `max_verbatim_blocks_per_note: int = 10`, `verbatim_high_risk_age: int = 365`), `LLMConfig`, `ProviderConfig`, `SchedulerConfig`, `SyncConfig`, `WhisperConfig`
- `load_config(path: str | Path) -> AgentConfig`: reads YAML, overlays env vars via `python-dotenv`
- All `api_key_*` fields read exclusively from env vars named by `api_key_env` — never from YAML values
- Must raise `ConfigError` (custom exception) with a clear message if required fields are missing or vault root does not exist
- `tag_taxonomy_summary` property: returns abbreviated string for prompt injection

### 4. `pipeline-py` (agent/core/pipeline.py)

- `KnowledgePipeline` class exactly as shown in ARCHITECTURE §5
- `process_file(raw_path: Path) -> ProcessingRecord` — full 8-stage sequence (S1→S7 inclusive, with S4b and S6b)
- `process_batch(paths: list[Path]) -> list[ProcessingRecord]` — `anyio.gather` (not `asyncio.gather`)
- `_wait_for_sync_unlock()` — polls `vault.sync_in_progress()` with timeout from config
- Stage imports (`agent.stages.*`) must use `from __future__ import annotations` or lazy imports; modules may not yet exist but `pipeline.py` must be importable
- Error path: uncaught exception → `vault.move_to_review(raw_path, error=str(e))` + log + append to `record.errors`
- `record.verbatim_count` populated from `len(verbatim_blocks)` after S4b
- Low-confidence path (< `review_threshold`): `vault.move_to_review()` → early return, no further stages

### 5. `watcher-py` (agent/core/watcher.py)

- `InboxWatcher` using `watchdog` `Observer` + `FileSystemEventHandler`
- Watches `config.vault.root / "00_INBOX"` recursively
- On `on_created` / `on_moved` (into inbox): debounce 2s then enqueue path to `anyio.MemoryObjectSendStream`
- `async def run(pipeline: KnowledgePipeline)` — starts observer + drains queue via `anyio.TaskGroup`
- Handles `.part`, `.tmp`, `.crdownload` extensions — skip until stable
- Inbox path from config — no hardcoding
- Must be cross-platform (Windows path separators handled by `pathlib.Path`)

### 6. `scheduler-py` (agent/core/scheduler.py)

- `AgentScheduler` wrapping `APScheduler AsyncIOScheduler` (anyio-compatible)
- Registers two periodic jobs from config:
  - `outdated_review_job`: weekly on `config.scheduler.outdated_review_day` at `config.scheduler.outdated_review_hour` → calls `agent.tasks.outdated_review.run(vault, config)`
  - `index_rebuild_job`: daily at 03:00 local → calls `agent.tasks.index_updater.rebuild_all_counts(vault)`
- Task module imports (`agent.tasks.*`) are lazy — scheduler must be importable even before those modules exist
- `start(vault, config)` / `stop()` public API
- On job failure: log error, do not crash the scheduler

---

## Implementation ordering rationale

1. **`pyproject-scaffold` first** — nothing can be imported until the package structure exists and `pip install -e .` succeeds. This is a hard prerequisite for all `pytest` runs.

2. **`models-py` second** — pure data definitions, no imports from other `agent.*` submodules. Every subsequent module imports from `agent.core.models`. Spec and build can begin immediately after scaffold.

3. **`config-py` third** — config model references `models.py` enum types indirectly (through `VaultConfig` + `LLMConfig`). Must be DONE before pipeline, watcher, or scheduler can be tested with real config.

4. **`pipeline-py` fourth** — orchestrator references `models.py` types heavily and reads from `config.py`. Stage modules (`agent.stages.*`) are not yet implemented; lazy imports allow `pipeline.py` to be importable and unit-testable with mocked stages.

5. **`watcher-py` fifth** — requires a runnable pipeline (or at minimum a mockable interface). `config.py` must be DONE for path resolution.

6. **`scheduler-py` last** — wires together task modules that belong to a later section (`Scheduled Tasks`). Can be built and unit-tested with mock task callables; real integration waits for the Scheduled Tasks section.

---

## Excluded (Phase 2 or out of scope)

| Item | Why excluded |
|---|---|
| `AtomNote` model and `atom_id` field | Phase 2 only (REQUIREMENTS §11) |
| `06_ATOMS/` path constant in `ObsidianVault` | Phase 2 |
| `extract_atoms.md` prompt | Phase 2 |
| `agent/main.py` (CLI entry point) | Separate section: `CLI Entry Point` |
| `ObsidianVault` implementation | Separate section: `Vault Layer` |
| All `agent/stages/` implementations | Separate section: `Pipeline Stages` |
| `agent/tasks/outdated_review.py` and `index_updater.py` | Separate section: `Scheduled Tasks` |
| Any LLM provider code | Separate section: `LLM Provider Layer` |
| Web UI / FastAPI dashboard | Phase 2 |
| MS Teams Graph API polling | Phase 2 |
