from __future__ import annotations

import os
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4


BACKUP_COMMANDS = {"/memory backup", "/system checkpoint"}


@dataclass(frozen=True)
class BackupResult:
    archive_path: Path
    included_paths: list[str]


def is_backup_command(command: str) -> bool:
    return " ".join(command.strip().lower().split()) in BACKUP_COMMANDS


def create_project_backup(
    project_root: Path,
    *,
    backups_dir: Path | None = None,
    timestamp: str | None = None,
) -> BackupResult:
    root = project_root.resolve()
    destination = backups_dir.resolve() if backups_dir else root / "backups"
    destination.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = destination / f"proto_mind_backup_{stamp}.tar.gz"
    included_paths = _backup_sources(root)

    descriptor, temporary_name = tempfile.mkstemp(prefix=".proto_mind_backup_", suffix=".tmp", dir=destination)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            with tarfile.open(fileobj=output, mode="w:gz", dereference=False) as archive:
                for relative_path in included_paths:
                    source = root / relative_path
                    if source.exists():
                        archive.add(source, arcname=relative_path, filter=_backup_filter)
            output.flush()
            os.fsync(output.fileno())
        # Publish completed bytes without replacing another same-second checkpoint.
        while True:
            try:
                os.link(temporary_path, archive_path)
                break
            except FileExistsError:
                archive_path = destination / f"proto_mind_backup_{stamp}_{uuid4().hex[:8]}.tar.gz"
    finally:
        temporary_path.unlink(missing_ok=True)

    return BackupResult(archive_path=archive_path, included_paths=included_paths)


def format_backup_command(command: str, project_root: Path) -> str | None:
    if not is_backup_command(command):
        return None
    result = create_project_backup(project_root)
    return f"Memory backup created:\n  {result.archive_path}"


def _backup_sources(project_root: Path) -> list[str]:
    sources = [name for name in ("proto_mind", "native", "scripts", "docs", "assets", "contest", "evals")
               if (project_root / name).exists()]
    sources.extend(path.name for path in sorted(project_root.glob("*.md")) if path.is_file())
    for filename in (
        "LICENSE",
        ".gitignore",
        ".env.example",
        "requirements.txt",
        "requirements-ui.txt",
        "pyproject.toml",
    ):
        if (project_root / filename).exists():
            sources.append(filename)
    return sources


def _backup_filter(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
    parts = PurePosixPath(member.name).parts
    if any(part in {"__pycache__", ".build", ".swiftpm", ".DS_Store"} for part in parts):
        return None
    return None if member.name.endswith((".pyc", ".pyo")) else member
