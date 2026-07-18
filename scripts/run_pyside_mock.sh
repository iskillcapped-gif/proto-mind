#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"
export PROTO_MIND_REASONER=mock
PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")" || {
  echo "Could not find Python 3.11+ for Proto-Mind PySide." >&2
  exit 1
}
exec "${PYTHON_BIN}" -m proto_mind.pyside_app
