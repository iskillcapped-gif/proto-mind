from __future__ import annotations

from pathlib import Path

from proto_mind.main import build_coordinator
from proto_mind.memory_hygiene import MemoryHygiene
from proto_mind.models import InteractionResult, MemoryRecord
from proto_mind.session_log import SessionOperatorLogger

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "FastAPI UI dependencies are not installed. Install fastapi and uvicorn to run the research UI."
    ) from exc


class TurnRequest(BaseModel):
    message: str


app = FastAPI(title="Proto-Mind Research UI")
project_root = Path(__file__).resolve().parents[1]
session_logger = SessionOperatorLogger.from_project_root(project_root)
coordinator = build_coordinator(project_root, session_logger=session_logger)
hygiene = MemoryHygiene(coordinator.memory_keeper.store)
turn_history: list[dict[str, object]] = []


def serialize_memory_record(record: MemoryRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "content": record.content,
        "type": record.type,
        "importance": record.importance,
        "source": record.source,
        "timestamp": record.timestamp,
        "tags": list(record.tags),
        "last_used": record.last_used,
        "usage_count": record.usage_count,
        "weight": record.weight,
        "active": record.active,
        "superseded_by": record.superseded_by,
        "superseded_at": record.superseded_at,
        "superseded_reason": record.superseded_reason,
    }


