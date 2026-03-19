# Feature Spec: Pipeline Stages
slug: feature-pipeline-stages
sections_covered: [ProgressTracking/tasks/06_pipeline-stages.md]
arch_sections: [§5 Pipeline Implementation, §6 Stage Implementations, §7 Verbatim Module, §8 Vault Module]

---

## Scope

Implement all `agent/stages/` modules that form the 7-stage processing pipeline.
Two stages are already DONE (`s2_classify.py`, `s4a_summarize.py`); this spec covers
the remaining **7 TODO stages** in implementation order.

The pipeline contract (from `agent/core/pipeline.py`) drives all data shapes:
- Input to each stage is a typed Pydantic model from `agent/core/models.py`
- All LLM calls go through `ProviderFactory` / `AbstractLLMProvider`
- All vault writes go through `ObsidianVault` exclusively
- Async throughout — `anyio`-compatible coroutines (`async def run(...)`)

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `agent/stages/s1_normalize.py` | `s1-normalize` | adapters (DONE), models (DONE) | stages |
| 2 | `agent/stages/s3_dates.py` | `s3-dates` | models (DONE), s2_classify (DONE) | stages |
| 3 | `agent/stages/s4b_verbatim.py` ★ | `s4b-verbatim` | models (DONE), ProviderFactory (DONE), prompts/extract_verbatim.md (DONE), vault/verbatim.py (DONE) | stages |
| 4 | `agent/stages/s6b_index_update.py` ★ | `s6b-index-update` | vault.py (DONE) — `ensure_domain_index`, `increment_index_count` | stages |
| 5 | `agent/stages/s6a_write.py` | `s6a-write` | vault.py (DONE), templates.py (DONE), vault/verbatim.py (DONE), models (DONE) | stages |
| 6 | `agent/stages/s5_deduplicate.py` | `s5-deduplicate` | models (DONE), **vector/store.py (TODO — build Vector Store section first)** | stages |
| 7 | `agent/stages/s7_archive.py` | `s7-archive` | vault.py (DONE), **vault/archive.py (TODO — build Vault Layer archive.py first)** | stages |

> Modules 6–7 are sequenced last because they have cross-section blocking dependencies.
> Do not start `s5-deduplicate` or `s7-archive` until those dependencies are DONE.

---

## Cross-cutting constraints

| Constraint | Applies to |
|---|---|
| `async def run(...)` signature — all stages are awaitable coroutines | all |
| All LLM calls via `ProviderFactory` / `AbstractLLMProvider.chat()` only — no direct HTTP | s4b |
| All vault writes via `ObsidianVault` methods only — never raw `Path.write_text` | s6a, s6b, s7 |
| `anyio` for async, not `asyncio` directly | all |
| Pydantic v2 models for all I/O; no plain `dict` as stage output | all |
| `NormalizedItem.raw_id` is set by s1 and propagated unchanged through all stages | all |
| `VerbatimBlock.content` must be byte-identical to source passage — never paraphrased | s4b |
| Maximum 10 verbatim blocks per note (`config.vault.max_verbatim_blocks_per_note`) | s4b |
| `staleness_risk` defaults by type: `code/prompt → high`, `quote → low`, `transcript → medium` | s4b |
| `_index.md` body MUST NOT be modified — only frontmatter (`note_count`, `last_updated`) | s6b |
| `ensure_domain_index` must be called before `increment_index_count` (idempotent create-then-update) | s6b |
| Stages must be stateless — no module-level mutable state | all |
| Python 3.11+ only — no `typing.Union`, use `X \| Y` syntax | all |
| No hardcoded vault paths — use `ObsidianVault` path helpers | all |

---

## Stage-by-stage I/O contract

### s1_normalize
- **Input**: `raw_path: Path`, `config: AgentConfig`
- **Output**: `NormalizedItem`
- Selects the correct adapter by file extension / MIME sniff, calls `adapter.run(raw_path)`, writes `raw_[id].md` to `01_PROCESSING/to_classify/`, returns `NormalizedItem` with `raw_file_path` set.
- No LLM. No vault writes beyond the staging file.

