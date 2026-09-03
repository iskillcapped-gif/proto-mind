"""Local context manifests and evidence-linked text artifacts; never an executor."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from proto_mind.native_library import NativeLibrary
from proto_mind.native_workspace import MAX_CONTEXT_FILE_CHARS, MAX_CONTEXT_FILES, WorkspaceReader
from proto_mind.native_review import criteria_contract
from proto_mind.native_images import IMAGE_FIELDS, MAX_IMAGES, MAX_IMAGE_BYTES, MAX_TOTAL_IMAGE_BYTES
from proto_mind.native_pdf import validate_pdf_metadata, MAX_PDF_BYTES, MAX_SELECTED_PAGES, MAX_PAGE_CHARS
from proto_mind.native_knowledge import validate_knowledge_metadata
from proto_mind.native_private_records import _object as unique_object, _constant as invalid_constant


CONTEXT_SCHEMA = "proto_mind.native_context_manifest.v1"
ARTIFACT_SCHEMA = "proto_mind.native_artifacts.v1"
MAX_ARTIFACTS = 24
_SHA = re.compile(r"[a-f0-9]{64}")


def _stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def injection_state(root: Path) -> dict:
    """Read one fixed core setting using the same bounded no-follow library reader."""
    result = {"enabled": None, "state": "unknown", "path": str(root / "proto_mind/data/context_injection.json")}
    try:
        raw, _ = NativeLibrary(root)._read_bytes("context_injection.json")
        value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        if not isinstance(value, dict) or type(value.get("enabled")) is not bool:
            return result
        result.update(enabled=value["enabled"], state="enabled" if value["enabled"] else "disabled")
    except FileNotFoundError:
        result.update(enabled=False, state="default_disabled")
    except (OSError, ValueError, RecursionError):
        pass
    return result


def context_manifest(*, root: Path, text: str, history: list[dict], files: list[dict],
                     provider: str, model: str, effort: str, mode: str,
                     workspace: str | None, operator: bool = False, criteria: list[str] | None = None,
                     images: list[dict] | None = None, pdfs: list[dict] | None = None,
                     provider_thread: dict | None = None, knowledge_context: dict | None = None) -> dict:
    """Compact manifest of adapter inputs, not a fabricated preview of future recall."""
    history = [] if operator else history
    files = [] if operator else files
    validate_knowledge_metadata(knowledge_context)
    return {"schema": CONTEXT_SCHEMA, "generated_at": _stamp(), "read_only": True,
            "operator": operator, "provider": provider, "requested_model": model, "requested_effort": effort,
            "destination": "operator_local" if operator else {"codex": "openai_cloud", "ollama": "ollama_loopback", "mock": "mock_local"}[provider],
            "input": {"characters": len(text), "sha256": _hash(text)},
            "history": {"messages": len(history), "characters": sum(len(row["content"]) for row in history),
                        "limit_messages": 12, "limit_chars_per_message": 2000},
            "files": [{key: item[key] for key in ("path", "sha256", "included_chars", "truncated") if key in item} for item in files],
            "file_limits": {"count": MAX_CONTEXT_FILES, "characters_each": MAX_CONTEXT_FILE_CHARS},
            "images": [] if operator else [{key: item[key] for key in IMAGE_FIELDS if key in item} for item in images or []],
            "image_limits": {"count": MAX_IMAGES, "bytes_each": MAX_IMAGE_BYTES, "bytes_total": MAX_TOTAL_IMAGE_BYTES},
            "pdfs": [] if operator else deepcopy(validate_pdf_metadata(pdfs or [])),
            "pdf_limits": {"count": 1, "bytes_each": MAX_PDF_BYTES, "selected_pages": MAX_SELECTED_PAGES, "characters_per_page": MAX_PAGE_CHARS},
            "workspace": workspace, "memory_scope": "shared_core_not_workspace",
            "memory_root": str(root / "proto_mind/data"),
            "recall": "bypassed" if operator else "selected_at_send_not_previewed",
            "context_injection": injection_state(root), "access_mode": "operator" if operator else mode,
            "provider_thread": deepcopy(provider_thread),
            "success_criteria": criteria_contract([] if operator or criteria is None else criteria),
            "permission_granted": False, "private_reasoning_included": False,
            **({"knowledge_context": deepcopy(knowledge_context)} if knowledge_context and not operator else {})}


def context_preview(*, reader: WorkspaceReader | None, specifications: object, cloud_consent: bool, **values) -> dict:
    if not isinstance(specifications, list) or len(specifications) > MAX_CONTEXT_FILES:
        raise ValueError("Select at most three previewed files for one message.")
    rows, accepted, seen = [], [], set()
    if not values["operator"]:
        for spec in specifications:
            if (not isinstance(spec, dict) or not isinstance(spec.get("path"), str)
                    or len(spec["path"]) > 4096 or not isinstance(spec.get("sha256"), str)
                    or not _SHA.fullmatch(spec["sha256"])):
                raise ValueError("Context preview requires explicit file paths and SHA-256 values.")
            if spec["path"] in seen:
                raise ValueError("Duplicate file attachment.")
            seen.add(spec["path"])
            row = {"path": spec["path"], "expected_sha256": spec["sha256"], "current_sha256": "",
                   "state": "unavailable", "excerpt": "", "included_chars": 0, "truncated": False}
            try:
                if reader is None:
                    raise ValueError("Choose the original workspace before inspecting selected files.")
                source = reader.read_file(spec["path"])
                row.update(current_sha256=source["sha256"], size_bytes=source["size_bytes"], modified_at=source["modified_at"])
                if source["sha256"] != spec["sha256"]:
                    row.update(state="changed", reason="File changed; review and select it again. Its new bytes are not attached.")
                else:
                    content = source["preview"][:MAX_CONTEXT_FILE_CHARS]
                    item = {"path": source["path"], "sha256": source["sha256"], "content": content,
                            "included_chars": len(content), "truncated": source["characters"] > len(content)}
                    accepted.append(item)
                    row.update(state="ready", excerpt=content, included_chars=len(content), truncated=item["truncated"])
            except (OSError, ValueError):
                row["reason"] = "Unavailable or excluded source. No fallback read or automatic reselection."
            rows.append(row)
    manifest = context_manifest(files=accepted, **values)
    return {"schema": "proto_mind.native_context_preview.v1", "read_only": True, "no_execution": True,
            "manifest": manifest, "sources": rows,
            "history": [] if values["operator"] else deepcopy(values["history"]),
            "attachments_ready": all(row["state"] == "ready" for row in rows),
            "cloud_consent": cloud_consent,
            "excluded_attachment_count": len(specifications) if values["operator"] else 0,
            "excluded_criterion_count": len(values.get("criteria", [])) if values["operator"] else 0,
            "notes": ["Local inspection only. Send revalidates selected file hashes; this preview grants no permission.",
                      "Core recall/correction context is selected during the turn, not simulated here. See the completed-turn inspector.",
                      "Workspace binding does not isolate legacy core memory. Native project notes are scoped separately. Full Mac tools can access additional files after Send.",
                      "Mock does not understand attachments. No complete provider/system prompt or private reasoning is displayed."]}


def _artifact_id(run_id: str, tool_id: str, path: str) -> str:
    return "artifact_" + _hash(json.dumps([run_id, tool_id, path], ensure_ascii=False))[:24]


def artifact_candidates(record: dict) -> list[dict]:
    result = []
    for tool in record["tools"]:
        if tool.get("kind") != "fileChange":
            continue
        paths = tool.get("paths", [])
        if not isinstance(paths, list):
            continue
        for path in dict.fromkeys(path for path in paths[:8] if isinstance(path, str)):
            result.append({"id": _artifact_id(record["id"], tool["id"], path), "tool_id": tool["id"],
                           "reported_path": path, "tool_status": tool.get("status", "unknown")})
    return result


def _relative_artifact(path: str, reader: WorkspaceReader) -> str:
    if not path or any(ord(char) < 32 for char in path) or "[preview truncated]" in path:
        raise ValueError("Artifact path is incomplete.")
    value = PurePosixPath(path)
    if value.is_absolute():
        try:
            value = value.relative_to(PurePosixPath(str(reader.root)))
        except ValueError:
            raise ValueError("Observed file is outside the selected workspace.") from None
    # Actual access still goes through WorkspaceReader's no-follow, protected-root and text limits.
    return value.as_posix()


def capture_artifacts(record: dict, reader: WorkspaceReader | None) -> dict:
    """Capture hashes at normal turn completion; never scan or copy a whole workspace."""
    candidates = artifact_candidates(record)
    items = []
    for row in candidates[:MAX_ARTIFACTS]:
        item = {**row, "path": "", "sha256": "", "state": "unavailable", "media_type": "text/plain",
                "original_sha256": "", "verification": "not_assessed"}
        try:
            if reader is None or row["tool_status"] != "completed":
                raise ValueError("No completed, workspace-bound change observation.")
            path = _relative_artifact(row["reported_path"], reader)
            source = reader.read_file(path)
            item.update(path=source["path"], sha256=source["sha256"], state="captured", size_bytes=source["size_bytes"],
                        modified_at=source["modified_at"])
            item["original_sha256"] = next((old["sha256"] for old in record["sources"] if old["path"] == source["path"]), "")
        except (OSError, ValueError):
            pass
        items.append(item)
    return {"schema": ARTIFACT_SCHEMA, "run_id": record["id"], "captured_at": _stamp(),
            "capture_boundary": "turn_completion_not_tool_transaction", "total": len(candidates),
            "partial": len(candidates) > MAX_ARTIFACTS, "items": items}


def valid_artifact_snapshot(value: object, record: dict) -> bool:
    if (not isinstance(value, dict) or value.get("schema") != ARTIFACT_SCHEMA or value.get("run_id") != record["id"]
            or not isinstance(value.get("captured_at"), str) or not isinstance(value.get("items"), list)
            or len(value["items"]) > MAX_ARTIFACTS):
        return False
    ordered = artifact_candidates(record)
    candidates = {row["id"]: row for row in ordered}
    if (value.get("capture_boundary") != "turn_completion_not_tool_transaction"
            or type(value.get("total")) is not int or value["total"] != len(ordered)
            or value.get("partial") is not (len(ordered) > MAX_ARTIFACTS)
            or len(value["items"]) != min(len(ordered), MAX_ARTIFACTS)):
        return False
    seen = set()
    for row in value["items"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in seen:
            return False
        seen.add(row["id"])
        candidate = candidates.get(row["id"])
        if (candidate is None or any(row.get(key) != candidate[key] for key in ("tool_id", "reported_path", "tool_status"))
                or row.get("state") not in {"captured", "unavailable"} or row.get("verification") != "not_assessed"
                or row.get("media_type") != "text/plain"
                or not isinstance(row.get("path"), str) or len(row["path"]) > 4096
                or not isinstance(row.get("sha256"), str) or not isinstance(row.get("original_sha256"), str)
                or (row["original_sha256"] and not _SHA.fullmatch(row["original_sha256"]))):
            return False
        if row["state"] == "captured" and (row["tool_status"] != "completed" or not row["path"]
                                             or not _SHA.fullmatch(row["sha256"])):
            return False
        if row["state"] == "unavailable" and (row["sha256"] or row["path"] or row["original_sha256"]):
            return False
        expected_original = next((old["sha256"] for old in record["sources"] if old["path"] == row["path"]), "")
        if row["original_sha256"] != expected_original:
            return False
    return True


def artifact_page(record: dict) -> dict:
    snapshot = record.get("artifact_snapshot")
    items = deepcopy(snapshot["items"]) if snapshot else [
        {**row, "state": "not_captured", "path": "", "sha256": "", "original_sha256": "",
         "media_type": "text/plain", "verification": "not_assessed"}
        for row in artifact_candidates(record)[:MAX_ARTIFACTS]]
    commands = [deepcopy(row) for row in record["tools"] if row.get("kind") == "commandExecution"]
    zero = sum(row.get("status") == "completed" and type(row.get("exit_code")) is int and row["exit_code"] == 0 for row in commands)
    failed = sum(row.get("status") == "completed" and type(row.get("exit_code")) is int and row["exit_code"] != 0 for row in commands)
    return {"schema": "proto_mind.native_artifact_desk.v1", "read_only": True, "no_execution": True,
            "run_id": record["id"], "run_fingerprint": record["fingerprint"], "run_status": record["display_status"],
            "workspace": record.get("workspace"), "items": items, "commands": commands,
            "partial": len(artifact_candidates(record)) > MAX_ARTIFACTS,
            "captured_at": snapshot.get("captured_at", "") if snapshot else "",
            "verification": {"status": "not_assessed", "acceptance": record["acceptance"],
                             "criteria": "declared" if record.get("success_criteria") else "not_structured",
                             "exit_zero": zero, "exit_nonzero": failed, "unknown": len(commands) - zero - failed},
            "success_criteria": deepcopy(record.get("success_criteria")),
            "operator_reviews": deepcopy(record.get("operator_reviews", [])),
            "answer_preview": record.get("answer_preview", ""), "context_manifest": record.get("context_manifest"),
            "notes": ["Only observed file-change paths are listed. Shell-created or unreported files are not discovered.",
                      "Hashes describe bytes observed at turn completion, not exclusive authorship or a verified tool transaction.",
                      "Exit codes are observations, not proof that tests ran or the user's goal was achieved.",
                      "No original file copies, automatic restore, HTML execution or cloud request. Manual review is a separate explicit write."]}


def review_observations(record: dict, reader: WorkspaceReader | None) -> tuple[list[dict], bool]:
    page = artifact_page(record)
    observations = []
    for item in page["items"]:
        preview = artifact_preview(record, item["id"], reader)
        observations.append({"id": item["id"], "state": preview["state"], "expected_sha256": item["sha256"],
                             "current_sha256": (preview["current"] or {}).get("sha256", "")})
    return observations, not page["partial"] and "artifact_snapshot" in record


def artifact_preview(record: dict, artifact_id: str, reader: WorkspaceReader | None) -> dict:
    page = artifact_page(record)
    item = next((row for row in page["items"] if row["id"] == artifact_id), None)
    if item is None:
        raise ValueError("Unknown artifact for this saved run. Reopen the journal.")
    tool = next(row for row in record["tools"] if row["id"] == item["tool_id"])
    result = {"schema": "proto_mind.native_artifact_preview.v1", "read_only": True, "no_execution": True,
              "run_id": record["id"], "run_fingerprint": record["fingerprint"], "artifact": item,
              "diff_preview": tool.get("diff_preview", ""), "diff_scope": "whole_observed_tool_fragment",
              "state": "unavailable", "current": None}
    try:
        if reader is None:
            raise ValueError("Original workspace identity is not available.")
        path = _relative_artifact(item["reported_path"], reader)
        current = reader.read_file(path)
        if item["state"] == "captured" and current["path"] != item["path"]:
            raise ValueError("Artifact path differs from its capture metadata.")
        result.update(current=current, state="not_captured" if not item["sha256"] else
                      "current" if current["sha256"] == item["sha256"] else "changed")
    except (OSError, ValueError):
        result["reason"] = "Source missing, excluded, moved or unreadable. No fallback or file repair."
    return result
