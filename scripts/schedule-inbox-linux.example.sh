#!/usr/bin/env bash
# Example: periodic inbox processing on Linux/macOS via cron.
#
# 1. Pick a config path (vault _AI_META/agent-config.yaml).
# 2. crontab -e and add (every 15 minutes):
#
#   */15 * * * * cd /tmp && /usr/bin/python3 -m agent process-inbox --config "/path/to/vault/_AI_META/agent-config.yaml" >>"/path/to/vault/_AI_META/process-inbox-scheduler.log" 2>&1
#
# Use `cd /tmp` so a stray ./agent folder in $HOME does not shadow the package.
# Adjust python path if you use a venv:
#
#   */15 * * * * cd /tmp && /path/to/venv/bin/python -m agent process-inbox --config "..." >>"..." 2>&1
#
exit 0
