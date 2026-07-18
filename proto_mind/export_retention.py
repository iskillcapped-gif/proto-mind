from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proto_mind.data_integrity import EXPORT_DIRS


MANY_FILES_THRESHOLD = 50
LARGE_DIRECTORY_BYTES = 50 * 1024 * 1024
KEEP_NEWEST_SUGGESTION = 10

_FRESH_EXPORT_COMMANDS = {
    "context_packs": "/context export",
    "context_prompts": "/context prompt-export",
    "consolidation": "/consolidation export",
    "consolidation_queue": "/consolidation queue-export",
    "action_queue": "/action queue-export",
    "proto_snapshots": "/proto snapshot-export",
    "proto_snapshot_diffs": "/proto snapshot-diff-export-latest",
}


def format_exports_command(command: str, *, project_root: Path) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if not normalized.startswith("/exports"):
        return None
    retention = ExportRetention.from_project_root(project_root)
    if normalized == "/exports status":
        return retention.format_status()
    if normalized == "/exports inventory":
        return retention.format_inventory()
    if normalized == "/exports cleanup-preview":
        return retention.format_cleanup_preview()
    if normalized == "/exports doctor":
        return retention.format_doctor()
    return "Usage:\n  /exports status\n  /exports inventory\n  /exports cleanup-preview\n  /exports doctor"


