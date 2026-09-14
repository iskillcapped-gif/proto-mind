#!/usr/bin/env bash

# CLT 6.4 ships the macOS 27 SwiftUI interface without its State macro plugin.
# Use the installed stable SDK for this macOS 14+ app; never change xcode-select.
proto_mind_swift_sdk() {
  if [ -n "${PROTO_MIND_SWIFT_SDK:-}" ]; then
    printf '%s\n' "${PROTO_MIND_SWIFT_SDK}"
    return
  fi
  local selected_sdk
  selected_sdk="$(xcrun --sdk macosx --show-sdk-path)"
  selected_sdk="$(cd "${selected_sdk}" && pwd -P)"
  case "${selected_sdk}" in
    /Library/Developer/CommandLineTools/SDKs/MacOSX27*.sdk)
      if [ -d /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk ]; then
        selected_sdk=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk
      fi
      ;;
  esac
  printf '%s\n' "${selected_sdk}"
}

PROTO_MIND_SELECTED_SDK="$(proto_mind_swift_sdk)"
PROTO_MIND_SWIFT_BUILD_ARGS=(--package-path native --build-system native --sdk "${PROTO_MIND_SELECTED_SDK}" --jobs "${PROTO_MIND_NATIVE_JOBS:-2}")
