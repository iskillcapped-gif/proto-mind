"""Core flow checks: durable."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    COMMAND_REGISTRY,
    Coordinator,
    EXPERIENCE_PILOT_ATTR,
    MemoryKeeper,
    MockReasoner,
    Observer,
    PROCEDURAL_SKILL_LIFECYCLE_AUDIT_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_MODE,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_WRITER_INSTALLED,
    PROCEDURAL_SKILL_LIFECYCLE_METADATA_REASON,
    Path,
    ProceduralSkillLifecycleAudit,
    ProceduralSkillLifecycleMetadataApplyError,
    ProceduralSkillLifecycleMetadataReadiness,
    SkillLibrary,
    TemporaryDirectory,
    action_policy_doctor,
    build_test_applied_procedural_skill,
    build_test_procedural_skill_lifecycle_readiness,
    classify_command,
    command_registry_doctor,
    deepcopy,
    format_experience_pilot_command,
    format_procedural_skill_lifecycle_metadata_apply_command,
    format_procedural_skill_lifecycle_readiness_command,
    format_skill_command,
    format_skill_lifecycle_audit_command,
    patch,
    procedural_skill_lifecycle_metadata_apply_confirmation_token,
    procedural_skill_lifecycle_metadata_apply_receipt_hash,
    procedural_skill_lifecycle_metadata_readiness_doctor,
    verify_procedural_skill_lifecycle_metadata,
)


class DurableFlowTests(unittest.TestCase):
    def test_durable_skill_lifecycle_writer_readiness_binds_archive_blueprint(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            report = ProceduralSkillLifecycleMetadataReadiness(reviewer).review(
                receipt
            )
            skill_after = library.skills_path.read_bytes()
            memory_after = store.persistent_path.read_bytes()

        self.assertEqual(report.status, "READY FOR DURABLE APPLY PREVIEW")
        self.assertTrue(report.ready_for_writer_design_review)
        self.assertTrue(report.metadata_required)
        self.assertEqual(len(report.metadata_blueprint_hash), 64)
        self.assertEqual(
            report.metadata_blueprint["decision_hash"], receipt.decision_hash
        )
        self.assertEqual(
            report.metadata_blueprint["capture_receipt_hashes"],
            receipt.capture_receipt_hashes,
        )
        self.assertEqual(
            report.expected_changed_fields,
            list(PROCEDURAL_SKILL_LIFECYCLE_METADATA_EXPECTED_CHANGED_FIELDS),
        )
        self.assertTrue(report.writer_installed)
        self.assertFalse(report.current_writer_compatible)
        self.assertFalse(report.apply_token_generated)
        self.assertFalse(report.mutation_performed)
        self.assertEqual(skill_after, skill_before)
        self.assertEqual(memory_after, memory_before)

    def test_durable_skill_lifecycle_plan_requires_exact_future_mutation_and_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            readiness = format_procedural_skill_lifecycle_readiness_command(
                (
                    "/experience learning skill-outcome-lifecycle-readiness "
                    f"{receipt.id} --durable"
                ),
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            plan = format_procedural_skill_lifecycle_readiness_command(
                (
                    "/experience learning skill-outcome-lifecycle-plan "
                    f"{receipt.skill_id} --durable"
                ),
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn("READY FOR DURABLE APPLY PREVIEW", readiness)
        self.assertIn(PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_MODE, readiness)
        self.assertIn("writer_installed: true", readiness)
        self.assertIn("current_writer_compatible: false", readiness)
        self.assertIn("future_writer_ready: true", readiness)
        self.assertIn("expected_record_mutations: 1", plan)
        self.assertIn("expected_changed_fields: lifecycle, status, updated_at", plan)
        self.assertIn("exact original Skill Library bytes", plan)
        for field in PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS:
            self.assertIn(f"- {field}", plan)
        self.assertNotIn("confirmation_token:", readiness)
        self.assertNotIn("confirmation_token:", plan)

    def test_durable_skill_lifecycle_keep_requires_no_metadata_or_record_mutation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            before_skill = library.skills_path.read_bytes()
            before_memory = store.persistent_path.read_bytes()
            readiness = format_procedural_skill_lifecycle_readiness_command(
                (
                    "/experience learning skill-outcome-lifecycle-readiness "
                    f"{receipt.id} --durable"
                ),
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            plan = format_procedural_skill_lifecycle_readiness_command(
                (
                    "/experience learning skill-outcome-lifecycle-plan "
                    f"{receipt.id} --durable"
                ),
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            after_skill = library.skills_path.read_bytes()
            after_memory = store.persistent_path.read_bytes()

        self.assertIn("NO DURABLE METADATA REQUIRED", readiness)
        self.assertIn("metadata_required: false", readiness)
        self.assertIn("expected_record_mutations: 0", plan)
        self.assertIn("skill_library_bytes_must_remain_identical: true", plan)
        self.assertEqual(after_skill, before_skill)
        self.assertEqual(after_memory, before_memory)

    def test_durable_skill_lifecycle_revise_remains_not_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="revise"
                )
            )
            output = format_procedural_skill_lifecycle_readiness_command(
                (
                    "/experience learning skill-outcome-lifecycle-readiness "
                    f"{receipt.id} --durable"
                ),
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )

        self.assertIn("Status: NOT READY", output)
        self.assertIn("metadata_required: false", output)
        self.assertIn("revise needs a separate replacement contract", output)
        self.assertIn("apply_token_generated: false", output)

    def test_durable_skill_lifecycle_writer_readiness_detects_later_skill_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, _, record, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            library.update_summary(
                str(record["id"]), "Changed after durable readiness source decision."
            )
            report = ProceduralSkillLifecycleMetadataReadiness(reviewer).review(
                receipt
            )

        self.assertEqual(report.status, "NOT READY")
        self.assertFalse(report.ready_for_writer_design_review)
        self.assertFalse(report.checks["base_lifecycle_readiness_current"])
        self.assertTrue(report.metadata_blueprint_hash)
        self.assertFalse(report.apply_token_generated)
        self.assertFalse(report.mutation_performed)

    def test_durable_skill_lifecycle_readiness_doctor_parser_and_registry_are_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, _, pilot, _, _, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(Path(temp_dir))
            )
            doctor = format_procedural_skill_lifecycle_readiness_command(
                "/experience learning skill-outcome-lifecycle-doctor",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            invalid = format_procedural_skill_lifecycle_readiness_command(
                "/experience learning skill-outcome-lifecycle-plan x --write",
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )
            chained = format_procedural_skill_lifecycle_readiness_command(
                (
                    "/experience learning skill-outcome-lifecycle-readiness x "
                    "--durable | /skills archive x"
                ),
                reviewer=reviewer,
                session=pilot.skill_outcome_decisions,
            )

        contract_doctor = procedural_skill_lifecycle_metadata_readiness_doctor()
        self.assertIn("Durable Procedural Skill Lifecycle Writer Readiness Doctor", doctor)
        self.assertIn("metadata_contract_status: OK", doctor)
        self.assertIn("writer_installed: true", doctor)
        self.assertIn("current_writer_compatible: false", doctor)
        self.assertIn("Usage:", invalid)
        self.assertIn("Command chaining", chained)
        self.assertEqual(contract_doctor.status, "OK")
        self.assertTrue(PROCEDURAL_SKILL_LIFECYCLE_METADATA_READINESS_WRITER_INSTALLED)
        self.assertFalse(PROCEDURAL_SKILL_LIFECYCLE_CURRENT_WRITER_SUPPORTS_METADATA)
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")

    def test_durable_skill_lifecycle_apply_preview_is_exact_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            preview = format_procedural_skill_lifecycle_metadata_apply_command(
                (
                    "/experience learning skill-outcome-lifecycle-apply-preview "
                    f"{receipt.id} --durable"
                ),
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_metadata_applies,
                reviewer=reviewer,
            )
            wrong = format_procedural_skill_lifecycle_metadata_apply_command(
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{receipt.id} WRONG --durable"
                ),
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_metadata_applies,
                reviewer=reviewer,
            )

            self.assertIn("Status: CONFIRMABLE", preview)
            self.assertIn("CONFIRM-DURABLE-SKILL-LIFECYCLE-ARCHIVE-", preview)
            self.assertIn(
                "expected_changed_fields: lifecycle, status, updated_at", preview
            )
            self.assertIn("token mismatch", wrong)
            self.assertEqual(library.skills_path.read_bytes(), skill_before)
            self.assertEqual(store.persistent_path.read_bytes(), memory_before)
            self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())

    def test_durable_skill_lifecycle_apply_writes_exact_envelope_and_receipt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            before_record = deepcopy(library.read_snapshot()["records"][0])
            memory_before = store.persistent_path.read_bytes()
            review = pilot.skill_lifecycle_metadata_applies.review(
                receipt, reviewer=reviewer
            )
            token = procedural_skill_lifecycle_metadata_apply_confirmation_token(
                review
            )
            applied = pilot.skill_lifecycle_metadata_applies.apply(
                receipt,
                token=token,
                reviewer=reviewer,
            )
            after_record = library.read_snapshot()["records"][0]
            memory_after = store.persistent_path.read_bytes()
            metadata_check = verify_procedural_skill_lifecycle_metadata(
                after_record["lifecycle"]
            )

        changed = sorted(
            key
            for key in set(before_record) | set(after_record)
            if before_record.get(key) != after_record.get(key)
        )
        self.assertEqual(str(record["id"]), applied.skill_id)
        self.assertEqual(changed, ["lifecycle", "status", "updated_at"])
        self.assertEqual(after_record["status"], "archived")
        self.assertEqual(after_record["provenance"], before_record["provenance"])
        self.assertEqual(after_record["lifecycle"]["id"], applied.metadata_id)
        self.assertEqual(after_record["lifecycle"]["metadata_hash"], applied.metadata_hash)
        self.assertTrue(metadata_check.verified)
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(
            set(applied.to_dict()),
            set(PROCEDURAL_SKILL_LIFECYCLE_METADATA_FUTURE_RECEIPT_FIELDS),
        )
        self.assertEqual(applied.exact_record_mutations, 1)
        self.assertEqual(applied.changed_fields, ["lifecycle", "status", "updated_at"])
        self.assertEqual(
            applied.receipt_hash,
            procedural_skill_lifecycle_metadata_apply_receipt_hash(
                applied.to_dict()
            ),
        )
        self.assertTrue(applied.post_state_verified)
        self.assertTrue(applied.durable_provenance_preserved)
        self.assertTrue(applied.persistent_memory_unchanged)
        self.assertFalse(applied.rollback_performed)

    def test_durable_skill_lifecycle_apply_is_run_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            review = pilot.skill_lifecycle_metadata_applies.review(
                receipt, reviewer=reviewer
            )
            token = procedural_skill_lifecycle_metadata_apply_confirmation_token(
                review
            )
            pilot.skill_lifecycle_metadata_applies.apply(
                receipt, token=token, reviewer=reviewer
            )
            before_second = library.skills_path.read_bytes()
            second = format_procedural_skill_lifecycle_metadata_apply_command(
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{receipt.id} {token} --durable"
                ),
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_metadata_applies,
                reviewer=reviewer,
            )

            self.assertIn("already durably applied", second)
            self.assertEqual(library.skills_path.read_bytes(), before_second)
            self.assertEqual(len(pilot.skill_lifecycle_metadata_applies.snapshot()), 1)

    def test_durable_skill_lifecycle_apply_refuses_keep_and_revise(self) -> None:
        for decision, outcomes in (("keep", ("success",)), ("revise", ("failure",))):
            with self.subTest(decision=decision), TemporaryDirectory() as temp_dir:
                store, library, pilot, _, receipt, reviewer = (
                    build_test_procedural_skill_lifecycle_readiness(
                        Path(temp_dir), outcomes=outcomes, decision=decision
                    )
                )
                skill_before = library.skills_path.read_bytes()
                memory_before = store.persistent_path.read_bytes()
                output = format_procedural_skill_lifecycle_metadata_apply_command(
                    (
                        "/experience learning skill-outcome-lifecycle-apply-preview "
                        f"{receipt.id} --durable"
                    ),
                    decision_session=pilot.skill_outcome_decisions,
                    apply_session=pilot.skill_lifecycle_metadata_applies,
                    reviewer=reviewer,
                )

                self.assertIn("Status: NOT CONFIRMABLE", output)
                self.assertNotIn("confirmation_token:", output)
                self.assertEqual(library.skills_path.read_bytes(), skill_before)
                self.assertEqual(store.persistent_path.read_bytes(), memory_before)

    def test_durable_skill_lifecycle_apply_refuses_drift_after_preview(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, pilot, record, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            review = pilot.skill_lifecycle_metadata_applies.review(
                receipt, reviewer=reviewer
            )
            token = procedural_skill_lifecycle_metadata_apply_confirmation_token(
                review
            )
            library.update_summary(str(record["id"]), "Changed after durable preview.")
            drifted_before = library.skills_path.read_bytes()
            output = format_procedural_skill_lifecycle_metadata_apply_command(
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{receipt.id} {token} --durable"
                ),
                decision_session=pilot.skill_outcome_decisions,
                apply_session=pilot.skill_lifecycle_metadata_applies,
                reviewer=reviewer,
            )

            self.assertIn("Current durable lifecycle readiness is not READY", output)
            self.assertEqual(library.skills_path.read_bytes(), drifted_before)
            self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())

    def test_durable_skill_lifecycle_archive_rolls_back_exact_bytes_on_verification_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            review = pilot.skill_lifecycle_metadata_applies.review(
                receipt, reviewer=reviewer
            )
            before = library.skills_path.read_bytes()
            with patch(
                "proto_mind.experience_learning_skill_lifecycle_metadata_apply._verify_durable_archive",
                side_effect=ProceduralSkillLifecycleMetadataApplyError(
                    "forced verification failure"
                ),
            ):
                output = format_procedural_skill_lifecycle_metadata_apply_command(
                    (
                        "/experience learning apply skill-outcome-lifecycle "
                        f"{receipt.id} "
                        f"{procedural_skill_lifecycle_metadata_apply_confirmation_token(review)} "
                        "--durable"
                    ),
                    decision_session=pilot.skill_outcome_decisions,
                    apply_session=pilot.skill_lifecycle_metadata_applies,
                    reviewer=reviewer,
                )
            after = library.skills_path.read_bytes()

        self.assertIn("exact original Skill Library bytes were restored", output)
        self.assertEqual(after, before)
        self.assertEqual(pilot.skill_lifecycle_metadata_applies.snapshot(), ())

    def test_durable_skill_lifecycle_receipt_views_and_doctor_are_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, _, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            review = pilot.skill_lifecycle_metadata_applies.review(
                receipt, reviewer=reviewer
            )
            applied = pilot.skill_lifecycle_metadata_applies.apply(
                receipt,
                token=procedural_skill_lifecycle_metadata_apply_confirmation_token(
                    review
                ),
                reviewer=reviewer,
            )
            skill_before = library.skills_path.read_bytes()
            memory_before = store.persistent_path.read_bytes()
            receipts_before = pilot.skill_lifecycle_metadata_applies.snapshot()
            common = {
                "decision_session": pilot.skill_outcome_decisions,
                "apply_session": pilot.skill_lifecycle_metadata_applies,
                "reviewer": reviewer,
            }
            listed = format_procedural_skill_lifecycle_metadata_apply_command(
                "/experience learning skill-outcome-lifecycle-applies --durable",
                **common,
            )
            inspected = format_procedural_skill_lifecycle_metadata_apply_command(
                (
                    "/experience learning skill-outcome-lifecycle-applies "
                    f"{applied.lifecycle_apply_id} --durable"
                ),
                **common,
            )
            doctor = format_procedural_skill_lifecycle_metadata_apply_command(
                "/experience learning skill-outcome-lifecycle-apply-doctor --durable",
                **common,
            )
            chained = format_procedural_skill_lifecycle_metadata_apply_command(
                (
                    "/experience learning skill-outcome-lifecycle-applies --durable; "
                    "/skills restore x"
                ),
                **common,
            )

            self.assertIn(applied.lifecycle_apply_id, listed)
            self.assertIn("Status: OK", inspected)
            self.assertIn(f"receipt_hash: {applied.receipt_hash}", inspected)
            self.assertIn("Status: OK", doctor)
            self.assertIn(PROCEDURAL_SKILL_LIFECYCLE_METADATA_APPLY_MODE, doctor)
            self.assertIn("Command chaining", chained)
            self.assertEqual(library.skills_path.read_bytes(), skill_before)
            self.assertEqual(store.persistent_path.read_bytes(), memory_before)
            self.assertEqual(
                pilot.skill_lifecycle_metadata_applies.snapshot(), receipts_before
            )

    def test_durable_skill_lifecycle_archive_routes_through_shared_experience_handler(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, pilot, _, receipt, _ = (
                build_test_procedural_skill_lifecycle_readiness(
                    root / "proto_mind",
                    outcomes=("failure",),
                    decision="archive",
                )
            )
            live_library_path = root / "proto_mind" / "data" / "skills.jsonl"
            live_library_path.parent.mkdir(parents=True, exist_ok=True)
            live_library_path.write_bytes(library.skills_path.read_bytes())
            coordinator = Coordinator(
                observer=Observer(),
                memory_keeper=MemoryKeeper(store),
                reasoner=MockReasoner(),
            )
            setattr(coordinator, EXPERIENCE_PILOT_ATTR, pilot)
            memory_before = store.persistent_path.read_bytes()
            preview = format_experience_pilot_command(
                (
                    "/experience learning skill-outcome-lifecycle-apply-preview "
                    f"{receipt.id} --durable"
                ),
                owner=coordinator,
                project_root=root,
            )
            token = next(
                line.split(": ", 1)[1]
                for line in preview.splitlines()
                if line.startswith("confirmation_token: ")
            )
            applied = format_experience_pilot_command(
                (
                    "/experience learning apply skill-outcome-lifecycle "
                    f"{receipt.id} {token} --durable"
                ),
                owner=coordinator,
                project_root=root,
            )
            live_record = SkillLibrary(live_library_path).read_snapshot()["records"][0]
            memory_after = store.persistent_path.read_bytes()

        self.assertIn("Status: CONFIRMABLE", preview)
        self.assertIn("Status: APPLIED", applied)
        self.assertIn("procedure_execution_performed: false", applied)
        self.assertEqual(live_record["status"], "archived")
        self.assertTrue(
            verify_procedural_skill_lifecycle_metadata(
                live_record["lifecycle"]
            ).verified
        )
        self.assertEqual(memory_after, memory_before)
        self.assertEqual(len(pilot.skill_lifecycle_metadata_applies.snapshot()), 1)

    def test_durable_skill_lifecycle_audit_handles_missing_stores_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skills_path = root / "skills.jsonl"
            memory_path = root / "persistent_memory.json"
            before = list(root.rglob("*"))
            audit = ProceduralSkillLifecycleAudit(
                skills_path=skills_path,
                persistent_memory_path=memory_path,
            )
            report = audit.inspect()
            status = format_skill_lifecycle_audit_command(
                "/skills lifecycle-status",
                skills_path=skills_path,
                persistent_memory_path=memory_path,
            )
            doctor = format_skill_lifecycle_audit_command(
                "/skills lifecycle-doctor",
                skills_path=skills_path,
                persistent_memory_path=memory_path,
            )
            after = list(root.rglob("*"))

        self.assertEqual(report.status, "OK")
        self.assertEqual(report.total_skills, 0)
        self.assertIn(PROCEDURAL_SKILL_LIFECYCLE_AUDIT_MODE, status)
        self.assertIn("Status: OK", doctor)
        self.assertIn("metadata_contract_status: OK", doctor)
        self.assertIn("metadata_writer_installed: true", doctor)
        self.assertIn("metadata_tamper_refused: true", doctor)
        self.assertEqual(after, before)

    def test_durable_skill_lifecycle_audit_recovers_active_verified_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(
                Path(temp_dir)
            )
            entry = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(applied.created_skill_id)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.state, "active_verified")
        self.assertTrue(entry.restart_safe)
        self.assertFalse(entry.outcome_archive_proven)
        self.assertEqual(entry.lifecycle_evidence, "none")

    def test_durable_skill_lifecycle_audit_recovers_verified_archive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, pilot, record, receipt, reviewer = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            review = pilot.skill_lifecycle_metadata_applies.review(
                receipt, reviewer=reviewer
            )
            pilot.skill_lifecycle_metadata_applies.apply(
                receipt,
                token=procedural_skill_lifecycle_metadata_apply_confirmation_token(
                    review
                ),
                reviewer=reviewer,
            )
            entry = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(str(record["id"]))

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.state, "archived_verified")
        self.assertTrue(entry.restart_safe)
        self.assertTrue(entry.outcome_archive_proven)
        self.assertEqual(
            entry.lifecycle_reason, PROCEDURAL_SKILL_LIFECYCLE_METADATA_REASON
        )

    def test_durable_skill_lifecycle_audit_does_not_invent_archive_cause(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, record, _, _ = (
                build_test_procedural_skill_lifecycle_readiness(
                    Path(temp_dir), outcomes=("failure",), decision="archive"
                )
            )
            library.set_status(str(record["id"]), "archived")
            # This simulates a legacy/manual archive without a lifecycle envelope.
            entry = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(str(record["id"]))

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.state, "archived_ambiguous")
        self.assertFalse(entry.restart_safe)
        self.assertFalse(entry.outcome_archive_proven)
        self.assertEqual(entry.lifecycle_reason, "not durably recorded")
        self.assertIn("cause is not", " ".join(entry.warnings))

    def test_durable_skill_lifecycle_history_separates_manual_skills(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = SkillLibrary(root / "skills.jsonl")
            library.add_skill("Operator-authored manual procedure")
            memory_path = root / "persistent_memory.json"
            report = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=memory_path,
            ).inspect()
            default = format_skill_lifecycle_audit_command(
                "/skills lifecycle-history",
                skills_path=library.skills_path,
                persistent_memory_path=memory_path,
            )
            include_all = format_skill_lifecycle_audit_command(
                "/skills lifecycle-history --all",
                skills_path=library.skills_path,
                persistent_memory_path=memory_path,
            )

        self.assertEqual(report.unprovenanced_count, 1)
        self.assertIn("showing: 0/1", default)
        self.assertIn("showing: 1/1", include_all)
        self.assertIn("unprovenanced", include_all)

    def test_durable_skill_lifecycle_audit_detects_payload_drift(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(
                Path(temp_dir)
            )
            library.update_summary(
                applied.created_skill_id,
                "Changed after the operator-confirmed projection.",
            )
            entry = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(applied.created_skill_id)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.state, "drifted")
        self.assertFalse(entry.restart_safe)
        self.assertTrue(entry.warnings)

    def test_durable_skill_lifecycle_audit_rejects_invented_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store, library, _, applied = build_test_applied_procedural_skill(
                Path(temp_dir)
            )
            records = library.read_snapshot()["records"]
            records[0]["lifecycle"] = {"reason": "outcome_archive"}
            library._write_records(records)
            entry = ProceduralSkillLifecycleAudit(
                skills_path=library.skills_path,
                persistent_memory_path=store.persistent_path,
            ).get(applied.created_skill_id)

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.state, "invalid")
        self.assertIn("unsupported durable lifecycle", " ".join(entry.issues))

    def test_durable_skill_lifecycle_commands_refuse_missing_and_chaining(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            common = {
                "skills_path": root / "skills.jsonl",
                "persistent_memory_path": root / "persistent_memory.json",
            }
            missing = format_skill_lifecycle_audit_command(
                "/skills lifecycle-inspect missing", **common
            )
            chained = format_skill_lifecycle_audit_command(
                "/skills lifecycle-status; /skills archive x", **common
            )

        self.assertIn("was not found", missing)
        self.assertIn("Command chaining", chained)
        self.assertIn("legacy archive remains ARCHIVED_AMBIGUOUS", chained)

    def test_durable_skill_lifecycle_shared_route_registry_and_policy_are_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, library, _, _ = build_test_applied_procedural_skill(root)
            live_path = root / "proto_mind" / "data" / "skills.jsonl"
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_bytes(library.skills_path.read_bytes())
            before_skill = live_path.read_bytes()
            before_memory = store.persistent_path.read_bytes()
            output = format_skill_command(
                "/skills lifecycle-doctor",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            usage = format_skill_command(
                "/skills lifecycle-unknown",
                project_root=root,
                persistent_memory_path=store.persistent_path,
            )
            after_skill = live_path.read_bytes()
            after_memory = store.persistent_path.read_bytes()

        registry = {entry.prefix: entry for entry in COMMAND_REGISTRY}
        self.assertIn("Status: OK", output)
        self.assertIn("Usage:", usage)
        self.assertEqual(after_skill, before_skill)
        self.assertEqual(after_memory, before_memory)
        for prefix in (
            "/skills lifecycle-status",
            "/skills lifecycle-history",
            "/skills lifecycle-inspect",
            "/skills lifecycle-doctor",
        ):
            self.assertTrue(registry[prefix].read_only)
            self.assertEqual(registry[prefix].mutates, "none")
            self.assertEqual(registry[prefix].risk, "low")
            self.assertEqual(classify_command(prefix).policy_class, "auto_allowed")
        self.assertEqual(len(COMMAND_REGISTRY), 387)
        self.assertEqual(len({entry.category for entry in COMMAND_REGISTRY}), 41)
        self.assertEqual(command_registry_doctor()["status"], "OK")
        self.assertEqual(action_policy_doctor()["status"], "OK")
