from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
from tempfile import NamedTemporaryFile
from typing import Any


PROVENANCE_SCHEMA_VERSION = 1
SUBMISSION_PERIOD_START = "2026-07-13T09:00:00-07:00"
SUBMISSION_DEADLINE = "2026-07-21T17:00:00-07:00"
OFFICIAL_RULES_URL = "https://openai.devpost.com/rules"
DEFAULT_BASELINE_ARCHIVE = "backups/proto_mind_backup_2026-07-11_05-02-19.tar.gz"
DEFAULT_OUTPUT_DIR = "contest/provenance"

_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "backups",
        "data",
        "dist",
        "exports",
        "logs",
    }
)
_ROOT_FILES = frozenset(
    {
        ".env.example",
        ".gitignore",
        "LICENSE",
        "LICENSE.md",
        "pyproject.toml",
        "requirements.txt",
        "requirements-ui.txt",
    }
)
_REGISTRY_PATTERN = re.compile(
    r"describes\s+(\d+)\s+command prefixes across\s+(\d+)\s+categories",
    re.IGNORECASE,
)
_TEST_PATTERN = re.compile(r"^\s{4}def test_", re.MULTILINE)


def build_contest_provenance(
    project_root: Path,
    baseline_archive: Path,
    output_dir: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    archive = Path(baseline_archive).resolve()
    destination = Path(output_dir).resolve()
    timestamp = generated_at or datetime.now(UTC).isoformat()

    baseline_content = read_relevant_archive_files(archive)
    current_content = read_relevant_project_files(root, excluded_output=destination)
    archive_hash = _hash_file(archive)

    baseline_manifest = _build_manifest(
        label="pre_contest_baseline",
        content=baseline_content,
        generated_at=timestamp,
        source={
            "kind": "timestamped_backup_archive",
            "path": _display_path(archive, root),
            "sha256": archive_hash,
            "filename_timestamp": "2026-07-11T05:02:19+03:00",
            "before_submission_period": True,
        },
    )
    _preserve_equivalent_baseline_timestamp(destination / "baseline_manifest.json", baseline_manifest)
    current_manifest = _build_manifest(
        label="current_contest_state",
        content=current_content,
        generated_at=timestamp,
        source={
            "kind": "working_tree",
            "path": ".",
            "baseline_archive_sha256": archive_hash,
        },
    )
    delta = _build_delta(baseline_manifest, current_manifest, timestamp)

    destination.mkdir(parents=True, exist_ok=True)
    outputs = {
        "baseline_manifest": destination / "baseline_manifest.json",
        "current_manifest": destination / "current_manifest.json",
        "contest_delta": destination / "contest_delta.json",
    }
    _atomic_json_write(outputs["baseline_manifest"], baseline_manifest)
    _atomic_json_write(outputs["current_manifest"], current_manifest)
    _atomic_json_write(outputs["contest_delta"], delta)
    return {
        "baseline_manifest": baseline_manifest,
        "current_manifest": current_manifest,
        "contest_delta": delta,
        "outputs": {key: str(path) for key, path in outputs.items()},
    }


def _preserve_equivalent_baseline_timestamp(path: Path, manifest: dict[str, Any]) -> None:
    """Keep the original evidence timestamp when the immutable baseline is unchanged."""
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(existing, dict):
        return
    existing_without_time = {key: value for key, value in existing.items() if key != "generated_at"}
    current_without_time = {key: value for key, value in manifest.items() if key != "generated_at"}
    if existing_without_time == current_without_time and isinstance(existing.get("generated_at"), str):
        manifest["generated_at"] = existing["generated_at"]


def read_relevant_archive_files(archive_path: Path) -> dict[str, bytes]:
    content: dict[str, bytes] = {}
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            normalized = _normalize_member_path(member.name)
            if not member.isfile() or normalized is None or not is_submission_relevant(normalized):
                continue
            source = archive.extractfile(member)
            if source is not None:
                content[normalized] = source.read()
    return dict(sorted(content.items()))


def read_relevant_project_files(
    project_root: Path,
    *,
    excluded_output: Path | None = None,
) -> dict[str, bytes]:
    root = Path(project_root).resolve()
    excluded = excluded_output.resolve() if excluded_output else None
    content: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if excluded and (resolved == excluded or excluded in resolved.parents):
            continue
        relative = path.relative_to(root).as_posix()
        if is_submission_relevant(relative):
            content[relative] = path.read_bytes()
    return dict(sorted(content.items()))


def is_submission_relevant(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or any(part in _EXCLUDED_PARTS for part in path.parts):
        return False
    if path.parts[:2] == ("contest", "provenance"):
        return False
    if len(path.parts) == 1:
        return path.name in _ROOT_FILES or path.suffix.lower() == ".md"
    if path.parts[0] == "proto_mind":
        return path.suffix.lower() == ".py" or path.as_posix() == "proto_mind/README.md"
    if path.parts[0] == "scripts":
        return path.suffix.lower() in {".py", ".sh"}
    if path.parts[0] == "assets":
        return path.suffix.lower() in {".svg", ".png", ".icns"}
    if path.parts[0] == "contest":
        return path.suffix.lower() == ".md"
    return False


def _build_manifest(
    *,
    label: str,
    content: dict[str, bytes],
    generated_at: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    files = [
        {
            "path": path,
            "category": _category(path),
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for path, payload in sorted(content.items())
    ]
    categories = Counter(item["category"] for item in files)
    docs = _decoded(content.get("ARCHITECTURE_MAP_V2.md", b""))
    registry_match = _REGISTRY_PATTERN.search(docs)
    tests = _decoded(content.get("proto_mind/tests/test_flow.py", b""))
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "label": label,
        "generated_at": generated_at,
        "contest": {
            "submission_period_start": SUBMISSION_PERIOD_START,
            "submission_deadline": SUBMISSION_DEADLINE,
            "official_rules": OFFICIAL_RULES_URL,
        },
        "scope": {
            "included": "source, tests, scripts, architecture/docs, safe setup metadata, and assets",
            "excluded": "data, exports, backups, logs, dist, caches, virtualenv, Git metadata, and generated provenance JSON",
        },
        "source": source,
        "metrics": {
            "file_count": len(files),
            "total_bytes": sum(item["size"] for item in files),
            "python_file_count": sum(item["path"].endswith(".py") for item in files),
            "test_method_count": len(_TEST_PATTERN.findall(tests)),
            "registry_command_count": int(registry_match.group(1)) if registry_match else None,
            "registry_category_count": int(registry_match.group(2)) if registry_match else None,
            "category_counts": dict(sorted(categories.items())),
        },
        "files": files,
    }


def _build_delta(
    baseline: dict[str, Any],
    current: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    old = {item["path"]: item for item in baseline["files"]}
    new = {item["path"]: item for item in current["files"]}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(path for path in set(old) & set(new) if old[path]["sha256"] != new[path]["sha256"])
    unchanged = sorted(path for path in set(old) & set(new) if old[path]["sha256"] == new[path]["sha256"])
    metric_names = (
        "file_count",
        "total_bytes",
        "python_file_count",
        "test_method_count",
        "registry_command_count",
        "registry_category_count",
    )
    metric_delta: dict[str, Any] = {}
    for name in metric_names:
        before = baseline["metrics"].get(name)
        after = current["metrics"].get(name)
        metric_delta[name] = {
            "baseline": before,
            "current": after,
            "delta": after - before if isinstance(before, int) and isinstance(after, int) else None,
        }
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "baseline_label": baseline["label"],
        "current_label": current["label"],
        "baseline_archive_sha256": baseline["source"]["sha256"],
        "classification": {
            "pre_existing": "Present in the July 11 baseline archive.",
            "contest_added": "Absent from baseline and present in current submission scope.",
            "contest_modified": "Present in both scopes with a changed SHA-256.",
            "removed_during_contest": "Present in baseline but absent from current submission scope.",
        },
        "metrics": metric_delta,
        "files": {
            "added": added,
            "changed": changed,
            "removed": removed,
            "unchanged": unchanged,
        },
        "summary": {
            "added_count": len(added),
            "changed_count": len(changed),
            "removed_count": len(removed),
            "unchanged_count": len(unchanged),
            "meaningful_extension_evidence": bool(added or changed),
        },
        "limitations": [
            "This is local equivalent evidence, not a third-party timestamp authority.",
            "Codex /feedback Session IDs and future dated Git commits should accompany this manifest.",
            "The manifest intentionally excludes private runtime stores and generated artifacts.",
        ],
    }


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _normalize_member_path(value: str) -> str | None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    normalized = path.as_posix().lstrip("./")
    return normalized or None


def _category(path: str) -> str:
    if path.startswith("proto_mind/tests/"):
        return "tests"
    if path.startswith("proto_mind/") and path.endswith(".py"):
        return "source"
    if path.startswith("scripts/"):
        return "scripts"
    if path.startswith("assets/"):
        return "assets"
    if path.endswith(".md"):
        return "documentation"
    return "setup"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decoded(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build local OpenAI Build Week provenance manifests.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline-archive", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    archive = args.baseline_archive or root / DEFAULT_BASELINE_ARCHIVE
    output = args.output_dir or root / DEFAULT_OUTPUT_DIR
    result = build_contest_provenance(root, archive, output)
    delta = result["contest_delta"]
    metrics = delta["metrics"]
    print("Proto-Mind Build Week Provenance Pack v1")
    print(f"Baseline archive SHA-256: {delta['baseline_archive_sha256']}")
    print(
        "Delta: "
        f"files +{delta['summary']['added_count']} changed={delta['summary']['changed_count']} "
        f"removed={delta['summary']['removed_count']}"
    )
    print(
        "Tests: "
        f"{metrics['test_method_count']['baseline']} -> {metrics['test_method_count']['current']}"
    )
    print(
        "Registry: "
        f"{metrics['registry_command_count']['baseline']} -> {metrics['registry_command_count']['current']} commands"
    )
    for label, path in result["outputs"].items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
