"""Work-session, evidence and Session Spine routes for the local Native bridge.

The backend owns shared turn exclusion and stores; this module owns only routing.
"""
from proto_mind.native_desk import artifact_page, artifact_preview
from proto_mind.native_session_spine_live import build_live_session_spine_preview
from proto_mind.native_session_spine_writer import preview_native_session_spine_writer, apply_native_session_spine_writer
from proto_mind.native_work_sessions import workspace_identity

HISTORY_METHODS = frozenset(['artifact_list', 'artifact_preview', 'review_preview', 'review_save', 'session_spine_preview', 'session_spine_writer_apply', 'session_spine_writer_preview', 'work_session_continuation', 'work_session_lookup', 'work_sessions'])


def dispatch_history(self, method: str, params: dict) -> dict:
    if method == "work_sessions":
        return self.work_sessions.page(params.get("conversation_id", ""), params.get("cursor"))
    if method == "work_session_lookup":
        return {"schema": "proto_mind.native_work_session_lookup.v1", "read_only": True,
                "run": self.work_sessions.lookup(params.get("run_id", ""), params.get("conversation_id", ""))}
    if method == "session_spine_preview":
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait for the active turn before opening its Session Spine preview.")
        try:
            return build_live_session_spine_preview(self.work_sessions, params)
        finally:
            self.busy.release()
    if method in {"session_spine_writer_preview", "session_spine_writer_apply"}:
        if self.closing.is_set() or not self.busy.acquire(blocking=False):
            raise ValueError("Wait for the active turn before opening the Session Spine writer pilot.")
        try:
            if method == "session_spine_writer_preview":
                return preview_native_session_spine_writer(self.work_sessions, self.state_dir, params)
            return apply_native_session_spine_writer(self.work_sessions, self.state_dir, params)
        finally:
            self.busy.release()
    if method == "review_preview":
        record = self.work_sessions.inspect(params.get("run"), params.get("conversation_id", ""))
        return self._review_preview(params, record)
    if method == "review_save":
        return self.save_review(params)
    if method in {"artifact_list", "artifact_preview"}:
        record = self.work_sessions.inspect(params.get("run"), params.get("conversation_id", ""))
        if method == "artifact_list":
            return artifact_page(record)
        return artifact_preview(record, params.get("artifact_id", ""), self._artifact_workspace(params, record))
    if method == "work_session_continuation":
        workspace = workspace_identity(self.workspace(params).root) if params.get("workspace_root") else None
        result = self.work_sessions.continuation(params.get("continuation"), params.get("conversation_id", ""), workspace)
        if result["sources"]:
            self.workspace(params).context_files(result["sources"])
        return result
    raise ValueError("Unknown Native history method.")
