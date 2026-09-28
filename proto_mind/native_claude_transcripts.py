"""Claude Code session transcripts: where they are and where a resume continues.

Claude Code writes each session to projects/<cwd>/<session id>.jsonl in its
profile. PM reads a bounded tail of that file only to recognise its own resume
point; the only write is one metadata line that pins that point.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

TAIL_BYTES = 16 * 1024 * 1024


def transcript_files(profile: Path, session_id: str) -> list[Path]:
    """Regular transcript files of a session; Claude Code may prune old ones."""
    found = []
    try:
        with os.scandir(profile / "projects") as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    path = Path(entry.path, session_id + ".jsonl")
                    try:
                        if stat.S_ISREG(os.lstat(path).st_mode):
                            found.append(path)
                    except FileNotFoundError:
                        continue
    except (FileNotFoundError, NotADirectoryError):
        pass
    return found


def pin_resume_point(profile: Path, session_id: str, leaf: str) -> bool:
    """Makes the next resume of a session continue right after `leaf`, its last answer.

    Claude Code resumes from its last `last-prompt` record and the last entry it
    wrote. It sometimes writes an answer's parent, a `deferred_tools_record`
    attachment, after the answer and records that parent as the leaf. The chain it
    then loads ends before the answer, and --resume-session-at at the answer fails
    with "No message found". For a point chosen on purpose (a rewind or a fork)
    Claude Code writes an explicit `last-prompt` record; PM appends the same record
    when the transcript does not already end at the answer.

    Returns False when the answer is not among the recent entries or the file is
    not safe to update; the caller then resumes plainly.
    """
    files = transcript_files(profile, session_id)
    if len(files) != 1:
        return False
    try:
        descriptor = os.open(files[0], os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size == 0:
            return False
        start = max(0, info.st_size - TAIL_BYTES)
        tail = os.pread(descriptor, info.st_size - start, start)
        if not tail.endswith(b"\n"):
            return False  # A torn last line is Claude Code's to repair.
        lines = tail.split(b"\n")[:-1]
        if start:
            lines = lines[1:]  # The window may begin inside a line.
        recorded = explicit = None
        written_after = after_record = False
        for raw in reversed(lines):
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("uuid") == leaf:
                if entry.get("type") != "assistant" or entry.get("isSidechain"):
                    return False
                break
            if entry.get("type") == "last-prompt":
                if recorded is None:
                    recorded, explicit = entry.get("leafUuid") or "", entry.get("explicit") is True
            elif isinstance(entry.get("uuid"), str) and "parentUuid" in entry and not entry.get("isSidechain"):
                written_after = True
                after_record = after_record or recorded is None
        else:
            return False
        # Claude Code keeps an explicit record until another entry follows it; a plain one
        # names the answer only while the answer is also the last entry written.
        if recorded == leaf and not after_record and (explicit or not written_after):
            return True
        record = json.dumps({"type": "last-prompt", "leafUuid": leaf, "explicit": True, "sessionId": session_id},
                            separators=(",", ":")).encode() + b"\n"
        return os.write(descriptor, record) == len(record)
    except OSError:
        return False
    finally:
        os.close(descriptor)
