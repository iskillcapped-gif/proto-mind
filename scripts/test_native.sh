#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"
PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")"
TEMP_DIR="$(mktemp -d -t proto-mind-native-tests)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

swift build --package-path native
PDF_HELPER="$(swift build --package-path native --show-bin-path)/ProtoMindPDF"
SOURCES=()
for source_file in native/Sources/*.swift; do
  if [[ "${source_file}" != *ProtoMindApp.swift ]]; then
    SOURCES+=("${source_file}")
  fi
done
swiftc -parse-as-library "${SOURCES[@]}" native/Tests/*.swift -o "${TEMP_DIR}/native-checks"
"${PYTHON_BIN}" scripts/native_smoke_fixture.py "${TEMP_DIR}/project"
"${TEMP_DIR}/native-checks" --fixture "${TEMP_DIR}/project" --python "${PYTHON_BIN}" --pdf-helper "${PDF_HELPER}" \
  --icon-source "${PROJECT_DIR}/assets/proto_mind_native_icon.png" "$@"
