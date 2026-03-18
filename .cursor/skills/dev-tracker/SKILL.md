# Dev: Tracker

Updates `.cursor/dev/TRACKER.md` status and appends to `.cursor/dev/lessons.md`.
Mechanical only — no code, no design decisions. Always called via `/done` or `/log`.
Trigger: "mark done", "update tracker", "add lesson", "log this".

---

You update two files and nothing else.

## File 1: `.cursor/dev/TRACKER.md`

Change the status prefix of the exact item text given to you.
Format: `- [ STATUS ]  description`
Valid statuses: TODO | IN_PROGRESS | DONE | BLOCKED | PHASE_2

Find the line by matching the description text (case-insensitive, partial match OK).
Report: "Changed '[item]' from [OLD] to [NEW]"

## File 2: `.cursor/dev/lessons.md`

Append an entry in this format:
```
## [YYYY-MM-DD] [module or layer name]
**Pattern**: what happened (mistake, edge case, discovery)
**Rule**: the rule that prevents recurrence or encodes the learning
```

Only modify what you are explicitly asked to modify. Confirm what changed.
