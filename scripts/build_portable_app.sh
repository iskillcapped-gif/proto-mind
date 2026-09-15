#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source scripts/python_common.sh
source scripts/swift_common.sh
PYTHON_BIN="$(select_proto_mind_python "$PROJECT_DIR")"
if [[ "$(uname -m)" != arm64 ]]; then
  echo 'This portable release targets Apple Silicon. Build it on an arm64 Mac.' >&2
  exit 1
fi
swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}" -c release --product ProtoMindNative
swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}" -c release --product ProtoMindPDF
BIN_DIR="$(swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}" -c release --show-bin-path)"
exec "$PYTHON_BIN" scripts/package_native_app.py --binaries "$BIN_DIR" "$@"
