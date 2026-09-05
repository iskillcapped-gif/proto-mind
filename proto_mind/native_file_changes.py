"""Bounded file-change display metadata, computed before output preview truncation."""
from __future__ import annotations

import re

MAX_FILE_CHANGES = 64
_HUNK = re.compile(r"^@@ -(\d{1,9})(?:,(\d{1,7}))? \+(\d{1,9})(?:,(\d{1,7}))? @@(?:.*)$")


def diff_line_counts(diff: object) -> tuple[int, int] | None:
    """Count complete unified hunks only; absent/malformed/binary diffs are unknown.

    These are observed edit counts, not a net comparison with a Git baseline.
    Hunk lengths distinguish file headers from source lines beginning with +/−.
    """
    if not isinstance(diff, str) or len(diff) > 4_000_000:
        return None
    additions = deletions = old_left = new_left = 0
    seen = False
    for line in diff.splitlines():
        match = _HUNK.match(line)
        if match:
            if old_left or new_left:
                return None
            old_left = int(match[2]) if match[2] is not None else 1
            new_left = int(match[4]) if match[4] is not None else 1
            seen = True
        elif line == "\\ No newline at end of file":
            continue
        elif old_left or new_left:
            if line.startswith("+"):
                additions += 1
                new_left -= 1
            elif line.startswith("-"):
                deletions += 1
                old_left -= 1
            elif line.startswith(" "):
                old_left -= 1
                new_left -= 1
            else:
                return None
            if min(old_left, new_left) < 0:
                return None
        elif line.startswith(("+", "-")) and not line.startswith(("+++ ", "--- ")):
            return None
        elif seen and line and not line.startswith(("diff --git ", "index ", "--- ", "+++ ")):
            return None
    return (additions, deletions) if seen and not (old_left or new_left) else None


def file_change_metadata(changes: list) -> dict:
    result = []
    path_bytes = 0
    for change in changes[:MAX_FILE_CHANGES]:
        if not isinstance(change, dict):
            continue
        path = change.get("path")
        if not isinstance(path, str) or not path or len(path) > 1024 or any(ord(c) < 32 for c in path):
            continue
        path_bytes += len(path.encode("utf-8"))
        if path_bytes > 8192:
            break
        row = {"path": path}
        counts = diff_line_counts(change.get("diff"))
        if counts is not None:
            row.update(additions=counts[0], deletions=counts[1])
        result.append(row)
    return {"file_changes": result, "file_changes_truncated": len(result) != len(changes)}
