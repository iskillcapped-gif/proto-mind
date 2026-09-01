#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"
PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")" || {
  echo "Proto-Mind Native agent evals require Python 3.11+." >&2
  exit 1
}
exec "${PYTHON_BIN}" -m proto_mind.native_agent_evals
