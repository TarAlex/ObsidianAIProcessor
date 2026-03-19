# Tasks: Tests

Source: [ProgressTracking/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

Implement tests in the same order as implementation: unit tests alongside or immediately after the module; integration tests once pipeline stages exist.

---

## Task list

- [ ] tests/unit/test_models.py
- [ ] tests/unit/test_vault.py
- [ ] tests/unit/test_verbatim.py ★ (round-trip lossless contract)
- [ ] tests/unit/test_index_update.py ★
- [ ] tests/unit/test_vector_store.py
- [ ] tests/unit/test_s3_dates.py
- [ ] tests/unit/test_reference_linker.py
- [ ] tests/integration/test_pipeline_youtube.py
- [ ] tests/integration/test_pipeline_pdf.py
- [ ] tests/integration/test_pipeline_verbatim.py ★
- [ ] tests/integration/test_pipeline_index.py ★
- [ ] tests/integration/test_llm_ollama.py
- [ ] tests/integration/test_sync_lock.py
- [ ] tests/fixtures/ (sample_youtube_transcript.md, sample_article.html, sample_pdf_extracted.txt, sample_code_heavy.md ★, sample_prompt_doc.md ★, vault_structure/)

---

## Implementation prompts

### 1. tests/unit/test_models.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/unit/test_models.py"
- Layer: tests
- Phase: 1
- Depends on: agent/core/models.py (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §3, §17 Testing Strategy

Special constraints:
- Unit tests only; cover all v1.1 models (NormalizedItem, ClassificationResult, SummaryResult, VerbatimBlock, VerbatimType, StatenessRisk, ProcessingStatus); validation, serialization; use fixtures

Output: Write the spec to ProgressTracking/specs/test-models.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/test-models.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §3, §17
3. Read: agent/core/models.py

Then implement tests/unit/test_models.py. Run pytest tests/unit/test_models.py -v before returning.
```

---

### 2. tests/unit/test_vault.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/unit/test_vault.py"
- Layer: tests
- Phase: 1
- Depends on: agent/vault/vault.py (DONE)
- Already done in this layer: test_models

Special constraints:
- Unit tests; mock or temp dir for vault root; test read_note, write_note (atomic), ensure_domain_index (no overwrite), update_domain_index (frontmatter only)

Output: Write the spec to ProgressTracking/specs/test-vault.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec. Read agent/vault/vault.py and docs/ARCHITECTURE.md §8. Implement tests/unit/test_vault.py. Use tests/fixtures/vault_structure/ or temp dir. Run pytest before returning.
```

---

### 3. tests/unit/test_verbatim.py ★

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/unit/test_verbatim.py ★ (round-trip lossless contract)"
- Layer: tests
- Phase: 1
- Depends on: agent/vault/verbatim.py (DONE)
- Already done in this layer: test_models, test_vault

Special constraints:
- Round-trip: render_verbatim_block(block) → parse_verbatim_blocks(output)[0] equals block; content byte-identical; all VerbatimType values; malformed header skipped silently; load verbatim-contract skill

Output: Write the spec to ProgressTracking/specs/test-verbatim.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec. Read agent/vault/verbatim.py, docs/ARCHITECTURE.md §7. Load .cursor/skills/verbatim-contract/SKILL.md. Implement tests/unit/test_verbatim.py: round-trip for all types, byte-identical content, malformed skip. Run pytest before returning.
```

---

### 4. tests/unit/test_index_update.py ★

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/unit/test_index_update.py ★"
- Layer: tests
- Phase: 1
- Depends on: agent/stages/s6b_index_update.py (DONE), agent/tasks/index_updater.py (DONE)
- Already done in this layer: test_models, test_vault, test_verbatim

Special constraints:
- rebuild_all_counts() corrects manual note_count; write 3 notes to professional_dev/ai_tools/ → subdomain and domain _index.md note_count == 3; load index-update-contract skill

Output: Write the spec to ProgressTracking/specs/test-index_update.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec. Read agent/stages/s6b_index_update.py, agent/tasks/index_updater.py. Load .cursor/skills/index-update-contract/SKILL.md. Implement tests/unit/test_index_update.py. Run pytest before returning.
```

---

### 5. tests/unit/test_vector_store.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/unit/test_vector_store.py"
- Layer: tests
- Phase: 1
- Depends on: agent/vector/store.py (DONE)
- Already done in this layer: (other unit tests)

Special constraints:
- Unit tests for add, similarity_search, delete; use temp or in-memory ChromaDB

Output: Write the spec to ProgressTracking/specs/test-vector_store.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement tests/unit/test_vector_store.py. Read agent/vector/store.py. Run pytest before returning.
```

---

### 6. tests/unit/test_s3_dates.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/unit/test_s3_dates.py"
- Layer: tests
- Phase: 1
- Depends on: agent/stages/s3_dates.py (DONE)
- Already done in this layer: (other unit tests)

Special constraints:
- Unit tests for Stage 3 date extraction; ClassificationResult → dated NormalizedItem

Output: Write the spec to ProgressTracking/specs/test-s3_dates.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement tests/unit/test_s3_dates.py. Read agent/stages/s3_dates.py. Run pytest before returning.
```

---

### 7. tests/unit/test_reference_linker.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/unit/test_reference_linker.py"
- Layer: tests
- Phase: 1
- Depends on: agent/tasks/reference_linker.py (DONE)
- Already done in this layer: (other unit tests)

Special constraints:
- Unit tests for reference linking; mock vault/references

Output: Write the spec to ProgressTracking/specs/test-reference_linker.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement tests/unit/test_reference_linker.py. Read agent/tasks/reference_linker.py. Run pytest before returning.
```

---

### 8–13. Integration tests (test_pipeline_*, test_llm_ollama, test_sync_lock)

**/plan session** (per test file)

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/integration/test_[name].py"
- Layer: tests (integration)
- Phase: 1
- Depends on: corresponding pipeline stage or LLM/vault (DONE)
- Already done in this layer: (unit tests, other integration tests)

Special constraints:
- Use tests/fixtures/vault_structure/; pipeline tests use real or mocked LLM per requirements; test_llm_ollama validates prompt output parses to target model

Output: Write the spec to ProgressTracking/specs/test-integration.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec for the integration test. Read relevant stage and docs/ARCHITECTURE.md §17. Use tests/fixtures/. Run pytest for the new test file before returning.
```

---

### 14. tests/fixtures/

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "tests/fixtures/ (sample_youtube_transcript.md, sample_article.html, sample_pdf_extracted.txt, sample_code_heavy.md ★, sample_prompt_doc.md ★, vault_structure/)"
- Layer: tests
- Phase: 1
- Depends on: none (can be done early)
- Already done in this layer: (any)

Special constraints:
- Add fixtures to tests/fixtures/; vault_structure/ as base for integration; never generate fixture data inline in tests

Output: Write the spec to ProgressTracking/specs/test-fixtures.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Create or extend tests/fixtures/ per spec: sample_youtube_transcript.md, sample_article.html, sample_pdf_extracted.txt, sample_code_heavy.md, sample_prompt_doc.md, vault_structure/. Do not duplicate; reference from tests only.
```
