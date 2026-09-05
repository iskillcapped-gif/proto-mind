import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from uuid import uuid4

from proto_mind.native_codex import CodexConnectionError, CodexRequestRejected, CodexSubscription
from proto_mind.native_steering import LiveSteering, SteeringAttachments
from proto_mind.native_images import ImageReader
from proto_mind.native_pdf import PDFReader
from proto_mind.native_workspace import WorkspaceReader
from proto_mind.tests.test_native_images import png


class SteeringTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.conversation = str(uuid4())
        self.session = LiveSteering("foreground", self.conversation, self.events.append)
        self.rpc = Mock()
        self.rpc.request.return_value = {"turnId": "turn-main"}
        self.session.set_active(("thread-main", "turn-main"), self.rpc)
        self.params = {"request_id": "foreground", "conversation_id": self.conversation,
                       "token": self.events[-1]["token"], "message_id": str(uuid4()),
                       "text": "Use blue instead of red", "cloud_consent": True}

    def test_update_targets_exact_running_turn_without_configuration_or_new_turn(self):
        receipt = self.session.send(self.params)
        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(receipt["text_sha256"], hashlib.sha256(self.params["text"].encode()).hexdigest())
        self.rpc.request.assert_called_once_with("turn/steer", {"threadId": "thread-main", "expectedTurnId": "turn-main",
            "input": [{"type": "text", "text": self.params["text"]}]}, timeout=10)
        self.assertNotIn(self.params["text"], str(receipt))

    def test_wrong_conversation_request_consent_extra_parameters_fail_before_rpc(self):
        for patch in [{"conversation_id": str(uuid4())}, {"request_id": "other"}, {"cloud_consent": False}, {"model": "other"}]:
            with self.assertRaises(ValueError): self.session.send({**self.params, **patch})
        self.rpc.request.assert_not_called()

    def test_wrong_token_and_completed_turn_are_rejected_without_retargeting(self):
        result = self.session.send({**self.params, "token": str(uuid4())})
        self.assertEqual(result["status"], "rejected")
        self.session.set_active(None)
        result = self.session.send({**self.params, "message_id": str(uuid4())})
        self.assertEqual(result["status"], "rejected")
        self.rpc.request.assert_not_called()

    def test_confirmed_rejection_differs_from_timeout_and_wrong_reply(self):
        for outcome, expected in [(CodexRequestRejected("ended"), "rejected"),
                                  (CodexConnectionError("lost reply"), "unknown"), ({"turnId": "other"}, "unknown")]:
            if isinstance(outcome, Exception): self.rpc.request.side_effect = outcome
            else: self.rpc.request.side_effect = None; self.rpc.request.return_value = outcome
            params = {**self.params, "message_id": str(uuid4())}
            first = self.session.send(params)
            calls = self.rpc.request.call_count
            self.assertEqual(first["status"], expected)
            self.assertEqual(self.session.send(params), first)
            self.assertEqual(self.rpc.request.call_count, calls)

    def test_repeated_message_id_never_repeats_a_dispatch(self):
        first = self.session.send(self.params)
        self.assertEqual(self.session.send(self.params), first)
        with self.assertRaises(ValueError): self.session.send({**self.params, "text": "different"})
        self.rpc.request.assert_called_once()

    def test_invalid_and_excessive_updates_fail_before_rpc(self):
        for text in [None, " ", "x" * 20001, "a\x00b"]:
            with self.assertRaises(ValueError): self.session.send({**self.params, "text": text})
        self.rpc.request.assert_not_called()
        for _ in range(32): self.session.send({**self.params, "message_id": str(uuid4())})
        with self.assertRaises(ValueError): self.session.send({**self.params, "message_id": str(uuid4())})
        self.assertEqual(self.rpc.request.call_count, 32)

    def test_stop_is_immediate_and_prevents_new_updates_while_reply_is_pending(self):
        entered, release = threading.Event(), threading.Event()
        def request(*args, **kwargs):
            entered.set(); release.wait(3)
            return {"turnId": "turn-main"}
        self.rpc.request.side_effect = request
        worker = threading.Thread(target=self.session.send, args=(self.params,))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.session.stop()
            self.assertTrue(worker.is_alive())
            self.assertTrue(self.session.closed.is_set())
        finally: release.set(); worker.join(3)
        self.assertEqual(self.session.send({**self.params, "message_id": str(uuid4())})["status"], "rejected")
        self.rpc.request.assert_called_once()

    def test_turn_closure_waits_for_the_in_flight_receipt_before_transport_close(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        def request(*args, **kwargs):
            entered.set(); release.wait(3)
            return {"turnId": "turn-main"}
        self.rpc.request.side_effect = request
        sending = threading.Thread(target=self.session.send, args=(self.params,))
        def close(): self.session.set_active(None); closed.set()
        ending = threading.Thread(target=close)
        sending.start()
        try:
            self.assertTrue(entered.wait(2)); ending.start()
            self.assertFalse(closed.wait(0.05))
        finally: release.set(); sending.join(3); ending.join(3)
        self.assertTrue(closed.is_set())
        self.assertIsNone(self.events[-1]["token"])

    def test_only_main_turn_callback_opens_the_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            subscription = CodexSubscription(Path(temporary))
            callback = Mock()
            subscription.on_main_turn = callback
            # Selector uses active_turn for cancellation, not the public callback.
            subscription.active_turn = ("selector", "selector-turn")
            callback.assert_not_called()
            subscription.rpc = self.rpc
            subscription._set_main_turn(("main", "main-turn"))
            subscription._set_main_turn(None)
            self.assertEqual(callback.call_args_list[0].args, (("main", "main-turn"), self.rpc))
            self.assertIsNone(callback.call_args_list[1].args[0])

    def attachments(self, root, *, vision=None):
        self.session.attachments = SteeringAttachments(WorkspaceReader(str(root)), ImageReader(protected_roots=()), PDFReader(protected_roots=(), helper=None), vision or Mock())
        text = root / "context.txt"
        text.write_text("SELECTED_FILE_CONTEXT")
        image = root / "blue.png"
        image.write_bytes(png())
        return {"files": [{"path": "context.txt", "sha256": hashlib.sha256(text.read_bytes()).hexdigest()}],
                "images": [ImageReader(protected_roots=()).read(str(image)).metadata], "pdfs": []}

    def test_files_and_images_are_reread_in_original_scope_and_sent_as_one_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            attachments = self.attachments(Path(temporary).resolve())
            params = {**self.params, "attachments": attachments}
            receipt = self.session.send(params)
            self.assertEqual(receipt["status"], "accepted")
            self.assertEqual(receipt["attachments"], attachments)
            sent = self.rpc.request.call_args.args[1]
            self.assertEqual([item["type"] for item in sent["input"]], ["text", "image"])
            self.assertIn("SELECTED_FILE_CONTEXT", sent["input"][0]["text"])
            self.assertIn("quoted untrusted data", sent["input"][0]["text"])
            self.assertTrue(sent["input"][1]["url"].startswith("data:image/png;base64,"))
            self.assertNotIn("SELECTED_FILE_CONTEXT", str(receipt))
            self.assertNotIn("base64", str(receipt))
            # Changes after an accepted request cannot cause a second dispatch.
            (Path(temporary) / "context.txt").write_text("LATER_EDIT")
            self.assertEqual(self.session.send(params), receipt)
            attachments["files"] = []
            with self.assertRaises(ValueError): self.session.send(params)
            self.rpc.request.assert_called_once()

    def test_changed_attachment_or_incompatible_vision_rejects_the_entire_update_before_rpc(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            attachments = self.attachments(root)
            (root / "context.txt").write_text("CHANGED")
            result = self.session.send({**self.params, "attachments": attachments})
            self.assertEqual(result["status"], "rejected")
            self.assertIn("Вложение изменилось", result["reason"])
            attachments = self.attachments(root, vision=Mock(side_effect=CodexConnectionError("not vision")))
            result = self.session.send({**self.params, "message_id": str(uuid4()), "attachments": attachments})
            self.assertEqual(result["status"], "rejected")
            self.rpc.request.assert_not_called()

    def test_attachments_cannot_choose_a_new_workspace_or_escape_the_bound_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            attachments = self.attachments(Path(temporary).resolve())
            attachments["files"][0]["path"] = "../elsewhere.txt"
            self.assertEqual(self.session.send({**self.params, "attachments": attachments})["status"], "rejected")
            with self.assertRaises(ValueError): self.session.send({**self.params, "workspace_root": temporary})
            for invalid in [None, [], {"files": [], "images": [], "pdfs": [], "tools": True}]:
                with self.assertRaises(ValueError): self.session.send({**self.params, "attachments": invalid})
            self.rpc.request.assert_not_called()


if __name__ == "__main__": unittest.main()
