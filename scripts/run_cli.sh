#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"

PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")" || {
  echo "Could not find Python 3.11+ for Proto-Mind." >&2
  echo "Recommended: /opt/homebrew/opt/python@3.11/bin/python3.11 -m proto_mind.main" >&2
  exit 1
}

exec "${PYTHON_BIN}" -m proto_mind.main "$@"
