"""Disposable Native UI/integration service. Never starts a real model or tool."""
import json
from pathlib import Path
import time
from uuid import uuid4

from proto_mind.native_codex import CodexSubscription, CodexConnectionError, CodexRequestRejected, model_options
from proto_mind.native_progress import PublicMessages


class FixtureRPC:
    def __init__(self, state):
        self.state, self.closed = state, False
        self.thread_id, self.turn_id = "fixture-thread", None

    def control(self):
        path = self.state / "steering-control.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def request(self, method, params=None, **kwargs):
        self.state.mkdir(parents=True, exist_ok=True)
        with (self.state / "steering-rpc.jsonl").open("a") as log:
            log.write(json.dumps({"method": method, "params": params}) + "\n")
        control = self.control()
        if method == "account/rateLimits/read":
            time.sleep(control.get("limits_delay", 0))
            if control.get("limits_error"): raise CodexConnectionError("Fixture unavailable")
            return {"rateLimits": {"primary": {"usedPercent": control.get("primary", 27), "windowDurationMins": 300,
                "resetsAt": int(time.time()) + 3600}, "secondary": {"usedPercent": control.get("weekly", 48),
                "windowDurationMins": 10080, "resetsAt": int(time.time()) + 86400}}, "rateLimitResetCredits": {"availableCount": 0}}
        if method == "account/usage/read": return {"summary": {"lifetimeTokens": 1000}, "dailyUsageBuckets": []}
        if method == "turn/steer":
            if params["expectedTurnId"] != self.turn_id or control.get("outcome") == "rejected":
                raise CodexRequestRejected("Fixture turn rejected update")
            with (self.state / "steering-received.jsonl").open("a") as log:
                log.write(json.dumps(params) + "\n")
            if control.get("outcome") == "unknown": raise CodexConnectionError("Fixture lost reply")
            return {"turnId": self.turn_id}
        raise AssertionError("Unexpected fixture RPC: " + method)

    def close(self): self.closed = True


class FixtureSubscription(CodexSubscription):
    def account(self): return {"connected": True, "auth_type": "chatgpt", "plan": "plus", "email": "ui-test@example.invalid"}

    def models(self):
        return model_options([{"id": "gpt-6-astra", "model": "gpt-6-astra", "displayName": "GPT-6 Astra",
            "isDefault": True, "defaultReasoningEffort": "medium",
            "supportedReasoningEfforts": [{"reasoningEffort": "medium", "description": "Medium"}]}])

    def connect(self):
        if self.rpc is None or self.rpc.closed: self.rpc = FixtureRPC(self.home.parent)
        return self.rpc

    def _chat_answer(self, prompt, instructions, model, on_delta, progress, reasoning_effort, images,
                     conversation, logical_workspace, history):
        rpc = self.connect()
        rpc.state.mkdir(parents=True, exist_ok=True)
        time.sleep(rpc.control().get("ready_delay", 0))
        if self.cancelled.is_set(): raise CodexConnectionError("Fixture stopped before start")
        rpc.turn_id = str(uuid4())
        self._set_main_turn((rpc.thread_id, rpc.turn_id))
        progress.stage("working")
        messages = PublicMessages(on_delta, progress, limit=5000, error_type=CodexConnectionError)
        messages.observe("item/completed", {"item": {"type": "userMessage", "id": "initial"}})
        messages.observe("item/completed", {"item": {"type": "agentMessage", "id": "old-answer", "phase": "final_answer", "text": "Предварительный ответ"}})
        try:
            deadline = time.monotonic() + 180
            while not (rpc.state / "finish-steering").exists():
                if self.cancelled.is_set(): raise CodexConnectionError("Fixture stopped")
                if time.monotonic() > deadline: raise CodexConnectionError("Fixture deadline")
                if (rpc.state / "steering-received.jsonl").exists():
                    messages.observe("item/completed", {"item": {"type": "userMessage", "id": "correction"}})
                time.sleep(0.02)
            received = rpc.state / "steering-received.jsonl"
            texts = [json.loads(line)["input"][0]["text"] for line in received.read_text().splitlines()] if received.exists() else []
            answer = "Задача завершена. Полученные уточнения: " + "; ".join(texts)
            messages.observe("item/completed", {"item": {"type": "agentMessage", "id": "final-answer", "phase": "final_answer", "text": answer}})
            return messages.answer()
        finally: self._set_main_turn(None)

    def interrupt(self): self.cancelled.set()
    def select_skills(self, *args, **kwargs): raise AssertionError("No real selector in this fixture")
    def agent_answer(self, *args, **kwargs): raise AssertionError("No real tools in this fixture")
