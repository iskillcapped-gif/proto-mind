#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"

PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")" || {
  echo "Could not find Python 3.11+ for Proto-Mind tests." >&2
  echo "Recommended: /opt/homebrew/opt/python@3.11/bin/python3.11 -m unittest proto_mind.tests.test_flow" >&2
  exit 1
}

echo "Using Python: ${PYTHON_BIN}"
"${PYTHON_BIN}" -m unittest proto_mind.tests.test_flow
"${PYTHON_BIN}" -m compileall proto_mind

if "${PYTHON_BIN}" -c "import pytest" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pytest
else
  echo "pytest not installed; skipping optional pytest run."
fi
