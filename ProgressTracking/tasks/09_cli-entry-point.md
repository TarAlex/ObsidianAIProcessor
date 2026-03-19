# Tasks: CLI Entry Point

Source: [ProgressTracking/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] agent/main.py (click: run, process-file, rebuild-indexes, outdated-review)

---

## Implementation prompts

### 1. agent/main.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "agent/main.py (click: run, process-file, rebuild-indexes, outdated-review)"
- Layer: cli
- Phase: 1
- Depends on: pipeline (DONE), watcher (DONE), scheduler (DONE), vault (DONE), tasks (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §14 CLI Interface

Special constraints:
- Click CLI; commands: run, process-file, rebuild-indexes, outdated-review; --config, --dry-run; no writes when --dry-run; graceful errors; all paths from config

Output: Write the spec to ProgressTracking/specs/main-py.md using the format in .claude/agents/dev-planner.md. Do not ask the user; use the context above. Then set this item to IN_PROGRESS in ProgressTracking/TRACKER.md.
```

**/build session**

```
Implement the spec at ProgressTracking/specs/main-py.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §14
3. Read: agent/core/pipeline.py, agent/core/watcher.py, agent/core/scheduler.py, agent/vault/vault.py, agent/tasks/outdated_review.py, agent/tasks/index_updater.py

Then implement agent/main.py. Test with Click CliRunner; --dry-run must never write. Run integration tests before returning.
```
