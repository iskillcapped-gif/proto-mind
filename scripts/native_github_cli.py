#!/usr/bin/env python3
"""Credential-free entry point for the explicitly connected GitHub CLI account."""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from proto_mind.native_github import GitHubConnection

if __name__ == "__main__":
    try:
        connection = GitHubConnection(Path(sys.argv[1]))
        connection.require_connection()
        executable = connection.executable
        if not executable:
            raise ValueError("GitHub CLI недоступен.")
        os.execve(executable, [executable, *sys.argv[2:]], connection.environment())
    except (ValueError, OSError, IndexError) as exc:
        print(str(exc) if isinstance(exc, ValueError) else "Не удалось запустить подключение GitHub.", file=sys.stderr)
        sys.exit(1)
