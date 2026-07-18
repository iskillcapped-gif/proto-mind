from __future__ import annotations

import sys
from typing import Any

MIN_PYTHON_VERSION = (3, 11)
RECOMMENDED_PYTHON = "/opt/homebrew/opt/python@3.11/bin/python3.11"


def is_supported_python(version_info: Any | None = None) -> bool:
    active_version = version_info or sys.version_info
    return (active_version.major, active_version.minor) >= MIN_PYTHON_VERSION


def format_python_version(version_info: Any | None = None) -> str:
    active_version = version_info or sys.version_info
    return f"{active_version.major}.{active_version.minor}.{active_version.micro}"


def format_unsupported_python_message(version_info: Any | None = None) -> str:
    return "\n".join(
        [
            "Proto-Mind requires Python 3.11+.",
            f"Current Python: {format_python_version(version_info)}",
            "Recommended:",
            f"{RECOMMENDED_PYTHON} -m proto_mind.main",
        ]
    )


def enforce_python_version() -> None:
    if is_supported_python():
        return
    print(format_unsupported_python_message(), file=sys.stderr)
    raise SystemExit(1)
