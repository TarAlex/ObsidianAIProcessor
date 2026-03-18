# Done

Mark a tracker item DONE (after `/review` passes).
Usage: `/done "item description"`

---

First confirm the user has run `/review` and it returned APPROVED.
If not, say: "Run `/review [module]` first. `/done` requires an APPROVED review."

If confirmed: use the dev-tracker workflow: @dev-tracker

Tell it: "In `.cursor/dev/TRACKER.md`, set '[ITEM]' to DONE.
Then ask the user: 'Any lesson to capture for `.cursor/dev/lessons.md`?'"

Replace `[ITEM]` with the description provided by the user.

After finishing, remind: any lessons? Run `/log 'lesson text'` to capture them.
