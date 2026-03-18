# Tasks: Scheduled Tasks (agent/tasks/)

Source: [.cursor/dev/TRACKER.md](../TRACKER.md).  
Use [feature-initiation-prompts.md](../feature-initiation-prompts.md) for session discipline.

---

## Task list

- [ ] outdated_review.py (weekly scan: stale notes + stale verbatim blocks)
- [ ] index_updater.py ★ (daily rebuild_all_counts from scratch)
- [ ] reference_linker.py

---

## Implementation prompts

### 1. outdated_review.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "outdated_review.py (weekly scan: stale notes + stale verbatim blocks)"
- Layer: tasks (scheduled)
- Phase: 1
- Depends on: vault.py (DONE), models.py (DONE)
- Already done in this layer: none

Architecture ref: docs/ARCHITECTURE.md §12 Outdated Review Task, docs/requirements.md §6.2

Special constraints:
- Two passes: stale notes (review_after < today) AND stale verbatim blocks (staleness_risk=HIGH, added_at older than config threshold); output to _AI_META/outdated-review.md; MUST NOT auto-archive or auto-delete — human review only; emit staleness.scan.started, staleness.found, staleness.scan.completed

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/outdated-review.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §12, docs/requirements.md §6.2
3. Read: agent/vault/vault.py, agent/core/models.py, agent/core/config.py

Then implement agent/tasks/outdated_review.py. Run tests with mocked clock. Idempotent; no auto-delete. Run pytest before returning.
```

---

### 2. index_updater.py ★

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "index_updater.py ★ (daily rebuild_all_counts from scratch)"
- Layer: tasks (scheduled)
- Phase: 1
- Depends on: vault (DONE) — ensure_domain_index, update_domain_index / rebuild
- Already done in this layer: outdated_review

Architecture ref: docs/ARCHITECTURE.md §13 Index Updater Task

Special constraints:
- rebuild_all_counts() walks 02_KNOWLEDGE/, counts per domain_path, rewrites note_count + last_updated in every _index.md; corrects manual edits; only frontmatter; never touch body (Bases)

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/index-updater.md

Before writing any code:
1. Read the full spec
2. Read docs/ARCHITECTURE.md §13
3. Read: agent/vault/vault.py, agent/core/config.py
4. Load skill: .cursor/skills/index-update-contract/SKILL.md

Then implement agent/tasks/index_updater.py. Run pytest tests/unit/test_index_update.py before returning.
```

---

### 3. reference_linker.py

**/plan session**

```
I'm starting a new feature for the obsidian-agent project.

Context:
- Tracker item: "reference_linker.py"
- Layer: tasks
- Phase: 1
- Depends on: vault (DONE), references.py (DONE)
- Already done in this layer: outdated_review, index_updater

Architecture ref: docs/requirements.md §2.2, docs/ARCHITECTURE.md (references)

Special constraints:
- Link notes to REFERENCES/ (people, work projects, personal projects); no auto-delete; human-review safe

Run /plan
```

**/build session**

```
Implement the spec at .cursor/dev/specs/reference-linker.md

Before writing any code:
1. Read the full spec
2. Read docs/requirements.md §2.2
3. Read: agent/vault/vault.py, agent/vault/references.py

Then implement agent/tasks/reference_linker.py. Run pytest tests/unit/test_reference_linker.py before returning.
```
