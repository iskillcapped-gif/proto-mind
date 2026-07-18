#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"

PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")" || {
  echo "No Python 3.11+ candidate found."
  exit 1
}

echo "Selected Python: ${PYTHON_BIN}"
"${PYTHON_BIN}" --version

if "${PYTHON_BIN}" -c "import sys; sys.path.insert(0, '${PROJECT_DIR}'); import proto_mind" >/dev/null 2>&1; then
  echo "proto_mind import: OK"
else
  echo "proto_mind import: FAIL"
fi

if "${PYTHON_BIN}" -c "import PySide6" >/dev/null 2>&1; then
  echo "PySide6 import: OK"
else
  echo "PySide6 import: unavailable"
fi
