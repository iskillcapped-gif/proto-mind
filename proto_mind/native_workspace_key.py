"""What identifies a selected project folder across restarts.

PM records a folder as ``{"path", "device", "inode"}``. The device number of an
APFS volume is assigned when the volume is mounted and can change after a reboot
or a macOS update, so a saved identity is the same folder when its path and inode
match. Compare saved identities with ``same_workspace`` and hash ``workspace_key``.
"""
from __future__ import annotations


def workspace_key(workspace):
    """The part of a folder identity that stays stable across restarts."""
    if isinstance(workspace, dict) and "path" in workspace and "inode" in workspace:
        return {"path": workspace["path"], "inode": workspace["inode"]}
    return workspace


def same_workspace(first, second) -> bool:
    return workspace_key(first) == workspace_key(second)
