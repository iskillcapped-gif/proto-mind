#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="${PROJECT_DIR}/assets/proto_mind_native_icon.png"
OUTPUT="${1:-${PROJECT_DIR}/dist/ProtoMindCube.icns}"

if [ "$#" -gt 1 ] || [[ "${OUTPUT}" != *.icns ]]; then
  echo "Usage: scripts/build_native_icon.sh [output.icns]" >&2
  exit 1
fi
for tool in sips iconutil; do
  command -v "${tool}" >/dev/null || { echo "Native icon packaging requires macOS ${tool}." >&2; exit 1; }
done
if [ ! -f "${SOURCE}" ]; then
  echo "Native icon source is missing: ${SOURCE}" >&2
  exit 1
fi

INFO="$(sips -g format -g pixelWidth -g pixelHeight -g hasAlpha "${SOURCE}" | sed 's/^[[:space:]]*//')"
for property in 'format: png' 'pixelWidth: 1024' 'pixelHeight: 1024' 'hasAlpha: yes'; do
  if ! printf '%s\n' "${INFO}" | grep -Fxq "${property}"; then
    echo "Native icon must be a 1024 x 1024 PNG with real alpha transparency." >&2
    exit 1
  fi
done

TEMP_DIR="$(mktemp -d -t proto-mind-native-icon)"
trap 'rm -rf -- "$TEMP_DIR"' EXIT
ICONSET="${TEMP_DIR}/ProtoMindCube.iconset"
mkdir -p "${ICONSET}"
while read -r name pixels; do
  sips --resampleHeightWidth "${pixels}" "${pixels}" "${SOURCE}" --out "${ICONSET}/${name}" >/dev/null
done <<'SIZES'
icon_16x16.png 16
icon_16x16@2x.png 32
icon_32x32.png 32
icon_32x32@2x.png 64
icon_128x128.png 128
icon_128x128@2x.png 256
icon_256x256.png 256
icon_256x256@2x.png 512
icon_512x512.png 512
icon_512x512@2x.png 1024
SIZES
iconutil -c icns "${ICONSET}" -o "${TEMP_DIR}/ProtoMindCube.icns"
mkdir -p "$(dirname "${OUTPUT}")"
cp "${TEMP_DIR}/ProtoMindCube.icns" "${OUTPUT}"
printf 'Native icon: %s\n' "${OUTPUT}"
