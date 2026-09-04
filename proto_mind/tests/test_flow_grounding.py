"""Core flow checks: grounding."""
from __future__ import annotations

import unittest
from proto_mind.tests.flow_fixtures import (
    MemoryRecord,
    Observer,
    Path,
    TemporaryDirectory,
    audit_for_test,
    build_test_system,
)


class GroundingFlowTests(unittest.TestCase):
    def test_grounding_audit_not_needed_for_generic_new_question(self) -> None:
        state = Observer().analyze("Hello there.")

        audit = audit_for_test(
            "Hello. How can I help with Proto-Mind today?",
            user_input="Hello there.",
            observer_state=state,
        )

        self.assertFalse(audit.grounding_needed)
        self.assertEqual(audit.grounding_status, "not_needed")
        self.assertEqual(audit.memory_support, "none_needed")

    def test_grounding_audit_marks_grounded_answer_using_selected_memory(self) -> None:
        selected = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )

        audit = audit_for_test(
            "The active decision is SQLite for the storage direction.",
            retrieved_memory=[selected],
            persistent_memory=[selected],
        )

        self.assertEqual(audit.grounding_status, "grounded")
        self.assertEqual(audit.memory_support, "selected_memory_used")
        self.assertEqual(audit.active_decision_status, "aligned")
        self.assertFalse(audit.warnings)

    def test_grounding_audit_flags_active_sqlite_contradicted_by_current_json_decision(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )

        audit = audit_for_test(
            "The current architectural decision is JSON-backed memory for storage.",
            retrieved_memory=[active_sqlite],
            persistent_memory=[active_sqlite],
        )

        self.assertEqual(audit.grounding_status, "contradicted")
        self.assertEqual(audit.active_decision_status, "contradicted")
        self.assertTrue(any("active SQLite decision" in warning for warning in audit.warnings))

    def test_grounding_audit_allows_json_implementation_with_sqlite_direction_when_supported(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )
        json_implementation = MemoryRecord(
            "Current implemented storage is JSON-backed memory files.",
            "project",
            0.8,
            "test",
            tags=["json", "storage"],
        )

        audit = audit_for_test(
            "The current implementation is JSON-backed, but the active architectural direction is SQLite.",
            retrieved_memory=[active_sqlite, json_implementation],
            persistent_memory=[active_sqlite, json_implementation],
        )

        self.assertNotEqual(audit.grounding_status, "contradicted")
        self.assertEqual(audit.active_decision_status, "aligned")
        self.assertFalse(audit.warnings)

    def test_grounding_audit_does_not_treat_instead_of_json_as_current_json(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )

        audit = audit_for_test(
            "Current stored memory: Active decisions: Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            retrieved_memory=[active_sqlite],
            persistent_memory=[active_sqlite],
        )

        self.assertEqual(audit.active_decision_status, "aligned")
        self.assertNotEqual(audit.grounding_status, "contradicted")
        self.assertFalse(audit.warnings)

    def test_grounding_audit_does_not_treat_rejected_json_as_superseded_current(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )
        old_json = MemoryRecord(
            "We decided Proto-Mind should use JSON-backed memory.",
            "decision",
            0.8,
            "promoted",
            tags=["json", "storage"],
            active=False,
            superseded_by=active_sqlite.id,
        )

        audit = audit_for_test(
            "Current stored memory: Active decisions: Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            retrieved_memory=[active_sqlite, old_json],
            persistent_memory=[old_json, active_sqlite],
        )

        self.assertNotEqual(audit.superseded_memory_status, "treated_as_current")
        self.assertNotEqual(audit.grounding_status, "contradicted")
        self.assertFalse(audit.warnings)

    def test_grounding_audit_warns_when_superseded_json_treated_as_current(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )
        old_json = MemoryRecord(
            "We decided Proto-Mind should use JSON-backed memory.",
            "decision",
            0.8,
            "promoted",
            tags=["json", "storage"],
            active=False,
            superseded_by=active_sqlite.id,
        )

        audit = audit_for_test(
            "The current decision is JSON-backed memory for storage.",
            retrieved_memory=[old_json],
            persistent_memory=[old_json, active_sqlite],
        )

        self.assertEqual(audit.grounding_status, "contradicted")
        self.assertEqual(audit.superseded_memory_status, "treated_as_current")
        self.assertTrue(any("superseded memory" in warning for warning in audit.warnings))

    def test_grounding_audit_allows_superseded_json_when_described_historically(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )
        old_json = MemoryRecord(
            "We decided Proto-Mind should use JSON-backed memory.",
            "decision",
            0.8,
            "promoted",
            tags=["json", "storage"],
            active=False,
            superseded_by=active_sqlite.id,
        )

        audit = audit_for_test(
            "Previously, the old decision was JSON-backed memory; the current direction is SQLite.",
            user_input="What did we use before SQLite?",
            retrieved_memory=[old_json, active_sqlite],
            persistent_memory=[old_json, active_sqlite],
        )

        self.assertNotEqual(audit.grounding_status, "contradicted")
        self.assertEqual(audit.superseded_memory_status, "historical_only")
        self.assertFalse(audit.warnings)

    def test_grounding_audit_allows_current_stored_memory_previous_decisions_heading(self) -> None:
        active_sqlite = MemoryRecord(
            "Actually, we are changing direction: Proto-Mind should use SQLite instead of JSON.",
            "decision",
            0.95,
            "promoted",
            tags=["sqlite", "storage"],
        )
        old_json = MemoryRecord(
            "We decided Proto-Mind should use JSON-backed memory.",
            "decision",
            0.8,
            "promoted",
            tags=["json", "storage"],
            active=False,
            superseded_by=active_sqlite.id,
        )

        audit = audit_for_test(
            "Current stored memory: Previous decisions: We decided Proto-Mind should use JSON-backed memory.",
            user_input="Did we previously decide to use JSON-backed memory?",
            retrieved_memory=[old_json, active_sqlite],
            persistent_memory=[old_json, active_sqlite],
        )

        self.assertNotEqual(audit.grounding_status, "contradicted")
        self.assertEqual(audit.superseded_memory_status, "historical_only")
        self.assertFalse(audit.warnings)

    def test_grounding_audit_warns_on_unsupported_memory_claim_without_support(self) -> None:
        state = Observer().analyze("What did we decide?")

        audit = audit_for_test(
            "I remember we decided JSON-backed memory is current.",
            user_input="What did we decide?",
            observer_state=state,
        )

        self.assertEqual(audit.grounding_status, "ungrounded")
        self.assertTrue(audit.unsupported_claims)
        self.assertTrue(any("without selected or stored support" in warning for warning in audit.warnings))

    def test_grounding_audit_accepts_russian_rejected_alternative(self) -> None:
        active_sqlite = MemoryRecord(
            "Теперь используем SQLite вместо JSON для хранения памяти.",
            "decision",
            0.95,
            "operator",
            tags=["sqlite", "json", "storage"],
        )

        audit = audit_for_test(
            "Текущее решение — SQLite вместо JSON.",
            user_input="Какое решение сейчас активно?",
            retrieved_memory=[active_sqlite],
            persistent_memory=[active_sqlite],
        )

        self.assertEqual(audit.grounding_status, "grounded")
        self.assertEqual(audit.active_decision_status, "aligned")
        self.assertFalse(audit.warnings)

    def test_grounding_audit_treats_russian_superseded_decision_as_history(self) -> None:
        active_sqlite = MemoryRecord(
            "Теперь используем SQLite вместо JSON для хранения памяти.",
            "decision",
            0.95,
            "operator",
            tags=["sqlite", "json", "storage"],
        )
        old_json = MemoryRecord(
            "Мы решили использовать JSON для хранения памяти.",
            "decision",
            0.8,
            "operator",
            tags=["json", "storage"],
            active=False,
            superseded_by=active_sqlite.id,
        )

        audit = audit_for_test(
            "Раньше решением был JSON, а сейчас используем SQLite.",
            user_input="Что мы использовали раньше?",
            retrieved_memory=[old_json, active_sqlite],
            persistent_memory=[old_json, active_sqlite],
        )

        self.assertEqual(audit.grounding_status, "grounded")
        self.assertEqual(audit.superseded_memory_status, "historical_only")
        self.assertFalse(audit.warnings)

    def test_grounding_audit_detects_russian_unsupported_memory_claim(self) -> None:
        state = Observer().analyze("Что мы решили по хранению памяти?")

        audit = audit_for_test(
            "Я помню, что мы решили использовать JSON для хранения памяти.",
            user_input="Что мы решили по хранению памяти?",
            observer_state=state,
        )

        self.assertEqual(audit.grounding_status, "ungrounded")
        self.assertTrue(audit.unsupported_claims)
        self.assertIn("я помню", audit.unsupported_claims[0])

    def test_grounding_evidence_includes_memory_provenance(self) -> None:
        selected = MemoryRecord(
            "Теперь используем SQLite вместо JSON для хранения памяти.",
            "decision",
            0.95,
            "operator",
            tags=["sqlite", "json", "storage"],
            id="decision-source-1",
        )

        audit = audit_for_test(
            "Текущее архитектурное решение — SQLite для хранения памяти.",
            retrieved_memory=[selected],
            persistent_memory=[selected],
        )

        self.assertTrue(any("id=decision-source-1" in item for item in audit.evidence))
        self.assertTrue(any("source=operator" in item for item in audit.evidence))

    def test_grounding_audit_is_included_in_interaction_result_serialization(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            coordinator, _, _ = build_test_system(tmp_path)

            result = coordinator.handle("Hello there.")
            payload = result.to_dict()

            self.assertIsNotNone(result.grounding_audit)
            self.assertIn("grounding_audit", payload)
            self.assertEqual(payload["grounding_audit"]["grounding_status"], "not_needed")
