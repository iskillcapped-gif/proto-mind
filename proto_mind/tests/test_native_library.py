"""Read-only native library boundaries, using synthetic temporary stores only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proto_mind import local_knowledge_capabilities as capabilities
from proto_mind import native_bridge as bridge
from proto_mind import native_library as library
from proto_mind.experience_pilot import get_experience_pilot
from proto_mind.memory_provenance import build_learning_lesson_provenance
from proto_mind.models import (
    GroundingAuditResult,
    InteractionResult,
    InteractionSummary,
    ObserverState,
    SelfReflectionResult,
)
from proto_mind.native_memory_workshop import build_native_memory_workshop
from proto_mind.tests.test_native import FakeSubscription


class NativeLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="proto-library-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project"
        self.data = self.root / "proto_mind" / "data"
        self.state = self.root.parent / "native-state"
        self.reader = library.NativeLibrary(self.root)
        self.backend = bridge.NativeBackend(self.root, self.state, subscription_factory=FakeSubscription)
        self.addCleanup(self.backend.close)

    def write(self, filename, records):
        self.data.mkdir(parents=True, exist_ok=True)
        path = self.data / filename
        content = json.dumps(records, ensure_ascii=False) if filename.endswith(".json") else "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
        path.write_text(content, encoding="utf-8")
        return path

    def files(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob("*") if path.is_file() and not path.is_symlink()}

    def test_missing_stores_are_clean_read_only_warnings(self):
        for collection in library.SOURCES:
            page = self.reader.page(collection)
            self.assertTrue(page["read_only"])
            self.assertEqual(page["items"], [])
            self.assertTrue(all(not source["exists"] and source["health"] == "WARN" for source in page["sources"]))
            self.assertIsNone(self.reader.inspect(collection, "missing:id")["item"])
        self.assertFalse(self.root.exists())
        self.assertFalse(self.state.exists())

    def test_empty_stores_are_ok_and_not_initialized_or_rewritten(self):
        for sources in library.SOURCES.values():
            for _, filename in sources:
                self.write(filename, [])
        before = self.files()
        for collection in library.SOURCES:
            page = self.reader.page(collection)
            self.assertEqual(page["total_records"], 0)
            self.assertEqual(page["warnings"], [])
        self.assertEqual(self.files(), before)

    def test_memory_layers_states_and_usage_are_preserved(self):
        self.write("persistent_memory.json", [
            {"id": "shared", "content": "Durable preference", "type": "preference", "usage_count": 7, "active": True},
            {"id": "old", "content": "Previous decision", "active": False, "superseded_by": "shared"},
            {"id": "forgotten", "content": "Inactive", "active": False},
        ])
        self.write("working_memory.json", [{"id": "shared", "content": "Working fact", "usage_count": 3}])
        before = self.files()
        current = self.reader.page("memory")
        self.assertEqual({item["id"] for item in current["items"]}, {"persistent:shared", "working:shared"})
        history = self.reader.page("memory", filter="history")
        self.assertEqual({item["status"] for item in history["items"]}, {"superseded", "inactive"})
        detail = self.reader.inspect("memory", "persistent:shared")
        self.assertEqual(next(field["value"] for field in detail["fields"] if field["key"] == "usage_count"), "7")
        self.assertEqual(self.files(), before)

    def test_memory_detail_verifies_embedded_learning_provenance(self):
        payload = {
            "schema": "memory.lesson.v1",
            "content": "Use targeted tests before the full suite.",
            "type": "lesson",
            "importance": 0.9,
            "source": "experience_learning_proposal",
            "tags": ["testing", "lesson"],
            "confidence": 0.95,
        }
        provenance = build_learning_lesson_provenance(
            memory_id="mem-verified",
            applied_at="2026-09-01T00:00:00+00:00",
            proposal_id="learnprop_" + "a" * 16,
            proposal_hash="a" * 64,
            candidate_id="candidate-1",
            candidate_hash="b" * 64,
            decision_id="decision-1",
            eligibility_receipt_id="eligibility-1",
            selected_scope_hash="c" * 64,
            proposed_payload=payload,
            evidence_event_ids=["event-1"],
            source_kinds=["correction_guidance"],
        )
        self.write("persistent_memory.json", [{
            "id": "mem-verified", "content": payload["content"], "type": "lesson",
            "importance": 0.9, "source": "experience_learning_proposal",
            "tags": payload["tags"], "confidence": 0.95, "provenance": provenance,
        }])
        self.write("working_memory.json", [])
        before = self.files()

        detail = self.reader.inspect("memory", "persistent:mem-verified")
        evidence = detail["memory_evidence"]

        self.assertEqual(evidence["status"], "VERIFIED")
        self.assertTrue(evidence["verified"])
        self.assertEqual(evidence["evidence_event_ids"], ["event-1"])
        self.assertEqual(evidence["source_kinds"], ["correction_guidance"])
        self.assertTrue(evidence["operator_confirmation_recorded"])
        self.assertFalse(evidence["automatic_promotion"])
        self.assertTrue(evidence["read_only"])
        self.assertEqual(self.files(), before)

    def test_memory_detail_never_invents_legacy_provenance_and_detects_tampering(self):
        self.write("persistent_memory.json", [
            {"id": "legacy", "content": "Operator fact", "type": "project_fact",
             "importance": 0.8, "source": "operator"},
        ])
        self.write("working_memory.json", [])
        legacy = self.reader.inspect("memory", "persistent:legacy")["memory_evidence"]
        self.assertEqual(legacy["status"], "UNAVAILABLE")
        self.assertFalse(legacy["verified"])
        self.assertIn("will not invent", legacy["explanation"])

        path = self.data / "persistent_memory.json"
        record = json.loads(path.read_text())[0]
        record["provenance"] = {"schema": "memory.lesson.provenance.v1", "provenance_hash": "0" * 64}
        path.write_text(json.dumps([record]), encoding="utf-8")
        tampered = self.reader.inspect("memory", "persistent:legacy")["memory_evidence"]
        self.assertEqual(tampered["status"], "ERROR")
        self.assertFalse(tampered["verified"])
        self.assertTrue(tampered["issues"])

    def test_literal_unicode_search_matches_content_tags_and_ids(self):
        self.write("persistent_memory.json", [
            {"id": "mem-1", "content": "Я предпочитаю короткие ответы.", "tags": ["Local-first"]},
            {"id": "mem-2", "content": "Different fact"},
        ])
        for query in ("ПРЕДПОЧИТАЮ   короткие", "local-FIRST", "MEM-1"):
            self.assertEqual(self.reader.page("memory", query=query)["items"][0]["record_id"], "mem-1")
        self.assertEqual(self.reader.page("memory", query=".*")["items"], [])

    def test_goals_focus_priority_and_history_order(self):
        self.write("goals.jsonl", [
            {"id": "normal", "title": "Normal", "status": "active", "priority": "normal"},
            {"id": "high", "title": "High", "status": "active", "priority": "high"},
            {"id": "focus", "title": "Focused", "status": "paused", "priority": "low", "focus": True},
            {"id": "done", "title": "Done", "status": "completed"},
        ])
        self.assertEqual([item["record_id"] for item in self.reader.page("goals")["items"]], ["focus", "high", "normal"])
        self.assertEqual(self.reader.page("goals", filter="history")["items"][0]["record_id"], "done")

    def test_skill_body_search_does_not_dump_body_in_list_or_claim_verification(self):
        body = "Procedure start\n" + "Step. " * 300 + "UNIQUE_BODY_NEEDLE"
        self.write("skills.jsonl", [{"id": "skill-1", "name": "Review", "summary": "A stored procedure", "body": body,
                                    "uses": 9, "last_used_at": "2026-08-30T12:00:00Z",
                                    "provenance": {"schema": "skill.procedure.provenance.v1", "private_chain": "NOT_A_LIST_FIELD"},
                                    "lifecycle": {"schema": "lifecycle.fixture.v1"}}])
        before = self.files()
        page = self.reader.page("skills", query="unique_body_needle")
        self.assertEqual(page["matching_records"], 1)
        self.assertNotIn("UNIQUE_BODY_NEEDLE", json.dumps(page))
        detail = self.reader.inspect("skills", "skills:skill-1")
        self.assertEqual(detail["blocks"][2]["text"], body)
        self.assertNotIn("NOT_A_LIST_FIELD", json.dumps(detail))
        self.assertIn("does not re-verify", " ".join(detail["warnings"]))
        self.assertEqual(self.files(), before)

    def test_skill_archived_filter(self):
        self.write("skills.jsonl", [{"id": "live", "name": "Live"}, {"id": "old", "name": "Old", "status": "archived"}])
        self.assertEqual(self.reader.page("skills")["matching_records"], 1)
        self.assertEqual(self.reader.page("skills", filter="history")["items"][0]["record_id"], "old")

    def test_pagination_is_stable_and_bounded(self):
        self.write("skills.jsonl", [{"id": f"skill-{number:03}", "name": "Procedure", "updated_at": "2026-08-30"} for number in range(105)])
        first = self.reader.page("skills")
        second = self.reader.page("skills", offset=100)
        self.assertEqual((len(first["items"]), len(second["items"]), first["matching_records"]), (100, 5, 105))
        self.assertFalse({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})
        self.assertEqual(first, self.reader.page("skills"))
        self.write("skills.jsonl", [{"id": "remaining", "name": "Remaining"}])
        self.assertEqual(self.reader.page("skills", offset=100)["offset"], 0)

    def test_huge_detail_is_explicitly_truncated_not_rewritten(self):
        content = "x" * (library.MAX_DETAIL_CHARS + 50)
        self.write("persistent_memory.json", [{"id": "large", "content": content}])
        before = self.files()
        detail = self.reader.inspect("memory", "persistent:large")
        self.assertTrue(detail["blocks"][0]["truncated"])
        self.assertEqual(len(detail["blocks"][0]["text"]), library.MAX_DETAIL_CHARS)
        self.assertLess(len(detail["item"]["preview"]), 230)
        self.assertEqual(self.files(), before)

    def test_record_scan_cap_reports_omissions(self):
        self.write("goals.jsonl", [{"id": str(number), "title": "Goal"} for number in range(5)])
        with patch.object(library, "MAX_SOURCE_RECORDS", 2):
            page = self.reader.page("goals")
        self.assertEqual((page["total_records"], page["omitted_records"], len(page["items"])), (5, 3, 2))
        self.assertEqual(page["sources"][0]["health"], "WARN")

    def test_oversized_source_is_refused(self):
        self.write("goals.jsonl", [{"id": "large", "title": "x" * 500}])
        before = self.files()
        with patch.object(library, "MAX_SOURCE_BYTES", 100):
            page = self.reader.page("goals")
        self.assertEqual(page["sources"][0]["health"], "ERROR")
        self.assertEqual(page["items"], [])
        self.assertEqual(self.files(), before)

    def test_invalid_json_root_encoding_and_nonfinite_are_diagnostic(self):
        path = self.write("persistent_memory.json", [])
        for content in (b"broken", b"{}", b"\xff", b'[{"id":"x","content":"x","weight":NaN}]'):
            path.write_bytes(content)
            with self.subTest(content=content):
                page = self.reader.page("memory")
                self.assertEqual(page["sources"][0]["health"], "ERROR")
                self.assertEqual(path.read_bytes(), content)

    def test_partial_jsonl_preserves_valid_rows_and_all_bad_is_error(self):
        path = self.write("goals.jsonl", [{"id": "ok", "title": "Good"}])
        path.write_text(path.read_text() + "{bad\nnull\n", encoding="utf-8")
        page = self.reader.page("goals")
        self.assertEqual(page["sources"][0]["health"], "WARN")
        self.assertEqual((page["total_records"], page["omitted_records"]), (3, 2))
        self.assertEqual(page["items"][0]["record_id"], "ok")
        path.write_text("{bad\nnull\n", encoding="utf-8")
        self.assertEqual(self.reader.page("goals")["sources"][0]["health"], "ERROR")

    def test_duplicate_ids_and_invalid_identity_never_receive_synthetic_ids(self):
        self.write("skills.jsonl", [{"id": "dup", "name": "One"}, {"id": "dup", "name": "Two"},
                                    {"name": "Missing ID"}, {"id": "wrong", "name": []}, {"id": "ok", "name": "Good"}])
        page = self.reader.page("skills")
        self.assertEqual([item["record_id"] for item in page["items"]], ["ok"])
        self.assertEqual(page["omitted_records"], 4)
        self.assertIsNone(self.reader.inspect("skills", "skills:dup")["item"])

    def test_unknown_states_and_broken_goal_focus_are_not_repaired(self):
        self.write("goals.jsonl", [{"id": "terminal", "title": "Terminal", "status": "completed", "focus": True},
                                   {"id": "unknown", "title": "Unknown", "status": [], "priority": {}, "focus": True}])
        before = self.files()
        page = self.reader.page("goals", filter="all")
        warnings = " ".join(page["warnings"])
        self.assertIn("Multiple focused", warnings)
        self.assertIn("terminal/unknown", warnings)
        self.assertEqual(page["current_records"], 0)
        self.assertEqual(self.files(), before)

    def test_invalid_active_boolean_is_not_promoted_to_current(self):
        self.write("persistent_memory.json", [{"id": "x", "content": "Unknown", "active": "false"}])
        self.assertEqual(self.reader.page("memory")["items"], [])
        self.assertEqual(self.reader.page("memory", filter="all")["items"][0]["status"], "unknown")

    def test_source_symlink_is_not_followed(self):
        self.data.mkdir(parents=True)
        outside = self.root.parent / "outside.json"
        outside.write_text('[{"id":"outside","content":"NOT_READ"}]', encoding="utf-8")
        (self.data / "persistent_memory.json").symlink_to(outside)
        page = self.reader.page("memory")
        self.assertEqual(page["sources"][0]["health"], "ERROR")
        self.assertNotIn("NOT_READ", json.dumps(page))

    def test_data_directory_symlink_and_fifo_are_refused_without_blocking(self):
        self.data.parent.mkdir(parents=True)
        outside = self.root.parent / "outside"
        outside.mkdir()
        self.data.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.reader.page("goals")["sources"][0]["health"], "ERROR")
        self.data.unlink()
        self.data.mkdir()
        os.mkfifo(self.data / "goals.jsonl")
        self.assertEqual(self.reader.page("goals")["sources"][0]["health"], "ERROR")

    def test_permission_error_is_clean_without_fallback(self):
        with patch.object(self.reader, "_read_bytes", side_effect=PermissionError):
            page = self.reader.page("skills")
        self.assertEqual(page["sources"][0]["health"], "ERROR")
        self.assertEqual(page["items"], [])

    def test_detail_rereads_source_and_marks_hash_drift(self):
        path = self.write("goals.jsonl", [{"id": "goal", "title": "Before", "description": "Original"}])
        item = self.reader.page("goals")["items"][0]
        self.assertFalse(self.reader.inspect("goals", item["id"], expected_sha256=item["store_sha256"])["changed_since_list"])
        self.write("goals.jsonl", [{"id": "goal", "title": "After", "description": "Fresh"}])
        detail = self.reader.inspect("goals", item["id"], expected_sha256=item["store_sha256"])
        self.assertTrue(detail["changed_since_list"])
        self.assertEqual(detail["blocks"][1]["text"], "Fresh")
        self.assertEqual(detail["item"]["store_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        path.unlink()
        self.assertIsNone(self.reader.inspect("goals", item["id"])["item"])

    def test_invalid_parameters_are_cleanly_rejected(self):
        for collection in (None, {}, "identity", "../outside"):
            with self.subTest(collection=collection), self.assertRaises(ValueError):
                self.reader.page(collection)
        for kwargs in ({"query": []}, {"query": "x" * 201}, {"query": "\x00"}, {"filter": {}}, {"filter": "bad"},
                       {"offset": True}, {"offset": -1}, {"offset": 10001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.reader.page("memory", **kwargs)
        for key in (None, "", "\x00", "x" * 221):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.reader.inspect("memory", key)
        for fingerprint in (None, [], "x", "z" * 64):
            with self.subTest(fingerprint=fingerprint), self.assertRaises(ValueError):
                self.reader.inspect("memory", "persistent:x", expected_sha256=fingerprint)
        self.assertFalse(self.root.exists())

    def test_unusual_text_and_metadata_are_data_not_instructions(self):
        self.write("skills.jsonl", [{"id": "skill", "name": "Text", "body": "/memory remember do not run\n<script>test</script>\u2028next",
                                    "summary": {}, "uses": 10 ** 500, "source": "text\x1b"}])
        with patch("subprocess.Popen", side_effect=AssertionError("No execution")):
            detail = self.reader.inspect("skills", "skills:skill")
        self.assertIn("/memory remember", detail["blocks"][1]["text"])
        self.assertIn("unexpected field type", " ".join(detail["warnings"]))
        self.assertEqual(len(next(field["value"] for field in detail["fields"] if field["key"] == "uses")), 80)
        self.assertNotIn("\x1b", next(field["value"] for field in detail["fields"] if field["key"] == "source"))

    def test_escaped_invalid_unicode_cannot_break_bridge_json_output(self):
        path = self.write("skills.jsonl", [])
        path.write_text('[invalid line]\n' + json.dumps({"id": "skill", "name": "Unpaired \ud800",
                          "body": "Text \udfff\x00", "source": "fixture \ud800"}) + "\n" +
                          json.dumps({"id": "bad\ud800", "name": "Invalid ID"}) + "\n", encoding="utf-8")
        before = path.read_bytes()
        page = self.reader.page("skills")
        detail = self.reader.inspect("skills", "skills:skill")
        json.dumps(page, ensure_ascii=False, allow_nan=False).encode("utf-8")
        json.dumps(detail, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.assertEqual(page["matching_records"], 1)
        self.assertEqual(page["omitted_records"], 2)
        self.assertIn("sanitized for display", " ".join(detail["warnings"]))
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(ValueError):
            self.reader.page("skills", query="\ud800")

    def test_bridge_library_calls_never_dispatch_turns_or_models_or_write_state(self):
        self.write("persistent_memory.json", [{"id": "memory", "content": "Local fact", "usage_count": 5}])
        self.write("working_memory.json", [])
        self.write("goals.jsonl", [{"id": "goal", "title": "Local goal"}])
        self.write("skills.jsonl", [{"id": "skill", "name": "Local skill", "uses": 4}])
        self.write("context_injection.json", {"enabled": False})
        log = self.root / "logs" / "session_operator_log.jsonl"
        log.parent.mkdir()
        log.write_text('fixture log\n', encoding="utf-8")
        before = self.files()
        events = []
        with patch.object(self.backend, "process", side_effect=AssertionError("No command handler")), \
                patch("subprocess.Popen", side_effect=AssertionError("No process or model")):
            for collection in library.SOURCES:
                page = self.backend.dispatch("library_list", {"collection": collection}, events.append, "fixture")
                detail = self.backend.dispatch("library_inspect", {"collection": collection, "record_key": page["items"][0]["id"]}, events.append, "fixture")
                self.assertTrue(detail["read_only"])
        self.assertEqual(self.files(), before)
        self.assertFalse(self.state.exists())
        self.assertEqual(events, [])
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.backend.subscription.calls, [])

    def test_local_knowledge_contracts_are_exact_safe_and_local(self):
        descriptors = capabilities.local_knowledge_descriptors()
        self.assertEqual([item["name"] for item in descriptors], ["search", "fetch"])
        self.assertEqual(capabilities.local_knowledge_capability_doctor()["status"], "OK")
        for descriptor in descriptors:
            self.assertEqual(descriptor["annotations"], {
                "readOnlyHint": True, "destructiveHint": False,
                "openWorldHint": False, "idempotentHint": True,
            })
            self.assertEqual(descriptor["_meta"]["proto_mind"], {
                "contract_version": 1, "local_only": True,
                "transport": "private_stdio", "network_access": False,
                "store_mutation": False, "model_dispatch": False,
            })
            self.assertFalse(descriptor["inputSchema"]["additionalProperties"])
        descriptors[0]["inputSchema"]["properties"]["query"]["maxLength"] = 1
        self.assertEqual(
            capabilities.local_knowledge_descriptors()[0]["inputSchema"]["properties"]["query"]["maxLength"],
            200,
        )

    def test_typed_search_fetch_envelopes_are_read_only_and_do_not_dispatch(self):
        self.write("persistent_memory.json", [{"id": "memory", "content": "Typed local fact"}])
        self.write("working_memory.json", [])
        before = self.files()
        events = []
        with patch.object(self.backend, "process", side_effect=AssertionError("No command handler")), \
                patch("subprocess.Popen", side_effect=AssertionError("No process or model")):
            search = self.backend.dispatch("capability_search", {
                "collection": "memory", "query": "typed", "filter": "current", "offset": 0,
            }, events.append, "fixture")
            item = search["structuredContent"]["items"][0]
            fetch = self.backend.dispatch("capability_fetch", {
                "collection": "memory", "record_key": item["id"],
                "expected_sha256": item["store_sha256"],
            }, events.append, "fixture")
        for name, result in (("search", search), ("fetch", fetch)):
            self.assertEqual(tuple(result), capabilities.LOCAL_KNOWLEDGE_RESULT_KEYS)
            self.assertEqual(result["_meta"]["proto_mind"]["capability"], name)
            self.assertTrue(result["structuredContent"]["read_only"])
            self.assertEqual(result["content"][0]["type"], "text")
            self.assertIn("No store was changed", result["content"][0]["text"])
        self.assertEqual(fetch["structuredContent"]["item"]["record_id"], "memory")
        self.assertEqual(self.files(), before)
        self.assertFalse(self.state.exists())
        self.assertEqual(events, [])
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.backend.subscription.calls, [])

    def test_typed_capabilities_reject_undeclared_parameters(self):
        before = self.files()
        for method, params in (
            ("capability_search", {"collection": "memory", "execute": True}),
            ("capability_fetch", {"collection": "memory", "record_key": "persistent:x", "url": "https://example.invalid"}),
        ):
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, "Unexpected"):
                self.backend.dispatch(method, params, lambda _: None, "fixture")
        self.assertEqual(self.files(), before)
        self.assertFalse(self.state.exists())

    def test_bootstrap_advertises_only_private_search_and_fetch_contracts(self):
        bootstrap = self.backend.bootstrap()
        local = bootstrap["local_knowledge_capabilities"]
        self.assertEqual(local["transport"], "private_stdio")
        self.assertEqual([item["name"] for item in local["contracts"]], ["search", "fetch"])
        self.assertNotIn("url", json.dumps(local).lower())

    def test_memory_workshop_is_empty_read_only_and_does_not_create_a_session(self):
        before = self.files()
        result = self.backend.dispatch("memory_workshop", {
            "conversation_id": "00000000-0000-0000-0000-000000000001",
        }, lambda _: None, "fixture")
        self.assertEqual(result["status"], "EMPTY")
        self.assertFalse(result["pilot_present"])
        self.assertFalse(result["scope"]["project_isolation_enforced"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["command_execution_performed"])
        self.assertEqual(self.backend.sessions, {})
        self.assertEqual(self.files(), before)
        with self.assertRaisesRegex(ValueError, "Unexpected Memory Workshop"):
            self.backend.dispatch("memory_workshop", {
                "conversation_id": "00000000-0000-0000-0000-000000000001",
                "execute": True,
            }, lambda _: None, "fixture")
        self.assertEqual(self.files(), before)

    def test_memory_workshop_projects_existing_candidate_without_promotion(self):
        class Owner:
            pass

        owner = Owner()
        pilot = get_experience_pilot(owner, project_root=self.root)
        pilot.preview()
        pilot.consent(pilot.expected_consent_phrase)
        result = InteractionResult(
            response="Use the current decision.",
            observer_state=ObserverState("continuity_followup", True, 0.8, ["project"]),
            retrieved_memory=[],
            retrieval_trace=None,
            memory_summary=InteractionSummary("none", "", 0.0, [], False),
            working_memory_snapshot=[],
            persistent_memory_snapshot=[],
            reasoner_backend="fixture",
            self_reflection=SelfReflectionResult(False, "ok", "ok", "ok", "low", "low", "high"),
            grounding_audit=GroundingAuditResult(False, "not_needed", "not_needed", "not_needed", "not_needed"),
            previous_correction_hints=["Use the active decision as current state."],
        )
        observation = pilot.observe_normal_turn(
            "Продолжим Proto-Mind.", result,
        )
        self.assertTrue(observation.capture_performed)
        before = self.files()

        workshop = build_native_memory_workshop(
            owner,
            conversation_id="00000000-0000-0000-0000-000000000001",
            workspace={"path": str(self.root), "device": 1, "inode": 2},
        )

        self.assertEqual(workshop["status"], "REVIEW")
        self.assertEqual(workshop["candidate_count"], 1)
        self.assertEqual(workshop["candidates"][0]["decision"], "undecided")
        self.assertFalse(workshop["candidates"][0]["auto_apply_allowed"])
        self.assertFalse(workshop["automatic_promotion"])
        self.assertFalse(workshop["scope"]["project_isolation_enforced"])
        self.assertEqual(workshop["scope"]["memory_store_scope"], "global_legacy_stores")
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
