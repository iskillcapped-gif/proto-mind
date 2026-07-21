#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
APP_NAME="Proto-Mind"
APP_DIR="${PROJECT_DIR}/dist/${APP_NAME}.app"
CONTENTS_DIR="${APP_DIR}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"
LAUNCHER="${MACOS_DIR}/${APP_NAME}"
PLIST="${CONTENTS_DIR}/Info.plist"
ICON_FILE="${RESOURCES_DIR}/ProtoMind.icns"
ICONSET_DIR="${RESOURCES_DIR}/ProtoMind.iconset"

mkdir -p "${MACOS_DIR}" "${RESOURCES_DIR}"

ICON_PLIST_ENTRY=""

if command -v iconutil >/dev/null 2>&1; then
  mkdir -p "${ICONSET_DIR}"
  PROJECT_DIR="${PROJECT_DIR}" ICONSET_DIR="${ICONSET_DIR}" python3 - <<'PY'
from __future__ import annotations

from os import environ
from pathlib import Path
from struct import pack
from zlib import compress, crc32


def write_png(path: Path, size: int) -> None:
    def inside_round_rect(x: int, y: int) -> bool:
        radius = int(size * 0.21)
        left = radius
        right = size - radius - 1
        top = radius
        bottom = size - radius - 1
        if left <= x <= right or top <= y <= bottom:
            return True
        cx = left if x < left else right
        cy = top if y < top else bottom
        return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2

    def in_rect(x: int, y: int, x0: float, y0: float, x1: float, y1: float) -> bool:
        return int(x0 * size) <= x <= int(x1 * size) and int(y0 * size) <= y <= int(y1 * size)

    rows: list[bytes] = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            if not inside_round_rect(x, y):
                row.extend((0, 0, 0, 0))
                continue
            t = y / max(size - 1, 1)
            r = int(16 + 12 * t)
            g = int(24 + 18 * t)
            b = int(39 + 26 * t)
            a = 255
            dx = (x - size * 0.5) / size
            dy = (y - size * 0.5) / size
            ring = abs((dx * dx + dy * dy) ** 0.5 - 0.36)
            if ring < 0.024:
                r, g, b = 34, 211, 238
            # Blocky PM letters, drawn with rectangles so no font dependency is needed.
            p = (
                in_rect(x, y, 0.22, 0.30, 0.29, 0.70)
                or in_rect(x, y, 0.29, 0.30, 0.43, 0.36)
                or in_rect(x, y, 0.29, 0.47, 0.43, 0.53)
                or in_rect(x, y, 0.43, 0.36, 0.50, 0.47)
            )
            m = (
                in_rect(x, y, 0.56, 0.30, 0.63, 0.70)
                or in_rect(x, y, 0.79, 0.30, 0.86, 0.70)
                or in_rect(x, y, 0.63, 0.30, 0.70, 0.42)
                or in_rect(x, y, 0.70, 0.42, 0.75, 0.54)
                or in_rect(x, y, 0.75, 0.30, 0.79, 0.42)
            )
            if p:
                r, g, b = 229, 247, 255
            elif m:
                r, g, b = 167, 243, 208
            row.extend((r, g, b, a))
        rows.append(b"\x00" + bytes(row))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return pack(">I", len(payload)) + kind + payload + pack(">I", crc32(kind + payload) & 0xFFFFFFFF)

    raw = b"".join(rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


iconset = Path(environ["ICONSET_DIR"])
for name, size in {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}.items():
    write_png(iconset / name, size)
PY
  if iconutil -c icns "${ICONSET_DIR}" -o "${ICON_FILE}" >/dev/null 2>&1; then
    ICON_PLIST_ENTRY="  <key>CFBundleIconFile</key>
  <string>ProtoMind</string>"
  else
    echo "Icon generation skipped: iconutil could not create ${ICON_FILE}" >&2
  fi
else
  echo "Icon generation skipped: iconutil not found." >&2
fi

cat > "${PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>Proto-Mind</string>
  <key>CFBundleDisplayName</key>
  <string>Proto-Mind</string>
  <key>CFBundleExecutable</key>
  <string>Proto-Mind</string>
  <key>CFBundleIdentifier</key>
  <string>local.proto-mind.pyside</string>
  <key>CFBundleVersion</key>
  <string>2.1.0</string>
  <key>CFBundleShortVersionString</key>
  <string>2.1.0</string>
${ICON_PLIST_ENTRY}
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

cat > "${LAUNCHER}" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail

APP_EXEC_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${APP_EXEC_DIR}/../../../.." && pwd)"
OLLAMA_URL="${PROTO_MIND_OLLAMA_URL:-http://localhost:11434}"
LOG_FILE="/tmp/proto_mind_launcher.log"

: > "${LOG_FILE}"
echo "Proto-Mind launcher started: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}" >&2
echo "Project dir: ${PROJECT_DIR}" | tee -a "${LOG_FILE}" >&2
echo "Ollama URL: ${OLLAMA_URL}" | tee -a "${LOG_FILE}" >&2

show_error() {
  local message="$1"
  echo "Proto-Mind launcher error: ${message}" | tee -a "${LOG_FILE}" >&2
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"${message}\" with title \"Proto-Mind\" buttons {\"OK\"} default button \"OK\"" >/dev/null 2>&1 || true
  fi
}

if [ ! -d "${PROJECT_DIR}" ]; then
  show_error "Project directory not found: ${PROJECT_DIR}"
  exit 1
fi

cd "${PROJECT_DIR}"

PYTHON_CANDIDATES=(
  "${PROJECT_DIR}/.venv/bin/python"
  "$(command -v python3 || true)"
  "/opt/homebrew/opt/python@3.11/bin/python3"
  "/opt/homebrew/opt/python@3.11/bin/python3.11"
  "/opt/homebrew/bin/python3"
  "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
  "/usr/local/bin/python3"
  "/usr/bin/python3"
)

echo "Python candidates:" | tee -a "${LOG_FILE}" >&2
LOGGED_CANDIDATES_TEXT="|"
for candidate in "${PYTHON_CANDIDATES[@]}"; do
  if [ -z "${candidate}" ]; then
    continue
  fi
  case "${LOGGED_CANDIDATES_TEXT}" in
    *"|${candidate}|"*) continue ;;
  esac
  LOGGED_CANDIDATES_TEXT="${LOGGED_CANDIDATES_TEXT}${candidate}|"
  echo "  - ${candidate}" | tee -a "${LOG_FILE}" >&2
