"""Explicit API chat transport. Secrets live only in the current stdio request and HTTP headers."""
from __future__ import annotations

import http.client
import json
import socket
import ssl
import threading
from urllib.parse import urlsplit

from proto_mind.reasoners.base import BaseReasoner
from proto_mind.native_instructions import prepare_local_instructions, build_instruction_receipt
from proto_mind.native_workspace import file_context_message
from proto_mind.native_review import criteria_context_message
from proto_mind.native_pdf import pdf_context_message
from proto_mind.native_knowledge import knowledge_context_message


def validate_connection(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"endpoint", "format", "key"}:
        raise ValueError("Выберите API-подключение в настройках.")
    endpoint, key = value["endpoint"], value["key"]
    if (not isinstance(endpoint, str) or len(endpoint) > 2048 or any(ord(c) < 33 for c in endpoint)
            or not isinstance(key, str) or len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key)
            or value["format"] not in {"responses", "chat_completions"}):
        raise ValueError("Некорректные параметры API-подключения.")
    try:
        url = urlsplit(endpoint)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        valid = (url.hostname and not url.username and not url.password and not url.query and not url.fragment
                 and (url.scheme == "https" or (url.scheme == "http" and local)) and (key or local))
        _ = url.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("API требует HTTPS и ключ. HTTP без ключа разрешён только на этом Mac.")
    return dict(value)


class APITransport:
    def __init__(self, connection: dict):
        self.connection = validate_connection(connection)
        self.cancelled = threading.Event()
        self.http = None
        self.stream_socket = None
        self.workspace_tools = None
        self.on_activity = lambda _: None
        self.on_progress = lambda _: None

    def cancel(self):
        self.cancelled.set()
        current = self.stream_socket or (self.http.sock if self.http else None)
        if current:
            try:
                current.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def answer(self, model: str, instructions: str, history: list, prompt: str, on_delta) -> str:
        if self.workspace_tools is not None:
            from proto_mind.native_api_tools import run_api_tools
            return run_api_tools(self, model, instructions, history, prompt, on_delta)
        url = urlsplit(self.connection["endpoint"])
        responses = self.connection["format"] == "responses"
        messages = [*history, {"role": "user", "content": prompt}]
        payload = ({"model": model, "instructions": instructions, "input": messages, "stream": True, "store": False}
                   if responses else {"model": model, "messages": [{"role": "system", "content": instructions}, *messages], "stream": True})
        path = url.path.rstrip("/") + ("/responses" if responses else "/chat/completions")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.connection["key"]:
            headers["Authorization"] = "Bearer " + self.connection["key"]
        # A network-idle deadline is separate from a turn lifetime. Never retry a paid request.
        self.http = (http.client.HTTPSConnection(url.hostname, url.port, timeout=300, context=ssl.create_default_context())
                     if url.scheme == "https" else http.client.HTTPConnection(url.hostname, url.port, timeout=300))
        text, count, finished, reason = [], 0, False, None
        try:
            if self.cancelled.is_set():
                raise RuntimeError("API-запрос остановлен.")
            self.http.request("POST", path, body=json.dumps(payload, ensure_ascii=False).encode(), headers=headers)
            self.stream_socket = self.http.sock
            if self.cancelled.is_set():
                raise RuntimeError("API-запрос остановлен.")
            response = self.http.getresponse()
            if response.status != 200:
                # Do not reflect server error bodies: a custom endpoint can echo credentials or prompts.
                raise RuntimeError(f"API вернул HTTP {response.status}. Проверьте адрес, ключ и доступ к модели. Повтора не было.")
            while True:
                if self.cancelled.is_set():
                    raise RuntimeError("API-запрос остановлен. Автоповтора не было.")
                line = response.readline(262_145)
                if not line:
                    break
                if len(line) > 262_144:
                    raise RuntimeError("Событие API превышает размер буфера.")
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    finished = reason == "stop"
                    break
                event = json.loads(data)
                if not isinstance(event, dict) or "error" in event:
                    raise RuntimeError("API не завершил ответ. Проверьте подключение; повтора не было.")
                delta = ""
                if responses:
                    kind = event.get("type")
                    if kind in {"response.output_text.delta", "response.refusal.delta"}:
                        delta = event.get("delta", "")
                    elif kind == "response.completed":
                        finished = event.get("response", {}).get("status") == "completed"
                        break
                    elif kind in {"error", "response.failed", "response.incomplete"}:
                        raise RuntimeError("API остановился до завершения ответа. Повтора не было.")
                else:
                    choices = event.get("choices", [])
                    if choices:
                        choice = choices[0]
                        delta = choice.get("delta", {}).get("content") or choice.get("delta", {}).get("refusal") or ""
                        reason = choice.get("finish_reason") or reason
                if not isinstance(delta, str):
                    raise RuntimeError("API вернул неподдерживаемый формат текста.")
                if delta:
                    count += len(delta)
                    if count > 250_000:
                        raise RuntimeError("Ответ API превысил размер текстового буфера.")
                    text.append(delta)
                    on_delta(delta)
            if self.cancelled.is_set():
                raise RuntimeError("API-запрос остановлен.")
            if not finished or not "".join(text).strip():
                raise RuntimeError("API не подтвердил завершённый текстовый ответ. Повтора не было.")
            return "".join(text).strip()
        except (OSError, http.client.HTTPException, ValueError, TypeError, AttributeError, IndexError):
            raise RuntimeError("API-запрос остановлен." if self.cancelled.is_set() else "Соединение с API прервано или формат ответа не поддерживается. Повтора не было.") from None
        finally:
            self.http.close()
            self.http = None
            self.stream_socket = None
            self.connection["key"] = ""


class NativeAPIReasoner(BaseReasoner):
    backend_name = "native_api"
    instruction_provider = "api"

    def __init__(self, transport, model, history, on_delta, *, files, criteria, pdfs, project_notes, skill_task, before_provider_call):
        self.transport, self.model, self.history, self.on_delta = transport, model, history, on_delta
        self.files, self.criteria, self.pdfs = files, criteria, pdfs
        self.project_notes, self.skill_task = project_notes, skill_task
        self.before_provider_call = before_provider_call
        self.last_instruction_receipt = None

    def respond(self, user_input, retrieved_memory, observer_state, correction_hints=None):
        self.before_provider_call()
        hints = correction_hints or []
        mode = "full_access" if getattr(self.transport, "full_access", False) else "chat"
        prepared = prepare_local_instructions(self.instruction_provider, observer_state, retrieved_memory, hints,
            claude_full_access=mode == "full_access", claude_workspace_tools=self.transport.workspace_tools is not None)
        self.last_instruction_receipt = build_instruction_receipt(provider=self.instruction_provider, mode=mode, prepared=prepared,
            developer_instructions=None, selected_memory=retrieved_memory, correction_hints=hints)
        prompt = (criteria_context_message(self.criteria) + file_context_message(self.files) + pdf_context_message(self.pdfs)
                  + knowledge_context_message(self.project_notes, self.skill_task) + user_input)
        return self.transport.answer(self.model, prepared.text, self.history, prompt, self.on_delta)
