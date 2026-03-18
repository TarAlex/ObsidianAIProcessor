# Status

Show current dev progress across all layers.
Usage: `/status`

---

Read `.cursor/dev/TRACKER.md`. Output:

**In Progress** — items currently marked IN_PROGRESS
**Blocked** — items marked BLOCKED with reason if known
**Next up** — first 3 TODO items in pipeline order (foundations first, CLI last)
**Done** — count by layer (Foundations N/6, Adapters N/7, etc.)
**Phase 1 completion** — DONE count / total Phase 1 item count as percentage

Do not modify any files.