done

PYTHON_BIN=""
CHECKED_CANDIDATES_TEXT="|"

for candidate in "${PYTHON_CANDIDATES[@]}"; do
  if [ -z "${candidate}" ]; then
    continue
  fi
  case "${CHECKED_CANDIDATES_TEXT}" in
    *"|${candidate}|"*) continue ;;
  esac
  CHECKED_CANDIDATES_TEXT="${CHECKED_CANDIDATES_TEXT}${candidate}|"
  if [ ! -x "${candidate}" ]; then
    echo "Skipping Python candidate (not executable): ${candidate}" | tee -a "${LOG_FILE}" >&2
    continue
  fi
  if PROTO_MIND_PROJECT_DIR="${PROJECT_DIR}" "${candidate}" - <<'PY' >/dev/null 2>&1
import os
import sys
sys.path.insert(0, os.environ["PROTO_MIND_PROJECT_DIR"])
import proto_mind
import PySide6
PY
  then
    PYTHON_BIN="${candidate}"
    break
  fi
  echo "Skipping Python candidate (cannot import proto_mind and PySide6): ${candidate}" | tee -a "${LOG_FILE}" >&2
done

if [ -z "${PYTHON_BIN}" ]; then
  {
    echo "Could not find a Python that can import Proto-Mind and PySide6."
    echo "Candidates checked:"
    printf "%s\n" "${CHECKED_CANDIDATES_TEXT}" | tr '|' '\n' | while IFS= read -r candidate; do
      if [ -n "${candidate}" ]; then
        echo "  - ${candidate}"
      fi
    done
    echo "Suggested fixes:"
    echo "  cd ${PROJECT_DIR} && .venv/bin/python -m pip install PySide6"
    echo "  python3 -m pip install PySide6"
    echo "Launcher log: ${LOG_FILE}"
  } | tee -a "${LOG_FILE}" >&2
  show_error "Could not find a Python that can import Proto-Mind and PySide6. Try: python3 -m pip install PySide6. Details: ${LOG_FILE}"
  exit 1
fi

echo "Selected Python: ${PYTHON_BIN}" | tee -a "${LOG_FILE}" >&2

if ! "${PYTHON_BIN}" - "${OLLAMA_URL}" <<'PY' >/dev/null 2>&1
from sys import argv
from urllib.request import urlopen

url = argv[1].rstrip("/") + "/api/tags"
with urlopen(url, timeout=2) as response:
    if response.status >= 400:
        raise SystemExit(1)
PY
then
  show_error "Proto-Mind could not connect to Ollama at ${OLLAMA_URL}. Start Ollama and try again. Details: ${LOG_FILE}"
  exit 1
fi

echo "Ollama check: OK" | tee -a "${LOG_FILE}" >&2

export PROTO_MIND_REASONER=ollama
export PROTO_MIND_OLLAMA_MODEL="${PROTO_MIND_OLLAMA_MODEL:-qwen3:8b}"
export PROTO_MIND_OLLAMA_URL="${OLLAMA_URL}"

exec "${PYTHON_BIN}" -m proto_mind.pyside_app
LAUNCHER

chmod +x "${LAUNCHER}"

echo "Built: ${APP_DIR}"
