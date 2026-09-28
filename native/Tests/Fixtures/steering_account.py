"""Disposable Native UI/integration service. Never starts a real model or tool."""
import json
from pathlib import Path
import time
from uuid import uuid4

from proto_mind.native_codex import CodexSubscription, CodexConnectionError, CodexRequestRejected, model_options
from proto_mind.native_progress import PublicMessages, WorkLog


def delayed_steering_reply(state, steering, params):
    """Delay transport delivery after provider acceptance releases its turn lock."""
    result = steering.send(params)
    control = state / "steering-control.json"
    delay = json.loads(control.read_text()).get("reply_delay", 0) if control.exists() else 0
    if delay:
        (state / "steering-delayed-reply").write_text(params["message_id"])
        time.sleep(delay)
    return result


class FixtureRPC:
    def __init__(self, state):
        # On 2026-09-06 this fixture's log landed in the operator's own data folder, and every
        # private backup was refused from then on as an unknown section. Checks use disposable folders.
        if Path(state).resolve() == (Path.home() / "Library/Application Support/ProtoMindNative").resolve():
            raise RuntimeError("The steering fixture never writes into the operator's Proto-Mind data.")
        self.state, self.closed = state, False
        self.thread_id, self.turn_id = "fixture-" + str(uuid4()), None

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
            time.sleep(control.get("ack_delay", 0))
            return {"turnId": self.turn_id}
        raise AssertionError("Unexpected fixture RPC: " + method)

    def close(self): self.closed = True


class FixtureSubscription(CodexSubscription):
    def account(self): return {"connected": True, "auth_type": "chatgpt", "plan": "plus", "email": "ui-test@example.invalid"}

    def models(self):
        return model_options([{"id": "gpt-6-astra", "model": "gpt-6-astra", "displayName": "GPT-6 Astra",
            "inputModalities": ["text", "image"],
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
        (rpc.state / ("steering-started-" + conversation.lower())).write_text(rpc.turn_id)
        self._set_main_turn((rpc.thread_id, rpc.turn_id))
        progress.stage("working")
        messages = PublicMessages(on_delta, progress, limit=5000, error_type=CodexConnectionError)
        messages.observe("item/completed", {"item": {"type": "userMessage", "id": "initial"}})
        messages.observe("item/completed", {"item": {"type": "agentMessage", "id": "old-answer", "phase": "final_answer", "text": "Предварительный ответ · " + conversation[-8:]}})
        try:
            deadline = time.monotonic() + 180
            while not (rpc.state / "finish-steering").exists() and not (rpc.state / ("finish-steering-" + conversation.lower())).exists():
                if self.cancelled.is_set(): raise CodexConnectionError("Fixture stopped")
                if time.monotonic() > deadline: raise CodexConnectionError("Fixture deadline")
                if (rpc.state / "steering-received.jsonl").exists():
                    messages.observe("item/completed", {"item": {"type": "userMessage", "id": "correction"}})
                time.sleep(0.02)
            received = rpc.state / "steering-received.jsonl"
            texts = [row["input"][0]["text"] for row in (json.loads(line) for line in received.read_text().splitlines())
                     if row["expectedTurnId"] == rpc.turn_id] if received.exists() else []
            answer = "Задача завершена. Полученные уточнения: " + "; ".join(texts)
            messages.observe("item/completed", {"item": {"type": "agentMessage", "id": "final-answer", "phase": "final_answer", "text": answer}})
            return messages.answer()
        finally: self._set_main_turn(None)

    def interrupt(self): self.cancelled.set()
    def select_skills(self, *args, **kwargs): raise AssertionError("No real selector in this fixture")
    def agent_answer(self, prompt, instructions, model, on_delta, *, conversation, logical_workspace,
                     history=None, workspace, on_activity, on_progress=None, reasoning_effort="", images=None, criteria=None,
                     contract_version=1):
        from proto_mind.native_agent import AgentRun
        from proto_mind.native_agent_contract import build_agent_contract
        run = AgentRun(workspace, on_activity)
        run.attach_contract(build_agent_contract(workspace, model=model or "fixture", reasoning_effort=reasoning_effort,
                            computer_use=False, criteria=criteria, version=contract_version))
        progress = WorkLog(on_progress, "full_access")
        run.publish()
        try:
            answer = self._chat_answer(prompt, instructions, model, on_delta, progress, reasoning_effort,
                                       images, conversation, logical_workspace, history)
            run.finish("completed")
            return answer
        finally:
            if "finished_at" not in run.receipt: run.finish("interrupted" if self.cancelled.is_set() else "failed")
            progress.finish(run.receipt["status"])