def serialize_turn_result(result: InteractionResult, user_input: str) -> dict[str, object]:
    return {
        "user_input": user_input,
        "response": result.response,
        "observer_state": result.observer_state.to_dict(),
        "retrieved_memory": [serialize_memory_record(record) for record in result.retrieved_memory],
        "retrieval_trace": result.retrieval_trace.to_dict() if result.retrieval_trace else None,
        "memory_summary": result.memory_summary.to_dict(),
        "grounding_audit": result.grounding_audit.to_dict() if result.grounding_audit else None,
        "self_reflection": result.self_reflection.to_dict() if result.self_reflection else None,
        "working_memory_snapshot": [serialize_memory_record(record) for record in result.working_memory_snapshot],
        "persistent_memory_snapshot": [serialize_memory_record(record) for record in result.persistent_memory_snapshot],
        "reasoner_backend": result.reasoner_backend,
        "previous_correction_hints": list(result.previous_correction_hints),
    }


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Proto-Mind Research UI</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f1ea;
      --panel: #fffdf8;
      --border: #d2c8b8;
      --text: #1f1d18;
      --muted: #6a6358;
      --accent: #305252;
    }
    body {
      margin: 0;
      font-family: "SF Mono", "Menlo", monospace;
      background: linear-gradient(180deg, #ebe6da 0%, var(--bg) 100%);
      color: var(--text);
    }
    .layout {
      display: grid;
      grid-template-columns: 320px 1fr;
      min-height: 100vh;
    }
    .sidebar, .main {
      padding: 20px;
      box-sizing: border-box;
    }
    .sidebar {
      border-right: 1px solid var(--border);
      background: rgba(255, 253, 248, 0.7);
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      padding: 14px;
      margin-bottom: 14px;
      border-radius: 8px;
    }
    h1, h2, h3 {
      margin-top: 0;
      font-weight: 600;
    }
    textarea {
      width: 100%;
      min-height: 110px;
      box-sizing: border-box;
      padding: 12px;
      font: inherit;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fcfbf7;
    }
    button {
      margin-top: 10px;
      padding: 10px 16px;
      font: inherit;
      border: 1px solid var(--accent);
      color: white;
      background: var(--accent);
      border-radius: 8px;
      cursor: pointer;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .muted {
      color: var(--muted);
    }
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="panel">
        <h1>Proto-Mind v0</h1>
        <p class="muted">Local cognition inspection UI. Built for observing pipeline state, not polished chat UX.</p>
        <p><strong>Backend:</strong> <span id="backend">loading...</span></p>
      </div>
      <div class="panel">
        <h2>Send Turn</h2>
        <textarea id="message" placeholder="Enter a message for Proto-Mind"></textarea>
        <button id="send">Run Pipeline</button>
      </div>
      <div class="panel">
        <h2>Turn History</h2>
        <pre id="history">No turns yet.</pre>
      </div>
    </aside>
    <main class="main">
      <div class="panel"><h2>User Input</h2><pre id="user_input"></pre></div>
      <div class="panel"><h2>Observer Output</h2><pre id="observer_output"></pre></div>
      <div class="panel"><h2>Retrieved Memory</h2><pre id="retrieved_memory"></pre></div>
      <div class="panel"><h2>Retrieval Trace</h2><pre id="retrieval_trace"></pre></div>
      <div class="panel"><h2>Final Response</h2><pre id="final_response"></pre></div>
      <div class="panel"><h2>Memory Save Decision</h2><pre id="memory_decision"></pre></div>
      <div class="panel"><h2>Grounding Audit</h2><pre id="grounding_audit"></pre></div>
      <div class="panel"><h2>Previous Correction Hints</h2><pre id="previous_correction_hints"></pre></div>
      <div class="panel"><h2>Self-Reflection</h2><pre id="self_reflection"></pre></div>
      <div class="panel"><h2>Current Working Memory</h2><pre id="working_memory"></pre></div>
      <div class="panel"><h2>Current Persistent Memory</h2><pre id="persistent_memory"></pre></div>
    </main>
  </div>
  <script>
    const nodes = {
      backend: document.getElementById("backend"),
      history: document.getElementById("history"),
      user_input: document.getElementById("user_input"),
      observer_output: document.getElementById("observer_output"),
      retrieved_memory: document.getElementById("retrieved_memory"),
      retrieval_trace: document.getElementById("retrieval_trace"),
      final_response: document.getElementById("final_response"),
      memory_decision: document.getElementById("memory_decision"),
      grounding_audit: document.getElementById("grounding_audit"),
      previous_correction_hints: document.getElementById("previous_correction_hints"),
      self_reflection: document.getElementById("self_reflection"),
      working_memory: document.getElementById("working_memory"),
      persistent_memory: document.getElementById("persistent_memory"),
    };

    function format(value) {
      return JSON.stringify(value, null, 2);
    }

    async function sendTurn() {
      const message = document.getElementById("message").value.trim();
      if (!message) return;
      const response = await fetch("/api/turn", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message}),
      });
      const data = await response.json();
      if (!response.ok) {
        alert(data.detail || "Failed to run pipeline");
        return;
      }
      nodes.backend.textContent = data.reasoner_backend;
      nodes.user_input.textContent = data.user_input;
      nodes.observer_output.textContent = format(data.observer_state);
      nodes.retrieved_memory.textContent = format(data.retrieved_memory);
      nodes.retrieval_trace.textContent = format(data.retrieval_trace);
      nodes.final_response.textContent = data.response;
      nodes.memory_decision.textContent = format(data.memory_summary);
      nodes.grounding_audit.textContent = format(data.grounding_audit);
      nodes.previous_correction_hints.textContent = format(data.previous_correction_hints);
      nodes.self_reflection.textContent = format(data.self_reflection);
      nodes.working_memory.textContent = format(data.working_memory_snapshot);
      nodes.persistent_memory.textContent = format(data.persistent_memory_snapshot);
      nodes.history.textContent = data.history.map((item, index) =>
        `${index + 1}. ${item.user_input}\\n   backend=${item.reasoner_backend}; query_type=${item.observer_state.query_type}`
      ).join("\\n\\n");
      document.getElementById("message").value = "";
    }

    document.getElementById("send").addEventListener("click", sendTurn);
  </script>
</body>
</html>"""


@app.post("/api/turn")
async def run_turn(payload: TurnRequest) -> dict[str, object]:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty.")
    result = coordinator.handle(message)
    turn_payload = serialize_turn_result(result, message)
    turn_history.append(turn_payload)
    response_payload = dict(turn_payload)
    response_payload["history"] = [dict(item) for item in turn_history[-20:]]
    return response_payload


@app.get("/api/memory/hygiene-preview")
async def hygiene_preview() -> dict[str, object]:
    return hygiene.preview_cleanup().to_dict()


@app.post("/api/memory/cleanup-apply")
async def hygiene_apply() -> dict[str, object]:
    return hygiene.apply_cleanup().to_dict()
