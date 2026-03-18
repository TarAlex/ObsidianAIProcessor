# Task files by TRACKER section

Each file below contains:

1. **Task list** — checklist of items from [../TRACKER.md](../TRACKER.md) for that section.
2. **Implementation prompts** — /plan and /build prompts per task, following [../feature-initiation-prompts.md](../feature-initiation-prompts.md).

Use the core loop: **Session A** `/plan` → **Session B** `/build SLUG` → **Session C** `/review` + `/done`. Run `/clear` between sessions.

| # | Section | File | Notes |
|---|---------|------|--------|
| 01 | Foundations | [01_foundations.md](01_foundations.md) | pyproject, config, models, pipeline, watcher, scheduler |
| 02 | Source Adapters | [02_source-adapters.md](02_source-adapters.md) | base + markdown, web, pdf, youtube, audio, teams |
| 03 | LLM Provider Layer | [03_llm-provider-layer.md](03_llm-provider-layer.md) | base, prompt_loader, ollama, lmstudio, openai, anthropic, provider_factory |
| 04 | Tool Prompt Files | [04_tool-prompt-files.md](04_tool-prompt-files.md) | Use `/dev-prompt-author` for prompts/*.md |
| 05 | Vault Layer | [05_vault-layer.md](05_vault-layer.md) | vault, note, verbatim, templates, references, archive |
| 06 | Pipeline Stages | [06_pipeline-stages.md](06_pipeline-stages.md) | s1–s7 |
| 07 | Scheduled Tasks | [07_scheduled-tasks.md](07_scheduled-tasks.md) | outdated_review, index_updater, reference_linker |
| 08 | Vector Store | [08_vector-store.md](08_vector-store.md) | embedder, store |
| 09 | CLI Entry Point | [09_cli-entry-point.md](09_cli-entry-point.md) | agent/main.py |
| 10 | Setup Scripts | [10_setup-scripts.md](10_setup-scripts.md) | setup_vault, reindex |
| 11 | Tests | [11_tests.md](11_tests.md) | unit + integration + fixtures |

Phase 2 and Blocked sections are not included (see TRACKER.md).
