#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"
source "${PROJECT_DIR}/scripts/swift_common.sh"
PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")"
TEMP_DIR="$(mktemp -d -t proto-mind-native-tests)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}"
PDF_HELPER="$(swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}" --show-bin-path)/ProtoMindPDF"
SOURCES=()
for source_file in native/Sources/*.swift; do
  if [[ "${source_file}" != *ProtoMindApp.swift ]]; then
    SOURCES+=("${source_file}")
  fi
done
BIN_DIR="$(swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}" --show-bin-path)"
TERMINAL_OBJECTS=("${BIN_DIR}"/SwiftTerm.build/*.o)
swiftc -sdk "${PROTO_MIND_SELECTED_SDK}" -I "${BIN_DIR}/Modules" -parse-as-library "${SOURCES[@]}" ios/Shared/*.swift native/Tests/*.swift "${TERMINAL_OBJECTS[@]}" -o "${TEMP_DIR}/native-checks"
"${PYTHON_BIN}" scripts/native_smoke_fixture.py "${TEMP_DIR}/project"
# The full and interface suites exercise real Office previews in their isolated bridge.
if [[ $# -eq 0 || " $* " == *" --interface-only "* ]]; then
  DOCUMENT_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  DOCUMENT_PACKAGES="${PROJECT_DIR}/dist/document-runtime-${DOCUMENT_VERSION}"
  if [[ ! -f "${DOCUMENT_PACKAGES}/proto-mind-document-runtime.json" ]]; then
    DOCUMENT_PACKAGES="${TEMP_DIR}/document-runtime"
    "${PYTHON_BIN}" scripts/prepare_document_runtime.py --python "${PYTHON_BIN}" --destination "${DOCUMENT_PACKAGES}"
  fi
  ln -s "${DOCUMENT_PACKAGES}" "${TEMP_DIR}/project/document_packages"
fi
"${PYTHON_BIN}" scripts/native_smoke_fixture.py "${TEMP_DIR}/session-spine-project" \
  --session-spine-state "${TEMP_DIR}/session-spine-state"
"${TEMP_DIR}/native-checks" --fixture "${TEMP_DIR}/project" --python "${PYTHON_BIN}" --pdf-helper "${PDF_HELPER}" \
  --icon-source "${PROJECT_DIR}/assets/proto_mind_native_icon.png" \
  --steering-service "${PROJECT_DIR}/native/Tests/Fixtures/steering_account.py" \
  --session-spine-fixture "${TEMP_DIR}/session-spine-project" \
  --session-spine-state "${TEMP_DIR}/session-spine-state" "$@"
