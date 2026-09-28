import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from proto_mind import native_claude_transcripts
from proto_mind.native_claude_protocol import WorkspaceReplyError, error_code, failure_code
from proto_mind.native_claude_transcripts import pin_resume_point, transcript_files


class ResumePointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.profile = Path(temporary.name)
        self.session, self.prompt, self.record, self.answer = (str(uuid4()) for _ in range(4))

    def write(self, *entries, folder="-fixture", end="\n"):
        path = self.profile / "projects" / folder / (self.session + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(entry) for entry in entries) + end)
        return path

    def turn(self, *, late):
        prompt = {"type": "user", "uuid": self.prompt, "parentUuid": None, "message": {"content": "hello"}}
        parent = {"type": "attachment", "uuid": self.record, "parentUuid": self.prompt,
                  "attachment": {"type": "deferred_tools_record"}}
        answer = {"type": "assistant", "uuid": self.answer, "parentUuid": self.record}
        leaf = {"type": "last-prompt", "leafUuid": self.record if late else self.answer, "sessionId": self.session}
        ending = [answer, parent] if late else [parent, answer]
        return [prompt, *ending, leaf, {"type": "cost-state", "sessionId": self.session}]

    def pins(self, path):
        return [entry for entry in map(json.loads, path.read_text().splitlines()) if entry.get("explicit")]

    def test_an_answer_written_before_its_parent_is_pinned_once(self):
        path = self.write(*self.turn(late=True))
        self.assertTrue(pin_resume_point(self.profile, self.session, self.answer))
        self.assertEqual(self.pins(path), [{"type": "last-prompt", "leafUuid": self.answer, "explicit": True,
                                            "sessionId": self.session}])
        self.assertTrue(pin_resume_point(self.profile, self.session, self.answer))
        self.assertEqual(len(self.pins(path)), 1)

    def test_a_transcript_that_ends_at_the_answer_is_left_alone(self):
        path = self.write(*self.turn(late=False))
        before = path.read_bytes()
        self.assertTrue(pin_resume_point(self.profile, self.session, self.answer))
        self.assertEqual(path.read_bytes(), before)

    def test_entries_after_the_answer_still_pin_it(self):
        # A later entry would otherwise become the last written one.
        later = {"type": "attachment", "uuid": str(uuid4()), "parentUuid": self.answer}
        path = self.write(*self.turn(late=False), later)
        self.assertTrue(pin_resume_point(self.profile, self.session, self.answer))
        self.assertEqual(len(self.pins(path)), 1)

    def test_unknown_or_unsafe_transcripts_resume_plainly_without_writing(self):
        cases = {
            "missing answer": lambda: self.write(*self.turn(late=True)[:1]),
            "torn last line": lambda: self.write(*self.turn(late=True), end=""),
            "answer beyond the recent window": lambda: self.write(*self.turn(late=True), {"type": "user", "uuid": str(uuid4()), "parentUuid": None, "padding": "x" * 4096}),
            "not an answer": lambda: self.write(self.turn(late=True)[0], {"type": "user", "uuid": self.answer, "parentUuid": self.prompt}),
            "subagent answer": lambda: self.write(self.turn(late=True)[0], {"type": "assistant", "uuid": self.answer, "parentUuid": self.prompt, "isSidechain": True}),
        }
        for name, make in cases.items():
            with self.subTest(name), patch.object(native_claude_transcripts, "TAIL_BYTES", 2048):
                path = make()
                before = path.read_bytes()
                self.assertFalse(pin_resume_point(self.profile, self.session, self.answer))
                self.assertEqual(path.read_bytes(), before)
                path.unlink()
        self.assertFalse(pin_resume_point(self.profile, self.session, self.answer))

    def test_links_and_duplicate_transcripts_are_never_written(self):
        path = self.write(*self.turn(late=True))
        os.link(path, self.profile / "other.jsonl")
        self.assertFalse(pin_resume_point(self.profile, self.session, self.answer))
        (self.profile / "other.jsonl").unlink()
        target = self.profile / "target.jsonl"
        path.rename(target); path.symlink_to(target)
        self.assertEqual(transcript_files(self.profile, self.session), [])
        self.assertFalse(pin_resume_point(self.profile, self.session, self.answer))
        path.unlink(); target.rename(path)
        second = self.write(*self.turn(late=True), folder="-moved")
        self.assertEqual(len(transcript_files(self.profile, self.session)), 2)
        self.assertFalse(pin_resume_point(self.profile, self.session, self.answer))
        self.assertEqual(self.pins(path) + self.pins(second), [])


class ResumeRefusalTests(unittest.TestCase):
    refusal = dict(subtype="error_during_execution", errors=["No message found with message.uuid of: 00000000-0000-4000-8000-000000000000"])

    def test_claude_code_refusing_the_resume_point_has_its_own_category(self):
        # The pinned SDK raises ResultError with the CLI's result while connecting.
        error = type("ResultError", (Exception,), {})()
        error.subtype, error.errors, error.data = self.refusal["subtype"], self.refusal["errors"], {"num_turns": 0}
        self.assertEqual(failure_code(error), "resume_point")
        self.assertEqual(error_code(SimpleNamespace(**self.refusal, num_turns=0)), "resume_point")
        error.data = {"num_turns": 1}  # After a model request it is not a refused resume.
        self.assertEqual(failure_code(error), "unknown")
        self.assertEqual(error_code(SimpleNamespace(subtype="error_during_execution", errors=["other"], num_turns=0)), "unknown")
        self.assertEqual(failure_code(WorkspaceReplyError("closed")), "workspace_connection")
        self.assertEqual(failure_code(RuntimeError("No message found with message.uuid of: x")), "unknown")


if __name__ == "__main__":
    unittest.main()
