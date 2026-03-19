# Tasks: Pipeline Stages (agent/stages/)

Source: [ProgressTracking/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] s1_normalize.py
- [ ] s2_classify.py (uses prompts/classify.md via ProviderFactory)
- [ ] s3_dates.py
- [ ] s4a_summarize.py (uses prompts/summarize.md)
- [ ] s4b_verbatim.py ★ (uses prompts/extract_verbatim.md; max 10 blocks)
- [ ] s5_deduplicate.py (ChromaDB similarity)
- [ ] s6a_write.py (Jinja2 templates → vault notes)
- [ ] s6b_index_update.py ★ (ensure_domain_index + increment + parent rollup)
- [ ] s7_archive.py

---

## Implementation prompts

### 1. s1_normalize.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s1_normalize.py"
- Layer: stages
- Phase: 1
- Depends on: models (DONE), adapters (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §6 Stage 1

Special constraints:
- SourceAdapter → NormalizedItem; stateless; no LLM; no vault writes

Output: Write the spec to ProgressTracking/specs/s1-normalize.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s1-normalize.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 1
3. Read: agent/core/models.py, agent/adapters/base.py

Then implement agent/stages/s1_normalize.py. Run tests before returning.
```

---

### 2. s2_classify.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s2_classify.py (uses prompts/classify.md via ProviderFactory)"
- Layer: stages
- Phase: 1
- Depends on: models (DONE), ProviderFactory (DONE), prompts/classify.md (DONE)
- Already done in this layer: s1_normalize

Architecture ref: docs/ARCHITECTURE.md §6 Stage 2

Special constraints:
- NormalizedItem → ClassificationResult; use ProviderFactory only; no direct HTTP; domain_path and staleness_risk in output

Output: Write the spec to ProgressTracking/specs/s2-classify.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s2-classify.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 2, §9 classify.md
3. Read: agent/core/models.py, agent/llm/base.py, agent/llm/provider_factory.py
4. Load skill: .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/stages/s2_classify.py. Run pytest tests/unit/test_s2_classify.py before returning.
```

---

### 3. s3_dates.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s3_dates.py"
- Layer: stages
- Phase: 1
- Depends on: models (DONE), classify (DONE)
- Already done in this layer: s1, s2

Architecture ref: docs/ARCHITECTURE.md §6 Stage 3

Special constraints:
- ClassificationResult → dated NormalizedItem; stateless; no vault writes

Output: Write the spec to ProgressTracking/specs/s3-dates.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s3-dates.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 3
3. Read: agent/core/models.py, agent/stages/s2_classify.py

Then implement agent/stages/s3_dates.py. Run pytest tests/unit/test_s3_dates.py before returning.
```

---

### 4. s4a_summarize.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s4a_summarize.py (uses prompts/summarize.md)"
- Layer: stages
- Phase: 1
- Depends on: models (DONE), ProviderFactory (DONE), prompts/summarize.md (DONE)
- Already done in this layer: s1, s2, s3

Architecture ref: docs/ARCHITECTURE.md §6 Stage 4a

Special constraints:
- Dated item → SummaryResult; ProviderFactory only; prompts/summarize.md

Output: Write the spec to ProgressTracking/specs/s4a-summarize.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s4a-summarize.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 4a
3. Read: agent/core/models.py, agent/llm/provider_factory.py
4. Load skill: .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/stages/s4a_summarize.py. Run tests before returning.
```

---

### 5. s4b_verbatim.py ★

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s4b_verbatim.py ★ (uses prompts/extract_verbatim.md; max 10 blocks)"
- Layer: stages
- Phase: 1
- Depends on: models (DONE), ProviderFactory (DONE), prompts/extract_verbatim.md (DONE), verbatim.py (DONE)
- Already done in this layer: s1, s2, s3, s4a

Architecture ref: docs/ARCHITECTURE.md §6 Stage 4b, §7 Verbatim Module

Special constraints:
- VerbatimBlock.content byte-identical to source; max 10 blocks (discard lowest-signal); staleness defaults by type; use ProviderFactory; load verbatim-contract skill

Output: Write the spec to ProgressTracking/specs/s4b-verbatim.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s4b-verbatim.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 4b, §7
3. Read: agent/core/models.py (VerbatimBlock), agent/llm/provider_factory.py, agent/vault/verbatim.py
4. Load skill: .cursor/skills/verbatim-contract/SKILL.md, .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/stages/s4b_verbatim.py. Run pytest tests/unit/test_verbatim.py and tests/integration/test_pipeline_verbatim.py before returning.
```

---

### 6. s5_deduplicate.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s5_deduplicate.py (ChromaDB similarity)"
- Layer: stages
- Phase: 1
- Depends on: models (DONE), vector store (DONE)
- Already done in this layer: s1–s4b

Architecture ref: docs/ARCHITECTURE.md §6 Stage 5, §15 Vector Store

Special constraints:
- SummaryResult → dedup decision; ChromaDB similarity_search; no vault writes in stage

Output: Write the spec to ProgressTracking/specs/s5-deduplicate.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s5-deduplicate.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 5, §15
3. Read: agent/core/models.py, agent/vector/store.py

Then implement agent/stages/s5_deduplicate.py. Run tests before returning.
```

---

### 7. s6a_write.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s6a_write.py (Jinja2 templates → vault notes)"
- Layer: stages
- Phase: 1
- Depends on: vault (DONE), templates (DONE), verbatim (DONE)
- Already done in this layer: s1–s5

Architecture ref: docs/ARCHITECTURE.md §6 Stage 6a, §8, §11

Special constraints:
- Approved item → vault note; ONLY ObsidianVault.write_note; Jinja2 from templates; verbatim blocks rendered via verbatim.py

Output: Write the spec to ProgressTracking/specs/s6a-write.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s6a-write.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 6a, §8, §11
3. Read: agent/vault/vault.py, agent/vault/templates.py, agent/vault/verbatim.py, agent/core/models.py
4. Load skill: .cursor/skills/verbatim-contract/SKILL.md

Then implement agent/stages/s6a_write.py. Run tests before returning.
```

---

### 8. s6b_index_update.py ★

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s6b_index_update.py ★ (ensure_domain_index + increment + parent rollup)"
- Layer: stages
- Phase: 1
- Depends on: vault (DONE) — ensure_domain_index, update_domain_index
- Already done in this layer: s1–s6a

Architecture ref: docs/ARCHITECTURE.md §6 Stage 6b

Special constraints:
- After note write: ensure_domain_index then update_domain_index for subdomain and domain; only frontmatter; never touch _index.md body (Bases queries)

Output: Write the spec to ProgressTracking/specs/s6b-index-update.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s6b-index-update.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 6b
3. Read: agent/core/models.py, agent/vault/vault.py (ensure_domain_index, update_domain_index)
4. Load skill: .cursor/skills/index-update-contract/SKILL.md

Then implement agent/stages/s6b_index_update.py. Run pytest tests/unit/test_index_update.py and tests/integration/test_pipeline_index.py before returning.
```

---

### 9. s7_archive.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "s7_archive.py"
- Layer: stages
- Phase: 1
- Depends on: vault/archive (DONE)
- Already done in this layer: s1–s6b

Architecture ref: docs/ARCHITECTURE.md §6 Stage 7

Special constraints:
- Processed item → move to 05_ARCHIVE/ via vault; stateless; no LLM

Output: Write the spec to ProgressTracking/specs/s7-archive.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/s7-archive.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §6 Stage 7
3. Read: agent/vault/vault.py, agent/vault/archive.py

Then implement agent/stages/s7_archive.py. Run tests before returning.
```
