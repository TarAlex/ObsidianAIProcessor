---
description: Mark a tracker item DONE (after /review passes). Usage: /done "item description"
---
First confirm the user has run /review and it returned APPROVED.
If not, say: "Run /review [module] first. /done requires an APPROVED review."

If confirmed: route to `dev:tracker`.
Tell it: "In ProgressTracking/TRACKER.md, set '$ARGUMENTS' to DONE.
Then ask the user: 'Any lesson to capture for ProgressTracking/lessons.md?'"
