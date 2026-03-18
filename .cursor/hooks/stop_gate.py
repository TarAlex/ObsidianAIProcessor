#!/usr/bin/env python3
"""
Stop: Warn if any IN_PROGRESS items have no test results logged.
Soft warning — does not block completion.
"""
import json
from pathlib import Path

tracker = Path(".cursor/dev/TRACKER.md")
results = Path(".cursor/dev/test-results.log")

if not tracker.exists():
    exit()

in_prog = [l.strip() for l in tracker.read_text().splitlines() if "IN_PROGRESS" in l]
if in_prog:
    has_results = results.exists() and bool(results.read_text().strip())
    if not has_results:
        print(json.dumps({
            "type": "warning",
            "message": (
                f"{len(in_prog)} IN_PROGRESS item(s) but no test results in "
                ".cursor/dev/test-results.log. Run pytest before calling /done."
            )
        }))
