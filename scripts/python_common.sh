#!/usr/bin/env bash

proto_mind_project_dir() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "${script_dir}/.." >/dev/null 2>&1
  pwd
}

proto_mind_python_version_ok() {
  local candidate="$1"
  "${candidate}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

select_proto_mind_python() {
  local project_dir="${1:-$(proto_mind_project_dir)}"
  local candidates=(
    "${project_dir}/.venv/bin/python"
    "/opt/homebrew/opt/python@3.11/bin/python3.11"
    "/opt/homebrew/opt/python@3.11/bin/python3"
    "/opt/homebrew/bin/python3"
    "$(command -v python3 || true)"
  )
  local seen="|"
  local candidate
  for candidate in "${candidates[@]}"; do
    if [ -z "${candidate}" ]; then
      continue
    fi
    case "${seen}" in
      *"|${candidate}|"*) continue ;;
    esac
    seen="${seen}${candidate}|"
    if [ -x "${candidate}" ] && proto_mind_python_version_ok "${candidate}"; then
      printf "%s\n" "${candidate}"
      return 0
    fi
  done
  return 1
}
