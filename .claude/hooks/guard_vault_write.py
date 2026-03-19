#!/usr/bin/env python3
"""
PreToolUse: Block Write/Edit to vault path unless call originates from
ObsidianVault, setup_vault.py, or reindex.py.
Keeps the tool's own vault-write discipline enforced during dev.
"""
import json, sys, os

event   = json.load(sys.stdin)
path    = event.get("tool_input", {}).get("path", "")
vault   = os.environ.get("OBSIDIAN_VAULT_ROOT", "")
allowed = ("vault.py", "setup_vault.py", "reindex.py", "templates.py", "archive.py")

if vault and path.startswith(vault):
    stack = event.get("call_stack", "")
    if not any(a in stack for a in allowed):
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"Direct write to vault path '{path}' is blocked during dev. "
                "The tool must use ObsidianVault. If you are writing vault.py itself, "
                "this check does not apply — set CLAUDE_DEV_SKIP_VAULT_GUARD=1 temporarily."
            )
        }))
        sys.exit(0)

print(json.dumps({"decision": "allow"}))
