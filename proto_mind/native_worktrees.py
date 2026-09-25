"""Create isolated, user-visible Git working folders without touching the source checkout."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4


def git(root, *arguments):
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "TMPDIR", "LANG"}}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=" + os.devnull, "-C", str(root), *arguments],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35)
    if result.returncode:
        raise ValueError("Git worktree operation failed. Inspect the repository; no cleanup, commit or retry was performed.")
    if len(result.stdout) > 1_000_000: raise ValueError("Git result exceeds its limit.")
    return result.stdout.decode().strip()


def main_checkout(root: Path) -> Path | None:
    """The main checkout of a linked Git worktree, or None.

    Reads Git's own files without running Git. The worktree's `.git` file must
    be registered by the main repository, which records it in `<admin>/gitdir`,
    so a crafted `.git` file cannot claim another project.
    """
    marker = root / ".git"
    try:
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 4096:
            return None
        text = marker.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir: "):
            return None
        admin = (root / text[len("gitdir: "):]).resolve(strict=True)
        common = (admin / (admin / "commondir").read_text(encoding="utf-8").strip()).resolve(strict=True)
        # Git may record either path relatively (worktree.useRelativePaths).
        registered = (admin / (admin / "gitdir").read_text(encoding="utf-8").strip()).resolve(strict=True)
        main = common.parent
        if (registered != marker.resolve(strict=True) or common.name != ".git" or admin.parent != common / "worktrees"
                or not common.is_dir() or common.is_symlink()):
            return None
        return main
    except (OSError, UnicodeError, ValueError):
        return None


def project_workspace(workspace: dict | None) -> dict | None:
    """Folder identity that project memory and notes belong to: a linked Git
    worktree, such as an isolated PM task, uses its main checkout's identity."""
    if not workspace:
        return workspace
    from proto_mind.native_work_sessions import workspace_identity
    main = main_checkout(Path(workspace["path"]))
    try:
        return workspace_identity(main) if main else workspace
    except OSError:
        return workspace


def create(reader, directory: Path):
    root = reader.root
    top = Path(git(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top != root: raise ValueError("Choose the Git repository root before creating an isolated task.")
    head = git(root, "rev-parse", "--verify", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40,64}", head): raise ValueError("The repository has no usable commit.")
    dirty = bool(git(root, "status", "--porcelain", "--untracked-files=normal"))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or directory.resolve() != directory.absolute(): raise ValueError("Managed worktree folder cannot be a symlink.")
    identifier = uuid4().hex
    path, branch = directory / identifier, "codex/pm-" + identifier[:12]
    git(root, "worktree", "add", "-b", branch, str(path), head)
    actual = Path(git(path, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if actual != path or git(path, "rev-parse", "HEAD") != head: raise ValueError("Created worktree could not be verified. Inspect it before continuing.")
    return {"path": str(path), "branch": branch, "base_commit": head, "source_project": str(root),
            "source_has_uncommitted_changes": dirty, "uncommitted_changes_copied": False,
            "notice": "Independent checkout at the captured commit. Source changes were not copied. Nothing was merged or deleted; review the task's diff before integration."}
