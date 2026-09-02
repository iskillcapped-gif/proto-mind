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
"${PYTHON_BIN}" -m unittest proto_mind.tests.test_flow proto_mind.tests.test_native proto_mind.tests.test_native_workspace proto_mind.tests.test_native_library proto_mind.tests.test_native_agent proto_mind.tests.test_native_agent_contract proto_mind.tests.test_native_progress proto_mind.tests.test_native_work_sessions proto_mind.tests.test_native_desk proto_mind.tests.test_native_review proto_mind.tests.test_native_images proto_mind.tests.test_native_pdf proto_mind.tests.test_native_codex_threads proto_mind.tests.test_persona_engine proto_mind.tests.test_native_persona proto_mind.tests.test_persona_activation_readiness proto_mind.tests.test_persona_activation proto_mind.tests.test_backup_coverage \
    proto_mind.tests.test_native_learning_review proto_mind.tests.test_learning_apply_integrity proto_mind.tests.test_native_skill_authoring proto_mind.tests.test_native_skill_inspection proto_mind.tests.test_native_skill_outcome proto_mind.tests.test_native_skill_decision proto_mind.tests.test_native_skill_lifecycle
"${PYTHON_BIN}" -m compileall proto_mind

if "${PYTHON_BIN}" -c "import pytest" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pytest
else
  echo "pytest not installed; skipping optional pytest run."
fi
