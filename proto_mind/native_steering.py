"""Updates bound to one foreground model turn, never to a selector turn."""
from __future__ import annotations

import hashlib
from copy import deepcopy
import threading
from uuid import UUID, uuid4

from proto_mind.native_codex import CodexRequestRejected
from proto_mind.native_images import image_context_message, image_input_items
from proto_mind.native_pdf import pdf_context_message
from proto_mind.native_workspace import file_context_message


class SteeringAttachments:
    """Re-read only explicitly selected snapshots in the task's original scope."""
    def __init__(self, workspace, images, pdfs, require_vision):
        self.workspace, self.images, self.pdfs, self.require_vision = workspace, images, pdfs, require_vision

    def input(self, attachments):
        if not isinstance(attachments, dict) or set(attachments) != {"files", "images", "pdfs"}:
            raise ValueError("Invalid task attachment selection.")
        if attachments["files"] and self.workspace is None:
            raise ValueError("Выберите файл из рабочей папки текущей задачи.")
        files = self.workspace.context_files(attachments["files"]) if self.workspace else []
        if not isinstance(attachments["files"], list): raise ValueError("Invalid file selection.")
        images = self.images.selected(attachments["images"])
        if images: self.require_vision()
        pdfs = self.pdfs.selected(attachments["pdfs"])
        context = file_context_message(files) + image_context_message(images) + pdf_context_message(pdfs)
        return context, image_input_items(images)


class LiveSteering:
    def __init__(self, request_id, conversation_id, emit, *, attachments=None):
        self.request_id, self.conversation_id, self.emit = request_id, conversation_id, emit
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.target = None
        self.receipts = {}
        self.attachments = attachments

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
        if "attachments" in params: expected.add("attachments")
        if (set(params) != expected or params.get("request_id") != self.request_id
                or params.get("cloud_consent") is not True
                or str(UUID(str(params.get("conversation_id")))) != self.conversation_id):
            raise ValueError("Уточнение не относится к текущей задаче.")
        message_id = str(UUID(str(params["message_id"])))
        text = params["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000 or "\x00" in text:
            raise ValueError("Уточнение должно содержать от 1 до 20 000 символов.")
        digest = hashlib.sha256(text.encode()).hexdigest()
        attachments = deepcopy(params.get("attachments"))
        if "attachments" in params and (not isinstance(attachments, dict) or set(attachments) != {"files", "images", "pdfs"}):
            raise ValueError("Invalid task attachment selection.")
        with self.lock:
            if message_id in self.receipts:
                previous = self.receipts[message_id]
                if previous["text_sha256"] != digest or previous.get("attachments") != attachments:
                    raise ValueError("Текст или вложения этой отправки изменились.")
                return deepcopy(previous)
            if len(self.receipts) >= 32: raise ValueError("Слишком много уточнений в одной задаче.")
            receipt = {"schema": "proto_mind.task_update.v1", "message_id": message_id,
                       "request_id": self.request_id, "conversation_id": self.conversation_id,
                       "text_sha256": digest, "status": "rejected"}
            if attachments is not None: receipt["attachments"] = attachments
            if not self.closed.is_set() and self.target and params["token"] == self.target[0]:
                _, turn, rpc = self.target
                context, image_input = "", []
                try:
                    if attachments is not None:
                        if self.attachments is None: raise ValueError("Attachments are unavailable for this task.")
                        context, image_input = self.attachments.input(attachments)
                except (RuntimeError, OSError, ValueError):
                    receipt["reason"] = "Вложение изменилось или недоступно. Проверьте его и прикрепите заново."
                    self.receipts[message_id] = dict(receipt)
                    return deepcopy(receipt)
                # Stop remains immediate while local files or vision support are checked.
                if self.closed.is_set():
                    self.receipts[message_id] = dict(receipt)
                    return deepcopy(receipt)
                receipt["status"] = "unknown"
                # Freeze this attempt before sending. A lost reply is never retried.
                self.receipts[message_id] = dict(receipt)
                try:
                    if turn[0] == "claude":
                        # The Claude worker adds the update to its running session.
                        receipt["status"] = rpc.steer(message_id, context + text, image_input)
                    else:
                        thread_id, turn_id = turn
                        result = rpc.request("turn/steer", {"threadId": thread_id, "expectedTurnId": turn_id,
                            "input": [{"type": "text", "text": context + text}] + image_input}, timeout=10)
                        if result.get("turnId") == turn_id: receipt["status"] = "accepted"
                except CodexRequestRejected:
                    receipt["status"] = "rejected"
                except (RuntimeError, OSError, ValueError):
                    pass
            self.receipts[message_id] = dict(receipt)
            return deepcopy(receipt)
