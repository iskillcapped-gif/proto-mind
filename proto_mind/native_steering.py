"""Text updates bound to one foreground model turn, never to a selector turn."""
from __future__ import annotations

import hashlib
import threading
from uuid import UUID, uuid4

from proto_mind.native_codex import CodexRequestRejected


class LiveSteering:
    def __init__(self, request_id, conversation_id, emit):
        self.request_id, self.conversation_id, self.emit = request_id, conversation_id, emit
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.target = None
        self.receipts = {}

    def set_active(self, turn, rpc=None):
        # Wait for an already submitted update before the owner closes its RPC.
        # Stop uses an Event and does not wait for this bounded turn RPC lock.
        with self.lock:
            previous = self.target
            self.target = (str(uuid4()), turn, rpc) if turn and not self.closed.is_set() else None
            if previous is None and self.target is None: return
            self.emit({"event": "steering_ready", "request_id": self.request_id,
                       "conversation_id": self.conversation_id,
                       "token": self.target[0] if self.target else None})

    def stop(self):
        self.closed.set()

    def send(self, params):
        expected = {"request_id", "conversation_id", "token", "message_id", "text", "cloud_consent"}
        if (set(params) != expected or params.get("request_id") != self.request_id
                or params.get("cloud_consent") is not True
                or str(UUID(str(params.get("conversation_id")))) != self.conversation_id):
            raise ValueError("Уточнение не относится к текущей задаче.")
        message_id = str(UUID(str(params["message_id"])))
        text = params["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000 or "\x00" in text:
            raise ValueError("Уточнение должно содержать от 1 до 20 000 символов.")
        digest = hashlib.sha256(text.encode()).hexdigest()
        with self.lock:
            if message_id in self.receipts:
                previous = self.receipts[message_id]
                if previous["text_sha256"] != digest: raise ValueError("Текст этой отправки изменился.")
                return dict(previous)
            if len(self.receipts) >= 32: raise ValueError("Слишком много уточнений в одной задаче.")
            receipt = {"schema": "proto_mind.task_update.v1", "message_id": message_id,
                       "request_id": self.request_id, "conversation_id": self.conversation_id,
                       "text_sha256": digest, "status": "rejected"}
            if not self.closed.is_set() and self.target and params["token"] == self.target[0]:
                _, (thread_id, turn_id), rpc = self.target
                receipt["status"] = "unknown"
                # Freeze this attempt before sending. A lost reply is never retried.
                self.receipts[message_id] = dict(receipt)
                try:
                    result = rpc.request("turn/steer", {"threadId": thread_id, "expectedTurnId": turn_id,
                        "input": [{"type": "text", "text": text}]}, timeout=10)
                    if result.get("turnId") == turn_id: receipt["status"] = "accepted"
                except CodexRequestRejected:
                    receipt["status"] = "rejected"
                except (RuntimeError, OSError, ValueError):
                    pass
            self.receipts[message_id] = dict(receipt)
            return receipt
