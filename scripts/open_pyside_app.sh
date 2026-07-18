#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_PATH="$(pwd)/dist/Proto-Mind.app"

if [ ! -d "${APP_PATH}" ]; then
  echo "Proto-Mind.app is not built yet."
  echo "Run scripts/build_macos_app_launcher.sh first."
  exit 1
fi

open "${APP_PATH}"
