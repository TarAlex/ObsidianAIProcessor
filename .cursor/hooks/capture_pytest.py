#!/usr/bin/env python3
"""PostToolUse: Append pytest summary lines to .cursor/dev/test-results.log."""
import json, sys, re
from datetime import datetime
from pathlib import Path

event  = json.load(sys.stdin)
output = event.get("tool_result", {}).get("output", "")

# Match lines like "5 passed, 1 failed in 2.34s" or "3 passed in 0.12s"
match = re.search(r'(\d[\d\s\w,]+(passed|failed|error)[^\n]*)', output)
if match:
    log = Path(".cursor/dev/test-results.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {match.group(1).strip()}\n")
