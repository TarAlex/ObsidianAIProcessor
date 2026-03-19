# Tasks: Source Adapters (agent/adapters/)

Source: [ProgressTracking/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] base.py (BaseAdapter ABC → NormalizedItem)
- [ ] markdown_adapter.py
- [ ] web_adapter.py (httpx + markdownify)
- [ ] pdf_adapter.py (pymupdf)
- [ ] youtube_adapter.py (youtube-transcript-api)
- [ ] audio_adapter.py (openai-whisper)
- [ ] teams_adapter.py

---

## Implementation prompts

### 1. base.py (BaseAdapter ABC)

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "base.py (BaseAdapter ABC → NormalizedItem)"
- Layer: adapters
- Phase: 1
- Depends on: agent/core/models.py (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §2, docs/requirements.md §5

Special constraints:
- Abstract base only; output NormalizedItem; no LLM, no vault writes; all paths from config

Output: Write the spec to ProgressTracking/specs/adapters-base.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/adapters-base.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §2, §5
3. Read: agent/core/models.py (NormalizedItem)

Then implement agent/adapters/base.py. Run pytest tests/unit/test_adapters_base.py if present.
```

---

### 2. markdown_adapter.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "markdown_adapter.py"
- Layer: adapters
- Phase: 1
- Depends on: base.py (DONE), models.py (DONE)
- Already done in this layer: base.py

Architecture ref: docs/requirements.md §5.1

Special constraints:
- Markdown files → NormalizedItem; no LLM; read-only from inbox path

Output: Write the spec to ProgressTracking/specs/markdown-adapter.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/markdown-adapter.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §5.1
3. Read: agent/adapters/base.py, agent/core/models.py

Then implement agent/adapters/markdown_adapter.py. Run tests before returning.
```

---

### 3. web_adapter.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "web_adapter.py (httpx + markdownify)"
- Layer: adapters
- Phase: 1
- Depends on: base.py (DONE), models.py (DONE)
- Already done in this layer: base.py, markdown_adapter.py

Architecture ref: docs/requirements.md §5.1

Special constraints:
- httpx for fetch; markdownify for HTML→markdown; no LLM; no hardcoded URLs

Output: Write the spec to ProgressTracking/specs/web-adapter.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/web-adapter.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §5.1
3. Read: agent/adapters/base.py, agent/core/models.py

Then implement agent/adapters/web_adapter.py. Run tests before returning.
```

---

### 4. pdf_adapter.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "pdf_adapter.py (pymupdf)"
- Layer: adapters
- Phase: 1
- Depends on: base.py (DONE), models.py (DONE)
- Already done in this layer: base, markdown, web

Architecture ref: docs/requirements.md §5.1

Special constraints:
- pymupdf for extraction; output NormalizedItem; no LLM

Output: Write the spec to ProgressTracking/specs/pdf-adapter.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/pdf-adapter.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §5.1
3. Read: agent/adapters/base.py, agent/core/models.py

Then implement agent/adapters/pdf_adapter.py. Run tests before returning.
```

---

### 5. youtube_adapter.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "youtube_adapter.py (youtube-transcript-api)"
- Layer: adapters
- Phase: 1
- Depends on: base.py (DONE), models.py (DONE)
- Already done in this layer: base, markdown, web, pdf

Architecture ref: docs/requirements.md §5.2

Special constraints:
- youtube-transcript-api for captions; no LLM; no hardcoded API keys

Output: Write the spec to ProgressTracking/specs/youtube-adapter.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/youtube-adapter.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §5.2
3. Read: agent/adapters/base.py, agent/core/models.py

Then implement agent/adapters/youtube_adapter.py. Run tests before returning.
```

---

### 6. audio_adapter.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "audio_adapter.py (openai-whisper)"
- Layer: adapters
- Phase: 1
- Depends on: base.py (DONE), models.py (DONE)
- Already done in this layer: (other adapters)

Architecture ref: docs/requirements.md §5.2

Special constraints:
- openai-whisper for transcription; local-first; no cloud API required for basic flow

Output: Write the spec to ProgressTracking/specs/audio-adapter.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/audio-adapter.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §5.2
3. Read: agent/adapters/base.py, agent/core/models.py

Then implement agent/adapters/audio_adapter.py. Run tests before returning.
```

---

### 7. teams_adapter.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "teams_adapter.py"
- Layer: adapters
- Phase: 1
- Depends on: base.py (DONE), models.py (DONE)
- Already done in this layer: (other adapters)

Architecture ref: docs/requirements.md §5 (extensibility)

Special constraints:
- MS Teams source; Phase 2 may add Graph API polling — Phase 1 stub or minimal interface only if needed

Output: Write the spec to ProgressTracking/specs/teams-adapter.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/teams-adapter.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §5
3. Read: agent/adapters/base.py, agent/core/models.py

Then implement agent/adapters/teams_adapter.py. Run tests before returning.
```
