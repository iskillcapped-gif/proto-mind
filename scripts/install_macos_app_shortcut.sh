#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT_DIR="$(pwd)"
APP_PATH="${PROJECT_DIR}/dist/Proto-Mind.app"
TARGET_DIR="${HOME}/Desktop"
TARGET_PATH="${TARGET_DIR}/Proto-Mind.app"

if [ "${1:-}" = "--applications" ]; then
  TARGET_DIR="/Applications"
  TARGET_PATH="${TARGET_DIR}/Proto-Mind.app"
elif [ "${1:-}" != "" ]; then
  echo "Usage: scripts/install_macos_app_shortcut.sh [--applications]"
  exit 1
fi

if [ ! -d "${APP_PATH}" ]; then
  scripts/build_macos_app_launcher.sh
fi

if [ "${TARGET_DIR}" = "/Applications" ] && [ ! -w "${TARGET_DIR}" ]; then
  echo "Cannot write to /Applications without elevated permissions."
  echo "Use the default Desktop shortcut instead:"
  echo "  scripts/install_macos_app_shortcut.sh"
  echo "Or open directly:"
  echo "  open ${APP_PATH}"
  exit 1
fi

mkdir -p "${TARGET_DIR}"

if [ -e "${TARGET_PATH}" ] && [ ! -L "${TARGET_PATH}" ]; then
  echo "Refusing to replace non-symlink path: ${TARGET_PATH}"
  exit 1
fi

ln -sfn "${APP_PATH}" "${TARGET_PATH}"

if [ "${TARGET_DIR}" = "/Applications" ]; then
  echo "Proto-Mind Applications shortcut installed:"
else
  echo "Proto-Mind shortcut installed:"
fi
echo "${TARGET_PATH}"
