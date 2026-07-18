from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from proto_mind.experience_ledger import (
    EXPERIENCE_EVENT_TYPES,
    EXPERIENCE_PREVIEW_MAX_CHARS,
    LIVE_EXPERIENCE_PERSISTENCE_ENABLED,
)


EXPERIENCE_CAPTURE_CONFIG_VERSION = 1
LIVE_CAPTURE_HOOK_INSTALLED = False
DEFAULT_CAPTURE_SETTINGS: dict[str, Any] = {
    "version": EXPERIENCE_CAPTURE_CONFIG_VERSION,
    "enabled": False,
    "mode": "preview_safe",
    "max_events_per_turn": 12,
    "persist_full_content": False,
    "write_path": "proto_mind/data/experience_ledger.jsonl",
}


@dataclass(frozen=True)
class ExperienceCaptureStatus:
    status: str
    project_root: str
    settings_path: str
    settings_exists: bool
    settings_source: str
    enabled_requested: bool
    effective_enabled: bool
    mode: str
    max_events_per_turn: int
    persist_full_content: bool
    write_path: str
    live_writer_installed: bool
    live_ledger_exists: bool
    issues: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperienceCaptureGate:
    """Read-only gate. It can describe capture, but has no activation or write method."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.settings_path = self.project_root / "proto_mind" / "data" / "experience_capture.json"
        self.live_ledger_path = self.project_root / "proto_mind" / "data" / "experience_ledger.jsonl"

    def status(self) -> ExperienceCaptureStatus:
        settings, source, issues, warnings = self._read_settings()
        enabled_requested = settings.get("enabled") is True
        if enabled_requested:
            warnings.append(
                "Capture was requested in settings, but no live writer hook is installed; "
                "effective capture remains disabled."
            )
        if self.live_ledger_path.exists():
            warnings.append(
                "A live Experience Ledger path exists while the capture hook is absent; "
                "inspect it manually before any future activation."
            )

        status = "ERROR" if issues else "WARN" if warnings else "OK"
        max_events = settings.get("max_events_per_turn")
        return ExperienceCaptureStatus(
            status=status,
            project_root=str(self.project_root),
            settings_path=str(self.settings_path),
            settings_exists=self.settings_path.exists(),
            settings_source=source,
            enabled_requested=enabled_requested,
            effective_enabled=(
                enabled_requested
                and LIVE_CAPTURE_HOOK_INSTALLED
                and LIVE_EXPERIENCE_PERSISTENCE_ENABLED
                and not issues
            ),
            mode=str(settings.get("mode", "invalid")),
            max_events_per_turn=(max_events if isinstance(max_events, int) else 0),
            persist_full_content=settings.get("persist_full_content") is True,
            write_path=str(settings.get("write_path", "")),
            live_writer_installed=LIVE_CAPTURE_HOOK_INSTALLED,
            live_ledger_exists=self.live_ledger_path.exists(),
            issues=issues,
            warnings=warnings,
        )

    def preview(self) -> dict[str, Any]:
        status = self.status()
        return {
            "status": status.status,
            "would_capture": status.effective_enabled,
            "reason": self._capture_reason(status),
            "event_schema_version": 1,
            "event_types": sorted(EXPERIENCE_EVENT_TYPES),
            "max_events_per_turn": status.max_events_per_turn,
            "content_preview_max_chars": EXPERIENCE_PREVIEW_MAX_CHARS,
            "full_content_allowed": False,
            "write_path": status.write_path,
            "live_writer_installed": status.live_writer_installed,
            "mutation_performed": False,
        }

    def doctor(self) -> ExperienceCaptureStatus:
        return self.status()

    def _read_settings(self) -> tuple[dict[str, Any], str, list[str], list[str]]:
        if not self.settings_path.exists():
            return dict(DEFAULT_CAPTURE_SETTINGS), "safe_defaults_missing_file", [], []
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return dict(DEFAULT_CAPTURE_SETTINGS), "invalid_file", [f"Settings are unreadable: {exc}."], []
        if not isinstance(raw, dict):
            return dict(DEFAULT_CAPTURE_SETTINGS), "invalid_file", ["Settings root must be a JSON object."], []

        settings = dict(DEFAULT_CAPTURE_SETTINGS)
        settings.update(raw)
        issues: list[str] = []
        warnings: list[str] = []
        if settings.get("version") != EXPERIENCE_CAPTURE_CONFIG_VERSION:
            issues.append("Unsupported capture settings version.")
        if not isinstance(settings.get("enabled"), bool):
            issues.append("enabled must be boolean.")
        if settings.get("mode") != "preview_safe":
            issues.append("Only mode=preview_safe is recognized by the disabled gate.")
        max_events = settings.get("max_events_per_turn")
        if not isinstance(max_events, int) or isinstance(max_events, bool) or not 1 <= max_events <= 50:
            issues.append("max_events_per_turn must be an integer from 1 to 50.")
        if settings.get("persist_full_content") is not False:
            issues.append("persist_full_content must remain false.")
        if settings.get("write_path") != DEFAULT_CAPTURE_SETTINGS["write_path"]:
            issues.append("Alternate Experience Ledger write paths are not allowed by this gate.")
        unknown_keys = sorted(set(raw) - set(DEFAULT_CAPTURE_SETTINGS))
        if unknown_keys:
            warnings.append("Unknown settings keys are ignored: " + ", ".join(unknown_keys) + ".")
        return settings, "local_file", issues, warnings

    @staticmethod
    def _capture_reason(status: ExperienceCaptureStatus) -> str:
        if status.issues:
            return "settings_invalid_fail_closed"
        if not status.enabled_requested:
            return "disabled_by_default"
        if not status.live_writer_installed:
            return "live_writer_hook_absent"
        if not LIVE_EXPERIENCE_PERSISTENCE_ENABLED:
            return "live_persistence_policy_disabled"
        return "eligible"


def format_experience_capture_status(gate: ExperienceCaptureGate) -> str:
    status = gate.status()
    lines = [
        "Proto-Mind Experience Capture Gate v1",
        f"Status: {status.status}",
        f"project_root: {status.project_root}",
        f"settings_path: {status.settings_path}",
        f"settings_exists: {str(status.settings_exists).lower()}",
        f"settings_source: {status.settings_source}",
        f"enabled_requested: {str(status.enabled_requested).lower()}",
        f"effective_enabled: {str(status.effective_enabled).lower()}",
        f"mode: {status.mode}",
        f"live_writer_installed: {str(status.live_writer_installed).lower()}",
        f"live_ledger_exists: {str(status.live_ledger_exists).lower()}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in status.issues)
    lines.extend(f"- WARN: {warning}" for warning in status.warnings)
    if not status.issues and not status.warnings:
        lines.append("- Capture is safely disabled; no live writer or ledger file is present.")
    lines.append("- Read-only report: no config initialization, event capture, or store write occurred.")
    return "\n".join(lines)


def format_experience_capture_preview(gate: ExperienceCaptureGate) -> str:
    preview = gate.preview()
    lines = [
        "Proto-Mind Experience Capture Preview v1",
        f"Status: {preview['status']}",
        f"would_capture: {str(preview['would_capture']).lower()}",
        f"reason: {preview['reason']}",
        f"live_writer_installed: {str(preview['live_writer_installed']).lower()}",
        f"max_events_per_turn: {preview['max_events_per_turn']}",
        f"content_preview_max_chars: {preview['content_preview_max_chars']}",
        "event_types:",
    ]
    lines.extend(f"- {event_type}" for event_type in preview["event_types"])
    lines.extend(
        [
            "Boundary:",
            "- No normal prompt was processed and no event was captured.",
            "- No full content, Context Injection payload, config, ledger, or core store was written.",
            "- mutation_performed: false",
        ]
    )
    return "\n".join(lines)


def format_experience_capture_doctor(gate: ExperienceCaptureGate) -> str:
    status = gate.doctor()
    lines = [
        "Proto-Mind Experience Capture Doctor v1",
        f"Status: {status.status}",
        f"settings: {status.settings_source}",
        f"enabled_requested: {str(status.enabled_requested).lower()}",
        f"effective_enabled: {str(status.effective_enabled).lower()}",
        f"live_writer_installed: {str(status.live_writer_installed).lower()}",
        f"live_persistence_policy: {'enabled' if LIVE_EXPERIENCE_PERSISTENCE_ENABLED else 'disabled'}",
        f"live_ledger_exists: {str(status.live_ledger_exists).lower()}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in status.issues)
    lines.extend(f"- WARN: {warning}" for warning in status.warnings)
    if not status.issues and not status.warnings:
        lines.extend(
            [
                "- Missing config resolves to safe disabled defaults.",
                "- No activation, enable, append, repair, or migration method is exposed.",
                "- Privacy and temporary-store policies remain fail closed.",
            ]
        )
    lines.append("- Doctor is read-only and performs no capture or file initialization.")
    return "\n".join(lines)


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    gate = ExperienceCaptureGate(project_root)
    print(format_experience_capture_status(gate))
    print()
    print(format_experience_capture_preview(gate))
    print()
    print(format_experience_capture_doctor(gate))
    return 0 if gate.doctor().status != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
