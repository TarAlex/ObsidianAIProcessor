# Tasks: LLM Provider Layer (agent/llm/)

Source: [ProgressTracking/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] base.py (BaseProvider ABC: complete(prompt_name, ctx) → str)
- [ ] prompt_loader.py (reads prompts/*.md, caches)
- [ ] ollama_provider.py (default / privacy-first)
- [ ] lmstudio_provider.py
- [ ] openai_provider.py
- [ ] anthropic_provider.py
- [ ] provider_factory.py (registry + env-driven selection)

---

## Implementation prompts

### 1. base.py (BaseProvider ABC)

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "base.py (BaseProvider ABC: complete(prompt_name, ctx) → str)"
- Layer: llm
- Phase: 1
- Depends on: models.py (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §4 LLM Provider Abstraction

Special constraints:
- Never call HTTP directly from stages; complete(prompt_name, ctx) returns str; no function-calling in contract

Output: Write the spec to ProgressTracking/specs/llm-base.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/llm-base.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §4
3. Read: agent/core/models.py
4. Load skill: .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/llm/base.py. Run tests before returning.
```

---

### 2. prompt_loader.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "prompt_loader.py (reads prompts/*.md, caches)"
- Layer: llm
- Phase: 1
- Depends on: config (DONE)
- Already done in this layer: base.py

Architecture ref: docs/ARCHITECTURE.md §9 Prompts

Special constraints:
- Load from prompts/*.md; {{variable}} substitution; cache at startup; no vault dependency

Output: Write the spec to ProgressTracking/specs/prompt-loader.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/prompt-loader.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §9
3. Read: agent/core/config.py, agent/llm/base.py

Then implement agent/llm/prompt_loader.py. Run tests before returning.
```

---

### 3. ollama_provider.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "ollama_provider.py (default / privacy-first)"
- Layer: llm
- Phase: 1
- Depends on: base.py (DONE), prompt_loader (DONE)
- Already done in this layer: base, prompt_loader

Architecture ref: docs/ARCHITECTURE.md §4, docs/requirements.md §7

Special constraints:
- Local Ollama; default provider; no API key required; plain JSON in completion text

Output: Write the spec to ProgressTracking/specs/ollama-provider.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/ollama-provider.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §4, §9
3. Read: agent/llm/base.py, agent/llm/prompt_loader.py
4. Load skill: .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/llm/ollama_provider.py. Run tests before returning.
```

---

### 4. lmstudio_provider.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "lmstudio_provider.py"
- Layer: llm
- Phase: 1
- Depends on: base.py (DONE), prompt_loader (DONE)
- Already done in this layer: base, prompt_loader, ollama

Architecture ref: docs/ARCHITECTURE.md §4, docs/requirements.md §7

Special constraints:
- LM Studio local API; same contract as Ollama (plain JSON); opt-in via config

Output: Write the spec to ProgressTracking/specs/lmstudio-provider.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/lmstudio-provider.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §4
3. Read: agent/llm/base.py, agent/llm/ollama_provider.py
4. Load skill: .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/llm/lmstudio_provider.py. Run tests before returning.
```

---

### 5. openai_provider.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "openai_provider.py"
- Layer: llm
- Phase: 1
- Depends on: base.py (DONE), prompt_loader (DONE)
- Already done in this layer: base, prompt_loader, ollama, lmstudio

Architecture ref: docs/ARCHITECTURE.md §4, docs/requirements.md §7

Special constraints:
- OpenAI API; API key from config/env only; opt-in; plain JSON output required

Output: Write the spec to ProgressTracking/specs/openai-provider.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/openai-provider.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §4
3. Read: agent/llm/base.py, agent/llm/ollama_provider.py
4. Load skill: .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/llm/openai_provider.py. Run tests before returning.
```

---

### 6. anthropic_provider.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "anthropic_provider.py"
- Layer: llm
- Phase: 1
- Depends on: base.py (DONE), prompt_loader (DONE)
- Already done in this layer: base, prompt_loader, ollama, lmstudio, openai

Architecture ref: docs/ARCHITECTURE.md §4, docs/requirements.md §7

Special constraints:
- Anthropic API; API key from config/env only; opt-in; plain JSON output required

Output: Write the spec to ProgressTracking/specs/anthropic-provider.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/anthropic-provider.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §4
3. Read: agent/llm/base.py, agent/llm/openai_provider.py
4. Load skill: .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/llm/anthropic_provider.py. Run tests before returning.
```

---

### 7. provider_factory.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "provider_factory.py (registry + env-driven selection)"
- Layer: llm
- Phase: 1
- Depends on: base.py (DONE), all provider implementations (DONE)
- Already done in this layer: base, prompt_loader, ollama, lmstudio, openai, anthropic

Architecture ref: docs/ARCHITECTURE.md §4

Special constraints:
- ProviderFactory.get(config.llm) returns BaseProvider; registry; env-driven; no direct HTTP from pipeline

Output: Write the spec to ProgressTracking/specs/provider-factory.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/provider-factory.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §4
3. Read: agent/llm/base.py, agent/llm/ollama_provider.py, agent/core/config.py
4. Load skill: .cursor/skills/provider-factory-pattern/SKILL.md

Then implement agent/llm/provider_factory.py. Run tests before returning.
```
