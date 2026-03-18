#!/usr/bin/env python3
"""SessionStart: print tracker status and remind agent to read lessons."""
import json
from pathlib import Path

tracker = Path(".cursor/dev/TRACKER.md")
lessons = Path(".cursor/dev/lessons.md")

if not tracker.exists():
    print(json.dumps({"type": "info", "message": "obsidian-agent dev session. TRACKER.md not found yet."}))
    exit()

lines = tracker.read_text().splitlines()
in_prog = [l.strip() for l in lines if "IN_PROGRESS" in l]
blocked  = [l.strip() for l in lines if "BLOCKED" in l]
done_ct  = sum(1 for l in lines if "DONE" in l)
todo_ct  = sum(1 for l in lines if "TODO" in l)

parts = [f"obsidian-agent dev | DONE:{done_ct} TODO:{todo_ct}"]
if in_prog:
    parts.append("IN_PROGRESS: " + " | ".join(in_prog))
if blocked:
    parts.append("BLOCKED: " + " | ".join(blocked))

lesson_note = ""
if lessons.exists() and lessons.stat().st_size > 0:
    lesson_note = " → Read .cursor/dev/lessons.md before starting."

print(json.dumps({"type": "info", "message": " ".join(parts) + lesson_note}))