class ExportRetention:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.exports_root = project_root / "proto_mind" / "exports"

    @classmethod
    def from_project_root(cls, project_root: Path) -> "ExportRetention":
        return cls(project_root)

    def inventory(self) -> list[dict[str, Any]]:
        return [self._inspect_directory(name) for name in EXPORT_DIRS]

    def format_status(self) -> str:
        inventory = self.inventory()
        present = sum(1 for item in inventory if item["exists"])
        total_files = sum(item["file_count"] for item in inventory)
        total_size = sum(item["size_bytes"] for item in inventory)
        lines = [
            "Export Retention Status",
            f"exports_root: {self.exports_root}",
            f"exports_root_exists: {self.exports_root.exists()}",
            f"known_directories: {len(EXPORT_DIRS)}",
            f"present_directories: {present}",
            f"missing_directories: {len(EXPORT_DIRS) - present}",
            f"total_files: {total_files}",
            f"approx_size_bytes: {total_size}",
            "",
            "Newest export per directory:",
        ]
        for item in inventory:
            newest = item["newest_file"]
            lines.append(f"- {item['name']}: {newest['path']} ({newest['modified_at']})" if newest else f"- {item['name']}: none")
        lines.extend(
            [
                "",
                "Available commands:",
                "- /exports status",
                "- /exports inventory",
                "- /exports cleanup-preview",
                "- /exports doctor",
                "",
                "Mutation policy:",
                "- Read-only status; no export or core files were changed.",
            ]
        )
        return "\n".join(lines)

    def format_inventory(self) -> str:
        lines = ["Export Inventory", f"exports_root: {self.exports_root}", ""]
        for item in self.inventory():
            lines.extend(
                [
                    f"{item['name']}:",
                    f"- path: {item['path']}",
                    f"- exists: {item['exists']}",
                    f"- files: {item['file_count']} (md={item['md_count']}, json={item['json_count']}, other={item['other_count']})",
                    f"- size_bytes: {item['size_bytes']}",
                    f"- oldest: {_file_line(item['oldest_file'])}",
                    f"- newest: {_file_line(item['newest_file'])}",
                    f"- newest_json_validation: {item['newest_json_validation']}",
                    "",
                ]
            )
        lines.extend(["Mutation policy:", "- Read-only inventory; no files were changed."])
        return "\n".join(lines)

    def format_cleanup_preview(self) -> str:
        inventory = self.inventory()
        lines = [
            "Export Cleanup Preview",
            "Status: REVIEW",
            "",
            "Global guidance:",
            "- No files will be deleted, moved, rewritten, compressed, or migrated.",
            "- Before manual cleanup, create a fresh relevant export and archive older reports outside the project.",
            f"- For snapshot and diff history, consider keeping at least the newest {KEEP_NEWEST_SUGGESTION} complete pairs.",
            "",
            "Directory suggestions:",
        ]
        for item in inventory:
            lines.append(f"{item['name']}:")
            suggestions = self._cleanup_suggestions(item)
            lines.extend(f"- {suggestion}" for suggestion in suggestions)
        lines.extend(
            [
                "",
                "Mutation policy:",
                "- Suggestions only; no retention policy was enforced and no filesystem action was performed.",
            ]
        )
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = [
            "Export Retention Doctor",
            f"Status: {report['status']}",
            f"exports_root: {self.exports_root}",
            "",
            "Summary:",
            f"- known directories: {len(EXPORT_DIRS)}",
            f"- present directories: {report['present_count']}",
            f"- total files: {report['total_files']}",
            f"- invalid JSON files: {report['invalid_json_count']}",
            f"- unreadable files: {report['unreadable_count']}",
            f"- orphan Markdown files: {report['orphan_md_count']}",
            f"- orphan JSON files: {report['orphan_json_count']}",
            "",
            "Findings:",
        ]
        if report["findings"]:
            lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        else:
            lines.append("- [OK] Export directories and JSON/Markdown pairs look healthy.")
        lines.extend(["", "Mutation policy:", "- Read-only diagnostics; no export or core files were changed."])
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        inventory = self.inventory()
        findings: list[dict[str, str]] = []
        if not self.exports_root.exists():
            findings.append({"severity": "WARN", "message": f"Exports root is missing: {self.exports_root}"})
        for item in inventory:
            name = item["name"]
            if not item["exists"]:
                findings.append({"severity": "WARN", "message": f"Known export directory is missing: {name}"})
                continue
            for path in item["invalid_json_files"]:
                findings.append({"severity": "WARN", "message": f"Invalid JSON export in {name}: {path}"})
            for path in item["unreadable_files"]:
                findings.append({"severity": "ERROR", "message": f"Unreadable export file in {name}: {path}"})
            for stem in item["orphan_md"]:
                findings.append({"severity": "WARN", "message": f"Orphan Markdown export in {name}: {stem}.md"})
            for stem in item["orphan_json"]:
                findings.append({"severity": "WARN", "message": f"Orphan JSON export in {name}: {stem}.json"})
            if item["file_count"] > MANY_FILES_THRESHOLD:
                findings.append(
                    {"severity": "WARN", "message": f"Large export file count in {name}: {item['file_count']} > {MANY_FILES_THRESHOLD}"}
                )
            if item["size_bytes"] > LARGE_DIRECTORY_BYTES:
                findings.append(
                    {"severity": "WARN", "message": f"Large export directory size in {name}: {item['size_bytes']} bytes"}
                )
            if name == "proto_snapshots" and item["json_count"] == 0:
                findings.append({"severity": "WARN", "message": "No Proto snapshot JSON exports are available."})
            if name == "proto_snapshot_diffs" and item["json_count"] == 0:
                findings.append({"severity": "WARN", "message": "No Proto snapshot diff JSON exports are available."})
        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if findings else "OK"
        return {
            "status": status,
            "findings": findings,
            "present_count": sum(1 for item in inventory if item["exists"]),
            "total_files": sum(item["file_count"] for item in inventory),
            "invalid_json_count": sum(len(item["invalid_json_files"]) for item in inventory),
            "unreadable_count": sum(len(item["unreadable_files"]) for item in inventory),
            "orphan_md_count": sum(len(item["orphan_md"]) for item in inventory),
            "orphan_json_count": sum(len(item["orphan_json"]) for item in inventory),
        }

    def _inspect_directory(self, name: str) -> dict[str, Any]:
        path = self.exports_root / name
        base = {
            "name": name,
            "path": str(path),
            "exists": path.exists() and path.is_dir(),
            "file_count": 0,
            "md_count": 0,
            "json_count": 0,
            "other_count": 0,
            "size_bytes": 0,
            "oldest_file": None,
            "newest_file": None,
            "newest_json_validation": "none",
            "invalid_json_files": [],
            "unreadable_files": [],
            "orphan_md": [],
            "orphan_json": [],
        }
        if not base["exists"]:
            return base
        files: list[tuple[Path, int, float]] = []
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            try:
                stat = item.stat()
            except OSError:
                base["unreadable_files"].append(str(item))
                continue
            files.append((item, stat.st_size, stat.st_mtime))
        base["file_count"] = len(files)
        base["size_bytes"] = sum(size for _, size, _ in files)
        base["md_count"] = sum(1 for item, _, _ in files if item.suffix.lower() == ".md")
        base["json_count"] = sum(1 for item, _, _ in files if item.suffix.lower() == ".json")
        base["other_count"] = base["file_count"] - base["md_count"] - base["json_count"]
        if files:
            oldest = min(files, key=lambda value: value[2])
            newest = max(files, key=lambda value: value[2])
            base["oldest_file"] = _file_metadata(oldest)
            base["newest_file"] = _file_metadata(newest)
        json_files = sorted(
            ((item, size, modified) for item, size, modified in files if item.suffix.lower() == ".json"),
            key=lambda value: value[2],
            reverse=True,
        )
        for item, _, _ in json_files:
            validation = _validate_json(item)
            if validation == "unreadable":
                base["unreadable_files"].append(str(item))
            elif validation == "invalid":
                base["invalid_json_files"].append(str(item))
        if json_files:
            base["newest_json_validation"] = _validate_json(json_files[0][0])
        md_stems = {_relative_stem(item, path) for item, _, _ in files if item.suffix.lower() == ".md"}
        json_stems = {_relative_stem(item, path) for item, _, _ in files if item.suffix.lower() == ".json"}
        base["orphan_md"] = sorted(md_stems - json_stems)
        base["orphan_json"] = sorted(json_stems - md_stems)
        return base

    def _cleanup_suggestions(self, item: dict[str, Any]) -> list[str]:
        if not item["exists"]:
            return ["No cleanup action: directory is absent and may be created by its owning exporter when needed."]
        suggestions: list[str] = []
        if item["newest_file"]:
            suggestions.append(f"Inspect newest report: {item['newest_file']['path']}")
        if item["oldest_file"] and item["oldest_file"] != item["newest_file"]:
            suggestions.append(f"Inspect oldest report before any archival decision: {item['oldest_file']['path']}")
        if item["invalid_json_files"]:
            suggestions.append(f"Review {len(item['invalid_json_files'])} invalid JSON export(s); do not rely on them as valid archives.")
        if item["orphan_md"] or item["orphan_json"]:
            suggestions.append(
                f"Review incomplete Markdown/JSON pairs: md_only={len(item['orphan_md'])}, json_only={len(item['orphan_json'])}."
            )
        if item["file_count"] > MANY_FILES_THRESHOLD or item["size_bytes"] > LARGE_DIRECTORY_BYTES:
            suggestions.append(
                f"Directory is large; consider keeping the newest {KEEP_NEWEST_SUGGESTION} complete pairs and archiving older exports outside the project."
            )
            suggestions.append(f"Create a fresh export first if appropriate: {_FRESH_EXPORT_COMMANDS[item['name']]}")
        if not (
            item["invalid_json_files"]
            or item["unreadable_files"]
            or item["orphan_md"]
            or item["orphan_json"]
            or item["file_count"] > MANY_FILES_THRESHOLD
            or item["size_bytes"] > LARGE_DIRECTORY_BYTES
        ):
            suggestions.append("No retention action suggested; directory is small and healthy.")
        return suggestions


def _file_metadata(value: tuple[Path, int, float]) -> dict[str, Any]:
    path, size, modified = value
    return {
        "path": str(path),
        "size_bytes": size,
        "modified_at": datetime.fromtimestamp(modified, UTC).isoformat(),
    }


def _file_line(value: dict[str, Any] | None) -> str:
    if not value:
        return "none"
    return f"{value['path']} ({value['modified_at']}, {value['size_bytes']} bytes)"


def _validate_json(path: Path) -> str:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return "unreadable"
    except json.JSONDecodeError:
        return "invalid"
    return "valid"


def _relative_stem(path: Path, root: Path) -> str:
    return str(path.relative_to(root).with_suffix(""))
