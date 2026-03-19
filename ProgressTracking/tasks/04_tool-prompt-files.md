# Tasks: Tool Prompt Files (prompts/)

Source: [ProgressTracking/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

**Use `/dev-prompt-author` (prompt-author skill) for these items, not `/dev-builder`.**

---

## Task list

- [ ] prompts/classify.md
- [ ] prompts/summarize.md
- [ ] prompts/extract_verbatim.md ★ (includes Appendix A decision tree)
- [ ] prompts/extract_entities.md
- [ ] prompts/suggest_tags.md

---

## Implementation prompts

### 1. prompts/classify.md

**/plan session** (or invoke @dev-planner with prompt-author focus)

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "prompts/classify.md"
- Layer: prompts (tool prompt files — use dev:prompt-author)
- Phase: 1
- Depends on: agent/llm/prompt_loader.py (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §9 Prompts (classify.md schema)

Special constraints:
- Static markdown file; target Pydantic model: ClassificationResult; output JSON only; local LLM compatible (no function calling); few-shot examples; list input variables

Output: Write the spec to ProgressTracking/specs/prompt-classify.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**Implementation** (use `/dev-prompt-author` or @dev-prompt-author)

```
Create the tool prompt file prompts/classify.md.

Before writing:
1. Read docs/ARCHITECTURE.md §9 (classify.md), docs/requirements.md §3, §4
2. Read agent/core/models.py (ClassificationResult, domain_path, staleness_risk)
3. Load skill: .cursor/skills/dev-prompt-author (prompt file format, local LLM compatibility)

Output: prompts/classify.md with role block, input schema, output JSON schema, 1–2 few-shot examples, constraints (no tool calls, no code fences in JSON). Validate manually via Ollama if possible.
```

---

### 2. prompts/summarize.md

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "prompts/summarize.md"
- Layer: prompts
- Phase: 1
- Depends on: prompt_loader (DONE), models (SummaryResult) (DONE)
- Already done in this layer: classify.md

Architecture ref: docs/ARCHITECTURE.md §9, docs/requirements.md §6.1

Special constraints:
- Target model: SummaryResult; plain JSON; local LLM compatible; few-shot

Output: Write the spec to ProgressTracking/specs/prompt-summarize.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**Implementation**

```
Create prompts/summarize.md using dev-prompt-author workflow.

Before writing: Read spec at ProgressTracking/specs/prompt-summarize.md if present; docs/ARCHITECTURE.md §9; agent/core/models.py (SummaryResult). Output JSON only, no function calling. Validate via Ollama.
```

---

### 3. prompts/extract_verbatim.md ★

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "prompts/extract_verbatim.md ★ (includes Appendix A decision tree)"
- Layer: prompts
- Phase: 1
- Depends on: prompt_loader (DONE), models (VerbatimBlock, VerbatimType, StatenessRisk) (DONE)
- Already done in this layer: classify, summarize

Architecture ref: docs/ARCHITECTURE.md §9 extract_verbatim.md, Appendix A — Verbatim Block Decision Tree

Special constraints:
- Embed Appendix A decision tree; output JSON array of VerbatimBlock-shaped objects; max 10 blocks (instruct model to keep highest-signal); staleness defaults: code/prompt=high, quote=low, transcript=medium; local LLM compatible

Output: Write the spec to ProgressTracking/specs/prompt-extract_verbatim.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**Implementation**

```
Create prompts/extract_verbatim.md using dev-prompt-author workflow.

Before writing: Read docs/ARCHITECTURE.md §9 and Appendix A; agent/core/models.py (VerbatimBlock, VerbatimType, StatenessRisk); .cursor/skills/verbatim-contract/SKILL.md. Embed decision tree; max 10 blocks; output schema matching VerbatimBlock. Validate via Ollama.
```

---

### 4. prompts/extract_entities.md

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "prompts/extract_entities.md"
- Layer: prompts
- Phase: 1
- Depends on: prompt_loader (DONE), models (DONE)
- Already done in this layer: classify, summarize, extract_verbatim

Architecture ref: docs/ARCHITECTURE.md §9, requirements §3

Special constraints:
- Entity extraction output schema; plain JSON; local LLM compatible; few-shot

Output: Write the spec to ProgressTracking/specs/prompt-extract_entities.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**Implementation**

```
Create prompts/extract_entities.md using dev-prompt-author workflow. Read spec and models; output JSON only. Validate via Ollama.
```

---

### 5. prompts/suggest_tags.md

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "prompts/suggest_tags.md"
- Layer: prompts
- Phase: 1
- Depends on: prompt_loader (DONE), tag taxonomy (requirements §4) (DONE)
- Already done in this layer: classify, summarize, extract_verbatim, extract_entities

Architecture ref: docs/ARCHITECTURE.md §9, docs/requirements.md §4 Tag Taxonomy

Special constraints:
- Tag suggestion output; constrained to taxonomy; plain JSON; local LLM compatible

Output: Write the spec to ProgressTracking/specs/prompt-suggest_tags.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**Implementation**

```
Create prompts/suggest_tags.md using dev-prompt-author workflow. Read docs/requirements.md §4; output JSON; validate via Ollama.
```
