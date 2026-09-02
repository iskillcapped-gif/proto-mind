"""Bundled templates stay distinct from learned provenance and never seed stores."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from proto_mind.native_auto_skills import validate_auto_skills, LEGACY_SCHEMA, PACK_FIELDS
from proto_mind.native_private_records import digest
from proto_mind.native_starter_skills import StarterSkills, validate_pack, PACK_PATH, IDS, MAX_BYTES
from proto_mind.native_work_sessions import WorkSessionStore
from proto_mind.tests import test_native_auto_skills as auto_fixture


class StarterPackTests(TestCase):
    def test_four_non_executable_non_learned_templates_with_stable_detached_snapshot(self):
        before = PACK_PATH.read_bytes()
        pack = StarterSkills(); report = pack.snapshot()
        self.assertEqual(set(pack.rows()), IDS)
        self.assertFalse(report["pack"]["learned_from_user"])
        self.assertFalse(report["pack"]["executable"])
        self.assertEqual(report["sha256"], digest(report["pack"]))
        report["pack"]["skills"].clear()
        self.assertEqual(len(pack.snapshot()["pack"]["skills"]), 4)
        self.assertEqual(PACK_PATH.read_bytes(), before)
        for row in pack.rows().values():
            self.assertEqual(row["reference"]["origin"], "bundled")
            self.assertNotIn("source_lesson_id", row["reference"])
            self.assertEqual(row["reference"]["contract_hash"], digest(row["contract"]))

    def test_pack_rejects_widened_origin_ids_execution_and_contracts(self):
        body = StarterSkills().body
        mutations = [lambda p: p.update(executable=True), lambda p: p.update(learned_from_user=True),
            lambda p: p.update(origin="learned"), lambda p: p.update(version="unknown"),
            lambda p: p["skills"][0].update(id="shell"), lambda p: p["skills"][0].update(id=[]),
            lambda p: p["skills"].__setitem__(0, p["skills"][1]),
            lambda p: p["skills"][0].update(execute="rm"),
            lambda p: p["skills"][0]["contract"].update(steps=[]),
            lambda p: p["skills"][0]["contract"].update(name="x\x00y")]
        for mutation in mutations:
            bad = deepcopy(body); mutation(bad)
            with self.assertRaises(ValueError): validate_pack(bad)

    def test_pack_read_rejects_symlink_oversize_duplicate_json_and_missing_resource(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "pack.json"
            for raw in (b"invalid", b"x" * (MAX_BYTES + 1), PACK_PATH.read_bytes().replace(b'"origin": "bundled"', b'"origin": "bundled", "origin": "bundled"', 1)):
                file.write_bytes(raw)
                with patch("proto_mind.native_starter_skills.PACK_PATH", file), self.assertRaises(ValueError): StarterSkills()
            file.unlink(); file.symlink_to(PACK_PATH)
            with patch("proto_mind.native_starter_skills.PACK_PATH", file), self.assertRaises(OSError): StarterSkills()
            file.unlink()
            with patch("proto_mind.native_starter_skills.PACK_PATH", file), self.assertRaises(FileNotFoundError): StarterSkills()

    def test_procedures_include_actual_verification_and_preserve_permission_boundaries(self):
        rows = StarterSkills().rows()
        self.assertIn("regression test", " ".join(rows["builtin.verified_change"]["contract"]["steps"]))
        self.assertIn("Do not edit source", " ".join(rows["builtin.failure_diagnosis"]["contract"]["steps"]))
        self.assertIn("Do not write a report", " ".join(rows["builtin.work_handoff"]["contract"]["steps"]))
        self.assertIn("without running", " ".join(rows["builtin.project_orientation"]["contract"]["steps"]))


class StarterIntegrationTests(TestCase):
    setUp = auto_fixture.AutoSkillTests.setUp
    seed = auto_fixture.AutoSkillTests.seed
    files = auto_fixture.AutoSkillTests.files
    params = auto_fixture.AutoSkillTests.params
    auto = auto_fixture.AutoSkillTests.auto
    send = auto_fixture.AutoSkillTests.send
    core = auto_fixture.AutoSkillTests.core

    def test_inspection_rpc_is_fixed_read_only_and_does_not_need_personal_sources(self):
        self.skills.unlink(); before = self.files()
        with patch("subprocess.Popen", side_effect=AssertionError("No process")):
            report = self.backend.dispatch("starter_skills", {}, lambda _: None, "inspect")
        self.assertEqual(len(report["pack"]["skills"]), 4)
        self.assertTrue(report["read_only"] and report["no_execution"])
        self.assertEqual(before, self.files())
        self.assertEqual(self.backend.sessions, {})
        for params in ({"path": str(PACK_PATH)}, {"execute": True}, {"skill_id": "builtin.work_handoff"}):
            with self.assertRaises(ValueError): self.backend.dispatch("starter_skills", params, lambda _: None, "inspect")

    def test_legacy_only_library_has_four_starters_without_promoting_or_rewriting_it(self):
        self.skills.write_text(json.dumps({"id": "legacy", "name": "Old skill", "status": "active"}) + "\n")
        before = self.core(); report = self.auto().report
        self.assertEqual((report["state"], report["learned_count"], report["bundled_count"], report["excluded_count"]), ("ready", 0, 4, 1))
        result = self.send()
        self.assertEqual(result["auto_skills"]["selected"][0]["origin"], "bundled")
        self.assertEqual(result["work_session"]["verification"], "not_assessed")
        self.assertEqual(before, self.core())

    def test_reserved_builtin_ids_cannot_be_spoofed_by_core_records(self):
        self.skills.write_text(json.dumps({**self.record, "id": "builtin.verified_change"}) + "\n")
        report = self.auto().report
        self.assertEqual(report["learned_count"], 0)
        self.assertEqual(report["excluded_count"], 1)
        self.assertEqual(len(self.auto().rows), 4)

    def test_mixed_selection_preserves_distinct_provenance_and_old_sources(self):
        before = self.core()
        self.backend.subscription.selection_result = json.dumps({"skill_ids": [self.record["id"], "builtin.verified_change"],
            "reason": "Two distinct requested concerns.", "checks": ["Inspect actual outputs."]})
        result = self.send(); report = result["auto_skills"]
        self.assertEqual([row["origin"] for row in report["selected"]], ["learned", "bundled"])
        self.assertNotIn("source_lesson_id", report["selected"][1])
        self.assertIn("application-authored templates", self.backend.subscription.calls[0][0])
        self.assertIn("regression test", self.backend.subscription.calls[0][0])
        self.assertEqual(before, self.core())
        path = self.backend.work_sessions.directory / (result["work_session"]["id"] + ".json")
        self.assertEqual(WorkSessionStore._parse(path.read_bytes(), path.name)["auto_skills"], report)

    def test_v1_historical_reports_still_validate_without_inventing_pack_metadata(self):
        result = self.send(); record = result["work_session"]
        legacy = deepcopy(result["auto_skills"])
        legacy["schema"] = LEGACY_SCHEMA
        for key in PACK_FIELDS: del legacy[key]
        for row in legacy["selected"]: del row["origin"]
        validate_auto_skills(legacy, record)
        record["auto_skills"] = legacy
        read = WorkSessionStore._parse(json.dumps(record).encode(), record["id"] + ".json")
        self.assertEqual(read["auto_skills"], legacy)

    def test_bundled_receipts_cannot_claim_learned_provenance_or_different_pack(self):
        self.backend.subscription.selection_result = json.dumps({"skill_ids": ["builtin.work_handoff"], "reason": "Handoff", "checks": []})
        report = self.send()["auto_skills"]
        for changes in ({"origin": "learned"}, {"pack_hash": "0" * 64}, {"version": "9.0.0"},
                        {"source_lesson_id": "fake"}, {"skill_id": "builtin.unknown"}):
            bad = deepcopy(report); bad["selected"][0].update(changes)
            with self.assertRaises(ValueError): validate_auto_skills(bad)
        for changes in ({"bundled_count": True}, {"learned_count": 99}, {"catalog_count": 0}):
            with self.assertRaises(ValueError): validate_auto_skills({**report, **changes})

    def test_pack_drift_after_selection_stops_main_task_without_overwriting_change(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "starter.json"; path.write_bytes(PACK_PATH.read_bytes())
            changed = path.read_bytes() + b"\n"
            self.backend.subscription.selection_hook = lambda: path.write_bytes(changed)
            with patch("proto_mind.native_starter_skills.PACK_PATH", path), self.assertRaisesRegex(ValueError, "pack changed"):
                self.send()
            self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(self.backend.subscription.calls, [])

    def test_broken_pack_fails_before_selection_and_main_without_fallback(self):
        with patch("proto_mind.native_starter_skills.PACK_PATH", self.base / "missing"), self.assertRaises(FileNotFoundError): self.send()
        self.assertFalse(self.backend.subscription.selections or self.backend.subscription.calls)
