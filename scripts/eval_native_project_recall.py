#!/usr/bin/env python3
"""Opt-in subscription recall checks using synthetic notes and tool-free turns only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proto_mind.config import ProtoMindConfig
from proto_mind.native_bridge import NativeBackend
from proto_mind.native_codex import CodexSubscription
from proto_mind.native_project_memory import NativeProjectMemory
from proto_mind.native_work_sessions import workspace_identity


def hashes(root: Path) -> dict:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile-state", type=Path, default=Path.home() / "Library/Application Support/ProtoMindNative")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required; no generation or task was run.")
    profile = args.profile_state.resolve() / "codex-profile"
    if not profile.is_dir():
        parser.error("An existing Native subscription profile is required; no login or credential copy.")
    results = []

    class CountingSubscription(CodexSubscription):
        generations = 0

        def answer(self, *values, **kwargs):
            self.generations += 1
            return super().answer(*values, **kwargs)

        def agent_answer(self, *values, **kwargs):
            raise AssertionError("No Full Mac task in a recall evaluation.")

        def select_skills(self, *values, **kwargs):
            raise AssertionError("Local recall must not call a model selector.")

    def factory(state):
        subscription = CountingSubscription(state); subscription.home = profile
        return subscription

    with TemporaryDirectory(prefix="proto-project-recall-live-") as temporary:
        base = Path(temporary).resolve(); root = base / "core"; data = root / "proto_mind/data"
        workspace = base / "workspace"; other = base / "other-project"
        workspace.mkdir(); other.mkdir(); data.mkdir(parents=True)
        (data / "persistent_memory.json").write_text("[]\n")
        (data / "skills.jsonl").write_text("")
        (data / "context_injection.json").write_text('{"enabled":false}\n')
        core_before = hashes(data)
        backend = NativeBackend(root, base / "state", subscription_factory=factory)
        conversation = str(uuid4())
        memory = NativeProjectMemory(root, backend.state_dir, conversation, workspace_identity(workspace))

        def save(content, supersedes=""):
            note = {"kind": "decision", "content": content, "basis": "Explicit synthetic operator statement.", "supersedes_id": supersedes}
            preview = memory.preview(note)
            return memory.save({"note": note, "preview_fingerprint": preview["preview_fingerprint"],
                                "confirmation_token": preview["confirmation_token"], "acknowledge_operator_note": True})["item"]

        def run(name, text, expected, selected, *, chat=None, folder=workspace, automatic=True):
            params = {"conversation_id": chat or str(uuid4()), "workspace_root": str(folder), "provider": "codex",
                      "model": args.model, "reasoning_effort": "low", "cloud_consent": True, "access_mode": "chat",
                      "auto_skills": False, "auto_project_recall": automatic, "text": text}
            source_before = hashes(memory.store.directory)
            preview = backend.preview_context(params)
            expected_recall = preview["manifest"].get("knowledge_context", {}).get("project_recall")
            if expected_recall and expected_recall["source_snapshot_hash"]:
                params["expected_project_snapshot"] = expected_recall["source_snapshot_hash"]
            calls_before = backend.subscription.generations
            with patch.object(ProtoMindConfig, "from_env", return_value=ProtoMindConfig(data_dir=data)):
                output = backend.process(params, lambda _: None, "recall-" + name)
            answer = ((output.get("cognitive_turn") or {}).get("response") or output.get("text") or "").strip()
            report = (output.get("knowledge_context") or {}).get("project_recall")
            ids = report["selected_ids"] if report else []
            sources_unchanged = hashes(memory.store.directory) == source_before and hashes(data) == core_before and not hashes(workspace) and not hashes(other)
            correct_answer = answer == expected or name == "en_accent" and answer.casefold() == expected.casefold()
            passed = (correct_answer and ids == selected and report == expected_recall and sources_unchanged
                      and backend.subscription.generations == calls_before + 1 and output["agent_run"] is None
                      and output["work_session"]["verification"] == "not_assessed")
            result = {"case": name, "passed": passed, "answer": answer[:300], "expected": expected, "selected_count": len(ids),
                      "main_generations": backend.subscription.generations - calls_before, "sources_unchanged": sources_unchanged,
                      "provider_thread_state": (output.get("provider_thread") or {}).get("state")}
            results.append(result); print(json.dumps(result, ensure_ascii=False), flush=True)
            return passed

        try:
            port = save("Порт сервера: 4317.")
            accent = save("UI accent uses cobalt.")
            old = save("Deployment code is OLDALDER.")
            current = save("Deployment code is NEWCEDAR.", old["id"])
            cases = [
                ("ru_port", "Какой порт сервера указан в текущих заметках? Ответь только числом.", "4317", [port["id"]], {"chat": conversation}),
                ("en_accent", "What is the UI accent in the current project notes? Reply with only the color name.", "cobalt", [accent["id"]], {}),
                ("current_version", "What is the current deployment code? Reply only with that exact code.", "NEWCEDAR", [current["id"]], {}),
                ("unrelated", "What is the invoice routing number? If it is absent from THIS TURN's attached project notes, reply exactly UNKNOWN.", "UNKNOWN", [], {}),
                ("other_project", "What is the UI accent? If it is absent from THIS TURN's attached project notes, reply exactly UNKNOWN.", "UNKNOWN", [], {"folder": other}),
                ("disabled", "Какой порт сервера? Если в ЭТОМ сообщении нет прикреплённых заметок, ответь только UNKNOWN.", "UNKNOWN", [], {"automatic": False}),
            ]
            for name, text, expected, selected, options in cases:
                if not run(name, text, expected, selected, **options): break
            if all(row["passed"] for row in results):
                changed = save("Порт сервера: 4319.", port["id"])
                run("same_thread_updated_note", "Какой текущий порт сервера? Ответь только числом из актуальной заметки этого хода.",
                    "4319", [changed["id"]], chat=conversation)
            if all(row["passed"] for row in results):
                run("same_thread_disabled", "Для этой проверки используй только заметки, прикреплённые в ЭТОМ ходе, а не историю. Какой порт сервера? Если таких заметок нет, ответь только UNKNOWN.",
                    "UNKNOWN", [], chat=conversation, automatic=False)
        finally:
            backend.close()
        passed = len(results) == 8 and all(row["passed"] for row in results)
        print(json.dumps({"passed": passed, "cases": len(results), "main_generations": backend.subscription.generations,
                          "extra_selector_generations": 0, "personal_data_used": False, "core_unchanged": hashes(data) == core_before,
                          "automatic_learning": False, "tools_enabled": False}), flush=True)
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
