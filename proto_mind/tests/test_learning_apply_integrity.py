from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID

from proto_mind.experience_learning_apply import (
    LearningMemoryApplyError,
    learning_memory_apply_confirmation_token,
)
from proto_mind.tests.test_flow import build_test_learning_apply


class LearningApplyIntegrityTests(unittest.TestCase):
    def prepare(self, root: Path):
        _, store, pilot, bridge, candidate, skills, proposal = build_test_learning_apply(root)
        rows = json.loads(store.persistent_path.read_bytes())
        rows[0]["legacy_extension"] = {"keep": ["original", {"nested": True}]}
        rows[0].pop("updated_at")
        store.persistent_path.write_text(json.dumps(rows, indent="\t") + "\n", encoding="utf-8")
        dependencies = {
            "candidates": {candidate.id: candidate}, "decisions": pilot.learning_decisions,
            "memory_store": store, "skill_library": skills,
        }
        review = pilot.learning_applies.review(proposal, **dependencies)
        self.assertTrue(review.confirmable, review.issues)
        return store, pilot, proposal, dependencies, learning_memory_apply_confirmation_token(review)

    def test_apply_preserves_unknown_fields_and_absent_legacy_fields(self):
        with TemporaryDirectory() as directory:
            store, pilot, proposal, dependencies, token = self.prepare(Path(directory))
            original = json.loads(store.persistent_path.read_bytes())
            working = store.working_path.read_bytes()
            receipt = pilot.learning_applies.apply(proposal, token=token, **dependencies)
            current = json.loads(store.persistent_path.read_bytes())
            self.assertEqual(current[:-1], original)
            self.assertNotIn("updated_at", current[0])
            self.assertEqual(current[-1]["id"], receipt.created_record_id)
            self.assertEqual(store.working_path.read_bytes(), working)
            self.assertEqual(pilot.learning_applies.doctor(store).status, "OK")

    def test_failed_verification_restores_noncanonical_bytes_exactly(self):
        with TemporaryDirectory() as directory:
            store, pilot, proposal, dependencies, token = self.prepare(Path(directory))
            before = store.persistent_path.read_bytes()
            with patch("proto_mind.experience_learning_apply._verify_created_record", side_effect=ValueError("fixture")):
                with self.assertRaisesRegex(LearningMemoryApplyError, "byte-for-byte"):
                    pilot.learning_applies.apply(proposal, token=token, **dependencies)
            self.assertEqual(store.persistent_path.read_bytes(), before)
            self.assertEqual(pilot.learning_applies.snapshot(), ())
            self.assertEqual(list(store.persistent_path.parent.glob(".*.tmp")), [])

    def test_failed_verification_never_rolls_back_over_a_concurrent_change(self):
        with TemporaryDirectory() as directory:
            store, pilot, proposal, dependencies, token = self.prepare(Path(directory))
            concurrent = b'[{"id":"external-edit","content":"preserve this later change"}]\n'

            def external_change(*args, **kwargs):
                store.persistent_path.write_bytes(concurrent)
                raise ValueError("fixture concurrent change")

            with patch("proto_mind.experience_learning_apply._verify_created_record", side_effect=external_change):
                with self.assertRaisesRegex(LearningMemoryApplyError, "safe rollback could not be verified"):
                    pilot.learning_applies.apply(proposal, token=token, **dependencies)
            self.assertEqual(store.persistent_path.read_bytes(), concurrent)
            self.assertEqual(pilot.learning_applies.snapshot(), ())

    def test_symlink_store_is_not_confirmable(self):
        with TemporaryDirectory() as directory:
            store, pilot, proposal, dependencies, _ = self.prepare(Path(directory))
            target = store.persistent_path.with_name("original.json")
            store.persistent_path.rename(target)
            store.persistent_path.symlink_to(target)
            before = target.read_bytes()
            review = pilot.learning_applies.review(proposal, **dependencies)
            self.assertFalse(review.confirmable)
            self.assertEqual(target.read_bytes(), before)

    def test_failed_atomic_replace_leaves_original_and_no_temporary_file(self):
        with TemporaryDirectory() as directory:
            store, pilot, proposal, dependencies, token = self.prepare(Path(directory))
            before = store.persistent_path.read_bytes()
            with patch.object(Path, "replace", side_effect=OSError("replacement fixture")):
                with self.assertRaisesRegex(LearningMemoryApplyError, "byte-for-byte"):
                    pilot.learning_applies.apply(proposal, token=token, **dependencies)
            self.assertEqual(store.persistent_path.read_bytes(), before)
            self.assertEqual(list(store.persistent_path.parent.glob(".*.tmp")), [])
            self.assertEqual(pilot.learning_applies.snapshot(), ())

    def test_temporary_name_collision_preserves_the_existing_file(self):
        with TemporaryDirectory() as directory:
            store, pilot, proposal, dependencies, token = self.prepare(Path(directory))
            before = store.persistent_path.read_bytes()
            identity = UUID("00000000-0000-0000-0000-000000000001")
            unrelated = store.persistent_path.with_name(f".{store.persistent_path.name}.{identity.hex}.tmp")
            unrelated.write_bytes(b"An existing file must not be removed.")
            with patch("proto_mind.experience_learning_apply.uuid4", return_value=identity):
                with self.assertRaises(LearningMemoryApplyError):
                    pilot.learning_applies.apply(proposal, token=token, **dependencies)
            self.assertEqual(store.persistent_path.read_bytes(), before)
            self.assertEqual(unrelated.read_bytes(), b"An existing file must not be removed.")
            self.assertEqual(pilot.learning_applies.snapshot(), ())


if __name__ == "__main__":
    unittest.main()
