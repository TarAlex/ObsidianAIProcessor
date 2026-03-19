# Tasks: Foundations

Source: [ProgressTracking/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] pyproject.toml + project scaffold
- [ ] agent/core/config.py (YAML + .env loading, Config Pydantic model)
- [ ] agent/core/models.py (all v1.1 models: NormalizedItem, ClassificationResult, SummaryResult, VerbatimBlock, VerbatimType, StatenessRisk, ProcessingStatus)
- [ ] agent/core/pipeline.py (stage orchestrator, error routing to to_review/)
- [ ] agent/core/watcher.py (watchdog InboxWatcher)
- [ ] agent/core/scheduler.py (APScheduler: weekly outdated-review, daily index-rebuild)

---

## Implementation prompts

### 1. pyproject.toml + project scaffold

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "pyproject.toml + project scaffold"
- Layer: cli / foundations
- Phase: 1
- Depends on: none
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §2 Project Structure, §16 Dependencies

Special constraints:
- Python 3.11+ only; all paths relative to project root; no hardcoded vault paths or API keys

Output: Write the spec to ProgressTracking/specs/pyproject-scaffold.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session** (after spec exists at `ProgressTracking/specs/pyproject-scaffold.md`)

```
Implement the spec at ProgressTracking/specs/pyproject-scaffold.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §2, §16
3. Read: (none — this is Tier 0)

Then implement. Run pytest for any tests under tests/ before returning.
```

---

### 2. agent/core/config.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "agent/core/config.py (YAML + .env loading, Config Pydantic model)"
- Layer: core
- Phase: 1
- Depends on: pyproject.toml (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §10 Configuration Schema

Special constraints:
- All paths and API keys from config/env — no hardcoding; Pydantic v2 for Config model

Output: Write the spec to ProgressTracking/specs/config-py.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/config-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §10
3. Read: (existing config schema in docs)

Then implement agent/core/config.py. Run pytest tests/unit/test_config.py if present.
```

---

### 3. agent/core/models.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "agent/core/models.py (all v1.1 models: NormalizedItem, ClassificationResult, SummaryResult, VerbatimBlock, VerbatimType, StatenessRisk, ProcessingStatus)"
- Layer: core
- Phase: 1
- Depends on: none (Tier 0)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §3 Core Data Models, docs/requirements.md §3

Special constraints:
- Pydantic v2 only; match v1.1 schema exactly; VerbatimBlock has content, type, staleness_risk, added_at; domain_path on ClassificationResult

Output: Write the spec to ProgressTracking/specs/models-py.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/models-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §3, docs/requirements.md §3
3. Read: (none)

Then implement agent/core/models.py. Run pytest tests/unit/test_models.py before returning.
```

---

### 4. agent/core/pipeline.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "agent/core/pipeline.py (stage orchestrator, error routing to to_review/)"
- Layer: stages / core
- Phase: 1
- Depends on: models.py (DONE), all stage modules as they become DONE
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §5 Pipeline Implementation

Special constraints:
- anyio for async; failed items route to to_review/; stateless stages only

Output: Write the spec to ProgressTracking/specs/pipeline-py.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/pipeline-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §5
3. Read: agent/core/models.py, agent/core/config.py

Then implement agent/core/pipeline.py. Run pipeline tests before returning.
```

---

### 5. agent/core/watcher.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "agent/core/watcher.py (watchdog InboxWatcher)"
- Layer: core
- Phase: 1
- Depends on: config.py (DONE), pipeline (or run interface) (DONE)
- Already done in this layer: pipeline.py

Architecture ref: docs/requirements.md §5.3 Inbox Monitoring

Special constraints:
- Watch inbox path from config; no hardcoded paths; cross-platform (anyio/watchdog)

Output: Write the spec to ProgressTracking/specs/watcher-py.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/watcher-py.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §5.3
3. Read: agent/core/config.py, agent/core/pipeline.py

Then implement agent/core/watcher.py. Run tests before returning.
```

---

### 6. agent/core/scheduler.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "agent/core/scheduler.py (APScheduler: weekly outdated-review, daily index-rebuild)"
- Layer: core / tasks
- Phase: 1
- Depends on: config (DONE), outdated_review.py (DONE), index_updater.py (DONE)
- Already done in this layer: pipeline, watcher

Architecture ref: docs/ARCHITECTURE.md §12, §13

Special constraints:
- APScheduler or equivalent; weekly for outdated-review, daily for index-rebuild; no hardcoded paths

Output: Write the spec to ProgressTracking/specs/scheduler-py.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/scheduler-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §12, §13
3. Read: agent/core/config.py, agent/tasks/outdated_review.py, agent/tasks/index_updater.py

Then implement agent/core/scheduler.py. Run tests before returning.
```
