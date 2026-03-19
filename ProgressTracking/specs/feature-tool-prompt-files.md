# Feature Spec: Tool Prompt Files
slug: feature-tool-prompt-files
sections_covered: [ProgressTracking/tasks/04_tool-prompt-files.md]
arch_sections: [§9 Prompts, Appendix A — Verbatim Block Decision Tree]

---

## Scope

Five static Markdown prompt files loaded at runtime by `agent/llm/prompt_loader.py`.
These are **text files only** — no Python code. Each file defines:
- A role/system block
- Input variable schema (`{{variable}}` placeholders)
- Required JSON output schema (matched 1:1 to the corresponding Pydantic model)
- 1–2 few-shot examples for local LLM compatibility
- Explicit constraints (no function calling, no code fences wrapping JSON)

All five prompts must be local-LLM-compatible (Ollama / LM Studio) and produce
plain JSON in the completion text — no markdown wrappers, no tool calls.

Authored via `dev:prompt-author` skill, NOT `dev:builder`.

---

## Module breakdown (in implementation order)

| # | Module | Spec slug | Depends on | Layer |
|---|--------|-----------|------------|-------|
| 1 | `prompts/classify.md` | `prompt-classify` | `ClassificationResult` model (models.py), `prompt_loader.py` (LLM layer) | prompts |
| 2 | `prompts/summarize.md` | `prompt-summarize` | `SummaryResult` model (models.py), `prompt_loader.py`, classify.md semantics | prompts |
| 3 | `prompts/extract_verbatim.md` ★ | `prompt-extract-verbatim` | `VerbatimBlock`, `VerbatimType`, `StatenessRisk` models, Appendix A decision tree | prompts |
| 4 | `prompts/extract_entities.md` | `prompt-extract-entities` | models.py (entity fields), prompt_loader.py | prompts |
| 5 | `prompts/suggest_tags.md` | `prompt-suggest-tags` | tag-taxonomy (requirements §4), models.py | prompts |

---

## Cross-cutting constraints

**Format**
- Each file MUST begin with a YAML front-matter block: `version`, `task`, `output_format: json`
- Input variables use `{{double_braces}}` syntax — matched by `prompt_loader.py`'s `str.format_map()`
- Output MUST be raw JSON — no enclosing markdown code fences, no prose around the JSON

**Local LLM compatibility**
- No function calling, no tool-use syntax
- No chain-of-thought instructions that rely on multi-turn context
- Instructions must work with 7B–13B quantised models (e.g., Mistral 7B, Llama 3 8B)
- Include at least one few-shot example block per prompt
- Keep prompts under 1200 tokens (excluding the `{text}` input variable)

**Output schema fidelity**
- Every field in the JSON output schema must map 1:1 to the corresponding Pydantic model field
- Fields not computed by the LLM (e.g., `domain_path`, `staleness_risk` on classify) MUST be
  explicitly excluded from the prompt schema with a comment noting they are computed in Python
- Optional JSON fields (e.g., `attribution`, `timestamp`, `model_target` in VerbatimBlock)
  MUST be documented as "omit if not applicable" to prevent null-injection

**Verbatim prompt extra constraints** (`extract_verbatim.md`)
- Appendix A decision tree MUST be embedded verbatim as a numbered decision sequence
- `max_blocks` is a runtime variable (`{{max_blocks}}`); default is 10
- `staleness_risk` defaults per type MUST be stated inline: code/prompt = `high`, quote = `low`,
  transcript = `medium`
- Ordering instruction: if more than `max_blocks` candidates are found, keep highest-signal
  (prefer code > prompt > quote > transcript)

**Tag taxonomy prompt extra constraints** (`suggest_tags.md`)
- Tag namespace list (source/, domain/, subdomain/, proj/, ref/, relationship/, status/, entity/,
  type/, lang/, verbatim/, index/) MUST be listed in the prompt as the allowed set
- `verbatim/*` and `index/*` tags are NEVER suggested by this prompt (agent-assigned only)
- Output must be a JSON array of strings, not an object

---

## Implementation ordering rationale

1. **classify.md first** — used at Stage 2, the first LLM call in the pipeline. All downstream
   prompts benefit from understanding how classification output is structured.

2. **summarize.md second** — Stage 4a; depends on classification context in pipeline but the
   prompt itself only needs `SummaryResult` model knowledge. Simpler than verbatim extraction.

3. **extract_verbatim.md third ★** — Stage 4b; most complex prompt. Embeds Appendix A decision
   tree; requires understanding of all four `VerbatimType` values and their default staleness
   rules. Best authored after classification and summary patterns are established.

4. **extract_entities.md fourth** — Stage 4a sub-task (people, project extraction). Straightforward
   schema; sits logically after summarize since entities are identified during summarization context.

5. **suggest_tags.md last** — Stage 2 supplementary call. Tag taxonomy is the constraint; no new
   Pydantic model. Simplest output schema (string array). Safe to do last as it reuses patterns
   already established in classify.md.

---

## Excluded (Phase 2 or out of scope)

- `prompts/extract_atoms.md` — Phase 2 (Atom Note layer, 06_ATOMS/)
- Any prompt for bi-directional link proposals — Phase 2
- Any prompt for MS Teams polling — Phase 2
- `model_target` superseded-detection prompt — Phase 2
- Prompt for FastAPI dashboard queries — Phase 2
- Web UI or interactive Obsidian plugin prompts — out of scope for CLI agent
