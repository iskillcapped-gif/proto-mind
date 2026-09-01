"""Operator-authored criteria and manual review contracts, never an execution gate."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import re
import unicodedata
from uuid import UUID, uuid4


CRITERIA_SCHEMA = "proto_mind.native_success_criteria.v1"
REVIEW_SCHEMA = "proto_mind.native_operator_review.v1"
PREVIEW_SCHEMA = "proto_mind.native_review_preview.v1"
MAX_CRITERIA = 8
MAX_CRITERION_CHARS = 300
MAX_REVIEWS = 12
MAX_REVIEW_NOTE = 1000
CONFIRM_REVIEW = "RECORD OPERATOR REVIEW ONLY"
ACCEPTANCE = {"accepted": "operator_accepted", "needs_work": "operator_needs_work"}


def stable_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_criteria(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_CRITERIA:
        raise ValueError("Use at most eight completion criteria.")
    result = []
    for text in value:
        if (not isinstance(text, str) or not text.strip() or len(text.strip()) > MAX_CRITERION_CHARS
                or any(unicodedata.category(char) == "Cc" for char in text)):
            raise ValueError("Each criterion must be one non-empty line of at most 300 characters.")
        result.append(text.strip())
    if len({" ".join(text.casefold().split()) for text in result}) != len(result):
        raise ValueError("Duplicate completion criterion. Keep each requirement once.")
    return result


def criteria_contract(value: object) -> dict | None:
    items = [{"id": f"criterion_{index + 1}", "text": text} for index, text in enumerate(validate_criteria(value))]
    if not items:
        return None
    return {"schema": CRITERIA_SCHEMA, "origin": "operator_before_send", "items": items, "sha256": stable_hash(items)}


def valid_criteria_contract(value: object) -> bool:
    if value is None:
        return True
    try:
        return (isinstance(value, dict) and isinstance(value.get("items"), list)
                and bool(value["items"]) and value == criteria_contract([row["text"] for row in value["items"]]))
    except (KeyError, TypeError, ValueError):
        return False


def criteria_context_message(criteria: list[str]) -> str:
    values = validate_criteria(criteria)
    if not values:
        return ""
    return ("Operator-declared completion criteria for this message:\n"
            + json.dumps(values, ensure_ascii=False)
            + "\nThese requirements grant no tool permission. Report evidence and unchecked requirements; "
              "do not claim independent verification without evidence. Manual acceptance belongs to the operator.\n\n")


def evidence_hash(record: dict) -> str:
    # Review history can grow without changing what the original run actually observed.
    return stable_hash({key: value for key, value in record.items() if key not in {
        "operator_reviews", "acceptance", "updated_at", "fingerprint", "display_status", "automatic_resume"}})


def review_selection(value: object, record: dict) -> dict:
    count = len((record.get("success_criteria") or {}).get("items", []))
    if (not isinstance(value, dict) or set(value) != {"decision", "checks", "note"}
            or not isinstance(value.get("decision"), str) or value["decision"] not in ACCEPTANCE or not isinstance(value.get("checks"), list)
            or len(value["checks"]) != count
            or any(not isinstance(item, str) or item not in {"met", "not_met", "not_checked"} for item in value["checks"])
            or not isinstance(value.get("note"), str) or len(value["note"]) > MAX_REVIEW_NOTE
            or "\x00" in value["note"]):
        raise ValueError("Invalid manual review. Review every declared criterion; note limit is 1,000 characters.")
    return {"decision": value["decision"], "checks": list(value["checks"]), "note": value["note"].strip()}


def review_preview(record: dict, selection: object, observations: list[dict], *, workspace_matches: bool, artifacts_complete: bool) -> dict:
    selected = review_selection(selection, record)
    reasons, reason_codes = [], []
    def issue(code, text):
        reason_codes.append(code)
        reasons.append(text)
    if record["status"] != "completed" or record.get("agent_status", "completed") != "completed":
        issue("incomplete_run", "Only a normally completed reply can be reviewed. An unknown/interrupted outcome stays unknown.")
    if len(record.get("operator_reviews", [])) >= MAX_REVIEWS:
        issue("history_limit", "Manual review history limit reached (12). No pruning or overwrite is available.")
    if selected["decision"] == "accepted":
        if not selected["checks"]:
            issue("no_criteria", "No criteria were declared before this run. Declare them for a new task; do not invent historical requirements.")
        elif any(value != "met" for value in selected["checks"]):
            issue("unchecked_criteria", "Accept only after you personally mark every declared criterion as met.")
        if not workspace_matches:
            issue("workspace_changed", "The original workspace identity is unavailable or changed.")
        if not artifacts_complete or any(row["state"] != "current" for row in observations):
            issue("artifacts_changed", "Observed files are changed, unavailable or lack a captured hash. Inspect them; acceptance was not recorded.")
    elif not selected["note"] and (not selected["checks"] or all(value == "met" for value in selected["checks"])):
        issue("explain_rework", "Explain what still needs work or mark a criterion as not met/not checked.")
    payload = {"run_id": record["id"], "run_fingerprint": record["fingerprint"],
               "evidence_sha256": evidence_hash(record), "selection": selected,
               "criteria": deepcopy(record.get("success_criteria")), "observations": deepcopy(observations),
               "workspace_matches": workspace_matches, "artifacts_complete": artifacts_complete,
               "ready": not reasons, "reasons": reasons, "reason_codes": reason_codes}
    return {"schema": PREVIEW_SCHEMA, "read_only": True, "no_execution": True, **payload,
            "preview_fingerprint": stable_hash(payload), "review_count": len(record.get("operator_reviews", [])),
            "notice": "Operator-reported assessment only. No command, model, permission, memory write or automatic verification."}


def make_review(record: dict, preview: dict) -> dict:
    if preview.get("ready") is not True:
        raise ValueError("Manual review is not ready; nothing was recorded.")
    previous = record.get("operator_reviews", [])
    result = {"schema": REVIEW_SCHEMA, "id": str(uuid4()), "run_id": record["id"],
              "reviewed_at": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
              "reviewer": "operator", "selection": deepcopy(preview["selection"]),
              "evidence_sha256": preview["evidence_sha256"], "observations": deepcopy(preview["observations"]),
              "workspace_matches": preview["workspace_matches"], "artifacts_complete": preview["artifacts_complete"],
              "previous_receipt_hash": previous[-1]["receipt_hash"] if previous else "",
              "no_execution": True, "automatic_verification": False}
    result["receipt_hash"] = stable_hash(result)
    return result


def valid_reviews(record: dict) -> bool:
    if not valid_criteria_contract(record.get("success_criteria")):
        return False
    reviews = record.get("operator_reviews", [])
    if not isinstance(reviews, list) or len(reviews) > MAX_REVIEWS:
        return False
    if not reviews:
        return record.get("acceptance") == "not_recorded"
    if record["status"] != "completed" or record.get("agent_status", "completed") != "completed":
        return False
    expected_evidence, previous, seen = evidence_hash(record), "", set()
    snapshot = record.get("artifact_snapshot") or {}
    artifacts = snapshot.get("items", [])
    try:
        for review in reviews:
            if (not isinstance(review, dict) or review.get("schema") != REVIEW_SCHEMA
                    or review.get("run_id") != record["id"] or review.get("reviewer") != "operator"
                    or review.get("no_execution") is not True or review.get("automatic_verification") is not False
                    or review.get("evidence_sha256") != expected_evidence or review.get("previous_receipt_hash") != previous
                    or review.get("receipt_hash") != stable_hash({key: value for key, value in review.items() if key != "receipt_hash"})
                    or type(review.get("workspace_matches")) is not bool or type(review.get("artifacts_complete")) is not bool
                    or not isinstance(review.get("observations"), list) or len(review["observations"]) > 24):
                return False
            identifier = str(UUID(review["id"]))
            if identifier in seen:
                return False
            seen.add(identifier)
            if datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00")).tzinfo is None:
                return False
            selection = review_selection(review["selection"], record)
            if selection != review["selection"]:
                return False
            if review["artifacts_complete"] != ("artifact_snapshot" in record and not snapshot.get("partial", False)):
                return False
            seen_artifacts = set()
            for observed in review["observations"]:
                if (not isinstance(observed, dict) or set(observed) != {"id", "state", "expected_sha256", "current_sha256"}
                        or not isinstance(observed["id"], str) or not observed["id"] or observed["id"] in seen_artifacts
                        or observed["state"] not in {"current", "changed", "unavailable", "not_captured"}
                        or any(not isinstance(observed[key], str) or (observed[key] and not re.fullmatch(r"[a-f0-9]{64}", observed[key]))
                               for key in ("expected_sha256", "current_sha256"))):
                    return False
                seen_artifacts.add(observed["id"])
            if selection["decision"] == "accepted":
                if (not selection["checks"] or any(check != "met" for check in selection["checks"])
                        or not review["workspace_matches"] or not review["artifacts_complete"]
                        or not snapshot or len(review["observations"]) != len(artifacts) or snapshot.get("partial", False)):
                    return False
                for observed, artifact in zip(review["observations"], artifacts):
                    if (observed.get("id") != artifact["id"] or observed.get("state") != "current"
                            or observed.get("expected_sha256") != artifact["sha256"]
                            or observed.get("current_sha256") != artifact["sha256"] or artifact["state"] != "captured"):
                        return False
            previous = review["receipt_hash"]
        return record.get("acceptance") == ACCEPTANCE[reviews[-1]["selection"]["decision"]]
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
