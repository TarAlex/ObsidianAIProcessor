#!/usr/bin/env bash
# Install obsidian-agent from GitHub (or local clone) and bootstrap the current
# directory as the Obsidian vault. Works on macOS, Linux, and Git Bash on Windows.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/TarAlex/ObsidianAIProcessor/main/scripts/install.sh | bash
#   ./scripts/install.sh [--vault PATH] [--local]
#
# Environment:
#   OBSIDIAN_AGENT_REPO_URL  Git URL (default: https://github.com/TarAlex/ObsidianAIProcessor.git)
#   OLLAMA_CHAT_MODEL        Default Ollama chat model (default: llama3.1:8b)
#   OLLAMA_EMBED_MODEL       Default embedding model (default: nomic-embed-text)
#   OLLAMA_BASE_URL          Passed to configure (default: http://127.0.0.1:11434)
set -euo pipefail

REPO_URL="${OBSIDIAN_AGENT_REPO_URL:-https://github.com/TarAlex/ObsidianAIProcessor.git}"
CHAT_MODEL="${OLLAMA_CHAT_MODEL:-llama3.1:8b}"
EMBED_MODEL="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
LOCAL=0
VAULT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault)
      VAULT="$2"
      shift 2
      ;;
    --local)
      LOCAL=1
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--vault DIR] [--local]"
      echo "  --local  pip install -e from repo root (parent of scripts/)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$VAULT" ]]; then
  VAULT="$(pwd)"
fi

if command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

"$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || {
  echo "Python 3.11+ is required." >&2
  exit 1
}

if [[ "$LOCAL" -eq 1 ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  echo "[install] pip install -e $ROOT"
  "$PY" -m pip install -e "$ROOT"
else
  echo "[install] pip install from $REPO_URL@main"
  "$PY" -m pip install "git+${REPO_URL}@main"
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "WARNING: ollama not found on PATH. Install from https://ollama.com and re-run:" >&2
  echo "  ollama pull $CHAT_MODEL && ollama pull $EMBED_MODEL" >&2
else
  echo "[install] ollama pull $CHAT_MODEL"
  ollama pull "$CHAT_MODEL"
  echo "[install] ollama pull $EMBED_MODEL"
  ollama pull "$EMBED_MODEL"
fi

VAULT_ABS="$(cd "$VAULT" && pwd)"
CFG="$VAULT_ABS/_AI_META/agent-config.yaml"

echo "[install] configure vault at $VAULT_ABS"
"$PY" -m agent configure --non-interactive \
  --vault "$VAULT_ABS" \
  --config "$CFG" \
  --provider ollama \
  --ollama-url "$OLLAMA_URL" \
  --ollama-model "$CHAT_MODEL" \
  --embedding-model "$EMBED_MODEL"

echo "[install] setup-vault"
"$PY" -m agent setup-vault --config "$CFG"

echo "[install] Done. Run: cd \"$VAULT_ABS\" && obsidian-agent run"
echo "         (or: $PY -m agent run --config \"$CFG\")"
