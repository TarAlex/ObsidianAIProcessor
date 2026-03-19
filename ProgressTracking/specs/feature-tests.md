# Feature Spec: Tests
slug: feature-tests
sections_covered: [ProgressTracking/tasks/11_tests.md]
arch_sections: [§3, §7, §8, §12, §13, §15, §17]

---

## Scope

Complete the Tests section as listed in TRACKER.md and defined in `ProgressTracking/tasks/11_tests.md`.

The test suite has three tiers:

1. **Fixtures** — static files and vault scaffold used by integration tests.
   `tests/fixtures/` is partially populated (has `.gitkeep`, `sample_note.md`,
   `sample_article.html`, `sample_youtube_transcript.md`, `sample_teams_transcript.vtt`).
   Still missing: `sample_pdf_extracted.txt`, `sample_code_heavy.md` ★,
   `sample_prompt_doc.md` ★, `vault_structure/`.

2. **Unit tests** — exercise individual modules in isolation; most files already exist on disk
   with real test bodies (19–30 tests each) but are still marked TODO in TRACKER (created as
   a side-effect of module /build sessions). They need /review → /done cycles, not
   re-implementation.

3. **Integration tests** — exercise the full pipeline end-to-end with real (or minimal mock)
   LLM calls and on-disk vault structures. Some files exist as stubs (2–4 tests); three files
   are completely absent: `test_pipeline_pdf.py`, `test_pipeline_verbatim.py`,
   `test_sync_lock.py`.

**Out of scope:** `tests/unit/test_s3_dates.py` and `tests/unit/test_reference_linker.py`
are already DONE. `tests/unit/test_main.py`, `tests/unit/test_setup_vault.py`, and
`tests/unit/test_reindex.py` are untracked new files belonging to the CLI/Setup Scripts
sections — they are closed under those sections' /done cycles, not here.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | tests/fixtures/ — complete the fixture set | `test-fixtures` | none | tests/fixtures |
| 2 | tests/unit/test_models.py | `test-models` | agent/core/models.py (DONE) | unit |
| 3 | tests/unit/test_vault.py | `test-vault` | agent/vault/vault.py (DONE) | unit |
| 4 | tests/unit/test_verbatim.py ★ | `test-verbatim` | agent/vault/verbatim.py (DONE) | unit |
| 5 | tests/unit/test_index_update.py ★ | `test-index-update` | agent/stages/s6b_index_update.py (IN_PROGRESS), agent/tasks/index_updater.py (IN_PROGRESS) | unit |
| 6 | tests/unit/test_vector_store.py | `test-vector-store` | agent/vector/store.py (IN_PROGRESS) | unit |
| 7 | tests/integration/test_pipeline_youtube.py | `test-pipeline-youtube` | all pipeline stages, test-fixtures | integration |
| 8 | tests/integration/test_pipeline_pdf.py | `test-pipeline-pdf` | all pipeline stages, test-fixtures | integration |
| 9 | tests/integration/test_pipeline_verbatim.py ★ | `test-pipeline-verbatim` | s4b_verbatim.py, s6a_write.py, verbatim.py, test-fixtures | integration |
| 10 | tests/integration/test_pipeline_index.py ★ | `test-pipeline-index` | s6b_index_update.py, index_updater.py, vault.py, test-fixtures | integration |
| 11 | tests/integration/test_llm_ollama.py | `test-llm-ollama` | ollama_provider.py (IN_PROGRESS), prompt_loader.py (DONE) | integration |
| 12 | tests/integration/test_sync_lock.py | `test-sync-lock` | vault.py (DONE), scheduler.py (DONE) | integration |

---

## Cross-cutting constraints

- **No inline fixture data** — all sample content lives in `tests/fixtures/`; tests load from there.
- **anyio** — async tests use `anyio.from_thread` or `@pytest.mark.anyio`; never raw `asyncio`.
- **Verbatim contract** — `test-verbatim` must load `.cursor/skills/verbatim-contract/SKILL.md` and prove round-trip losslessness (render → parse → equal); content byte-identical.
- **Index contract** — `test-index-update` must load `.cursor/skills/index-update-contract/SKILL.md` and verify `rebuild_all_counts` corrects a manually-inflated `note_count`.
- **No hardcoded vault paths** — all tests use `tmp_path` (pytest fixture) or `tests/fixtures/vault_structure/` as vault root.
- **Unit tests mock LLM calls** — `ProviderFactory` is monkeypatched; unit tests never touch real Ollama/OpenAI endpoints.
- **Integration LLM tests** — `test_llm_ollama.py` (and similar) are marked `@pytest.mark.integration` and skipped by default (`pytest -m "not integration"`).
- **Pydantic v2** — all model instantiations use v2 API; no `.dict()`, use `.model_dump()`.
- **Windows path safety** — use `pathlib.Path` / `tmp_path`; avoid OS-specific separators in fixture data.
- **pytest-anyio plugin required** — already in pyproject.toml dev deps.
- **Existing files noted as TODO** — modules 2–6 and parts of 7, 10, 11 have existing implementations; /plan sessions must inspect current content before deciding whether to augment or accept as-is.

---

## Implementation ordering rationale

1. **Fixtures first (#1)** — integration tests (#7–#12) cannot run without
   `sample_pdf_extracted.txt`, `sample_code_heavy.md`, `sample_prompt_doc.md`, and
   `vault_structure/`. Fixtures are dependency-free and unblock everything else.

2. **Unit tests (#2–#6) in dependency order** — models → vault → verbatim → index_update →
   vector_store. Each builds on the stable DONE module beneath it. These files largely exist
   but need formal /review cycles; /plan sessions should confirm coverage before closing.

3. **Integration tests (#7–#12) last** — require both fixtures AND all relevant pipeline stages
   to be at least IN_PROGRESS or DONE. Verbatim (#9) and index (#10) integration tests are
   highest-value (★); prioritize them over the simpler pipeline adapter tests if parallel
   sessions are running.

4. **test_pipeline_pdf (#8) before test_pipeline_verbatim (#9)** — verbatim integration test
   describes a PDF source that produces verbatim blocks; the PDF pipeline fixture scaffolded in
   #8 is reused in #9.

---

## Excluded (Phase 2 or out of scope)

- `06_ATOMS/` test coverage — Phase 2 (`AtomNote`, atom extraction pipeline).
- `test_pipeline_audio.py` — already DONE in audio adapter section.
- `test_pipeline_markdown.py` — already DONE in markdown adapter section.
- `test_pipeline_teams.py` — already DONE in teams adapter section.
- `tests/unit/test_main.py`, `tests/unit/test_setup_vault.py`, `tests/unit/test_reindex.py` — new untracked files; belong to CLI/Setup Scripts /done cycles.
- `tests/unit/test_outdated_review.py`, `tests/unit/test_index_updater.py` — created alongside their modules in Scheduled Tasks section; close under that section's /done cycle.
- MS Teams Graph API integration test — Phase 2.
- FastAPI web UI tests — Phase 2.
