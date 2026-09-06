"""Disposable, offline acceptance for ordinary project-memory questions."""
from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from proto_mind.native_project_memory import NativeProjectMemory
from proto_mind.native_project_recall import ProjectRecall
from proto_mind.native_work_sessions import workspace_identity


def file_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def evaluate(corpus: dict) -> dict:
    with TemporaryDirectory(prefix="proto-recall-quality-") as temporary:
        base = Path(temporary).resolve()
        root, state, workspace = base / "core", base / "private", base / "workspace"
        data = root / "proto_mind/data"
        data.mkdir(parents=True)
        (data / "context_injection.json").write_text('{"enabled":false}\n')
        workspace.mkdir()
        other = base / "other"
        other.mkdir()
        conversation = str(uuid4())
        memory = NativeProjectMemory(root, state, conversation, workspace_identity(workspace))
        saved = {}
        for spec in corpus["notes"]:
            target = memory if spec.get("scope") != "other" else NativeProjectMemory(
                root, state, conversation, workspace_identity(other))
            note = {"kind": spec.get("kind", "project_fact"), "content": spec["content"],
                    "basis": spec.get("basis", "Synthetic explicit operator note."),
                    "supersedes_id": saved[spec["supersedes"]]["id"] if spec.get("supersedes") else ""}
            preview = target.preview(note)
            saved[spec["key"]] = target.save({"note": note,
                "preview_fingerprint": preview["preview_fingerprint"],
                "confirmation_token": preview["confirmation_token"], "acknowledge_operator_note": True})["item"]
            if spec.get("archived"):
                params = {"record_id": saved[spec["key"]]["id"],
                          "record_hash": saved[spec["key"]]["record_hash"], "action": "archive"}
                preview = target.preview_state(params)
                target.save_state(params | {"preview_fingerprint": preview["preview_fingerprint"],
                    "confirmation_token": preview["confirmation_token"], "acknowledge_memory_change": True})
        names = {value["id"]: key for key, value in saved.items()}
        before = file_hashes(base)
        results = []
        for case in corpus["cases"]:
            auto = ProjectRecall(root, state, conversation=conversation, workspace=workspace_identity(workspace),
                                 text=case["query"], mode="chat")
            manual = memory.listing(query=case["query"])
            expected = set(case["expected"])
            for mode, items in (("automatic", auto.notes), ("library", manual["items"])):
                selected = [names[row["id"]] for row in items]
                actual = set(selected)
                results.append({"id": case["id"], "mode": mode, "expected": sorted(expected),
                                "selected": selected, "pass": actual == expected,
                                "true_positive": len(actual & expected), "false_positive": len(actual - expected),
                                "false_negative": len(expected - actual)})
        if file_hashes(base) != before:
            raise AssertionError("Recall evaluation wrote to disposable notes, core or private state")
        modes = {}
        for mode in ("automatic", "library"):
            rows = [row for row in results if row["mode"] == mode]
            tp = sum(row["true_positive"] for row in rows)
            fp = sum(row["false_positive"] for row in rows)
            fn = sum(row["false_negative"] for row in rows)
            modes[mode] = {"passed": sum(row["pass"] for row in rows), "cases": len(rows),
                           "precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
                           "recall": round(tp / (tp + fn), 4) if tp + fn else 1.0,
                           "false_positive": fp, "false_negative": fn}
        return {"modes": modes, "state_byte_stable": True, "results": results,
                "scope": "Synthetic local selection only; no provider generation or general semantic-quality claim."}
