#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"
PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")" || {
  echo "Proto-Mind Native requires Python 3.11+." >&2
  exit 1
}
command -v swift >/dev/null || { echo "Install Apple Command Line Tools before building." >&2; exit 1; }

swift build --package-path native -c release --product ProtoMindNative
swift build --package-path native -c release --product ProtoMindPDF
BIN_DIR="$(swift build --package-path native -c release --show-bin-path)"
APP_DIR="${PROJECT_DIR}/dist/Proto-Mind Native.app"
CONTENTS="${APP_DIR}/Contents"
mkdir -p "${CONTENTS}/MacOS" "${CONTENTS}/Resources"
cp "${BIN_DIR}/ProtoMindNative" "${CONTENTS}/MacOS/ProtoMindNative"
cp "${BIN_DIR}/ProtoMindPDF" "${CONTENTS}/MacOS/ProtoMindPDF"
cp native/Info.plist "${CONTENTS}/Info.plist"
if [ -f "${PROJECT_DIR}/dist/Proto-Mind.app/Contents/Resources/ProtoMind.icns" ]; then
  cp "${PROJECT_DIR}/dist/Proto-Mind.app/Contents/Resources/ProtoMind.icns" "${CONTENTS}/Resources/ProtoMind.icns"
fi

# Machine-local build metadata, not credentials or a public distributable config.
"${PYTHON_BIN}" -c 'import json, pathlib, sys; pathlib.Path(sys.argv[1]).write_text(json.dumps({"project_root": sys.argv[2], "python": sys.argv[3]}, indent=2) + "\n", encoding="utf-8")' \
  "${CONTENTS}/Resources/native-config.json" "${PROJECT_DIR}" "${PYTHON_BIN}"
chmod +x "${CONTENTS}/MacOS/ProtoMindNative"
chmod +x "${CONTENTS}/MacOS/ProtoMindPDF"
plutil -lint "${CONTENTS}/Info.plist"
codesign --force --sign - "${CONTENTS}/MacOS/ProtoMindPDF"
codesign --force --sign - "${APP_DIR}"
codesign --verify --strict "${APP_DIR}"
printf 'Native app: %s\nLegacy PySide app was not modified.\n' "${APP_DIR}"
