#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Do not change the operator's xcode-select or the Mac app's stable SDK choice.
if [[ -z "${DEVELOPER_DIR:-}" && -d /Applications/Xcode.app/Contents/Developer ]]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi
if ! xcrun --sdk iphonesimulator --show-sdk-path >/dev/null 2>&1; then
  echo 'Install and open Xcode, then install its iOS platform. Command Line Tools alone cannot build an iPhone app.' >&2
  exit 1
fi
xcodebuild -project ios/ProtoMindRemote.xcodeproj -scheme ProtoMindRemote \
  -configuration Debug -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath ios/build -jobs 2 CODE_SIGN_IDENTITY=- build
