---
name: provider-factory-pattern
description: >
  Load when implementing any pipeline stage that calls an LLM,
  or when adding a new provider to agent/llm/.
---

## The one rule
Never call an LLM HTTP endpoint directly from a stage.
Always go through:
```python
provider = ProviderFactory.get(config.llm)        # returns BaseProvider
result   = await provider.complete("prompt_name", ctx_dict)  # returns str
parsed   = TargetModel.model_validate_json(result)
```

## Adding a new provider
1. Create `agent/llm/[name]_provider.py` → implement `BaseProvider.complete()`
2. Register in `agent/llm/provider_factory.py`
3. Add config section in `_AI_META/agent-config.yaml`
4. Ollama remains the default; new providers are always opt-in via config

## Prompt loading
`PromptLoader.load("classify")` reads `prompts/classify.md`.
Caches at startup. Inject context vars as a dict — the loader handles
`{{variable}}` substitution.

## Local LLM constraint
Prompts must produce plain JSON in the completion text.
No function-calling syntax. No structured output API.
The stage must handle JSON parse errors gracefully (route to to_review/).
