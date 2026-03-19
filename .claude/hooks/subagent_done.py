#!/usr/bin/env python3
"""
SubagentStop: After builder/tester/reviewer finishes, remind orchestrator
to route status updates through dev:tracker — not update TRACKER.md inline.
"""
import json, sys

event = json.load(sys.stdin)
agent = event.get("subagent_type", "")

builders = ("dev:builder", "dev:tester", "dev:reviewer", "dev:prompt-author")
if agent in builders:
    print(json.dumps({
        "type": "reminder",
        "message": (
            f"✓ {agent} finished. "
            "Next: run /review if not done, then /done 'item name' to update TRACKER.md. "
            "Any lessons? Run /log 'lesson text'."
        )
    }))
