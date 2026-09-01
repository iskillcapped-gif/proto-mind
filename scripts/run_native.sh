#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
if [ ! -x "dist/Proto-Mind Native.app/Contents/MacOS/ProtoMindNative" ]; then
  scripts/build_native_app.sh
fi
open "$(pwd)/dist/Proto-Mind Native.app" --args "$@"
