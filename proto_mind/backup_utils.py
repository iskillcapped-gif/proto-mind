from __future__ import annotations

import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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

    with tarfile.open(archive_path, "w:gz") as archive:
        for relative_path in included_paths:
            source = root / relative_path
            if source.exists():
                archive.add(source, arcname=relative_path)

    return BackupResult(archive_path=archive_path, included_paths=included_paths)


def format_backup_command(command: str, project_root: Path) -> str | None:
    if not is_backup_command(command):
        return None
    result = create_project_backup(project_root)
    return f"Memory backup created:\n  {result.archive_path}"


def _backup_sources(project_root: Path) -> list[str]:
    sources = ["proto_mind"]
    for filename in (
        "ARCHITECTURE_MAP_V2.md",
        ".env.example",
        "requirements.txt",
        "requirements-ui.txt",
        "pyproject.toml",
    ):
        if (project_root / filename).exists():
            sources.append(filename)
    return sources
