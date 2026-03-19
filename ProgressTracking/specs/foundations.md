# Spec: Foundations (pyproject + agent/core)

slug: foundations
layer: core
phase: 1
arch_section: §1, §2, §3, §5, §10, §16

## Problem statement

The pipeline, watcher, and scheduler need a runnable project scaffold, a single source of configuration, and shared Pydantic models. Without this layer, no stage or adapter can be implemented or tested in isolation.

## Module contract

Deliverables are five modules under `agent/core/` plus project metadata; they do not form a single callable with one Input/Output. Contract per component:

| Component | Input | Output / side effect |
|-----------|--------|----------------------|
| config.py | Path or str (config path), env vars | `AgentConfig` instance |
| models.py | — | Pydantic models (no I/O) |
| pipeline.py | `Path` (raw file), `AgentConfig`, `ObsidianVault` | `ProcessingRecord` (async) |
| watcher.py | `AgentConfig`, callback | Starts watchdog observer; invokes callback on inbox events |
| scheduler.py | `AgentConfig`, vault, task refs | APScheduler with weekly/daily jobs; no direct pipeline call |

Pipeline contract in detail:

- **Input:** `Path` to a single raw file in (or destined for) the inbox.
- **Output:** `ProcessingRecord` with at least `raw_id`, `source_type`, `input_path`, `output_path`, `archive_path`, `domain`, `domain_path`, `confidence`, `verbatim_count`, `llm_provider`, `llm_model`, `processing_time_s`, `timestamp`, `errors`.
- Pipeline MUST route to `vault.move_to_review(raw_path, ...)` when classification confidence &lt; `config.review_threshold`; MUST NOT write to vault paths directly except via `ObsidianVault` (see vault write guard).
- Pipeline stages are stubs or raise “not implemented” until their layers exist; pipeline orchestration order and error handling are implemented.

## Key implementation notes

1. **pyproject.toml**
   - Python `>=3.11`.
   - Dependencies per ARCHITECTURE §16: pydantic≥2, pyyaml, click, httpx, python-dotenv, watchdog, apscheduler, openai, anthropic, pymupdf, markdownify, youtube-transcript-api, openai-whisper, chromadb, jinja2, anyio. No hardcoded vault paths or API keys.
   - Package layout: `agent` as the main package (flat under `agent/` with `core`, `adapters`, `llm`, `vault`, `stages`, `tasks`, `vector`).

2. **config.py**
   - Load YAML from path (default `_AI_META/agent-config.yaml` relative to vault root or cwd); override with env vars where specified (e.g. API keys via `api_key_env`).
   - Expose a single Pydantic model `AgentConfig` matching ARCHITECTURE §10: `vault` (root, review_threshold, merge_threshold, related_threshold, max_verbatim_blocks_per_note, verbatim_high_risk_age), `llm` (default_provider, review_threshold, fallback_chain, providers, task_routing), `whisper`, `scheduler` (poll_interval_minutes, outdated_review_day, outdated_review_hour), `sync`.
   - `config.review_threshold` used by pipeline for classification routing must be available (e.g. from `vault.review_threshold` or `llm.review_threshold`; pick one and document). `domains` and `tag_taxonomy_summary` can be loaded from vault meta files and attached to config or passed separately; spec defers to “sufficient for s2_classify to receive domains + tag_taxonomy_summary”.

3. **models.py**
   - Implement all v1.1 enums and models from ARCHITECTURE §3: `SourceType`, `ContentAge`, `ProcessingStatus`, `StatenessRisk`, `VerbatimType`, `VerbatimBlock`, `NormalizedItem`, `ClassificationResult`, `SummaryResult`, `DomainIndexEntry`, `ProcessingRecord`, `PersonReference`, `ProjectReference`. Use Pydantic v2 and `field(default_factory=...)` where needed. No Phase 2–only models (e.g. AtomNote).

4. **pipeline.py**
   - `KnowledgePipeline(config, vault)` with `async def process_file(self, raw_path: Path) -> ProcessingRecord` and `async def process_batch(self, paths: list[Path]) -> list[ProcessingRecord]`.
   - Follow stage order: S1 normalize → S2 classify → (if confidence &lt; threshold → move_to_review, return) → S3 dates → S4a summarize → S4b verbatim → S5 deduplicate → (if merge → move_to_merge, return) → S6a write → S6b index update → S7 archive. Append to vault log and set `processing_time_s` in `finally`.
   - Import stages as modules; stages may be stubs that raise or return minimal data until implemented. Pipeline MUST call `anyio` or project-standard async (per AGENTS: anyio for async). `_wait_for_sync_unlock` with configurable timeout.

5. **watcher.py**
   - InboxWatcher or equivalent: watch `vault.inbox` (from config vault.root) with `watchdog`; on created/moved-in events, invoke a callback (e.g. list of Paths). Do not run the full pipeline inside the watcher; delegate to caller/scheduler. Respect `sync.check_lock_before_write` / `sync.sync_poll_interval_s` if waiting before enqueueing.

6. **scheduler.py**
   - APScheduler: periodic poll of inbox (interval from `scheduler.poll_interval_minutes`) and weekly job for outdated review on `scheduler.outdated_review_day` / `outdated_review_hour`. Daily job for index rebuild. Jobs receive vault and config; they call into `agent.tasks` (outdated_review, index_updater) when those exist. No Phase 2 logic.

## Data model changes

None beyond implementing ARCHITECTURE §3 in `models.py`. Config model is new and lives in `config.py` (or a small `config_models.py` if preferred).

## LLM prompt file needed

None in this layer.

## Tests required

- **unit:** `tests/unit/test_models.py` — (de)serialization of NormalizedItem, ClassificationResult, SummaryResult, VerbatimBlock, ProcessingRecord; enum values.
- **unit:** `tests/unit/test_config.py` — load from a fixture YAML + env override for one key; `AgentConfig` has expected attributes.
- **unit:** `tests/unit/test_pipeline.py` — pipeline returns a `ProcessingRecord` with required fields when given a stub vault and stub stages; low-confidence path calls `move_to_review` and does not call write.
- **integration:** Optional `tests/integration/test_pipeline_smoke.py` — one file through pipeline with stub/mock LLM and real temp vault dir; only to verify wiring (can be added later).

## Explicitly out of scope

- Implementing real stage logic (s1–s7); stubs or “not implemented” are acceptable.
- Vault implementation (vault is a dependency; interface only or minimal mock).
- LLM provider implementation (pipeline uses `get_provider(config)`; factory can raise until llm layer is built).
- Phase 2 features (atoms, MOC content, web UI, etc.).
- `.env.example` content beyond placeholders (no real keys).

## Open questions

- None. Proceed with `review_threshold` taken from `config.vault.review_threshold` and exposed as `config.review_threshold` for pipeline use.
