#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"

export PROTO_MIND_REASONER=ollama
export PROTO_MIND_OLLAMA_MODEL="${PROTO_MIND_OLLAMA_MODEL:-qwen3:8b}"
export PROTO_MIND_OLLAMA_URL="${PROTO_MIND_OLLAMA_URL:-http://localhost:11434}"

PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")" || {
  echo "Could not find Python 3.11+ for Proto-Mind desktop." >&2
  exit 1
}

exec "${PYTHON_BIN}" -m proto_mind.desktop_app
