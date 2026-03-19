# Dev Tracker — Obsidian KB Inbox Processor
# Updated by `/dev-tracker` skill only.
# Status: TODO | IN_PROGRESS | DONE | BLOCKED | PHASE_2

---

## Foundations

- [ DONE ]  pyproject.toml + project scaffold  → spec: ProgressTracking/specs/pyproject-scaffold.md
- [ IN_PROGRESS ]  agent/core/config.py  (YAML + .env loading, Config Pydantic model)  → spec: ProgressTracking/specs/config-py.md
- [ IN_PROGRESS ]  agent/core/models.py  (all v1.1 models: NormalizedItem, ClassificationResult,
             SummaryResult, VerbatimBlock, VerbatimType, StatenessRisk, ProcessingStatus)  → spec: ProgressTracking/specs/models-py.md
- [ TODO ]  agent/core/pipeline.py  (stage orchestrator, error routing to to_review/)
- [ TODO ]  agent/core/watcher.py  (watchdog InboxWatcher)
- [ TODO ]  agent/core/scheduler.py  (APScheduler: weekly outdated-review, daily index-rebuild)

---

## Source Adapters  (agent/adapters/)

- [ TODO ]  base.py  (BaseAdapter ABC → NormalizedItem)
- [ TODO ]  markdown_adapter.py
- [ TODO ]  web_adapter.py  (httpx + markdownify)
- [ TODO ]  pdf_adapter.py  (pymupdf)
- [ TODO ]  youtube_adapter.py  (youtube-transcript-api)
- [ TODO ]  audio_adapter.py  (openai-whisper)
- [ TODO ]  teams_adapter.py

---

## LLM Provider Layer  (agent/llm/)

- [ TODO ]  base.py  (BaseProvider ABC: complete(prompt_name, ctx) → str)
- [ TODO ]  prompt_loader.py  (reads prompts/*.md, caches)
- [ TODO ]  ollama_provider.py  (default / privacy-first)
- [ TODO ]  lmstudio_provider.py
- [ TODO ]  openai_provider.py
- [ TODO ]  anthropic_provider.py
- [ TODO ]  provider_factory.py  (registry + env-driven selection)

---

## Tool Prompt Files  (prompts/)
# These are TEXT FILES the tool loads at runtime — the prompt-author skill writes them.

- [ TODO ]  prompts/classify.md
- [ TODO ]  prompts/summarize.md
- [ TODO ]  prompts/extract_verbatim.md  ★  (includes Appendix A decision tree)
- [ TODO ]  prompts/extract_entities.md
- [ TODO ]  prompts/suggest_tags.md

---

## Vault Layer  (agent/vault/)

- [ TODO ]  vault.py  (ObsidianVault: read_note, write_note, ensure_domain_index,
             update_domain_index, path helpers)
- [ TODO ]  note.py  (frontmatter parse/render — python-frontmatter)
- [ TODO ]  verbatim.py  ★  (render_verbatim_block, parse_verbatim_blocks — round-trip lossless)
- [ TODO ]  templates.py  (Jinja2 template loader from _AI_META/templates/)
- [ TODO ]  references.py  (REFERENCES/ CRUD: people, work projects, personal projects)
- [ TODO ]  archive.py

---

## Pipeline Stages  (agent/stages/)

- [ TODO ]  s1_normalize.py
- [ TODO ]  s2_classify.py  (uses prompts/classify.md via ProviderFactory)
- [ TODO ]  s3_dates.py
- [ TODO ]  s4a_summarize.py  (uses prompts/summarize.md)
- [ TODO ]  s4b_verbatim.py  ★  (uses prompts/extract_verbatim.md; max 10 blocks)
- [ TODO ]  s5_deduplicate.py  (ChromaDB similarity)
- [ TODO ]  s6a_write.py  (Jinja2 templates → vault notes)
- [ TODO ]  s6b_index_update.py  ★  (ensure_domain_index + increment + parent rollup)
- [ TODO ]  s7_archive.py

---

## Scheduled Tasks  (agent/tasks/)

- [ TODO ]  outdated_review.py  (weekly scan: stale notes + stale verbatim blocks)
- [ TODO ]  index_updater.py  ★  (daily rebuild_all_counts from scratch)
- [ TODO ]  reference_linker.py

---

## Vector Store  (agent/vector/)

- [ TODO ]  embedder.py
- [ TODO ]  store.py  (ChromaDB: add, similarity_search, delete)

---

## CLI Entry Point

- [ TODO ]  agent/main.py  (click: run, process-file, rebuild-indexes, outdated-review)

---

## Setup Scripts

- [ TODO ]  scripts/setup_vault.py  (creates all _index.md from templates on first run)
- [ TODO ]  scripts/reindex.py

---

## Tests

- [ TODO ]  tests/unit/test_models.py
- [ TODO ]  tests/unit/test_vault.py
- [ TODO ]  tests/unit/test_verbatim.py  ★  (round-trip lossless contract)
- [ TODO ]  tests/unit/test_index_update.py  ★
- [ TODO ]  tests/unit/test_vector_store.py
- [ TODO ]  tests/unit/test_s3_dates.py
- [ TODO ]  tests/unit/test_reference_linker.py
- [ TODO ]  tests/integration/test_pipeline_youtube.py
- [ TODO ]  tests/integration/test_pipeline_pdf.py
- [ TODO ]  tests/integration/test_pipeline_verbatim.py  ★
- [ TODO ]  tests/integration/test_pipeline_index.py  ★
- [ TODO ]  tests/integration/test_llm_ollama.py
- [ TODO ]  tests/integration/test_sync_lock.py
- [ TODO ]  tests/fixtures/  (sample_youtube_transcript.md, sample_article.html,
             sample_pdf_extracted.txt, sample_code_heavy.md ★, sample_prompt_doc.md ★,
             vault_structure/)

---

## Phase 2 (not started — do not implement)

- [ PHASE_2 ]  06_ATOMS/ support in vault layer
- [ PHASE_2 ]  extract_atoms.md prompt
- [ PHASE_2 ]  AtomNote Pydantic model
- [ PHASE_2 ]  MOC atom-level content in _index.md
- [ PHASE_2 ]  Bi-directional link proposals
- [ PHASE_2 ]  FastAPI Web UI
- [ PHASE_2 ]  MS Teams Graph API polling
- [ PHASE_2 ]  Prompt version migration tracking (model_target superseded detection)

---

## Blocked

_(none)_
