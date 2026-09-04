"""Core flow checks: skill."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    Coordinator,
    EXPERIENCE_PILOT_ATTR,
    MemoryKeeper,
    MockReasoner,
    Observer,
    OperatorReviewedProceduralSkillOutcomeCaptureSession,
    OperatorReviewedProceduralSkillRestoreApplySession,
    PROCEDURAL_SKILL_LIFECYCLE_APPLY_MAX_RECEIPTS,
    PROCEDURAL_SKILL_LIFECYCLE_APPLY_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_FUTURE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED,
    PROCEDURAL_SKILL_LIFECYCLE_READINESS_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA,
    PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED,
    PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS,
    PROCEDURAL_SKILL_OUTCOME_CAPTURE_MODE,
    PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS,
    PROCEDURAL_SKILL_OUTCOME_DECISION_MODE,
    PROCEDURAL_SKILL_RESTORE_APPLY_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_APPLY_MAX_RECEIPTS,
    PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS,
    PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_SCHEMA,
    PROCEDURAL_SKILL_RESTORE_DURABLY_RECOVERABLE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_RESTORE_PROCESS_ONLY_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_MODE,
    PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_SCHEMA,
    PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS,
    PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED,
    PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED,
    Path,
    ProceduralSkillLifecycleApplyReadiness,
    ProceduralSkillLifecycleAudit,
    ProceduralSkillOutcomeCaptureBuilder,
    ProceduralSkillOutcomeDecisionBuilder,
    ProceduralSkillOutcomeDecisionError,
    ProceduralSkillOutcomeReviewer,
    ProceduralSkillRestoreApplyError,
    ProceduralSkillRestoreReceiptAudit,
    SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED,
    SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED,
    SessionOperatorLogger,
    SkillLibrary,
    SupervisedExperiencePilot,
    TemporaryDirectory,
    UTC,
    action_policy_doctor,
    build_procedural_skill_lifecycle_metadata_preview,
    build_procedural_skill_lifecycle_restore_metadata_preview,
    build_procedural_skill_restore_receipt_evidence,
    build_test_applied_procedural_skill,
    build_test_captured_procedural_skill_outcomes,
    build_test_durably_archived_procedural_skill,
    build_test_procedural_skill_lifecycle_readiness,
    build_test_procedural_skill_outcome_events,
    build_test_system,
    classify_command,
    command_registry_doctor,
    datetime,
    deepcopy,
    format_experience_pilot_command,
    format_procedural_skill_lifecycle_apply_command,
    format_procedural_skill_lifecycle_metadata_contract,
    format_procedural_skill_lifecycle_readiness_command,
    format_procedural_skill_lifecycle_restore_command,
    format_procedural_skill_outcome_capture_command,
    format_procedural_skill_outcome_decision_command,
    format_procedural_skill_restore_apply_command,
    format_procedural_skill_restore_authorization_command,
    format_procedural_skill_restore_receipt_audit_command,
    format_skill_command,
    format_skill_lifecycle_audit_command,
    format_skill_provenance_doctor,
    format_skill_why,
    json,
    patch,
    procedural_skill_lifecycle_apply_confirmation_token,
    procedural_skill_lifecycle_metadata_doctor,
    procedural_skill_lifecycle_restore_doctor,
    procedural_skill_outcome_capture_confirmation_token,
    procedural_skill_outcome_decision_confirmation_token,
    procedural_skill_restore_apply_confirmation_token,
    procedural_skill_restore_apply_receipt_hash,
    procedural_skill_restore_authorization_doctor,
    process_interactive_input,
    reset_procedural_skill_restore_apply_session,
    review_procedural_skill_lifecycle_restore,
    review_procedural_skill_restore_authorization,
    skill_provenance_doctor,
    verify_procedural_skill_lifecycle_metadata,
    verify_procedural_skill_lifecycle_restore_metadata,
    verify_procedural_skill_provenance,
    verify_procedural_skill_restore_receipt_evidence,
)


class SkillFlowTests(unittest.TestCase):
    def test_skill_library_read_snapshot_is_detached_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "skills.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "id": "skill_one",
                        "name": "One",
                        "status": "active",
                        "category": "testing",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            library = SkillLibrary(path)
            before = path.read_bytes()

            snapshot = library.read_snapshot()
            snapshot["records"][0]["name"] = "Changed outside library"
            second = library.read_snapshot()

            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(second["records"][0]["name"], "One")
        self.assertFalse(second["mutation_performed"])

    def test_skill_status_works_when_file_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_skill_command("/skills status", project_root=project_root)

            self.assertIsNotNone(output)
            self.assertIn("Skill Library status:", output)
            self.assertIn("exists: False", output)
            self.assertIn("total_skills: 0", output)
            self.assertIn("most_recently_updated: none", output)

    def test_skill_add_creates_schema_and_list_inspect_work(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            output = format_skill_command(
                "/skills add Create backup before changes --category workflow --summary Always checkpoint first",
                project_root=project_root,
            )
            library = SkillLibrary.from_project_root(project_root)
            state = library._read_state()
            skill = state.records[0]
            skill_id = skill["id"]
            list_output = format_skill_command("/skills list", project_root=project_root)
            inspect_output = format_skill_command(f"/skills inspect {skill_id}", project_root=project_root)

            self.assertIn("Skill added:", output)
            self.assertTrue(skill_id.startswith("skill_"))
            self.assertEqual(skill["name"], "Create backup before changes")
            self.assertEqual(skill["summary"], "Always checkpoint first")
            self.assertEqual(skill["status"], "active")
            self.assertEqual(skill["category"], "workflow")
            self.assertEqual(skill["source"], "operator")
            self.assertEqual(skill["uses"], 0)
            self.assertIsNone(skill["last_used_at"])
            self.assertIn("created_at", skill)
            self.assertIn("updated_at", skill)
            self.assertIn(skill_id, list_output)
            self.assertIn("Skill:", inspect_output)
            self.assertIn("name: Create backup before changes", inspect_output)

    def test_skill_update_body_append_tag_untag_and_search(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            output = format_skill_command("/skills add Create checkpoint before code changes", project_root=project_root)
            skill_id = next(line.strip().split(" — ")[0] for line in output.splitlines() if line.strip().startswith("skill_"))

            summary = format_skill_command(
                f"/skills update {skill_id} --summary Always checkpoint first",
                project_root=project_root,
            )
            body = format_skill_command(f"/skills body {skill_id} Step 1: cd /path/to/proto_mind", project_root=project_root)
            append = format_skill_command(f"/skills append {skill_id} Step 2: run /memory backup", project_root=project_root)
            tag = format_skill_command(f"/skills tag {skill_id} backup", project_root=project_root)
            search_upper = format_skill_command("/skills search BACKUP", project_root=project_root)
            untag = format_skill_command(f"/skills untag {skill_id} backup", project_root=project_root)
            inspect = format_skill_command(f"/skills inspect {skill_id}", project_root=project_root)

            self.assertIn("Summary updated:", summary)
            self.assertIn("Body updated:", body)
            self.assertIn("Body appended:", append)
            self.assertIn("Tag added:", tag)
            self.assertIn(skill_id, search_upper)
            self.assertIn("Tag removed:", untag)
            self.assertIn("summary: Always checkpoint first", inspect)
            self.assertIn("Step 1: cd /path/to/proto_mind", inspect)
            self.assertIn("Step 2: run /memory backup", inspect)
            self.assertIn("tags: []", inspect)

    def test_skill_use_increments_uses_and_sets_last_used_at(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            output = format_skill_command("/skills add Use me", project_root=project_root)
            skill_id = next(line.strip().split(" — ")[0] for line in output.splitlines() if line.strip().startswith("skill_"))
            format_skill_command(f"/skills body {skill_id} Step 1: breathe", project_root=project_root)

            used = format_skill_command(f"/skills use {skill_id}", project_root=project_root)
            record = SkillLibrary.from_project_root(project_root)._read_state().records[0]

            self.assertIn("Skill used:", used)
            self.assertIn("Body:", used)
            self.assertIn("Step 1: breathe", used)
            self.assertEqual(record["uses"], 1)
            self.assertIsNotNone(record["last_used_at"])

    def test_skill_archive_restore_list_all_and_category_filter(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            workflow_output = format_skill_command("/skills add Workflow skill --category workflow", project_root=project_root)
            coding_output = format_skill_command("/skills add Coding skill --category coding", project_root=project_root)
            workflow_id = next(line.strip().split(" — ")[0] for line in workflow_output.splitlines() if line.strip().startswith("skill_"))
            coding_id = next(line.strip().split(" — ")[0] for line in coding_output.splitlines() if line.strip().startswith("skill_"))

            archived = format_skill_command(f"/skills archive {workflow_id}", project_root=project_root)
            default_list = format_skill_command("/skills list", project_root=project_root)
            all_list = format_skill_command("/skills list --all", project_root=project_root)
            workflow_list = format_skill_command("/skills list --category workflow --all", project_root=project_root)
            restored = format_skill_command(f"/skills restore {workflow_id}", project_root=project_root)
            restored_list = format_skill_command("/skills list", project_root=project_root)

            self.assertIn("Archived skill:", archived)
            self.assertNotIn(workflow_id, default_list)
            self.assertIn(coding_id, default_list)
            self.assertIn(workflow_id, all_list)
            self.assertIn("[archived]", all_list)
            self.assertIn(workflow_id, workflow_list)
            self.assertNotIn(coding_id, workflow_list)
            self.assertIn("Active skill:", restored)
            self.assertIn(workflow_id, restored_list)

    def test_skill_unknown_empty_and_corrupted_file_are_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            library = SkillLibrary.from_project_root(project_root)
            empty_add = format_skill_command("/skills add   ", project_root=project_root)
            unknown = format_skill_command("/skills use missing", project_root=project_root)
            missing_body_text = format_skill_command("/skills body missing", project_root=project_root)
            library.skills_path.parent.mkdir(parents=True)
            library.skills_path.write_text("{not json\n", encoding="utf-8")
            status = format_skill_command("/skills status", project_root=project_root)
            refused = format_skill_command("/skills add Should not overwrite corruption", project_root=project_root)

            self.assertIn("Usage: /skills add", empty_add)
            self.assertIn("Skill not found: missing", unknown)
            self.assertIn("Usage: /skills body <id> <text>", missing_body_text)
            self.assertIn("file_health: malformed_jsonl", status)
            self.assertIn("refusing to modify", refused)
            self.assertEqual(library.skills_path.read_text(encoding="utf-8"), "{not json\n")

    def test_skill_commands_work_through_shared_input_handler_without_session_log_turn(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            coordinator, _, _ = build_test_system(project_root)
            logger = SessionOperatorLogger.from_project_root(project_root)
            coordinator.session_logger = logger

            output = process_interactive_input(
                "/skills add Shared handler skill",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )
            status = process_interactive_input(
                "/skills status",
                coordinator=coordinator,
                session_logger=logger,
                project_root=project_root,
            )

            self.assertIn("Skill added:", output)
            self.assertIn("total_skills: 1", status)
            self.assertEqual(logger.status().entry_count, 0)

    def test_skill_lifecycle_metadata_contract_is_deterministic_and_writer_gated(self) -> None:
        first = format_procedural_skill_lifecycle_metadata_contract()
        second = format_procedural_skill_lifecycle_metadata_contract()
        doctor = procedural_skill_lifecycle_metadata_doctor()

        self.assertEqual(first, second)
        self.assertEqual(doctor.status, "OK")
        self.assertTrue(doctor.deterministic_example_verified)
        self.assertTrue(doctor.tamper_refused)
        self.assertTrue(doctor.writer_installed)
        self.assertTrue(PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED)
        self.assertIn(PROCEDURAL_SKILL_LIFECYCLE_METADATA_MODE, first)
        self.assertIn(PROCEDURAL_SKILL_LIFECYCLE_METADATA_SCHEMA, first)
        self.assertIn("evidence_replay_after_restart: false", first)
        self.assertIn("separately confirmed v3.5n archive writer", first)

    def test_skill_lifecycle_metadata_preview_hashes_exact_bounded_contract(self) -> None:
        metadata = build_procedural_skill_lifecycle_metadata_preview(
            skill_id="skill_contract_test",
            skill_provenance_id="skillprov_contract_test",
            transitioned_at="2026-07-20T01:00:00+00:00",
            decision_receipt_id="skilloutdec_contract_test",
            decision_hash="1" * 64,
            outcome_status="FAILURE_CANDIDATE",
            selected_signal_id="evt_failure",
            evidence_event_ids=("evt_result", "evt_failure", "evt_failure"),
            capture_receipt_hashes=("3" * 64, "2" * 64),
            review_hash="4" * 64,
            before_record_hash="5" * 64,
            confirmation_token_hash="6" * 64,
        )
        check = verify_procedural_skill_lifecycle_metadata(metadata)

        self.assertTrue(check.verified)
        self.assertEqual(check.status, "VERIFIED")
        self.assertEqual(set(metadata), set(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FIELDS))
        self.assertEqual(metadata["evidence_event_ids"], ["evt_failure", "evt_result"])
        self.assertEqual(metadata["capture_receipt_hashes"], ["2" * 64, "3" * 64])
        self.assertTrue(metadata["id"].startswith("skilllife_"))
        self.assertEqual(len(metadata["metadata_hash"]), 64)
        self.assertFalse(metadata["evidence_replay_available"])
        self.assertFalse(metadata["automatic"])
        self.assertFalse(metadata["procedure_execution_performed"])

    def test_skill_lifecycle_metadata_verifier_refuses_tamper_and_scope_expansion(self) -> None:
        common = {
            "skill_id": "skill_contract_test",
            "skill_provenance_id": "skillprov_contract_test",
            "transitioned_at": "2026-07-20T01:00:00+00:00",
            "decision_receipt_id": "skilloutdec_contract_test",
            "decision_hash": "1" * 64,
            "outcome_status": "MIXED_EVIDENCE",
            "selected_signal_id": "evt_mixed",
            "evidence_event_ids": ("evt_mixed",),
            "capture_receipt_hashes": ("2" * 64,),
            "review_hash": "3" * 64,
            "before_record_hash": "4" * 64,
            "confirmation_token_hash": "5" * 64,
        }
        metadata = build_procedural_skill_lifecycle_metadata_preview(**common)
        tampered = deepcopy(metadata)
        tampered["reason"] = "operator_archive_without_evidence"
        tampered_check = verify_procedural_skill_lifecycle_metadata(tampered)
        invalid = {**common, "outcome_status": "SUCCESS_CANDIDATE"}

        self.assertFalse(tampered_check.verified)
        self.assertIn("reason", " ".join(tampered_check.issues).lower())
        self.assertIn("hash", " ".join(tampered_check.issues).lower())
        with self.assertRaises(ValueError):
            build_procedural_skill_lifecycle_metadata_preview(**invalid)

    def test_skill_lifecycle_audit_refuses_envelope_status_mismatch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(
                Path(temp_dir)
            )
            records = library.read_snapshot()["records"]
            provenance = records[0]["provenance"]
            records[0]["lifecycle"] = build_procedural_skill_lifecycle_metadata_preview(
                skill_id=applied.created_skill_id,
                skill_provenance_id=str(provenance["id"]),
                transitioned_at="2026-07-20T01:00:00+00:00",
                decision_receipt_id="skilloutdec_future",
                decision_hash="1" * 64,
                outcome_status="FAILURE_CANDIDATE",
                selected_signal_id="evt_failure",
                evidence_event_ids=("evt_failure",),
                capture_receipt_hashes=("2" * 64,),
                review_hash="3" * 64,
                before_record_hash="4" * 64,
                confirmation_token_hash="5" * 64,
            )
            library._write_records(records)
            entry = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(applied.created_skill_id)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.state, "invalid")
        self.assertEqual(entry.lifecycle_evidence, "invalid_envelope")
        self.assertFalse(entry.outcome_archive_proven)
        self.assertIn("requires archived skill status", " ".join(entry.issues))

    def test_skill_lifecycle_contract_bypasses_corrupt_store_without_writing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skills_path = root / "skills.jsonl"
            memory_path = root / "persistent_memory.json"
            skills_path.write_text("{not-json\n", encoding="utf-8")
            before = skills_path.read_bytes()
            output = format_skill_lifecycle_audit_command(
                "/skills lifecycle-status --contract",
                skills_path=skills_path,
                persistent_memory_path=memory_path,
            )
            after = skills_path.read_bytes()

        self.assertIn("Status: OK", output)
        self.assertIn("writer_installed: true", output)
        self.assertEqual(after, before)
        self.assertFalse(memory_path.exists())

    def test_skill_why_verifies_after_restart_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(Path(temp_dir))
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            output = format_skill_why(
                library.skills_path,
                store.persistent_path,
                applied.created_skill_id,
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertIn("Procedural Skill Provenance v1", output)
        self.assertIn("Status: VERIFIED", output)
        self.assertIn("source_status: current", output)
        self.assertIn("operator_confirmation_recorded: true", output)
        self.assertIn("procedure_execution_enabled: false", output)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)

    def test_skill_why_does_not_invent_provenance_for_operator_skill(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = SkillLibrary(root / "skills.jsonl")
            added = library.add_skill("Manual operator skill")
            skill_id = added.splitlines()[1].strip().split()[0]
            output = format_skill_why(
                library.skills_path,
                root / "missing_memory.json",
                skill_id,
            )

        self.assertIn("Status: UNAVAILABLE", output)
        self.assertIn("will not invent a provenance chain", output)
        self.assertIn("Read-only provenance inspection", output)

    def test_skill_provenance_detects_hash_tampering(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            record = library.read_snapshot()["records"][0]
            record["provenance"]["applied_at"] = "tampered"
            library._write_records([record])
            check = verify_procedural_skill_provenance(
                record,
                memory_records=store.load_persistent_memory(),
            )
            output = format_skill_why(library.skills_path, store.persistent_path, record["id"])

        self.assertEqual(check.status, "ERROR")
        self.assertIn("provenance hash", " ".join(check.issues).lower())
        self.assertIn("Status: ERROR", output)

    def test_skill_provenance_marks_current_payload_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(Path(temp_dir))
            library.set_body(applied.created_skill_id, "Operator edited procedure body.")
            record = library.read_snapshot()["records"][0]
            check = verify_procedural_skill_provenance(
                record,
                memory_records=store.load_persistent_memory(),
            )

        self.assertEqual(check.status, "DRIFTED")
        self.assertTrue(check.verified)
        self.assertFalse(check.current_payload_matches)
        self.assertIn("operator-confirmed", " ".join(check.warnings))

    def test_skill_provenance_allows_archived_lifecycle_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(Path(temp_dir))
            library.set_status(applied.created_skill_id, "archived")
            record = library.read_snapshot()["records"][0]
            check = verify_procedural_skill_provenance(
                record,
                memory_records=store.load_persistent_memory(),
            )

        self.assertEqual(record["status"], "archived")
        self.assertEqual(check.status, "VERIFIED")
        self.assertTrue(check.current_payload_matches)

    def test_skill_provenance_marks_changed_source_lifecycle_historical(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(Path(temp_dir))
            memories = store.load_persistent_memory()
            source = next(item for item in memories if item.id == applied.source_lesson_id)
            source.active = False
            source.updated_at = datetime.now(UTC).isoformat()
            store.save_persistent_memory(memories)
            record = library.read_snapshot()["records"][0]
            check = verify_procedural_skill_provenance(
                record,
                memory_records=store.load_persistent_memory(),
            )

        self.assertEqual(check.status, "HISTORICAL")
        self.assertEqual(check.source_status, "historical")
        self.assertTrue(check.verified)

    def test_skill_provenance_doctor_ignores_manual_skills_and_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _ = build_test_applied_procedural_skill(Path(temp_dir))
            library.add_skill("Manual skill without provenance")
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            report = skill_provenance_doctor(library.skills_path, store.persistent_path)
            output = format_skill_provenance_doctor(report)
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.total_skills, 2)
        self.assertEqual(report.provenanced_count, 1)
        self.assertEqual(report.verified_count, 1)
        self.assertEqual(report.unavailable_count, 1)
        self.assertEqual(report.legacy_applied_count, 0)
        self.assertIn("Status: OK", output)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)

    def test_skill_provenance_doctor_warns_for_legacy_supervised_apply(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = SkillLibrary(root / "skills.jsonl")
            library._write_records(
                [
                    {
                        "id": "skilllearn_legacy000000",
                        "name": "Legacy supervised skill",
                        "summary": "Predates durable skill provenance.",
                        "body": "Step 1. Inspect manually.",
                        "status": "active",
                        "category": "workflow",
                        "source": "experience_learning_skill_apply",
                        "tags": [],
                        "uses": 0,
                        "last_used_at": None,
                    }
                ]
            )
            report = skill_provenance_doctor(
                library.skills_path,
                root / "missing_memory.json",
            )

        self.assertEqual(report.status, "WARN")
        self.assertEqual(report.legacy_applied_count, 1)
        self.assertIn("legacy supervised apply", " ".join(report.warnings))

    def test_skill_provenance_commands_handle_missing_and_corrupt_stores(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skills_path = root / "skills.jsonl"
            memory_path = root / "persistent_memory.json"
            missing = format_skill_why(skills_path, memory_path, "missing")
            skills_path.write_text('{"id": "broken"}\nnot-json\n', encoding="utf-8")
            corrupt_skills = format_skill_why(skills_path, memory_path, "broken")
            skill_report = skill_provenance_doctor(skills_path, memory_path)
            skills_path.write_text("", encoding="utf-8")
            memory_path.write_text("{broken", encoding="utf-8")
            memory_report = skill_provenance_doctor(skills_path, memory_path)

        self.assertIn("Status: NOT FOUND", missing)
        self.assertIn("Status: ERROR", corrupt_skills)
        self.assertEqual(skill_report.status, "ERROR")
        self.assertEqual(memory_report.status, "ERROR")
        self.assertIn("Persistent memory is unreadable", " ".join(memory_report.issues))

    def test_skill_outcome_capture_preview_requires_pilot_consent_and_is_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            pilot = SupervisedExperiencePilot(root, session_id="skill-outcome-preview")
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            output = format_procedural_skill_outcome_capture_command(
                (
                    "/experience learning skill-outcome-capture-preview "
                    f"{record['id']} success --evidence operator verified the checklist"
                ),
                builder=builder,
                session=pilot.skill_outcome_captures,
                pilot_state=pilot.state,
                pilot_session_id=pilot.session_id,
                events=pilot.snapshot(),
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertIn("Status: NOT_READY", output)
        self.assertIn("capture_allowed_now: false", output)
        self.assertIn("CONFIRM-SKILL-OUTCOME-", output)
        self.assertEqual(pilot.event_count, 0)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)

    def test_skill_outcome_capture_exact_success_feeds_read_only_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            pilot = SupervisedExperiencePilot(root, session_id="skill-outcome-success")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            evidence = "Operator verified every expected checklist result."
            blueprint = builder.build(
                session_id=pilot.session_id,
                skill_id=str(record["id"]),
                outcome="success",
                evidence=evidence,
            )
            token = procedural_skill_outcome_capture_confirmation_token(blueprint)
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            output = format_procedural_skill_outcome_capture_command(
                (
                    "/experience learning capture skill-outcome "
                    f'{record["id"]} success {token} --evidence "{evidence}"'
                ),
                builder=builder,
                session=pilot.skill_outcome_captures,
                pilot_state=pilot.state,
                pilot_session_id=pilot.session_id,
                events=pilot.snapshot(),
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )
            review = ProceduralSkillOutcomeReviewer(
                pilot.snapshot(),
                [record],
                store.load_persistent_memory(),
            ).review(str(record["id"]))
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertIn("Status: CAPTURED", output)
        self.assertIn("execution_performed_by_proto_mind: false", output)
        self.assertEqual(pilot.event_count, 4)
        self.assertEqual(len(pilot.skill_outcome_captures.snapshot()), 1)
        self.assertEqual(review.status, "SUCCESS_CANDIDATE")
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)

    def test_skill_outcome_capture_failure_feeds_failure_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            pilot = SupervisedExperiencePilot(root, session_id="skill-outcome-failure")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            evidence = "Verification failed after the manual procedure."
            blueprint = builder.build(
                session_id=pilot.session_id,
                skill_id=str(record["id"]),
                outcome="failure",
                evidence=evidence,
            )
            token = procedural_skill_outcome_capture_confirmation_token(blueprint)
            format_procedural_skill_outcome_capture_command(
                (
                    "/experience learning capture skill-outcome "
                    f'{record["id"]} failure {token} --evidence "{evidence}"'
                ),
                builder=builder,
                session=pilot.skill_outcome_captures,
                pilot_state=pilot.state,
                pilot_session_id=pilot.session_id,
                events=pilot.snapshot(),
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )
            review = ProceduralSkillOutcomeReviewer(
                pilot.snapshot(),
                [record],
                store.load_persistent_memory(),
            ).review(str(record["id"]))

        self.assertEqual(review.status, "FAILURE_CANDIDATE")
        self.assertEqual(pilot.snapshot()[-1]["event_type"], "tool_failed")

    def test_skill_outcome_capture_refuses_wrong_token_without_events(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            pilot = SupervisedExperiencePilot(root, session_id="skill-outcome-wrong-token")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            output = format_procedural_skill_outcome_capture_command(
                (
                    "/experience learning capture skill-outcome "
                    f'{record["id"]} success WRONG --evidence "verified"'
                ),
                builder=builder,
                session=pilot.skill_outcome_captures,
                pilot_state=pilot.state,
                pilot_session_id=pilot.session_id,
                events=pilot.snapshot(),
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )

        self.assertIn("token mismatch", output)
        self.assertEqual(pilot.event_count, 0)
        self.assertEqual(pilot.skill_outcome_captures.snapshot(), ())

    def test_skill_outcome_capture_fails_closed_when_buffer_bound_is_reached(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            pilot = SupervisedExperiencePilot(
                root,
                session_id="skill-outcome-bound",
                max_events=3,
            )
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            evidence = "verified but the four-event batch exceeds this fixture bound"
            blueprint = builder.build(
                session_id=pilot.session_id,
                skill_id=str(record["id"]),
                outcome="success",
                evidence=evidence,
            )
            token = procedural_skill_outcome_capture_confirmation_token(blueprint)
            output = format_procedural_skill_outcome_capture_command(
                (
                    "/experience learning capture skill-outcome "
                    f'{record["id"]} success {token} --evidence "{evidence}"'
                ),
                builder=builder,
                session=pilot.skill_outcome_captures,
                pilot_state=pilot.state,
                pilot_session_id=pilot.session_id,
                events=pilot.snapshot(),
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )

        self.assertIn("total_event_limit", output)
        self.assertEqual(pilot.state, "stopped")
        self.assertEqual(pilot.event_count, 0)
        self.assertEqual(pilot.skill_outcome_captures.snapshot(), ())

    def test_skill_outcome_capture_refuses_without_exact_session_consent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            pilot = SupervisedExperiencePilot(root, session_id="skill-outcome-no-consent")
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            evidence = "verified"
            blueprint = builder.build(
                session_id=pilot.session_id,
                skill_id=str(record["id"]),
                outcome="success",
                evidence=evidence,
            )
            token = procedural_skill_outcome_capture_confirmation_token(blueprint)
            output = format_procedural_skill_outcome_capture_command(
                (
                    "/experience learning capture skill-outcome "
                    f'{record["id"]} success {token} --evidence "{evidence}"'
                ),
                builder=builder,
                session=pilot.skill_outcome_captures,
                pilot_state=pilot.state,
                pilot_session_id=pilot.session_id,
                events=pilot.snapshot(),
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )

        self.assertIn("exact session consent is not active", output)
        self.assertEqual(pilot.event_count, 0)

    def test_skill_outcome_capture_is_run_once_for_exact_blueprint(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            pilot = SupervisedExperiencePilot(root, session_id="skill-outcome-run-once")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            evidence = "verified once"
            blueprint = builder.build(
                session_id=pilot.session_id,
                skill_id=str(record["id"]),
                outcome="success",
                evidence=evidence,
            )
            token = procedural_skill_outcome_capture_confirmation_token(blueprint)
            command = (
                "/experience learning capture skill-outcome "
                f'{record["id"]} success {token} --evidence "{evidence}"'
            )
            kwargs = {
                "builder": builder,
                "session": pilot.skill_outcome_captures,
                "pilot_state": pilot.state,
                "pilot_session_id": pilot.session_id,
                "events": pilot.snapshot(),
                "append_events": pilot.append_supervised_manual_skill_outcome_events,
            }
            first = format_procedural_skill_outcome_capture_command(command, **kwargs)
            events_after_first = pilot.snapshot()
            second = format_procedural_skill_outcome_capture_command(command, **kwargs)

        self.assertIn("Status: CAPTURED", first)
        self.assertIn("already captured", second)
        self.assertEqual(pilot.snapshot(), events_after_first)
        self.assertEqual(pilot.event_count, 4)

    def test_skill_outcome_capture_refuses_drift_and_command_chaining(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, applied = build_test_applied_procedural_skill(root)
            pilot = SupervisedExperiencePilot(root, session_id="skill-outcome-drift")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            chained = format_procedural_skill_outcome_capture_command(
                "/experience learning skill-outcome-capture-preview x success --evidence ok; /skills list",
                builder=builder,
                session=pilot.skill_outcome_captures,
                pilot_state=pilot.state,
                pilot_session_id=pilot.session_id,
                events=pilot.snapshot(),
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )
            library.set_body(applied.created_skill_id, "Drifted body")
            drifted = format_procedural_skill_outcome_capture_command(
                (
                    "/experience learning skill-outcome-capture-preview "
                    f"{applied.created_skill_id} success --evidence verified"
                ),
                builder=builder,
                session=pilot.skill_outcome_captures,
                pilot_state=pilot.state,
                pilot_session_id=pilot.session_id,
                events=pilot.snapshot(),
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )

        self.assertIn("Command chaining", chained)
        self.assertIn("provenance/payload is not safe", drifted)
        self.assertEqual(pilot.event_count, 0)

    def test_skill_outcome_capture_redacts_evidence_before_process_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            blueprint = builder.build(
                session_id="skill-outcome-redaction",
                skill_id=str(record["id"]),
                outcome="success",
                evidence="Verified with token=super-secret-token-value.",
            )

        self.assertNotIn("super-secret-token-value", blueprint.evidence_preview)
        self.assertIn("[REDACTED:", blueprint.evidence_preview)
        self.assertEqual(len(blueprint.evidence_fingerprint), 64)

    def test_skill_outcome_capture_list_inspect_and_doctor_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            pilot = SupervisedExperiencePilot(root, session_id="skill-outcome-doctor")
            pilot.preview()
            pilot.consent(pilot.expected_consent_phrase)
            builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            blueprint = builder.build(
                session_id=pilot.session_id,
                skill_id=str(record["id"]),
                outcome="success",
                evidence="verified",
            )
            receipt = pilot.skill_outcome_captures.capture(
                blueprint,
                token=procedural_skill_outcome_capture_confirmation_token(blueprint),
                pilot_state=pilot.state,
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )
            events_before = pilot.snapshot()
            receipts_before = pilot.skill_outcome_captures.snapshot()
            common = {
                "builder": builder,
                "session": pilot.skill_outcome_captures,
                "pilot_state": pilot.state,
                "pilot_session_id": pilot.session_id,
                "events": pilot.snapshot(),
                "append_events": pilot.append_supervised_manual_skill_outcome_events,
            }
            listed = format_procedural_skill_outcome_capture_command(
                "/experience learning skill-outcome-captures", **common
            )
            inspected = format_procedural_skill_outcome_capture_command(
                f"/experience learning skill-outcome-captures {receipt.id}", **common
            )
            doctor = format_procedural_skill_outcome_capture_command(
                "/experience learning skill-outcome-capture-doctor", **common
            )

        self.assertIn(receipt.id, listed)
        self.assertIn("Status: CAPTURED", inspected)
        self.assertIn("Status: OK", doctor)
        self.assertIn(PROCEDURAL_SKILL_OUTCOME_CAPTURE_MODE, doctor)
        self.assertEqual(pilot.snapshot(), events_before)
        self.assertEqual(pilot.skill_outcome_captures.snapshot(), receipts_before)

    def test_skill_outcome_capture_registry_policy_and_bounds_are_safe(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}

        self.assertEqual(PROCEDURAL_SKILL_OUTCOME_CAPTURE_MAX_RECEIPTS, 16)
        for prefix in (
            "/experience learning skill-outcome-capture-preview",
            "/experience learning skill-outcome-captures",
            "/experience learning skill-outcome-capture-doctor",
        ):
            self.assertTrue(registry[prefix].read_only)
            self.assertEqual(registry[prefix].mutates, "none")
            self.assertEqual(classify_command(prefix).policy_class, "auto_allowed")
        capture = registry["/experience learning capture skill-outcome"]
        self.assertFalse(capture.read_only)
        self.assertEqual(capture.mutates, "session")
        self.assertEqual(
            classify_command("/experience learning capture skill-outcome").policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_outcome_decision_preview_binds_success_to_keep(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("success",)
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            blueprint = builder.build(str(record["id"]), "keep")
            output = format_procedural_skill_outcome_decision_command(
                f"/experience learning skill-outcome-decision-preview {record['id']} keep",
                builder=builder,
                session=pilot.skill_outcome_decisions,
            )

        self.assertEqual(blueprint.outcome_status, "SUCCESS_CANDIDATE")
        self.assertEqual(blueprint.decision, "keep")
        self.assertEqual(len(blueprint.capture_receipt_ids), 1)
        self.assertIn("Status: CONFIRMABLE", output)
        self.assertIn("CONFIRM-SKILL-KEEP-", output)
        self.assertIn("future_apply_ready: false", output)

    def test_skill_outcome_decision_records_keep_without_store_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("success",)
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            blueprint = builder.build(str(record["id"]), "keep")
            token = procedural_skill_outcome_decision_confirmation_token(blueprint)
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            output = format_procedural_skill_outcome_decision_command(
                (
                    "/experience learning decide skill-outcome keep "
                    f"{record['id']} {token}"
                ),
                builder=builder,
                session=pilot.skill_outcome_decisions,
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertIn("Status: RECORDED IN PROCESS MEMORY", output)
        self.assertIn("decision: keep", output)
        self.assertIn("skill_mutation_performed: false", output)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)

    def test_skill_outcome_decision_refuses_wrong_token_and_wrong_mapping(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("success",)
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            blueprint = builder.build(str(record["id"]), "keep")
            wrong_token = format_procedural_skill_outcome_decision_command(
                (
                    "/experience learning decide skill-outcome keep "
                    f"{record['id']} WRONG"
                ),
                builder=builder,
                session=pilot.skill_outcome_decisions,
            )
            wrong_mapping = format_procedural_skill_outcome_decision_command(
                f"/experience learning skill-outcome-decision-preview {record['id']} revise",
                builder=builder,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn("token mismatch", wrong_token)
        self.assertIn("permits keep, not revise", wrong_mapping)
        self.assertEqual(pilot.skill_outcome_decisions.snapshot(), ())
        self.assertTrue(blueprint.terminal_process_decision)

    def test_skill_outcome_decision_accepts_failure_revise(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("failure",)
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            blueprint = builder.build(str(record["id"]), "revise")
            receipt = pilot.skill_outcome_decisions.decide(
                blueprint,
                token=procedural_skill_outcome_decision_confirmation_token(blueprint),
            )

        self.assertEqual(blueprint.outcome_status, "FAILURE_CANDIDATE")
        self.assertEqual(receipt.decision, "revise")
        self.assertFalse(receipt.future_apply_ready)

    def test_skill_outcome_decision_accepts_failure_archive_as_receipt_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("failure",)
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            blueprint = builder.build(str(record["id"]), "archive")
            status_before = library.read_snapshot()["records"][0]["status"]
            receipt = pilot.skill_outcome_decisions.decide(
                blueprint,
                token=procedural_skill_outcome_decision_confirmation_token(blueprint),
            )
            status_after = library.read_snapshot()["records"][0]["status"]

        self.assertEqual(receipt.decision, "archive")
        self.assertEqual(status_before, "active")
        self.assertEqual(status_after, "active")
        self.assertFalse(receipt.skill_mutation_performed)

    def test_skill_outcome_decision_mixed_evidence_requires_all_confirmed_captures(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("success", "failure")
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            blueprint = builder.build(str(record["id"]), "revise")

        self.assertEqual(blueprint.outcome_status, "MIXED_EVIDENCE")
        self.assertEqual(len(blueprint.evidence_event_ids), 2)
        self.assertEqual(len(blueprint.capture_receipt_ids), 2)

    def test_skill_outcome_decision_refuses_unconfirmed_manual_event_fixture(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            record = library.read_snapshot()["records"][0]
            events = build_test_procedural_skill_outcome_events(record, outcome="success")
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=events,
                memory_store=store,
                skill_library=library,
                capture_session=OperatorReviewedProceduralSkillOutcomeCaptureSession(),
            )

            with self.assertRaises(ProceduralSkillOutcomeDecisionError) as raised:
                builder.build(str(record["id"]), "keep")

        self.assertIn("not backed by an exact confirmed v3.5g", str(raised.exception))

    def test_skill_outcome_decision_is_terminal_and_run_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("failure",)
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            blueprint = builder.build(str(record["id"]), "revise")
            token = procedural_skill_outcome_decision_confirmation_token(blueprint)
            first = pilot.skill_outcome_decisions.decide(blueprint, token=token)
            with self.assertRaises(ProceduralSkillOutcomeDecisionError) as raised:
                pilot.skill_outcome_decisions.decide(blueprint, token=token)
            preview = format_procedural_skill_outcome_decision_command(
                f"/experience learning skill-outcome-decision-preview {record['id']} revise",
                builder=builder,
                session=pilot.skill_outcome_decisions,
            )

        self.assertEqual(first.decision, "revise")
        self.assertIn("already has terminal", str(raised.exception))
        self.assertIn("Status: NOT CONFIRMABLE", preview)

    def test_skill_outcome_decision_list_inspect_doctor_and_historical_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, pilot, record = build_test_captured_procedural_skill_outcomes(
                root, outcomes=("success",)
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            blueprint = builder.build(str(record["id"]), "keep")
            receipt = pilot.skill_outcome_decisions.decide(
                blueprint,
                token=procedural_skill_outcome_decision_confirmation_token(blueprint),
            )
            common = {"builder": builder, "session": pilot.skill_outcome_decisions}
            listed = format_procedural_skill_outcome_decision_command(
                "/experience learning skill-outcome-decisions", **common
            )
            inspected = format_procedural_skill_outcome_decision_command(
                f"/experience learning skill-outcome-decisions {receipt.id}", **common
            )
            current_doctor = format_procedural_skill_outcome_decision_command(
                "/experience learning skill-outcome-decision-doctor", **common
            )

            capture_builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            evidence = "A later operator-reported failure changed the evidence set."
            capture_blueprint = capture_builder.build(
                session_id=pilot.session_id,
                skill_id=str(record["id"]),
                outcome="failure",
                evidence=evidence,
            )
            pilot.skill_outcome_captures.capture(
                capture_blueprint,
                token=procedural_skill_outcome_capture_confirmation_token(capture_blueprint),
                pilot_state=pilot.state,
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )
            drifted_builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            drifted_doctor = format_procedural_skill_outcome_decision_command(
                "/experience learning skill-outcome-decision-doctor",
                builder=drifted_builder,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn(receipt.id, listed)
        self.assertIn("Status: OK", inspected)
        self.assertIn("Status: OK", current_doctor)
        self.assertIn(PROCEDURAL_SKILL_OUTCOME_DECISION_MODE, current_doctor)
        self.assertIn("Status: WARN", drifted_doctor)
        self.assertIn("historical", drifted_doctor)

    def test_skill_outcome_decision_registry_policy_and_chaining_are_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, _ = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("success",)
            )
            builder = ProceduralSkillOutcomeDecisionBuilder(
                events=pilot.snapshot(),
                memory_store=store,
                skill_library=library,
                capture_session=pilot.skill_outcome_captures,
            )
            chained = format_procedural_skill_outcome_decision_command(
                "/experience learning skill-outcome-decisions; /skills archive x",
                builder=builder,
                session=pilot.skill_outcome_decisions,
            )
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}

        self.assertIn("Command chaining", chained)
        self.assertEqual(PROCEDURAL_SKILL_OUTCOME_DECISION_MAX_RECEIPTS, 16)
        for prefix in (
            "/experience learning skill-outcome-decision-preview",
            "/experience learning skill-outcome-decisions",
            "/experience learning skill-outcome-decision-doctor",
        ):
            self.assertTrue(registry[prefix].read_only)
            self.assertEqual(registry[prefix].mutates, "none")
            self.assertEqual(classify_command(prefix).policy_class, "auto_allowed")
        decision = registry["/experience learning decide skill-outcome"]
        self.assertFalse(decision.read_only)
        self.assertEqual(decision.mutates, "session")
        self.assertEqual(
            classify_command("/experience learning decide skill-outcome").policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_lifecycle_readiness_revalidates_keep_without_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            events_before = pilot.snapshot()
            decisions_before = pilot.skill_outcome_decisions.snapshot()
            output = format_procedural_skill_lifecycle_readiness_command(
                f"/experience learning skill-outcome-lifecycle-readiness {receipt.id}",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()
            events_after = pilot.snapshot()
            decisions_after = pilot.skill_outcome_decisions.snapshot()

        self.assertIn("Status: READY FOR LIFECYCLE APPLY DESIGN REVIEW", output)
        self.assertIn("decision: keep", output)
        self.assertIn("decision_hash_matches: true", output)
        self.assertIn("skill_record_hash:", output)
        self.assertIn("future_apply_ready: false", output)
        self.assertIn("apply_token_generated: false", output)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(events_after, events_before)
        self.assertEqual(decisions_after, decisions_before)
        self.assertEqual(str(record["status"]), "active")

    def test_skill_lifecycle_archive_plan_requires_atomic_status_only_transition(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, record, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            output = format_procedural_skill_lifecycle_readiness_command(
                f"/experience learning skill-outcome-lifecycle-plan {receipt.skill_id}",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn("decision: archive", output)
        self.assertIn("expected_skill_record_mutations: 1", output)
        self.assertIn("atomic_write_required: true", output)
        self.assertIn("future_target_status: archived", output)
        self.assertIn(
            "rollback_suggestion: manual review required; restore needs a separate "
            "durable lifecycle transition contract",
            output,
        )
        self.assertIn("confirmation_token_hash", output)

    def test_skill_lifecycle_revise_plan_requires_separate_versioned_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="revise"
                )
            )
            output = format_procedural_skill_lifecycle_readiness_command(
                f"/experience learning skill-outcome-lifecycle-plan {receipt.id}",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn("decision: revise", output)
        self.assertIn("expected_skill_record_mutations: 0", output)
        self.assertIn("direct_lifecycle_apply_allowed: false", output)
        self.assertIn("revision_payload_required: true", output)
        self.assertIn("preserve_original_until_verified: true", output)
        self.assertIn("no in-place revision is permitted", output)

    def test_skill_lifecycle_readiness_refuses_missing_decision_and_chaining(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, _ = build_test_captured_procedural_skill_outcomes(
                Path(temp_dir), outcomes=("success",)
            )
            reviewer = ProceduralSkillLifecycleApplyReadiness(
                builder=ProceduralSkillOutcomeDecisionBuilder(
                    events=pilot.snapshot(),
                    memory_store=store,
                    skill_library=library,
                    capture_session=pilot.skill_outcome_captures,
                ),
                skill_library=library,
            )
            missing = format_procedural_skill_lifecycle_readiness_command(
                "/experience learning skill-outcome-lifecycle-readiness missing",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            chained = format_procedural_skill_lifecycle_readiness_command(
                "/experience learning skill-outcome-lifecycle-doctor; /skills archive x",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            doctor = format_procedural_skill_lifecycle_readiness_command(
                "/experience learning skill-outcome-lifecycle-doctor",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn("No process-memory skill outcome decision", missing)
        self.assertIn("Command chaining", chained)
        self.assertIn("Status: WARN", doctor)
        self.assertIn("No procedural skill outcome decision", doctor)

    def test_skill_lifecycle_readiness_fails_closed_on_later_evidence_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, pilot, record, receipt, _ = (
                build_test_procedural_skill_lifecycle_readiness(root)
            )
            capture_builder = ProceduralSkillOutcomeCaptureBuilder(
                memory_store=store,
                skill_library=library,
            )
            evidence = "Later confirmed failure makes the old keep decision historical."
            capture = capture_builder.build(
                session_id=pilot.session_id,
                skill_id=str(record["id"]),
                outcome="failure",
                evidence=evidence,
            )
            pilot.skill_outcome_captures.capture(
                capture,
                token=procedural_skill_outcome_capture_confirmation_token(capture),
                pilot_state=pilot.state,
                append_events=pilot.append_supervised_manual_skill_outcome_events,
            )
            drifted = ProceduralSkillLifecycleApplyReadiness(
                builder=ProceduralSkillOutcomeDecisionBuilder(
                    events=pilot.snapshot(),
                    memory_store=store,
                    skill_library=library,
                    capture_session=pilot.skill_outcome_captures,
                ),
                skill_library=library,
            )
            output = format_procedural_skill_lifecycle_readiness_command(
                f"/experience learning skill-outcome-lifecycle-readiness {receipt.id}",
                reviewer=drifted,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn("Status: NOT READY", output)
        self.assertIn("current_decision_revalidated: false", output)
        self.assertIn("Current decision evidence cannot be revalidated", output)
        self.assertIn("apply_token_generated: false", output)

    def test_skill_lifecycle_readiness_detects_current_skill_payload_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, pilot, record, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            library.update_summary(str(record["id"]), "Drifted after outcome decision.")
            output = format_procedural_skill_lifecycle_readiness_command(
                f"/experience learning skill-outcome-lifecycle-readiness {receipt.id}",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn("Status: NOT READY", output)
        self.assertIn("current_decision_revalidated: false", output)
        self.assertIn("current decision evidence", output.lower())

    def test_skill_lifecycle_doctor_and_shared_route_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(root / "proto_mind")
            )
            expected_library = root / "proto_mind" / "data" / "skills.jsonl"
            expected_library.parent.mkdir(parents=True, exist_ok=True)
            expected_library.write_bytes(library.skills_path.read_bytes())
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=MockReasoner(),
            )
            setattr(coordinator, EXPERIENCE_PILOT_ATTR, pilot)
            skill_before = expected_library.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            decisions_before = pilot.skill_outcome_decisions.snapshot()
            routed = format_experience_pilot_command(
                f"/experience learning skill-outcome-lifecycle-readiness {receipt.id}",
                owner=coordinator,
                project_root=root,
            )
            doctor = format_procedural_skill_lifecycle_readiness_command(
                "/experience learning skill-outcome-lifecycle-doctor",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            skill_after = expected_library.read_bytes()
            memory_after = store.persistent_path.read_bytes()
            decisions_after = pilot.skill_outcome_decisions.snapshot()

        self.assertIn("READY FOR LIFECYCLE APPLY DESIGN REVIEW", routed)
        self.assertIn("Status: OK", doctor)
        self.assertIn(PROCEDURAL_SKILL_LIFECYCLE_READINESS_MODE, doctor)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(decisions_after, decisions_before)

    def test_skill_lifecycle_registry_policy_and_future_contract_are_safe(self) -> None:
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}

        self.assertEqual(len(PROCEDURAL_SKILL_LIFECYCLE_FUTURE_RECEIPT_FIELDS), 14)
        for prefix in (
            "/experience learning skill-outcome-lifecycle-readiness",
            "/experience learning skill-outcome-lifecycle-plan",
            "/experience learning skill-outcome-lifecycle-doctor",
        ):
            self.assertTrue(registry[prefix].read_only)
            self.assertEqual(registry[prefix].mutates, "none")
            self.assertEqual(registry[prefix].risk, "low")
            self.assertEqual(classify_command(prefix).policy_class, "auto_allowed")
        apply_gate = registry[
            "/experience learning apply skill-outcome-lifecycle"
        ]
        self.assertFalse(apply_gate.read_only)
        self.assertEqual(apply_gate.mutates, "skills")
        self.assertEqual(apply_gate.risk, "medium")
        self.assertEqual(
            classify_command(apply_gate.prefix).policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_lifecycle_apply_preview_binds_exact_current_keep(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            review = pilot.skill_lifecycle_applies.review(receipt, reviewer=reviewer)
            output = format_procedural_skill_lifecycle_apply_command(
                f"/experience learning skill-outcome-lifecycle-apply-preview {receipt.id}",
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_applies,
                reviewer=reviewer,
            )

        self.assertTrue(review.confirmable)
        self.assertEqual(review.status, "CONFIRMABLE")
        self.assertEqual(review.decision, "keep")
        self.assertEqual(review.expected_record_mutations, 0)
        self.assertIn("Status: CONFIRMABLE", output)
        self.assertIn("CONFIRM-SKILL-LIFECYCLE-KEEP-", output)
        self.assertIn("target_execution_allowed: false", output)

    def test_skill_lifecycle_keep_apply_is_byte_stable_and_receipted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            review = pilot.skill_lifecycle_applies.review(receipt, reviewer=reviewer)
            token = procedural_skill_lifecycle_apply_confirmation_token(review)
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            applied = pilot.skill_lifecycle_applies.apply(
                receipt,
                token=token,
                reviewer=reviewer,
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(applied.apply_result, "keep_verified_noop")
        self.assertEqual(applied.actual_record_mutations, 0)
        self.assertFalse(applied.skill_mutation_performed)
        self.assertFalse(applied.target_execution_performed)
        self.assertTrue(applied.post_state_verified)
        self.assertTrue(applied.persistent_memory_unchanged)
        self.assertEqual(len(applied.receipt_hash), 64)

    def test_skill_lifecycle_apply_refuses_wrong_token_and_second_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            wrong = format_procedural_skill_lifecycle_apply_command(
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{receipt.id} WRONG"
                ),
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_applies,
                reviewer=reviewer,
            )
            review = pilot.skill_lifecycle_applies.review(receipt, reviewer=reviewer)
            pilot.skill_lifecycle_applies.apply(
                receipt,
                token=procedural_skill_lifecycle_apply_confirmation_token(review),
                reviewer=reviewer,
            )
            before_second = library.skills_path.read_bytes()
            second = format_procedural_skill_lifecycle_apply_command(
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{receipt.id} {procedural_skill_lifecycle_apply_confirmation_token(review)}"
                ),
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_applies,
                reviewer=reviewer,
            )
            after_second = library.skills_path.read_bytes()

        self.assertIn("token mismatch", wrong)
        self.assertIn("already applied", second)
        self.assertEqual(after_second, before_second)
        self.assertEqual(len(pilot.skill_lifecycle_applies.snapshot()), 1)

    def test_skill_lifecycle_apply_refuses_revise_without_replacement_contract(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="revise"
                )
            )
            before = library.skills_path.read_bytes()
            output = format_procedural_skill_lifecycle_apply_command(
                f"/experience learning skill-outcome-lifecycle-apply-preview {receipt.id}",
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_applies,
                reviewer=reviewer,
            )
            after = library.skills_path.read_bytes()

        self.assertIn("Status: NOT CONFIRMABLE", output)
        self.assertIn("Only keep or archive", output)
        self.assertIn("separate versioned replacement", output)
        self.assertNotIn("confirmation_token:", output)
        self.assertEqual(after, before)

    def test_skill_lifecycle_apply_refuses_drift_after_preview(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, pilot, record, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            review = pilot.skill_lifecycle_applies.review(receipt, reviewer=reviewer)
            token = procedural_skill_lifecycle_apply_confirmation_token(review)
            library.update_summary(str(record["id"]), "Changed after exact preview.")
            drifted_before = library.skills_path.read_bytes()
            output = format_procedural_skill_lifecycle_apply_command(
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{receipt.id} {token}"
                ),
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_applies,
                reviewer=reviewer,
            )
            drifted_after = library.skills_path.read_bytes()

        self.assertIn("readiness is not READY", output)
        self.assertEqual(drifted_after, drifted_before)
        self.assertEqual(pilot.skill_lifecycle_applies.snapshot(), ())

    def test_skill_lifecycle_apply_receipt_views_and_doctor_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            review = pilot.skill_lifecycle_applies.review(receipt, reviewer=reviewer)
            applied = pilot.skill_lifecycle_applies.apply(
                receipt,
                token=procedural_skill_lifecycle_apply_confirmation_token(review),
                reviewer=reviewer,
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            receipts_before = pilot.skill_lifecycle_applies.snapshot()
            common = {
                "decision_session": pilot.skill_outcome_decisions,
                "apply_session": pilot.skill_lifecycle_applies,
                "reviewer": reviewer,
            }
            listed = format_procedural_skill_lifecycle_apply_command(
                "/experience learning skill-outcome-lifecycle-applies", **common
            )
            inspected = format_procedural_skill_lifecycle_apply_command(
                f"/experience learning skill-outcome-lifecycle-applies {applied.id}",
                **common,
            )
            doctor = format_procedural_skill_lifecycle_apply_command(
                "/experience learning skill-outcome-lifecycle-apply-doctor", **common
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()
            receipts_after = pilot.skill_lifecycle_applies.snapshot()

        self.assertIn(applied.id, listed)
        self.assertIn("Status: OK", inspected)
        self.assertIn("receipt_hash:", inspected)
        self.assertIn("Status: OK", doctor)
        self.assertIn(PROCEDURAL_SKILL_LIFECYCLE_APPLY_MODE, doctor)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(receipts_after, receipts_before)

    def test_skill_lifecycle_apply_registry_policy_chaining_and_bounds_are_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, _, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            chained = format_procedural_skill_lifecycle_apply_command(
                (
                    "/experience learning skill-outcome-lifecycle-applies; "
                    "/skills restore x"
                ),
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_applies,
                reviewer=reviewer,
            )
        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}

        self.assertIn("Command chaining", chained)
        self.assertEqual(PROCEDURAL_SKILL_LIFECYCLE_APPLY_MAX_RECEIPTS, 1)
        for prefix in (
            "/experience learning skill-outcome-lifecycle-apply-preview",
            "/experience learning skill-outcome-lifecycle-applies",
            "/experience learning skill-outcome-lifecycle-apply-doctor",
        ):
            self.assertTrue(registry[prefix].read_only)
            self.assertEqual(registry[prefix].mutates, "none")
            self.assertEqual(classify_command(prefix).policy_class, "auto_allowed")
        apply_gate = registry[
            "/experience learning apply skill-outcome-lifecycle"
        ]
        self.assertFalse(apply_gate.read_only)
        self.assertEqual(apply_gate.mutates, "skills")
        self.assertEqual(apply_gate.risk, "medium")
        self.assertEqual(
            classify_command(apply_gate.prefix).policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_lifecycle_restore_contract_embeds_verified_archive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, record = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            archive = deepcopy(record["lifecycle"])
            restore = build_procedural_skill_lifecycle_restore_metadata_preview(
                skill_id=str(record["id"]),
                skill_provenance_id=str(record["provenance"]["id"]),
                transitioned_at="2026-07-20T02:00:00+00:00",
                prior_archive_envelope=archive,
                restore_review_hash="6" * 64,
                before_record_hash="7" * 64,
                confirmation_token_hash="8" * 64,
            )
            check = verify_procedural_skill_lifecycle_restore_metadata(restore)
            tampered = deepcopy(restore)
            tampered["prior_archive_envelope"]["reason"] = "invented"
            tamper_check = verify_procedural_skill_lifecycle_restore_metadata(
                tampered
            )

        self.assertTrue(check.verified)
        self.assertEqual(restore["schema"], PROCEDURAL_SKILL_LIFECYCLE_RESTORE_SCHEMA)
        self.assertEqual(restore["prior_archive_envelope"], archive)
        self.assertEqual(restore["prior_archive_hash"], archive["metadata_hash"])
        self.assertEqual(set(restore), set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_FIELDS))
        self.assertFalse(tamper_check.verified)

    def test_skill_lifecycle_restore_readiness_accepts_only_verified_archive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, record = build_test_durably_archived_procedural_skill(
                root
            )
            report = review_procedural_skill_lifecycle_restore(
                str(record["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )

        self.assertEqual(report.status, "READY FOR RESTORE DESIGN REVIEW")
        self.assertTrue(report.ready_for_design_review)
        self.assertEqual(report.audit_state, "archived_verified")
        self.assertEqual(report.provenance_status, "VERIFIED")
        self.assertEqual(
            report.expected_changed_fields,
            list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS),
        )
        self.assertEqual(
            report.future_receipt_fields,
            list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS),
        )
        self.assertEqual(
            report.metadata_blueprint["prior_archive_envelope"],
            record["lifecycle"],
        )
        self.assertTrue(report.writer_installed)
        self.assertFalse(report.apply_token_generated)
        self.assertFalse(report.mutation_performed)

    def test_skill_lifecycle_restore_readiness_refuses_active_and_legacy_archive(self) -> None:
        with TemporaryDirectory() as active_dir, TemporaryDirectory() as legacy_dir:
            active_store, active_library, _, active_record = (
                build_test_applied_procedural_skill(Path(active_dir))
            )
            active = review_procedural_skill_lifecycle_restore(
                str(active_record.created_skill_id),
                skills_path=active_library.skills_path,
                persistent_memory_path=active_store.persistent_path,
            )
            legacy_store, legacy_library, _, legacy_record = (
                build_test_applied_procedural_skill(Path(legacy_dir))
            )
            legacy_library.set_status(legacy_record.created_skill_id, "archived")
            legacy = review_procedural_skill_lifecycle_restore(
                legacy_record.created_skill_id,
                skills_path=legacy_library.skills_path,
                persistent_memory_path=legacy_store.persistent_path,
            )

        self.assertFalse(active.ready_for_design_review)
        self.assertEqual(active.audit_state, "active_verified")
        self.assertIn("Only an archived_verified", " ".join(active.issues))
        self.assertFalse(legacy.ready_for_design_review)
        self.assertEqual(legacy.audit_state, "archived_ambiguous")
        self.assertIn("archive envelope", " ".join(legacy.issues).lower())

    def test_skill_lifecycle_restore_readiness_refuses_active_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, record = build_test_durably_archived_procedural_skill(
                root
            )
            library.add_skill(str(record["name"]))
            report = review_procedural_skill_lifecycle_restore(
                str(record["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )

        self.assertFalse(report.ready_for_design_review)
        self.assertTrue(report.active_duplicate_skill_ids)
        self.assertIn("active duplicate", " ".join(report.issues).lower())

    def test_skill_lifecycle_restore_commands_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, record = build_test_durably_archived_procedural_skill(
                root
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            common = {
                "skills_path": library.skills_path,
                "persistent_memory_path": store.persistent_path,
            }
            contract = format_procedural_skill_lifecycle_restore_command(
                "/skills lifecycle-status --restore-contract", **common
            )
            readiness = format_procedural_skill_lifecycle_restore_command(
                f"/skills lifecycle-inspect {record['id']} --restore-readiness",
                **common,
            )
            plan = format_procedural_skill_lifecycle_restore_command(
                f"/skills lifecycle-inspect {record['id']} --restore-plan", **common
            )
            doctor = format_procedural_skill_lifecycle_restore_command(
                "/skills lifecycle-doctor --restore-contract", **common
            )

            self.assertIn(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_MODE, contract)
            self.assertIn("Status: READY FOR RESTORE DESIGN REVIEW", readiness)
            self.assertIn("current_writer_installed: true", plan)
            self.assertIn("expected_changed_fields: lifecycle, status, updated_at", plan)
            self.assertNotIn("confirmation_token:", readiness)
            self.assertNotIn("confirmation_token:", plan)
            self.assertIn("Status: OK", doctor)
            self.assertEqual(library.skills_path.read_bytes(), skill_before)
            self.assertEqual(store.persistent_path.read_bytes(), memory_before)

    def test_skill_lifecycle_restore_shared_route_and_registry_are_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, record = build_test_durably_archived_procedural_skill(
                root / "fixture"
            )
            live_path = root / "proto_mind" / "data" / "skills.jsonl"
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(library.skills_path.read_bytes())
            before = live_path.read_bytes()
            output = format_skill_command(
                f"/skills lifecycle-inspect {record['id']} --restore-plan",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            chained = format_skill_command(
                (
                    "/skills lifecycle-status --restore-contract; "
                    "/skills restore x"
                ),
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )

            self.assertEqual(live_path.read_bytes(), before)

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        self.assertIn("Restore Plan v1", output)
        self.assertIn("Command chaining", chained)
        self.assertTrue(registry["/skills lifecycle-status"].read_only)
        self.assertTrue(registry["/skills lifecycle-inspect"].read_only)
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)

    def test_skill_lifecycle_restore_doctor_reports_supervised_writer(self) -> None:
        report = procedural_skill_lifecycle_restore_doctor()

        self.assertEqual(report.status, "OK")
        self.assertTrue(report.deterministic_example_verified)
        self.assertTrue(report.tamper_refused)
        self.assertTrue(report.registry_coverage_ok)
        self.assertTrue(report.direct_status_guard_installed)
        self.assertTrue(report.payload_guard_installed)
        self.assertTrue(report.writer_installed)
        self.assertTrue(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_WRITER_INSTALLED)
        self.assertTrue(SKILL_LIFECYCLE_DIRECT_STATUS_GUARD_INSTALLED)
        self.assertTrue(SKILL_LIFECYCLE_PAYLOAD_GUARD_INSTALLED)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_lifecycle_restore_missing_stores_remain_absent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skills_path = root / "skills.jsonl"
            memory_path = root / "persistent_memory.json"
            before = list(root.rglob("*"))
            output = format_procedural_skill_lifecycle_restore_command(
                "/skills lifecycle-inspect missing --restore-readiness",
                skills_path=skills_path,
                persistent_memory_path=memory_path,
            )
            after = list(root.rglob("*"))

        self.assertIn("Status: NOT READY", output)
        self.assertIn("exactly one target skill record", output)
        self.assertNotIn("Traceback", output)
        self.assertEqual(after, before)

    def test_skill_lifecycle_direct_restore_refuses_durable_archive_exact_bytes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            output = library.set_status(str(record["id"]), "active")
            entry = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(str(record["id"]))

            self.assertIn("Skill lifecycle mutation refused", output)
            self.assertIn("requested_status: active", output)
            self.assertIn("--restore-readiness", output)
            self.assertIn("mutation_performed: false", output)
            self.assertEqual(library.skills_path.read_bytes(), skill_before)
            self.assertEqual(store.persistent_path.read_bytes(), memory_before)
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertEqual(entry.state, "archived_verified")

    def test_skill_lifecycle_direct_archive_refuses_managed_record_exact_bytes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, record = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            before = library.skills_path.read_bytes()
            output = library.set_status(str(record["id"]), "archived")

            self.assertIn("Skill lifecycle mutation refused", output)
            self.assertIn("requested_status: archived", output)
            self.assertEqual(library.skills_path.read_bytes(), before)

    def test_skill_lifecycle_direct_status_refuses_invalid_envelope(self) -> None:
        with TemporaryDirectory() as temp_dir:
            library = SkillLibrary(Path(temp_dir) / "skills.jsonl")
            library.add_skill("Guard invalid lifecycle")
            identifier = str(library.read_snapshot()["records"][0]["id"])
            library.set_status(identifier, "archived")
            records = library.read_snapshot()["records"]
            records[0]["lifecycle"] = {"schema": "unsupported"}
            library._write_records(records)
            before = library.skills_path.read_bytes()
            refused = library.set_status(identifier, "active")

            self.assertIn("lifecycle_schema: unsupported", refused)
            self.assertIn("mutation_performed: false", refused)
            self.assertEqual(library.skills_path.read_bytes(), before)

    def test_skill_lifecycle_direct_restore_preserves_legacy_provenanced_behavior(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, _, applied = build_test_applied_procedural_skill(
                Path(temp_dir)
            )
            archived = library.set_status(applied.created_skill_id, "archived")
            restored = library.set_status(applied.created_skill_id, "active")
            record = library.read_snapshot()["records"][0]

        self.assertIn("Archived skill", archived)
        self.assertIn("Active skill", restored)
        self.assertEqual(record["status"], "active")
        self.assertNotIn("lifecycle", record)

    def test_skill_lifecycle_direct_restore_guard_routes_through_shared_cli(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, record = build_test_durably_archived_procedural_skill(
                root / "fixture"
            )
            live_path = root / "proto_mind" / "data" / "skills.jsonl"
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(library.skills_path.read_bytes())
            before = live_path.read_bytes()
            output = format_skill_command(
                f"/skills restore {record['id']}",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )

            self.assertIn("Skill lifecycle mutation refused", output)
            self.assertIn("--restore-readiness", output)
            self.assertEqual(live_path.read_bytes(), before)

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        restore_spec = registry["/skills restore"]
        self.assertFalse(restore_spec.read_only)
        self.assertEqual(restore_spec.mutates, "skills")
        self.assertEqual(restore_spec.risk, "medium")
        self.assertEqual(
            classify_command("/skills restore skill_x").policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)

    def test_skill_lifecycle_payload_mutations_refuse_exact_bytes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, record = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            identifier = str(record["id"])
            before = library.skills_path.read_bytes()
            operations = (
                ("update_summary", lambda: library.update_summary(identifier, "changed")),
                ("set_body", lambda: library.set_body(identifier, "changed")),
                ("append_body", lambda: library.append_body(identifier, "changed")),
                ("add_tag", lambda: library.add_tag(identifier, "changed")),
                ("remove_tag", lambda: library.remove_tag(identifier, "changed")),
            )

            for action, operation in operations:
                with self.subTest(action=action):
                    output = operation()
                    self.assertIn("Skill lifecycle payload mutation refused", output)
                    self.assertIn(f"requested_action: {action}", output)
                    self.assertIn("mutation_performed: false", output)
                    self.assertEqual(library.skills_path.read_bytes(), before)

    def test_skill_lifecycle_use_refuses_telemetry_mutation_exact_bytes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, record = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            identifier = str(record["id"])
            before = library.skills_path.read_bytes()
            uses_before = record.get("uses")
            last_used_before = record.get("last_used_at")
            output = library.use_skill(identifier)
            current = library.read_snapshot()["records"][0]
            after = library.skills_path.read_bytes()

        self.assertIn("requested_action: use_skill", output)
        self.assertIn("uses, last_used_at, updated_at", output)
        self.assertEqual(after, before)
        self.assertEqual(current.get("uses"), uses_before)
        self.assertEqual(current.get("last_used_at"), last_used_before)

    def test_skill_lifecycle_payload_guard_fails_closed_on_invalid_envelope(self) -> None:
        with TemporaryDirectory() as temp_dir:
            library = SkillLibrary(Path(temp_dir) / "skills.jsonl")
            library.add_skill("Guard invalid lifecycle payload")
            identifier = str(library.read_snapshot()["records"][0]["id"])
            records = library.read_snapshot()["records"]
            records[0]["lifecycle"] = "corrupt"
            library._write_records(records)
            before = library.skills_path.read_bytes()
            update = library.update_summary(identifier, "must not change")
            use = library.use_skill(identifier)

            self.assertIn("lifecycle_schema: invalid_or_unknown", update)
            self.assertIn("requested_action: use_skill", use)
            self.assertEqual(library.skills_path.read_bytes(), before)

    def test_skill_lifecycle_payload_guard_preserves_pre_lifecycle_behavior(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, _, applied = build_test_applied_procedural_skill(
                Path(temp_dir)
            )
            identifier = applied.created_skill_id
            original_tags = list(library.read_snapshot()["records"][0]["tags"])
            outputs = [
                library.update_summary(identifier, "Updated legacy summary"),
                library.set_body(identifier, "Step one"),
                library.append_body(identifier, "Step two"),
                library.add_tag(identifier, "legacy"),
                library.remove_tag(identifier, "legacy"),
                library.use_skill(identifier),
            ]
            current = library.read_snapshot()["records"][0]

        self.assertTrue(all("refused" not in output.lower() for output in outputs))
        self.assertEqual(current["summary"], "Updated legacy summary")
        self.assertEqual(current["body"], "Step one\nStep two")
        self.assertEqual(current["tags"], original_tags)
        self.assertEqual(current["uses"], 1)
        self.assertNotIn("lifecycle", current)

    def test_skill_lifecycle_payload_guard_routes_through_shared_cli(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, record = build_test_durably_archived_procedural_skill(
                root / "fixture"
            )
            live_path = root / "proto_mind" / "data" / "skills.jsonl"
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(library.skills_path.read_bytes())
            before = live_path.read_bytes()
            update = format_skill_command(
                f"/skills update {record['id']} --summary changed",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            use = format_skill_command(
                f"/skills use {record['id']}",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )

            self.assertIn("requested_action: update_summary", update)
            self.assertIn("requested_action: use_skill", use)
            self.assertEqual(live_path.read_bytes(), before)

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        self.assertIn("fail closed", registry["/skills update"].description)
        self.assertIn("fail closed", registry["/skills use"].description)
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_restore_authorization_doctor_reports_supervised_gate(self) -> None:
        report = procedural_skill_restore_authorization_doctor()
        output = format_procedural_skill_restore_authorization_command(
            "/skills lifecycle-doctor --restore-authorization",
            skills_path=Path("missing-skills.jsonl"),
            persistent_memory_path=Path("missing-memory.json"),
        )

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.schema, PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_SCHEMA)
        self.assertEqual(
            report.blueprint_field_count,
            len(PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_BLUEPRINT_FIELDS),
        )
        self.assertTrue(report.deterministic_example_verified)
        self.assertTrue(report.tamper_refused)
        self.assertTrue(report.restore_contract_healthy)
        self.assertTrue(report.authorization_engine_installed)
        self.assertTrue(report.token_generator_installed)
        self.assertTrue(report.run_once_state_installed)
        self.assertTrue(report.writer_installed)
        self.assertTrue(PROCEDURAL_SKILL_RESTORE_AUTHORIZATION_ENGINE_INSTALLED)
        self.assertTrue(PROCEDURAL_SKILL_RESTORE_TOKEN_GENERATOR_INSTALLED)
        self.assertTrue(PROCEDURAL_SKILL_RESTORE_RUN_ONCE_STATE_INSTALLED)
        self.assertIn("Status: OK", output)
        self.assertIn("token_generator_installed: true", output)

    def test_skill_restore_authorization_readiness_binds_current_archived_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            report = review_procedural_skill_restore_authorization(
                str(record["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )

            self.assertEqual(library.skills_path.read_bytes(), skill_before)
            self.assertEqual(store.persistent_path.read_bytes(), memory_before)

        blueprint = report.authorization_blueprint
        self.assertEqual(report.status, "READY FOR AUTHORIZATION DESIGN REVIEW")
        self.assertTrue(report.ready_for_authorization_design_review)
        self.assertEqual(len(report.authorization_blueprint_hash), 64)
        self.assertEqual(blueprint["skill_id"], record["id"])
        self.assertEqual(blueprint["from_status"], "archived")
        self.assertEqual(blueprint["to_status"], "active")
        self.assertEqual(
            blueprint["expected_changed_fields"],
            list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS),
        )
        self.assertEqual(
            blueprint["future_receipt_fields"],
            list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS),
        )
        self.assertIn("body", blueprint["immutable_record_fields"])
        self.assertIn("provenance", blueprint["immutable_record_fields"])
        self.assertFalse(report.token_generated)
        self.assertFalse(report.mutation_performed)

    def test_skill_restore_authorization_commands_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, record = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            common = {
                "skills_path": library.skills_path,
                "persistent_memory_path": store.persistent_path,
            }
            contract = format_procedural_skill_restore_authorization_command(
                "/skills lifecycle-status --restore-authorization-contract",
                **common,
            )
            readiness = format_procedural_skill_restore_authorization_command(
                f"/skills lifecycle-inspect {record['id']} --restore-authorization",
                **common,
            )
            plan = format_procedural_skill_restore_authorization_command(
                f"/skills lifecycle-inspect {record['id']} --restore-authorization-plan",
                **common,
            )

            self.assertEqual(library.skills_path.read_bytes(), skill_before)
            self.assertEqual(store.persistent_path.read_bytes(), memory_before)

        self.assertIn("Authorization Contract v1", contract)
        self.assertIn("token_generator_installed: true", contract)
        self.assertIn("READY FOR AUTHORIZATION DESIGN REVIEW", readiness)
        self.assertIn("token_generated: false", readiness)
        self.assertIn("<authorization_blueprint_hash>", readiness)
        self.assertIn("future_expected_changed_fields: lifecycle, status, updated_at", plan)
        self.assertIn("current_writer_installed: true", plan)
        self.assertNotIn("confirmation_token:", readiness)
        self.assertNotIn("confirmation_token:", plan)

    def test_skill_restore_authorization_refuses_active_and_missing_records(self) -> None:
        with TemporaryDirectory() as active_dir, TemporaryDirectory() as missing_dir:
            active_store, active_library, _, active_record = (
                build_test_applied_procedural_skill(Path(active_dir))
            )
            active = review_procedural_skill_restore_authorization(
                active_record.created_skill_id,
                skills_path=active_library.skills_path,
                persistent_memory_path=active_store.persistent_path,
            )
            missing_root = Path(missing_dir)
            before = list(missing_root.rglob("*"))
            missing = review_procedural_skill_restore_authorization(
                "missing",
                skills_path=missing_root / "skills.jsonl",
                persistent_memory_path=missing_root / "memory.json",
            )
            after = list(missing_root.rglob("*"))

        self.assertEqual(active.status, "NOT READY")
        self.assertIn("archived_verified", " ".join(active.issues))
        self.assertEqual(missing.status, "NOT READY")
        self.assertFalse(missing.ready_for_authorization_design_review)
        self.assertEqual(after, before)

    def test_skill_restore_authorization_shared_route_and_registry_are_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, record = build_test_durably_archived_procedural_skill(
                root / "fixture"
            )
            live_path = root / "proto_mind" / "data" / "skills.jsonl"
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(library.skills_path.read_bytes())
            before = live_path.read_bytes()
            output = format_skill_command(
                f"/skills lifecycle-inspect {record['id']} --restore-authorization-plan",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            chained = format_skill_command(
                (
                    "/skills lifecycle-status --restore-authorization-contract; "
                    "/skills restore x"
                ),
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )

            self.assertEqual(live_path.read_bytes(), before)

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        self.assertIn("Authorization Plan v1", output)
        self.assertIn("Command chaining", chained)
        self.assertTrue(registry["/skills lifecycle-status"].read_only)
        self.assertTrue(registry["/skills lifecycle-inspect"].read_only)
        self.assertTrue(registry["/skills lifecycle-doctor"].read_only)
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_restore_apply_exact_token_preserves_archive_and_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, archived = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            session = OperatorReviewedProceduralSkillRestoreApplySession()
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            review = session.review(
                str(archived["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            receipt = session.apply(
                str(archived["id"]),
                token=procedural_skill_restore_apply_confirmation_token(review),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            restored = library.read_snapshot()["records"][0]
            audit = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(str(archived["id"]))
            doctor = session.doctor(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            restored_bytes = library.skills_path.read_bytes()
            use_output = library.use_skill(str(archived["id"]))
            memory_after = store.persistent_path.read_bytes()
            skill_after_use = library.skills_path.read_bytes()

        self.assertEqual(review.status, "CONFIRMABLE")
        self.assertTrue(review.confirmable)
        self.assertNotEqual(restored_bytes, skill_before)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(restored["status"], "active")
        self.assertEqual(restored["provenance"], archived["provenance"])
        self.assertEqual(restored["body"], archived["body"])
        self.assertEqual(
            restored["lifecycle"]["prior_archive_envelope"], archived["lifecycle"]
        )
        self.assertTrue(
            verify_procedural_skill_lifecycle_restore_metadata(
                restored["lifecycle"]
            ).verified
        )
        self.assertEqual(
            set(receipt.to_dict()),
            set(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_RECEIPT_FIELDS),
        )
        self.assertEqual(receipt.exact_record_mutations, 1)
        self.assertEqual(
            receipt.changed_fields,
            list(PROCEDURAL_SKILL_LIFECYCLE_RESTORE_EXPECTED_CHANGED_FIELDS),
        )
        self.assertEqual(
            receipt.receipt_hash,
            procedural_skill_restore_apply_receipt_hash(receipt.to_dict()),
        )
        self.assertTrue(receipt.post_state_verified)
        self.assertTrue(receipt.archive_evidence_preserved)
        self.assertTrue(receipt.durable_provenance_preserved)
        self.assertTrue(receipt.persistent_memory_unchanged)
        self.assertFalse(receipt.rollback_performed)
        self.assertIsNotNone(audit)
        assert audit is not None
        self.assertEqual(audit.state, "active_restored_verified")
        self.assertTrue(audit.restart_safe)
        self.assertTrue(audit.outcome_archive_proven)
        self.assertEqual(doctor.status, "OK")
        self.assertIn("lifecycle payload mutation refused", use_output.lower())
        self.assertEqual(skill_after_use, restored_bytes)

    def test_skill_restore_apply_wrong_token_and_active_state_fail_closed(self) -> None:
        with TemporaryDirectory() as archived_dir, TemporaryDirectory() as active_dir:
            store, library, archived = build_test_durably_archived_procedural_skill(
                Path(archived_dir)
            )
            session = OperatorReviewedProceduralSkillRestoreApplySession()
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            with self.assertRaisesRegex(
                ProceduralSkillRestoreApplyError, "token mismatch"
            ):
                session.apply(
                    str(archived["id"]),
                    token="WRONG-TOKEN",
                    skills_path=library.skills_path,
                    persistent_memory_path=store.persistent_path,
                )
            active_store, active_library, _, active = (
                build_test_applied_procedural_skill(Path(active_dir))
            )
            active_review = session.review(
                active.created_skill_id,
                skills_path=active_library.skills_path,
                persistent_memory_path=active_store.persistent_path,
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(session.snapshot(), ())
        self.assertFalse(active_review.confirmable)
        self.assertIn("archived_verified", " ".join(active_review.issues))

    def test_skill_restore_apply_is_run_once_per_process(self) -> None:
        with TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
            first_store, first_library, first = (
                build_test_durably_archived_procedural_skill(Path(first_dir))
            )
            second_store, second_library, second = (
                build_test_durably_archived_procedural_skill(Path(second_dir))
            )
            session = OperatorReviewedProceduralSkillRestoreApplySession()
            first_review = session.review(
                str(first["id"]),
                skills_path=first_library.skills_path,
                persistent_memory_path=first_store.persistent_path,
            )
            session.apply(
                str(first["id"]),
                token=procedural_skill_restore_apply_confirmation_token(first_review),
                skills_path=first_library.skills_path,
                persistent_memory_path=first_store.persistent_path,
            )
            second_before = second_library.skills_path.read_bytes()
            second_review = session.review(
                str(second["id"]),
                skills_path=second_library.skills_path,
                persistent_memory_path=second_store.persistent_path,
            )
            with self.assertRaisesRegex(
                ProceduralSkillRestoreApplyError, "single durable restore slot"
            ):
                session.apply(
                    str(second["id"]),
                    token="unused",
                    skills_path=second_library.skills_path,
                    persistent_memory_path=second_store.persistent_path,
                )
            second_after = second_library.skills_path.read_bytes()

        self.assertEqual(PROCEDURAL_SKILL_RESTORE_APPLY_MAX_RECEIPTS, 1)
        self.assertFalse(second_review.confirmable)
        self.assertEqual(second_after, second_before)
        self.assertEqual(len(session.snapshot()), 1)

    def test_skill_restore_apply_rolls_back_exact_bytes_on_verification_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, archived = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            session = OperatorReviewedProceduralSkillRestoreApplySession()
            review = session.review(
                str(archived["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            with patch(
                "proto_mind.skill_lifecycle_restore_apply._verify_restore",
                side_effect=ProceduralSkillRestoreApplyError("injected failure"),
            ):
                with self.assertRaisesRegex(
                    ProceduralSkillRestoreApplyError, "exact original"
                ):
                    session.apply(
                        str(archived["id"]),
                        token=procedural_skill_restore_apply_confirmation_token(
                            review
                        ),
                        skills_path=library.skills_path,
                        persistent_memory_path=store.persistent_path,
                    )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(session.snapshot(), ())

    def test_skill_restore_apply_formatter_and_shared_route_are_guarded(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, archived = build_test_durably_archived_procedural_skill(
                root / "fixture"
            )
            live_path = root / "proto_mind" / "data" / "skills.jsonl"
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(library.skills_path.read_bytes())
            before = live_path.read_bytes()
            reset_procedural_skill_restore_apply_session()
            preview = format_skill_command(
                f"/skills lifecycle-inspect {archived['id']} --restore-apply-preview",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            token = next(
                line.split(": ", 1)[1]
                for line in preview.splitlines()
                if line.startswith("confirmation_token: ")
            )
            wrong = format_skill_command(
                f"/skills restore {archived['id']} WRONG --durable",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            chained = format_procedural_skill_restore_apply_command(
                f"/skills restore {archived['id']} {token} --durable; /skills list",
                skills_path=live_path,
                persistent_memory_path=store.persistent_path,
            )
            applied = format_skill_command(
                f"/skills restore {archived['id']} {token} --durable",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            receipt = format_skill_command(
                f"/skills lifecycle-inspect {archived['id']} --restore-apply-receipt",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            doctor = format_skill_command(
                "/skills lifecycle-doctor --restore-apply",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            live_after = live_path.read_bytes()
            reset_procedural_skill_restore_apply_session()

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        self.assertIn("Status: CONFIRMABLE", preview)
        self.assertIn("token mismatch", wrong)
        self.assertNotEqual(live_after, before)
        self.assertIn("Command chaining", chained)
        self.assertIn("Status: APPLIED", applied)
        self.assertIn("Status: OK", receipt)
        self.assertIn("Status: OK", doctor)
        self.assertTrue(PROCEDURAL_SKILL_RESTORE_APPLY_ENGINE_INSTALLED)
        self.assertFalse(registry["/skills restore"].read_only)
        self.assertEqual(registry["/skills restore"].mutates, "skills")
        self.assertEqual(registry["/skills restore"].risk, "medium")
        self.assertEqual(
            classify_command("/skills restore x token --durable").policy_class,
            "confirmation_required",
        )
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_restore_receipt_audit_recovers_durable_evidence_after_restart(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, archived = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            apply_session = OperatorReviewedProceduralSkillRestoreApplySession()
            review = apply_session.review(
                str(archived["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            apply_session.apply(
                str(archived["id"]),
                token=procedural_skill_restore_apply_confirmation_token(review),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            skills_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            # No process receipts simulates a fresh process after restart.
            entry = ProceduralSkillRestoreReceiptAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(str(archived["id"]))
            skills_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.status, "VERIFIED")
        self.assertEqual(entry.audit_state, "active_restored_verified")
        self.assertEqual(entry.process_receipt_status, "NOT_AVAILABLE")
        self.assertTrue(entry.current_state_verified)
        self.assertTrue(entry.restart_safe)
        self.assertFalse(entry.original_apply_receipt_reconstructed)
        self.assertFalse(entry.process_receipt_persisted)
        self.assertFalse(entry.mutation_performed)
        self.assertEqual(entry.evidence["schema"], PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_SCHEMA)
        self.assertEqual(set(entry.evidence), set(PROCEDURAL_SKILL_RESTORE_RECEIPT_EVIDENCE_FIELDS))
        self.assertTrue(
            verify_procedural_skill_restore_receipt_evidence(entry.evidence).verified
        )
        self.assertEqual(
            entry.durably_recoverable_receipt_fields,
            list(PROCEDURAL_SKILL_RESTORE_DURABLY_RECOVERABLE_RECEIPT_FIELDS),
        )
        self.assertEqual(
            entry.process_only_receipt_fields,
            list(PROCEDURAL_SKILL_RESTORE_PROCESS_ONLY_RECEIPT_FIELDS),
        )
        self.assertEqual(skills_after, skills_before)
        self.assertEqual(memory_after, memory_before)

    def test_skill_restore_receipt_audit_matches_current_process_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, archived = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            apply_session = OperatorReviewedProceduralSkillRestoreApplySession()
            review = apply_session.review(
                str(archived["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            receipt = apply_session.apply(
                str(archived["id"]),
                token=procedural_skill_restore_apply_confirmation_token(review),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            before = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())
            report = ProceduralSkillRestoreReceiptAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
                process_receipts=apply_session.snapshot(),
            ).inspect()
            after = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.verified_evidence_count, 1)
        self.assertEqual(report.matched_process_receipt_count, 1)
        self.assertEqual(report.unavailable_process_receipt_count, 0)
        self.assertEqual(report.entries[0].process_receipt_status, "MATCHED")
        self.assertEqual(report.entries[0].process_receipt_id, receipt.restore_apply_id)
        self.assertEqual(report.entries[0].process_receipt_hash, receipt.receipt_hash)
        self.assertFalse(report.receipt_history_invented)
        self.assertFalse(report.mutation_performed)
        self.assertEqual(after, before)

    def test_skill_restore_receipt_export_is_copyable_json_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, archived = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            apply_session = OperatorReviewedProceduralSkillRestoreApplySession()
            review = apply_session.review(
                str(archived["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            apply_session.apply(
                str(archived["id"]),
                token=procedural_skill_restore_apply_confirmation_token(review),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            before = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())
            common = {
                "skills_path": library.skills_path,
                "persistent_memory_path": store.persistent_path,
                "process_receipts": (),
            }
            contract = format_procedural_skill_restore_receipt_audit_command(
                "/skills lifecycle-status --restore-receipt-contract", **common
            )
            history = format_procedural_skill_restore_receipt_audit_command(
                "/skills lifecycle-history --restore-receipts", **common
            )
            inspected = format_procedural_skill_restore_receipt_audit_command(
                f"/skills lifecycle-inspect {archived['id']} --restore-receipt-audit",
                **common,
            )
            exported = format_procedural_skill_restore_receipt_audit_command(
                f"/skills lifecycle-inspect {archived['id']} --restore-receipt-export",
                **common,
            )
            doctor = format_procedural_skill_restore_receipt_audit_command(
                "/skills lifecycle-doctor --restore-receipts", **common
            )
            after = (library.skills_path.read_bytes(), store.persistent_path.read_bytes())

        assert contract is not None
        assert history is not None
        assert inspected is not None
        assert exported is not None
        assert doctor is not None
        evidence_text = exported.split("Evidence JSON:\n", 1)[1].split("\nBoundary:", 1)[0]
        evidence = json.loads(evidence_text)
        self.assertIn(PROCEDURAL_SKILL_RESTORE_RECEIPT_AUDIT_MODE, contract)
        self.assertIn("original_apply_receipt_reconstructed: false", contract)
        self.assertIn(str(archived["id"]), history)
        self.assertIn("process_receipt_status: NOT_AVAILABLE", inspected)
        self.assertEqual(evidence["skill_id"], archived["id"])
        self.assertTrue(verify_procedural_skill_restore_receipt_evidence(evidence).verified)
        self.assertIn("file_written: false", exported)
        self.assertIn("Status: OK", doctor)
        self.assertEqual(after, before)

    def test_skill_restore_receipt_audit_reports_legacy_and_tamper(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, archived = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            apply_session = OperatorReviewedProceduralSkillRestoreApplySession()
            review = apply_session.review(
                str(archived["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            apply_session.apply(
                str(archived["id"]),
                token=procedural_skill_restore_apply_confirmation_token(review),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            record = library.read_snapshot()["records"][0]
            evidence = build_procedural_skill_restore_receipt_evidence(record)
            tampered = deepcopy(evidence)
            tampered["prior_archive_hash"] = "0" * 64
            legacy = ({"restore_apply_id": "legacy", "skill_id": archived["id"]},)
            report = ProceduralSkillRestoreReceiptAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
                process_receipts=legacy,
            ).inspect()

        self.assertFalse(verify_procedural_skill_restore_receipt_evidence(tampered).verified)
        self.assertEqual(report.status, "WARN")
        self.assertEqual(report.legacy_process_receipt_count, 1)
        self.assertEqual(report.entries[0].status, "VERIFIED")
        self.assertEqual(report.entries[0].process_receipt_status, "LEGACY")
        self.assertIn("legacy/incomplete", " ".join(report.entries[0].warnings))

    def test_skill_restore_receipt_shared_route_and_registry_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, archived = build_test_durably_archived_procedural_skill(
                root / "fixture"
            )
            apply_session = OperatorReviewedProceduralSkillRestoreApplySession()
            review = apply_session.review(
                str(archived["id"]),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            apply_session.apply(
                str(archived["id"]),
                token=procedural_skill_restore_apply_confirmation_token(review),
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            )
            live_path = root / "proto_mind" / "data" / "skills.jsonl"
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(library.skills_path.read_bytes())
            before = (live_path.read_bytes(), store.persistent_path.read_bytes())
            reset_procedural_skill_restore_apply_session()
            output = format_skill_command(
                f"/skills lifecycle-inspect {archived['id']} --restore-receipt-audit",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            chained = format_skill_command(
                "/skills lifecycle-status --restore-receipt-contract; /skills restore x",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            after = (live_path.read_bytes(), store.persistent_path.read_bytes())

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        self.assertIn("Status: VERIFIED", output)
        self.assertIn("Command chaining", chained)
        self.assertEqual(after, before)
        for prefix in (
            "/skills lifecycle-status",
            "/skills lifecycle-history",
            "/skills lifecycle-inspect",
            "/skills lifecycle-doctor",
        ):
            self.assertTrue(registry[prefix].read_only)
            self.assertEqual(registry[prefix].mutates, "none")
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_skill_restore_receipt_doctor_detects_orphan_process_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _ = build_test_durably_archived_procedural_skill(
                Path(temp_dir)
            )
            report = ProceduralSkillRestoreReceiptAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
                process_receipts=(
                    {"restore_apply_id": "orphan", "skill_id": "missing_skill"},
                ),
            ).inspect()

        self.assertEqual(report.status, "WARN")
        self.assertEqual(report.durable_restore_count, 0)
        self.assertEqual(report.orphan_process_receipt_count, 1)
        self.assertEqual(report.legacy_process_receipt_count, 1)
        self.assertIn("no current durable restore envelope", " ".join(report.warnings))
