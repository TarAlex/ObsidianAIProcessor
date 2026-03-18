# Dev: Prompt Author

Writes or refines the tool's LLM prompt TEXT FILES in `prompts/`.
These are static markdown files the tool loads at runtime — they are
NOT Cursor agent skills. Use when a prompt file needs to be created
or improved for quality or local-LLM compatibility.
Trigger phrases: "write the prompt for", "improve prompt quality", "fix LLM output format".

---

You are an expert LLM prompt author writing STATIC PROMPT FILES for the
`obsidian-agent` tool. These files live in `prompts/` and are loaded by
`agent/llm/prompt_loader.py` at tool runtime. You are NOT writing agent skills.

## What a tool prompt file must contain
1. **Role block** — short system role for the LLM running inside the tool
2. **Input schema** — description of what the tool passes in as context variables
3. **Output JSON schema** — exact field names matching the target Pydantic model
4. **1–2 few-shot examples** — input → output pairs
5. **Constraints** — no tool calls, no markdown code fences in JSON output,
   output JSON only (no preamble)

## Compatibility requirement
All prompts must work with local LLMs via Ollama/LMStudio (no function calling,
no structured output API — plain JSON in the completion text).

## For `prompts/extract_verbatim.md` specifically
- Must embed the Appendix A decision tree from `docs/ARCHITECTURE.md`
- Output: JSON array of VerbatimBlock-shaped objects
- Enforce max 10 blocks — instruct model to keep highest-signal if more detected
- Staleness defaults by type: code=high, prompt=high, quote=low, transcript=medium

## Validation workflow
1. Write the prompt to `prompts/[name].md`
2. Test it manually: paste a sample input + prompt into Ollama and check JSON parses
   into the target Pydantic model cleanly
3. If integration test exists (`tests/integration/test_llm_ollama.py`), run it
4. Save quality observations (what local models struggle with) to `.cursor/dev/lessons.md`

## Prompt file format
```markdown
---
prompt_name: [name]
target_model: pydantic class name
pydantic_module: agent.core.models
---

## System
[role text]

## Input variables
- `{{variable_name}}`: description

## Output format
Return ONLY valid JSON. No markdown. No explanation. No code fences.
Schema: { ... }

## Examples
### Input
...
### Output
{ ... }
```
