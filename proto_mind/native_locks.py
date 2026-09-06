"""Open persistent sidecar locks without racing first-time creation."""
from __future__ import annotations

import os


def open_sidecar(name: str, *, directory: int) -> int:
    # On macOS, concurrent O_CREAT opens can report ENOENT even though the
    # competing creator has published the file. Exclusive creation gives a
    # definite winner; everyone else opens that existing inode without O_CREAT.
    # Never recreate a sidecar that disappears after losing the creation race.
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        return os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
    except FileExistsError:
        return os.open(name, flags, dir_fd=directory)
