"""Discover the installed OpenAI Computer Use service without bundling it.

Proto-Mind only exposes this optional runtime to an explicitly granted Full Mac
turn.  Discovery is fail-closed: the canonical app and nested CLI must retain
their OpenAI Developer ID signatures and expected bundle identifiers.
"""
from __future__ import annotations

import os
from pathlib import Path
import plistlib
import subprocess
import sys


OPENAI_TEAM_ID = "2DC432GLL2"
SERVICE_BUNDLE_ID = "com.openai.sky.CUAService"
CLIENT_BUNDLE_ID = "com.openai.sky.CUAService.cli"
SERVER_NAME = "computer-use"
COMPUTER_USE_TOOLS = frozenset({
    "get_app_state", "list_apps", "click", "set_value", "type_text",
    "press_key", "scroll", "drag", "select_text", "perform_secondary_action",
})
REQUIRED_COMPUTER_USE_TOOLS = frozenset({"get_app_state", "click", "type_text", "press_key", "scroll"})


def _paths(home: Path) -> tuple[Path, Path, Path]:
    service = home / ".codex" / "computer-use" / "Codex Computer Use.app"
    client_app = service / "Contents" / "SharedSupport" / "SkyComputerUseClient.app"
    command = client_app / "Contents" / "MacOS" / "SkyComputerUseClient"
    return service, client_app, command


def _signature(app: Path, runner) -> str:
    verified = runner(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if verified.returncode != 0:
        return ""
    described = runner(
        ["/usr/bin/codesign", "-dv", "--verbose=4", str(app)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if described.returncode != 0:
        return ""
    return (described.stdout or "") + "\n" + (described.stderr or "")


def discover_computer_use(*, home: Path | None = None, runner=subprocess.run,
                          platform: str | None = None) -> dict:
    """Return a private capability record; ``command`` is never sent to the UI."""
    platform = sys.platform if platform is None else platform
    base = Path.home() if home is None else Path(home)
    result = {
        "available": False,
        "provider": "openai_signed_local_service",
        "version": "",
        "reason": "OpenAI Computer Use is not available on this Mac.",
    }
    if platform != "darwin":
        result["reason"] = "OpenAI Computer Use is available only on supported macOS installations."
        return result
    service, client_app, command = _paths(base)
    try:
        if (not service.is_dir() or not client_app.is_dir() or not command.is_file()
                or service.is_symlink() or client_app.is_symlink() or command.is_symlink()
                or service.resolve(strict=True) != service.absolute()
                or client_app.resolve(strict=True) != client_app.absolute()
                or command.resolve(strict=True) != command.absolute()
                or not os.access(command, os.X_OK)):
            return result
        with (service / "Contents" / "Info.plist").open("rb") as handle:
            service_info = plistlib.load(handle)
        with (client_app / "Contents" / "Info.plist").open("rb") as handle:
            client_info = plistlib.load(handle)
        if (service_info.get("CFBundleIdentifier") != SERVICE_BUNDLE_ID
                or client_info.get("CFBundleIdentifier") != CLIENT_BUNDLE_ID):
            result["reason"] = "Computer Use bundle identity could not be verified."
            return result
        for app, bundle_id in ((service, SERVICE_BUNDLE_ID), (client_app, CLIENT_BUNDLE_ID)):
            signature = _signature(app, runner)
            if (f"Identifier={bundle_id}" not in signature
                    or f"TeamIdentifier={OPENAI_TEAM_ID}" not in signature
                    or "Authority=Developer ID Application: OpenAI OpCo, LLC" not in signature):
                result["reason"] = "Computer Use code signature could not be verified."
                return result
        version = service_info.get("CFBundleShortVersionString")
        if not isinstance(version, str) or not version or len(version) > 80:
            result["reason"] = "Computer Use version metadata is invalid."
            return result
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException, subprocess.SubprocessError):
        return result
    return {
        "available": True,
        "provider": "openai_signed_local_service",
        "version": version,
        "reason": "Installed OpenAI Computer Use service verified.",
        "command": str(command),
    }


def public_computer_use_capability(capability: dict | None = None) -> dict:
    source = discover_computer_use() if capability is None else capability
    return {
        "available": source.get("available") is True,
        "provider": "openai_signed_local_service",
        "version": source.get("version", "") if isinstance(source.get("version"), str) else "",
        "reason": source.get("reason", "") if isinstance(source.get("reason"), str) else "",
        "scope": "explicit_full_access_turn_only",
        "persistent_grant": False,
        "stores_screenshots": False,
    }


def validate_computer_use_status(response: object) -> set[str]:
    """Validate the exact single MCP server/tool surface before a model turn."""
    if not isinstance(response, dict) or response.get("nextCursor") not in {None, ""}:
        raise ValueError("Computer Use inventory is incomplete.")
    rows = response.get("data")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Computer Use is not the only configured MCP server.")
    row = rows[0]
    tools = row.get("tools")
    # Before a thread exists the app-server reports a validated inventory with
    # runtimeStatus=null. `required=true` still makes startup failures fatal.
    if (row.get("name") != SERVER_NAME or row.get("runtimeStatus") not in {None, "connected"}
            or not isinstance(tools, dict)):
        raise ValueError("Computer Use did not expose a usable runtime inventory.")
    names = {name for name in tools if isinstance(name, str)}
    if not REQUIRED_COMPUTER_USE_TOOLS.issubset(names) or not names.issubset(COMPUTER_USE_TOOLS):
        raise ValueError("Computer Use exposed an unexpected or incomplete tool set.")
    return names
