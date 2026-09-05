"""Content-free, append-only archive/restore events for explicit project notes."""
from uuid import UUID

from proto_mind.native_private_records import HASH


SCHEMA = "proto_mind.native_project_note_state.v1"
FIELDS = {"schema", "project_root", "workspace", "conversation_id", "note_id", "note_record_hash",
          "previous_state_id", "action", "source", "executable", "automatic_learning"}
ACTIONS = {"archive": "archived", "restore": "active"}


def validate_state(body):
    if (not isinstance(body, dict) or set(body) != FIELDS or body["schema"] != SCHEMA
            or not isinstance(body["action"], str) or body["action"] not in ACTIONS or body["source"] != "operator_explicit"
            or body["executable"] is not False or body["automatic_learning"] is not False
            or any(not isinstance(body[key], str) or not HASH.fullmatch(body[key]) for key in ("note_id", "note_record_hash"))
            or not isinstance(body["previous_state_id"], str)
            or body["previous_state_id"] and not HASH.fullmatch(body["previous_state_id"])):
        raise ValueError("Project-note state schema or reference does not verify.")
    UUID(body["conversation_id"])
    root, workspace = body["project_root"], body["workspace"]
    if (not isinstance(root, str) or not root.startswith("/") or len(root) > 4096
            or not isinstance(workspace, dict) or set(workspace) != {"path", "device", "inode"}
            or not isinstance(workspace["path"], str) or not workspace["path"].startswith("/") or len(workspace["path"]) > 4096
            or any(type(workspace[key]) is not int or workspace[key] < 0 for key in ("device", "inode"))):
        raise ValueError("Project-note state requires an exact project scope.")


def project_states(notes, events):
    """Resolve each linked chain, never choose a winner from timestamps or forks."""
    by_note = {row["id"]: row for row in notes}
    grouped, states, heads, issues = {}, {}, {}, []
    for event in events:
        body = event["body"]
        note = by_note.get(body["note_id"])
        if (note is None or note["record_hash"] != body["note_record_hash"]
                or any(note["body"][key] != body[key] for key in ("project_root", "workspace"))):
            issues.append("Project-note state points to a missing, changed or foreign note.")
            continue
        grouped.setdefault(note["id"], []).append(event)
    for identifier, chain in grouped.items():
        children = {}
        for event in chain:
            children.setdefault(event["body"]["previous_state_id"], []).append(event)
        cursor, expected, visited = "", "archive", set()
        while cursor in children:
            candidates = children[cursor]
            if len(candidates) != 1:
                issues.append("Project-note state has competing changes; inspect its history.")
                break
            event = candidates[0]
            if event["id"] in visited or event["body"]["action"] != expected:
                issues.append("Project-note state order or cycle does not verify.")
                break
            visited.add(event["id"])
            cursor = event["id"]
            states[identifier] = ACTIONS[event["body"]["action"]]
            heads[identifier] = cursor
            expected = "restore" if expected == "archive" else "archive"
        if len(visited) != len(chain):
            issues.append("Project-note state history is incomplete or ambiguous; no automatic recall.")
    return states, heads, issues
