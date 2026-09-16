#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
source "${PROJECT_DIR}/scripts/python_common.sh"
source "${PROJECT_DIR}/scripts/swift_common.sh"
PYTHON_BIN="$(select_proto_mind_python "${PROJECT_DIR}")" || {
  echo "Proto-Mind Native requires Python 3.11+." >&2
  exit 1
}
command -v swift >/dev/null || { echo "Install Apple Command Line Tools before building." >&2; exit 1; }

swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}" -c release --product ProtoMindNative
swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}" -c release --product ProtoMindPDF
BIN_DIR="$(swift build "${PROTO_MIND_SWIFT_BUILD_ARGS[@]}" -c release --show-bin-path)"
APP_DIR="${PROTO_MIND_NATIVE_OUTPUT:-${PROJECT_DIR}/dist/Proto-Mind Native.app}"
CONTENTS="${APP_DIR}/Contents"
mkdir -p "${CONTENTS}/MacOS" "${CONTENTS}/Resources"
cp "${BIN_DIR}/ProtoMindNative" "${CONTENTS}/MacOS/ProtoMindNative"
cp "${BIN_DIR}/ProtoMindPDF" "${CONTENTS}/MacOS/ProtoMindPDF"
cp -Rf "${BIN_DIR}/SwiftTerm_SwiftTerm.bundle" "${CONTENTS}/Resources/"
mkdir -p "${CONTENTS}/Resources/Licenses"
cp native/Distribution/SwiftTerm-LICENSE.txt "${CONTENTS}/Resources/Licenses/"
cp native/Info.plist "${CONTENTS}/Info.plist"
scripts/build_native_icon.sh "${CONTENTS}/Resources/ProtoMindCube.icns"

# Machine-local build metadata, not credentials or a public distributable config.
"${PYTHON_BIN}" -c 'import json, pathlib, sys; pathlib.Path(sys.argv[1]).write_text(json.dumps({"project_root": sys.argv[2], "python": sys.argv[3]}, indent=2) + "\n", encoding="utf-8")' \
  "${CONTENTS}/Resources/native-config.json" "${PROJECT_DIR}" "${PYTHON_BIN}"
chmod +x "${CONTENTS}/MacOS/ProtoMindNative"
chmod +x "${CONTENTS}/MacOS/ProtoMindPDF"
plutil -lint "${CONTENTS}/Info.plist"
codesign --force --sign - "${CONTENTS}/MacOS/ProtoMindPDF"
codesign --force --sign - "${APP_DIR}"
codesign --verify --strict "${APP_DIR}"
# Refresh this bundle's icon registration without resetting Dock or global caches.
touch "${APP_DIR}"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "${LSREGISTER}" ]; then
  "${LSREGISTER}" -f "${APP_DIR}" || echo "App built; local icon registration refresh was unavailable." >&2
fi
printf 'Native app: %s\nLegacy PySide app was not modified.\n' "${APP_DIR}"
