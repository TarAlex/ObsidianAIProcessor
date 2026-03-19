# Tasks: Vector Store (agent/vector/)

Source: [ProgressTracking/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] embedder.py
- [ ] store.py (ChromaDB: add, similarity_search, delete)

---

## Implementation prompts

### 1. embedder.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "embedder.py"
- Layer: vector
- Phase: 1
- Depends on: config (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §15 Vector Store

Special constraints:
- Embed text for vector store; local or configurable embedding model; no hardcoded API keys; used by store.py for add/similarity

Output: Write the spec to ProgressTracking/specs/embedder-py.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/embedder-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §15
3. Read: agent/core/config.py

Then implement agent/vector/embedder.py. Run tests before returning.
```

---

### 2. store.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "store.py (ChromaDB: add, similarity_search, delete)"
- Layer: vector
- Phase: 1
- Depends on: embedder (DONE), config (DONE)
- Already done in this layer: embedder

Architecture ref: docs/ARCHITECTURE.md §15 Vector Store

Special constraints:
- ChromaDB; add, similarity_search, delete; used by s5_deduplicate; paths from config; no hardcoded paths

Output: Write the spec to ProgressTracking/specs/store-py.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/store-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §15
3. Read: agent/vector/embedder.py, agent/core/config.py

Then implement agent/vector/store.py. Run pytest tests/unit/test_vector_store.py before returning.
```