### s3_dates
- **Input**: `item: NormalizedItem`, `classification: ClassificationResult`
- **Output**: `NormalizedItem` (with `source_date` and `review_after` populated on a sidecar dict — see arch §6 Stage 3)
- Date priority: source metadata → URL date pattern → `file_mtime`.
- Computes `review_after` from `content_age` rules (§3.1 REQUIREMENTS).
- No LLM. No vault writes.

### s4b_verbatim ★
- **Input**: `item: NormalizedItem`, `llm: AbstractLLMProvider`, `config: AgentConfig`
- **Output**: `list[VerbatimBlock]`
- Calls `extract_verbatim` prompt via `llm.chat()`; caps text at 8 000 chars.
- On LLM failure: logs warning, returns `[]` (never raises — pipeline continues).
- Trims to `max_blocks`; assigns `staleness_risk` from defaults if not in LLM response.
- Does NOT call `render_verbatim_block` — that happens in s6a.

### s6b_index_update ★
- **Input**: `classification: ClassificationResult`, `vault: ObsidianVault`
- **Output**: `None`
- Resolves subdomain path from `classification.domain_path` (e.g. `"professional_dev/ai_tools"`).
- Calls `vault.ensure_domain_index(...)` then `vault.increment_index_count(...)` for subdomain index, then repeats for parent domain index.
- If `domain_path` has no subdomain component (single-segment), only domain index is updated.

### s6a_write
- **Input**: `item: NormalizedItem`, `classification: ClassificationResult`, `summary: SummaryResult`, `merge_result: MergeResult`, `vault: ObsidianVault`, `config: AgentConfig`
- **Output**: `WriteResult` (source_note path, knowledge_note path(s))
- Renders source note via `templates.render_template("source_*.md", ctx)`.
- Appends rendered verbatim blocks (via `render_verbatim_block`) to note body.
- Writes source note to `01_PROCESSING/` (or directly to `02_KNOWLEDGE/` on merge-approved path).
- Creates/appends knowledge note(s) in `02_KNOWLEDGE/[domain_path]/`.
- Updates `verbatim_count` and `verbatim_types` in frontmatter after writing.

### s5_deduplicate
- **Input**: `item: NormalizedItem`, `classification: ClassificationResult`, `summary: SummaryResult`, `vault: ObsidianVault`, `llm: AbstractLLMProvider`
- **Output**: `MergeResult` (route_to_merge: bool, candidate_path: str | None, similarity_score: float)
- Calls `vector_store.similarity_search(summary.summary, top_k=3)`.
- Routes to `to_merge/` if top similarity ≥ `config.merge_threshold` (default 0.90).
- **Blocked** until `agent/vector/store.py` is DONE.

### s7_archive
- **Input**: `raw_path: Path`, `item: NormalizedItem`, `vault: ObsidianVault`
- **Output**: `Path` (archive destination)
- Moves processed source file to `05_ARCHIVE/YYYY/MM/` via `vault.archive_file()`.
- **Blocked** until `agent/vault/archive.py` is DONE.

---

## Implementation ordering rationale

1. **s1_normalize first** — it is the pipeline entry point; all other stages need a `NormalizedItem`. Has zero external blockers.
2. **s3_dates second** — pure date logic; no LLM; completes the enrichment chain before summarization.
3. **s4b_verbatim third** — all its dependencies (verbatim.py, extract_verbatim.md, ProviderFactory) are already DONE. Builds on the verbatim-contract skill.
4. **s6b_index_update fourth** — the simplest write stage; only touches frontmatter; validates the vault index integration before the full note-write in s6a.
5. **s6a_write fifth** — most complex write stage; benefits from s6b being verified first; uses all vault/template/verbatim primitives.
6. **s5_deduplicate sixth** — held until Vector Store section is complete.
7. **s7_archive last** — held until `vault/archive.py` is complete.

---

## Excluded (Phase 2 or out of scope)

| Item | Reason |
|---|---|
| `06_ATOMS/` writes in s6a | Phase 2 — `AtomNote` not in scope |
| `extract_atoms.md` prompt call | Phase 2 |
| Bi-directional link proposals | Phase 2 |
| `model_target` superseded detection in s4b | Phase 2 (prompt version migration tracking) |
| Web UI / FastAPI status updates from stages | Phase 2 |
| MS Teams Graph API polling | Phase 2 |
| s2_classify.py | Already DONE — not re-implemented |
| s4a_summarize.py | Already DONE — not re-implemented |
