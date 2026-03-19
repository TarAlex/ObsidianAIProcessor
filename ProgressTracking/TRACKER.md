# Dev Tracker — Obsidian KB Inbox Processor
# Updated by `/dev-tracker` skill only.
# Status: TODO | IN_PROGRESS | DONE | BLOCKED | PHASE_2

---

## Foundations

- [ DONE ]  pyproject.toml + project scaffold  → spec: ProgressTracking/specs/pyproject-scaffold.md
- [ DONE ]  agent/core/config.py  (YAML + .env loading, Config Pydantic model)  → spec: ProgressTracking/specs/config-py.md
- [ DONE ]  agent/core/models.py  (all v1.1 models: NormalizedItem, ClassificationResult,
             SummaryResult, VerbatimBlock, VerbatimType, StatenessRisk, ProcessingStatus)  → spec: ProgressTracking/specs/models-py.md
- [ DONE ]  agent/core/pipeline.py  (stage orchestrator, error routing to to_review/)  → spec: ProgressTracking/specs/pipeline-py.md
- [ DONE ]  agent/core/watcher.py  (watchdog InboxWatcher)  → spec: ProgressTracking/specs/watcher-py.md
- [ DONE ]  agent/core/scheduler.py  (APScheduler: weekly outdated-review, daily index-rebuild)  → spec: ProgressTracking/specs/scheduler-py.md

---

## Source Adapters  (agent/adapters/)

- [ DONE ]  base.py  (BaseAdapter ABC → NormalizedItem)  → spec: ProgressTracking/specs/adapters-base.md
- [ DONE ]  markdown_adapter.py  (MarkdownAdapter: .md/.txt → NormalizedItem; no LLM; anyio; frontmatter)  → spec: ProgressTracking/specs/markdown-adapter.md
- [ DONE ]  web_adapter.py  (httpx + markdownify)  → spec: ProgressTracking/specs/web-adapter.md
- [ DONE ]  pdf_adapter.py  (pymupdf)  → spec: ProgressTracking/specs/pdf-adapter.md
- [ DONE ]  youtube_adapter.py  (youtube-transcript-api)  → spec: ProgressTracking/specs/youtube-adapter.md
- [ DONE ]  audio_adapter.py  (openai-whisper)  → spec: ProgressTracking/specs/audio-adapter.md
- [ DONE ]  teams_adapter.py  (VTT WebVTT transcript parser; Phase 1 local only)  → spec: ProgressTracking/specs/teams-adapter.md

---

## LLM Provider Layer  (agent/llm/)

- [ DONE ]  base.py  (BaseProvider ABC: complete(prompt_name, ctx) → str)  → spec: ProgressTracking/specs/llm-base.md
- [ DONE ]  prompt_loader.py  (reads prompts/*.md, caches)  → spec: ProgressTracking/specs/prompt-loader.md
- [ IN_PROGRESS ]  ollama_provider.py  (default / privacy-first)  → spec: ProgressTracking/specs/ollama-provider.md
- [ DONE ]  lmstudio_provider.py  → spec: ProgressTracking/specs/lmstudio-provider.md
- [ DONE ]  openai_provider.py  → spec: ProgressTracking/specs/openai-provider.md
- [ DONE ]  anthropic_provider.py  → spec: ProgressTracking/specs/anthropic-provider.md
- [ DONE ]  provider_factory.py  (registry + env-driven selection)  → spec: ProgressTracking/specs/provider-factory.md

---

## Tool Prompt Files  (prompts/)
# These are TEXT FILES the tool loads at runtime — the prompt-author skill writes them.

- [ DONE ]  prompts/classify.md  → spec: ProgressTracking/specs/prompt-classify.md
- [ DONE ]  prompts/summarize.md  → spec: ProgressTracking/specs/prompt-summarize.md
- [ DONE ]  prompts/extract_verbatim.md  ★  (includes Appendix A decision tree)  → spec: ProgressTracking/specs/prompt-extract_verbatim.md
- [ DONE ]  prompts/extract_entities.md  → spec: ProgressTracking/specs/prompt-extract_entities.md
- [ DONE ]  prompts/suggest_tags.md  → spec: ProgressTracking/specs/prompt-suggest_tags.md

---

## Vault Layer  (agent/vault/)

- [ DONE ]  vault.py  (ObsidianVault: read_note, write_note, ensure_domain_index,
             update_domain_index, path helpers)  → spec: ProgressTracking/specs/vault-py.md
- [ DONE ]  note.py  (frontmatter parse/render — python-frontmatter)  → spec: ProgressTracking/specs/note-py.md
- [ DONE ]  verbatim.py  ★  (render_verbatim_block, parse_verbatim_blocks — round-trip lossless)  → spec: ProgressTracking/specs/vault-verbatim.md
- [ DONE ]  templates.py  (Jinja2 template loader from _AI_META/templates/)  → spec: ProgressTracking/specs/templates-py.md
- [ DONE ]  references.py  (REFERENCES/ CRUD: people, work projects, personal projects)  → spec: ProgressTracking/specs/references-py.md
- [ DONE ]  archive.py  → spec: ProgressTracking/specs/archive-py.md

---

## Pipeline Stages  (agent/stages/)

- [ DONE ]  s1_normalize.py  → spec: ProgressTracking/specs/s1-normalize.md
- [ IN_PROGRESS ]  s2_classify.py  (uses prompts/classify.md via ProviderFactory)  → spec: ProgressTracking/specs/s2-classify.md
- [ DONE ]  s3_dates.py  → spec: ProgressTracking/specs/s3-dates.md
- [ IN_PROGRESS ]  s4a_summarize.py  (uses prompts/summarize.md)  → spec: ProgressTracking/specs/s4a-summarize.md
- [ IN_PROGRESS ]  s4b_verbatim.py  ★  (uses prompts/extract_verbatim.md; max 10 blocks)  → spec: ProgressTracking/specs/s4b-verbatim.md
- [ IN_PROGRESS ]  s5_deduplicate.py  (ChromaDB similarity)  → spec: ProgressTracking/specs/s5-deduplicate.md
- [ IN_PROGRESS ]  s6a_write.py  (Jinja2 templates → vault notes)  → spec: ProgressTracking/specs/s6a-write.md
- [ TODO ]  s6b_index_update.py  ★  (ensure_domain_index + increment + parent rollup)
- [ DONE ]  s7_archive.py

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
- [ DONE ]  tests/unit/test_s3_dates.py
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
