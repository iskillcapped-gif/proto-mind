from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from proto_mind.action_policy import classify_command, classify_command_bundle
from proto_mind.action_preview import build_action_preview
from proto_mind.command_registry import match_registered_command


VALID_ACTION_STATUSES = {"proposed", "approved", "rejected", "archived"}
VALID_INPUT_TYPES = {"slash", "natural", "unknown"}
VALID_RESOLVED_TARGETS = {"command", "bundle", "unknown"}
VALID_POLICY_CLASSES = {"auto_allowed", "confirmation_required", "operator_only", "blocked"}
VALID_EXECUTION_STATES = {"unconfirmed", "confirmed", "executed"}
REQUIRED_ACTION_FIELDS = {
    "id",
    "created_at",
    "status",
    "original_input",
    "input_type",
    "resolved_target",
    "commands",
    "strictest_policy",
    "policy_summary",
    "registry_summary",
    "no_execution",
}
LEGACY_EXECUTION_RECEIPT_FIELDS = {"execution_result", "execution_receipt", "target_executed"}
ActionExecutor = Callable[[str], str | None]


def format_action_queue_command(
    command: str,
    *,
    project_root: Path,
    executor: ActionExecutor | None = None,
) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/action"):
        return None
    queue = ActionProposalQueue.from_project_root(project_root)
    if normalized == "/action queue-status":
        return queue.format_status()
    if normalized == "/action queue-export":
        return queue.export()
    if normalized == "/action cleanup-preview":
        return queue.format_cleanup_preview()
    if normalized == "/action readiness-doctor":
        return queue.format_readiness_doctor()
    if normalized == "/action run-audit":
        return queue.format_run_audit()
    if normalized.startswith("/action run-verify"):
        proposal_id = stripped[len("/action run-verify") :].strip()
        return queue.format_run_verify(proposal_id)
    if normalized == "/action runs" or normalized.startswith("/action runs "):
        parsed = _parse_runs_options(stripped)
        if isinstance(parsed, str):
            return parsed
        return queue.format_runs(limit=parsed["limit"], include_all=parsed["include_all"])
    if normalized.startswith("/action run-receipt"):
        proposal_id = stripped[len("/action run-receipt") :].strip()
        return queue.format_run_receipt(proposal_id)
    if normalized.startswith("/action run-preview"):
        proposal_id = stripped[len("/action run-preview") :].strip()
        return queue.format_run_preview(proposal_id)
    if normalized.startswith("/action run"):
        proposal_id = stripped[len("/action run") :].strip()
        return queue.run(proposal_id, executor=executor)
    if normalized.startswith("/action confirm-preview"):
        proposal_id = stripped[len("/action confirm-preview") :].strip()
        return queue.format_confirm_preview(proposal_id)
    if normalized.startswith("/action unconfirm"):
        parsed = _parse_id_reason(stripped, "/action unconfirm")
        if isinstance(parsed, str):
            return parsed
        return queue.unconfirm(parsed["id"], reason=parsed["reason"])
    if normalized.startswith("/action confirm"):
        parsed = _parse_id_token(stripped)
        if isinstance(parsed, str):
            return parsed
        return queue.confirm(parsed["id"], parsed["token"])
    if normalized == "/action proposals" or normalized == "/action proposals --all":
        return queue.format_list(include_archived="--all" in normalized.split())
    if normalized == "/action queue-doctor":
        return queue.format_doctor()
    if normalized.startswith("/action propose"):
        original_input = stripped[len("/action propose") :].strip()
        return queue.propose(original_input)
    if normalized.startswith("/action inspect"):
        proposal_id = stripped[len("/action inspect") :].strip()
        return queue.format_inspect(proposal_id)
    if normalized.startswith("/action approve"):
        proposal_id = stripped[len("/action approve") :].strip()
        return queue.set_status(proposal_id, "approved")
    if normalized.startswith("/action reject"):
        parsed = _parse_id_reason(stripped, "/action reject")
        if isinstance(parsed, str):
            return parsed
        return queue.set_status(parsed["id"], "rejected", reason=parsed["reason"])
    if normalized.startswith("/action archive"):
        proposal_id = stripped[len("/action archive") :].strip()
        return queue.set_status(proposal_id, "archived")
    return None


class ActionProposalQueue:
    def __init__(self, queue_path: Path) -> None:
        self.queue_path = queue_path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "ActionProposalQueue":
        return cls(project_root / "proto_mind" / "data" / "action_queue.jsonl")

    @property
    def export_dir(self) -> Path:
        return self.queue_path.parent.parent / "exports" / "action_queue"

    def format_status(self) -> str:
        state = self._read_state()
        records = state["records"]
        status_counts = Counter(str(item.get("status") or "missing") for item in records)
        policy_counts = Counter(str(item.get("strictest_policy") or "missing") for item in records)
        oldest_age = _oldest_proposed_age(records)
        lines = [
            "Action Proposal Queue Status",
            f"queue_path: {self.queue_path}",
            f"readable: {not bool(state['error'])}",
            f"total_records: {len(records)}",
            f"malformed_records: {state['malformed_count']}",
            f"status_counts: {_format_counter(status_counts)}",
            f"policy_counts: {_format_counter(policy_counts)}",
            f"execution_state_counts: {_format_counter(_execution_state_counts(records))}",
            f"oldest_proposed_age: {oldest_age}",
        ]
        if state["error"]:
            lines.append(f"error: {state['error']}")
        lines.extend(
            [
                "",
                "Available commands:",
                "- /action queue-status",
                "- /action proposals [--all]",
                "- /action inspect <id>",
                "- /action confirm-preview <id>",
                "- /action confirm <id> <token>",
                "- /action unconfirm <id> [reason]",
                "- /action run-preview <id>",
                "- /action run <id>",
                "- /action run-receipt <id>",
                "- /action runs [--all|--last N]",
                "- /action run-verify <id>",
                "- /action run-audit",
                "- /action readiness-doctor",
                "- /action queue-export",
                "- /action cleanup-preview",
                "- /action queue-doctor",
            ]
        )
        return "\n".join(lines)

    def export(self) -> str:
        state = self._read_state()
        if state["error"]:
            return f"Action Proposal Queue export failed: {state['error']}"
        if state["malformed_count"]:
            return (
                "Action Proposal Queue export refused: "
                f"malformed entries present: {state['malformed_count']}. Run /action queue-doctor."
            )
        records = state["records"]
        generated_at = _utc_now()
        status_counts = Counter(str(item.get("status") or "missing") for item in records)
        policy_counts = Counter(str(item.get("strictest_policy") or "missing") for item in records)
        compact_records = [_export_record(item) for item in records]
        payload = {
            "generated_at": generated_at,
            "source_queue_path": str(self.queue_path),
            "total_records": len(records),
            "counts_by_status": dict(sorted(status_counts.items())),
            "counts_by_strictest_policy": dict(sorted(policy_counts.items())),
            "no_target_commands_executed": True,
            "records": compact_records,
        }
        stamp = datetime.fromisoformat(generated_at).strftime("%Y%m%d_%H%M%S")
        suffix = uuid4().hex[:6]
        markdown_path = self.export_dir / f"action_queue_{stamp}_{suffix}.md"
        json_path = self.export_dir / f"action_queue_{stamp}_{suffix}.json"
        try:
            _atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            _atomic_write_text(markdown_path, _format_export_markdown(payload))
        except OSError as exc:
            return f"Action Proposal Queue export failed: {exc}"
        return "\n".join(
            [
                "Action Proposal Queue Export",
                f"generated_at: {generated_at}",
                f"records: {len(records)}",
                f"markdown: {markdown_path}",
                f"json: {json_path}",
                "No target commands were executed; export files only were created.",
            ]
        )

    def format_cleanup_preview(self) -> str:
        state = self._read_state()
        if state["error"]:
            return f"Action Proposal Queue cleanup preview error: {state['error']}"
        records = state["records"]
        suggestions = ["/action queue-export"]
        notes = ["Export the queue before any manual lifecycle cleanup."]
        now = datetime.now(UTC)
        for item in records:
            item_id = str(item.get("id") or "")
            if not item_id:
                continue
            status = item.get("status")
            policy = item.get("strictest_policy")
            if status == "approved":
                if _execution_state(item) == "confirmed":
                    suggestions.extend([f'/action unconfirm {item_id} "review complete"', f"/action archive {item_id}"])
                    notes.append(f"Confirmed proposal {item_id}: unconfirm before archiving after review and export.")
                else:
                    suggestions.append(f"/action archive {item_id}")
                    notes.append(f"Approved proposal {item_id}: archive after operator review and export.")
            if status == "proposed" and _is_older_than(str(item.get("created_at") or ""), now, days=30):
                suggestions.extend(
                    [
                        f"/action inspect {item_id}",
                        f'/action reject {item_id} "stale proposal"',
                        f"/action archive {item_id}",
                    ]
                )
                notes.append(f"Old proposed item {item_id}: inspect, then reject or archive manually.")
            if status == "proposed" and policy == "blocked":
                suggestions.extend([f"/action inspect {item_id}", f'/action reject {item_id} "blocked by policy"'])
                notes.append(f"Blocked proposal {item_id}: inspect and reject unless it is needed for historical review.")
        if len(records) > 100:
            notes.append(f"Queue is large ({len(records)} records); export before reducing reviewed items.")
        suggestions = list(dict.fromkeys(suggestions))
        lines = [
            "Action Proposal Queue Cleanup Preview",
            f"queue_path: {self.queue_path}",
            f"records_reviewed: {len(records)}",
            f"malformed_records: {state['malformed_count']}",
            "",
            "Notes:",
        ]
        lines.extend(f"- {note}" for note in notes)
        if len(notes) == 1:
            lines.append("- No stale, blocked, or approved proposals currently need lifecycle cleanup.")
        lines.extend(["", "Suggested manual commands:"])
        lines.extend(f"- {suggestion}" for suggestion in suggestions)
        lines.extend(
            [
                "",
                "No queue records or target stores were changed.",
                "No target command executed.",
            ]
        )
        return "\n".join(lines)

    def propose(self, original_input: str) -> str:
        original_input = original_input.strip()
        if not original_input:
            return "Usage: /action propose <slash command or exact natural phrase>"
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _mutation_refused(state)
        preview = build_action_preview(original_input)
        now = _utc_now()
        steps = preview["steps"]
        matched = bool(preview["matched"])
        if not matched:
            input_type = "unknown"
            resolved_target = "unknown"
        else:
            input_type = "slash" if preview["input_type"] == "slash_command" else "natural"
            resolved_target = "bundle" if len(steps) > 1 else "command"
        proposal = {
            "id": _new_action_id(now),
            "created_at": now,
            "updated_at": now,
            "status": "proposed",
            "original_input": original_input,
            "input_type": input_type,
            "resolved_target": resolved_target,
            "commands": [str(step.get("command") or "") for step in steps],
            "strictest_policy": preview["policy_class"],
            "policy_summary": preview["policy_reason"],
            "registry_summary": [
                {
                    "command": step.get("command"),
                    "prefix": step.get("matched_prefix"),
                    "category": step.get("category"),
                    "read_only": step.get("read_only"),
                    "mutates": step.get("mutates"),
                    "risk": step.get("risk"),
                    "policy": step.get("policy_class"),
                }
                for step in steps
            ],
            "no_execution": True,
            "rationale": "",
            "reason": "",
            "approved_at": None,
            "rejected_at": None,
            "archived_at": None,
            "execution_state": "unconfirmed",
            "confirmed_at": None,
            "unconfirmed_at": None,
            "confirmation_method": "",
            "confirmation_token_used": "",
            "unconfirmed_reason": "",
            "executed_at": None,
            "run_id": "",
            "executed_command_count": 0,
            "run_policy": "",
            "run_result_summary": "",
            "run_receipt": None,
            "target_execution_performed": False,
            "receipt_hash": "",
        }
        self._write_records([*state["records"], proposal])
        return "\n".join(
            [
                "Action proposal created:",
                f"  id: {proposal['id']}",
                f"  input: {proposal['original_input']}",
                f"  resolved_target: {proposal['resolved_target']}",
                f"  commands: {len(proposal['commands'])}",
                f"  strictest_policy: {proposal['strictest_policy']}",
                "No target command executed.",
            ]
        )

    def format_list(self, *, include_archived: bool = False) -> str:
        state = self._read_state()
        if state["error"]:
            return f"Action Proposal Queue error: {state['error']}"
        records = state["records"] if include_archived else [item for item in state["records"] if item.get("status") != "archived"]
        lines = ["Action Proposals (all):" if include_archived else "Action Proposals:"]
        if state["malformed_count"]:
            lines.append(f"  malformed_entries_skipped: {state['malformed_count']}")
        if not records:
            lines.append("  (none)")
            return "\n".join(lines)
        for item in sorted(records, key=lambda value: str(value.get("created_at") or ""), reverse=True):
            lines.append(
                f"  - {item.get('id', 'unknown')} [{item.get('status', 'unknown')}] "
                f"policy={item.get('strictest_policy', 'unknown')} "
                f"input={_preview(str(item.get('original_input') or ''))} "
                f"created_at={item.get('created_at', 'unknown')}"
            )
        return "\n".join(lines)

    def format_inspect(self, proposal_id: str) -> str:
        proposal_id = proposal_id.strip()
        if not proposal_id:
            return "Usage: /action inspect <id>"
        state = self._read_state()
        if state["error"]:
            return f"Action Proposal Queue error: {state['error']}"
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        lines = [
            "Action Proposal",
            f"id: {item.get('id')}",
            f"created_at: {item.get('created_at')}",
            f"updated_at: {item.get('updated_at')}",
            f"status: {item.get('status')}",
            f"original_input: {item.get('original_input')}",
            f"input_type: {item.get('input_type')}",
            f"resolved_target: {item.get('resolved_target')}",
            f"strictest_policy: {item.get('strictest_policy')}",
            f"policy_summary: {item.get('policy_summary')}",
            f"no_execution: {item.get('no_execution')}",
            f"rationale: {item.get('rationale') or ''}",
            f"reason: {item.get('reason') or ''}",
            f"approved_at: {item.get('approved_at') or ''}",
            f"rejected_at: {item.get('rejected_at') or ''}",
            f"archived_at: {item.get('archived_at') or ''}",
            f"execution_state: {_execution_state(item)}",
            f"confirmed_at: {item.get('confirmed_at') or ''}",
            f"unconfirmed_at: {item.get('unconfirmed_at') or ''}",
            f"confirmation_method: {item.get('confirmation_method') or ''}",
            f"confirmation_token_used: {item.get('confirmation_token_used') or ''}",
            f"unconfirmed_reason: {item.get('unconfirmed_reason') or ''}",
            f"confirmation_eligible: {_confirmation_eligibility(item)[0]}",
            f"confirmation_eligibility_reason: {_confirmation_eligibility(item)[1]}",
            f"executed_at: {item.get('executed_at') or ''}",
            f"run_id: {item.get('run_id') or ''}",
            f"executed_command_count: {item.get('executed_command_count') if item.get('executed_command_count') is not None else ''}",
            f"run_policy: {item.get('run_policy') or ''}",
            f"run_result_summary: {item.get('run_result_summary') or ''}",
            f"target_execution_performed: {item.get('target_execution_performed') is True}",
            f"receipt_hash: {item.get('receipt_hash') or ''}",
            f"run_receipt_present: {isinstance(item.get('run_receipt'), dict)}",
            "commands:",
        ]
        commands = item.get("commands") if isinstance(item.get("commands"), list) else []
        lines.extend(f"  - {command}" for command in commands)
        if not commands:
            lines.append("  - none")
        lines.append("registry_summary:")
        summaries = item.get("registry_summary") if isinstance(item.get("registry_summary"), list) else []
        for summary in summaries:
            if isinstance(summary, dict):
                lines.append(
                    "  - "
                    f"{summary.get('command')} prefix={summary.get('prefix')} category={summary.get('category')} "
                    f"read_only={summary.get('read_only')} mutates={summary.get('mutates')} "
                    f"risk={summary.get('risk')} policy={summary.get('policy')}"
                )
        if not summaries:
            lines.append("  - none")
        lines.append(_approval_guidance(str(item.get("strictest_policy") or "blocked")))
        lines.append("No target command executed.")
        return "\n".join(lines)

    def format_confirm_preview(self, proposal_id: str) -> str:
        proposal_id = proposal_id.strip()
        if not proposal_id:
            return "Usage: /action confirm-preview <id>"
        state = self._read_state()
        if state["error"]:
            return f"Action Proposal Queue error: {state['error']}"
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        eligible, reason = _confirmation_eligibility(item)
        token = _confirmation_token(item) if eligible else "unavailable"
        commands = item.get("commands") if isinstance(item.get("commands"), list) else []
        lines = [
            "Action Confirmation Preview",
            f"id: {item.get('id')}",
            f"status: {item.get('status')}",
            f"execution_state: {_execution_state(item)}",
            f"original_input: {item.get('original_input')}",
            f"strictest_policy: {item.get('strictest_policy')}",
            f"confirmable: {eligible}",
            f"reason: {reason}",
            "commands:",
        ]
        lines.extend(f"  - {command}" for command in commands)
        if not commands:
            lines.append("  - none")
        lines.extend(
            [
                f"confirmation_token: {token}",
                "Confirmation changes queue metadata only; it does not authorize or execute a target command.",
                "No target command executed.",
            ]
        )
        return "\n".join(lines)

    def format_run_preview(self, proposal_id: str) -> str:
        proposal_id = proposal_id.strip()
        if not proposal_id:
            return "Usage: /action run-preview <id>"
        state = self._read_state()
        if state["error"]:
            return f"Action Proposal Queue error: {state['error']}"
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        if _execution_state(item) == "executed":
            return "\n".join(
                [
                    "Action Run Preview",
                    f"id: {proposal_id}",
                    f"status: {item.get('status')}",
                    "execution_state: executed",
                    "readiness: NOT READY",
                    "Reasons:",
                    "- already executed",
                    f"suggestion: /action run-receipt {proposal_id}",
                    "No target command executed.",
                ]
            )
        eligibility = _run_execution_eligibility(item)
        report = eligibility["readiness"]
        readiness_status = "READY" if eligibility["eligible"] else "NOT READY"
        reasons = eligibility["reasons"] or ["All v1.5 read-only execution checks passed."]
        lines = [
            "Action Run Preview",
            f"id: {item.get('id')}",
            f"status: {item.get('status')}",
            f"execution_state: {_execution_state(item)}",
            f"readiness: {readiness_status}",
            f"stored_policy: {item.get('strictest_policy')}",
            f"current_policy: {report['current_policy']}",
            f"policy_summary: {report['policy_summary']}",
            "",
            "Reasons:",
        ]
        lines.extend(f"- {reason}" for reason in reasons)
        lines.extend(["", "Commands:"])
        if report["command_details"]:
            for detail in report["command_details"]:
                lines.append(
                    f"- {detail['command']} [policy={detail['policy']}, read_only={detail['read_only']}, "
                    f"mutates={detail['mutates']}, registered={detail['registered']}]"
                )
        else:
            lines.append("- none")
        lines.extend(["", "Required future safeguards:"])
        lines.extend(f"- {safeguard}" for safeguard in report["safeguards"])
        lines.extend(
            [
                "",
                "Readiness is advisory only; execution requires a separate explicit /action run command.",
                "No target command executed.",
            ]
        )
        return "\n".join(lines)

    def run(self, proposal_id: str, *, executor: ActionExecutor | None) -> str:
        proposal_id = proposal_id.strip()
        if not proposal_id:
            return "Usage: /action run <id>"
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _mutation_refused(state)
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        if _execution_state(item) == "executed":
            return "\n".join(
                [
                    "Action Run",
                    "Status: NOT RUN",
                    f"id: {proposal_id}",
                    "Reason: already executed",
                    f"Suggestion: /action run-receipt {proposal_id}",
                    "No target command executed.",
                ]
            )
        eligibility = _run_execution_eligibility(item)
        if executor is None:
            eligibility["reasons"].append("safe internal executor is unavailable")
            eligibility["eligible"] = False
        if not eligibility["eligible"]:
            lines = ["Action Run", "Status: NOT RUN", f"id: {proposal_id}", "Reasons:"]
            lines.extend(f"- {reason}" for reason in eligibility["reasons"])
            lines.append("No target command executed.")
            return "\n".join(lines)

        executed_at = _utc_now()
        run_id = _new_run_id(executed_at)
        receipt_commands: list[dict[str, Any]] = []
        rendered_outputs: list[str] = []
        warnings: list[str] = []
        commands = eligibility["commands"]
        for command in commands:
            success = True
            try:
                output = executor(command)
                if output is None:
                    raise RuntimeError("safe internal handler did not recognize the command")
                output_text = str(output)
            except Exception as exc:  # receipt must survive an internal read-only formatter failure
                success = False
                output_text = f"ERROR: {type(exc).__name__}: {exc}"
                warnings.append(f"{command}: {output_text}")
            spec = match_registered_command(command)
            receipt_commands.append(
                {
                    "command": command,
                    "matched_prefix": spec.prefix if spec else "",
                    "category": spec.category if spec else "unknown",
                    "description": spec.description if spec else "",
                    "risk": spec.risk if spec else "unknown",
                    "policy": classify_command(command).policy_class,
                    "read_only": spec.read_only if spec else False,
                    "mutates": spec.mutates if spec else "unknown",
                    "success": success,
                    "output_chars": len(output_text),
                    "output_preview": _receipt_preview(output_text),
                    "output_truncated": len(output_text) > 2000,
                }
            )
            rendered_outputs.extend([f"--- {command} ---", output_text])

        successful = sum(1 for record in receipt_commands if record["success"])
        run_receipt = {
            "version": 2,
            "run_id": run_id,
            "executed_at": executed_at,
            "executed_command_count": len(receipt_commands),
            "run_policy": "read_only_auto_allowed",
            "success": successful == len(receipt_commands),
            "commands": receipt_commands,
            "warnings": warnings,
        }
        receipt_hash = _receipt_hash(run_receipt)
        run_receipt["receipt_hash"] = receipt_hash
        summary = f"{successful}/{len(receipt_commands)} read-only commands completed"
        item.update(
            {
                "execution_state": "executed",
                "executed_at": executed_at,
                "run_id": run_id,
                "executed_command_count": len(receipt_commands),
                "run_policy": "read_only_auto_allowed",
                "run_result_summary": summary,
                "run_receipt": run_receipt,
                "target_execution_performed": True,
                "receipt_hash": receipt_hash,
                "no_execution": False,
                "updated_at": executed_at,
            }
        )
        self._write_records(state["records"])
        lines = [
            "Action Run",
            f"Status: {'RUN' if run_receipt['success'] else 'RUN WITH WARNINGS'}",
            f"id: {proposal_id}",
            f"executed_at: {executed_at}",
            f"run_id: {run_id}",
            f"executed_command_count: {len(receipt_commands)}",
            f"run_policy: {item['run_policy']}",
            f"result: {summary}",
            "target_execution_performed: True",
            f"receipt_hash: {receipt_hash}",
            "",
            "Target outputs:",
            *rendered_outputs,
            "",
            "Execution receipt stored in action_queue.jsonl.",
        ]
        if warnings:
            lines.extend(["Warnings:", *(f"- {warning}" for warning in warnings)])
        return "\n".join(lines)

    def format_run_receipt(self, proposal_id: str) -> str:
        proposal_id = proposal_id.strip()
        if not proposal_id:
            return "Usage: /action run-receipt <id>"
        state = self._read_state()
        if state["error"]:
            return f"Action Proposal Queue error: {state['error']}"
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        receipt = item.get("run_receipt") if isinstance(item.get("run_receipt"), dict) else None
        if _execution_state(item) != "executed" or receipt is None:
            return f"Action run receipt unavailable: proposal has not been executed: {proposal_id}"
        lines = [
            "Action Run Receipt",
            f"id: {item.get('id')}",
            f"status: {item.get('status')}",
            f"original_input: {item.get('original_input')}",
            f"execution_state: {_execution_state(item)}",
            f"run_id: {item.get('run_id') or receipt.get('run_id') or ''}",
            f"executed_at: {item.get('executed_at') or ''}",
            f"executed_command_count: {item.get('executed_command_count') if item.get('executed_command_count') is not None else receipt.get('executed_command_count', '')}",
            f"target_execution_performed: {item.get('target_execution_performed') is True}",
            f"no_execution: {item.get('no_execution')}",
            f"run_policy: {item.get('run_policy') or ''}",
            f"run_result_summary: {item.get('run_result_summary') or ''}",
            f"receipt_hash: {item.get('receipt_hash') or receipt.get('receipt_hash') or ''}",
            "commands:",
        ]
        command_receipts = receipt.get("commands") if isinstance(receipt.get("commands"), list) else []
        for record in command_receipts:
            if not isinstance(record, dict):
                continue
            lines.extend(
                [
                    f"- {record.get('command')}",
                    f"  policy: {record.get('policy')}",
                    f"  read_only: {record.get('read_only')}",
                    f"  mutates: {record.get('mutates')}",
                    f"  success: {record.get('success')}",
                    f"  output_chars: {record.get('output_chars')}",
                    f"  output_preview: {record.get('output_preview')}",
                ]
            )
        warnings = receipt.get("warnings") if isinstance(receipt.get("warnings"), list) else []
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
        if not warnings:
            lines.append("- none")
        lines.append("Receipt inspection is read-only; no target command executed.")
        return "\n".join(lines)

    def format_runs(self, *, limit: int | None = 20, include_all: bool = False) -> str:
        state = self._read_state()
        if state["error"]:
            return f"Action Execution Audit error: {state['error']}"
        executed = [item for item in state["records"] if _execution_state(item) == "executed"]
        executed.sort(key=lambda item: str(item.get("executed_at") or ""), reverse=True)
        shown = executed if include_all or limit is None else executed[:limit]
        lines = [
            "Action Runs" + (" (all)" if include_all else ""),
            f"executed_total: {len(executed)}",
            f"shown: {len(shown)}",
        ]
        if state["malformed_count"]:
            lines.append(f"malformed_records_skipped: {state['malformed_count']}")
        if not shown:
            lines.append("- none")
        for item in shown:
            receipt = item.get("run_receipt") if isinstance(item.get("run_receipt"), dict) else {}
            warnings = receipt.get("warnings") if isinstance(receipt.get("warnings"), list) else []
            success = receipt.get("success", "unknown")
            receipt_hash = str(item.get("receipt_hash") or receipt.get("receipt_hash") or "")
            command_count = item.get("executed_command_count")
            if command_count is None or (command_count == 0 and item.get("commands")):
                commands = item.get("commands") if isinstance(item.get("commands"), list) else []
                command_count = len(commands)
            lines.append(
                "- "
                f"{item.get('id', 'unknown')} run_id={item.get('run_id') or receipt.get('run_id') or 'legacy'} "
                f"executed_at={item.get('executed_at') or 'unknown'} commands={command_count} "
                f"success={success} hash={_short_hash(receipt_hash)} warnings={len(warnings)} "
                f"input={_preview(str(item.get('original_input') or ''))}"
            )
        lines.append("Read-only execution history; no target command executed.")
        return "\n".join(lines)

    def format_run_verify(self, proposal_id: str) -> str:
        proposal_id = proposal_id.strip()
        if not proposal_id:
            return "Usage: /action run-verify <id>"
        state = self._read_state()
        if state["error"]:
            return f"Action Execution Verify error: {state['error']}"
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        if _execution_state(item) != "executed":
            return "\n".join(
                [
                    "Action Run Verify",
                    "Status: ERROR",
                    f"id: {proposal_id}",
                    "- proposal is not executed",
                    "No target command executed.",
                ]
            )
        findings = _executed_record_findings(item)
        status = _verification_status(findings)
        receipt = item.get("run_receipt") if isinstance(item.get("run_receipt"), dict) else {}
        lines = [
            "Action Run Verify",
            f"Status: {status}",
            f"id: {proposal_id}",
            f"run_id: {item.get('run_id') or receipt.get('run_id') or ''}",
            f"executed_at: {item.get('executed_at') or ''}",
            f"executed_command_count: {item.get('executed_command_count') if item.get('executed_command_count') is not None else ''}",
            f"target_execution_performed: {item.get('target_execution_performed') is True}",
            f"no_execution: {item.get('no_execution')}",
            f"run_policy: {item.get('run_policy') or ''}",
            f"receipt_hash: {item.get('receipt_hash') or receipt.get('receipt_hash') or ''}",
            "Reasons:",
        ]
        if findings:
            lines.extend(f"- [{finding['severity']}] {finding['message']}" for finding in findings)
        else:
            lines.append("- [OK] Receipt fields, hash, command count, registry metadata, and current policy verified.")
        lines.append("No target command executed.")
        return "\n".join(lines)

    def format_run_audit(self) -> str:
        report = self.run_audit_report()
        lines = [
            "Action Execution Audit",
            f"Status: {report['status']}",
            f"Path: {self.queue_path}",
            "",
            "Summary:",
            f"- executed records: {report['executed_count']}",
            f"- receipt v2: {report['v2_count']}",
            f"- legacy receipts: {report['legacy_count']}",
            f"- missing receipts: {report['missing_receipt_count']}",
            f"- hash verified: {report['hash_verified_count']}",
            f"- hash mismatch: {report['hash_mismatch_count']}",
            f"- duplicate run_id groups: {report['duplicate_run_id_count']}",
            f"- current non-auto_allowed records: {report['non_auto_policy_count']}",
            f"- mutating command records: {report['mutating_command_count']}",
            f"- receipt warnings: {report['receipt_warning_count']}",
            "",
            "Findings:",
        ]
        if report["findings"]:
            lines.extend(f"- [{finding['severity']}] {finding['message']}" for finding in report["findings"])
        else:
            lines.append("- [OK] All execution receipts and current command policies verified.")
        lines.extend(["", "Mutation policy:", "- Read-only audit only; no queue or target stores were changed."])
        return "\n".join(lines)

    def run_audit_report(self) -> dict[str, Any]:
        state = self._read_state()
        executed = [item for item in state["records"] if _execution_state(item) == "executed"]
        findings: list[dict[str, str]] = []
        if state["error"]:
            findings.append({"severity": "ERROR", "message": f"Queue unreadable: {state['error']}"})
        if state["malformed_count"]:
            findings.append({"severity": "WARN", "message": f"Malformed JSONL records: {state['malformed_count']}"})
        v2_count = 0
        legacy_count = 0
        missing_receipt_count = 0
        hash_verified_count = 0
        hash_mismatch_count = 0
        non_auto_policy_count = 0
        mutating_record_ids: set[str] = set()
        receipt_warning_count = 0
        run_ids: list[str] = []
        for item in executed:
            item_id = str(item.get("id") or "unknown")
            receipt = item.get("run_receipt") if isinstance(item.get("run_receipt"), dict) else None
            if receipt is None:
                missing_receipt_count += 1
            else:
                try:
                    version = int(receipt.get("version") or 1)
                except (TypeError, ValueError):
                    version = 0
                if version >= 2:
                    v2_count += 1
                else:
                    legacy_count += 1
                warnings = receipt.get("warnings") if isinstance(receipt.get("warnings"), list) else []
                receipt_warning_count += len(warnings)
                stored_hash = str(item.get("receipt_hash") or receipt.get("receipt_hash") or "")
                if stored_hash:
                    if stored_hash == _receipt_hash(receipt):
                        hash_verified_count += 1
                    else:
                        hash_mismatch_count += 1
            run_id = str(item.get("run_id") or (receipt or {}).get("run_id") or "")
            if run_id:
                run_ids.append(run_id)
            commands = item.get("commands") if isinstance(item.get("commands"), list) else []
            current = classify_command_bundle(commands)["policy_class"] if commands else "blocked"
            if current != "auto_allowed":
                non_auto_policy_count += 1
            for command in commands:
                spec = match_registered_command(command) if isinstance(command, str) else None
                if spec is None or spec.read_only is not True or spec.mutates != "none":
                    mutating_record_ids.add(item_id)
            for finding in _executed_record_findings(item):
                findings.append({"severity": finding["severity"], "message": f"{item_id}: {finding['message']}"})
        duplicate_run_ids = sorted(run_id for run_id, count in Counter(run_ids).items() if count > 1)
        if duplicate_run_ids:
            findings.append({"severity": "ERROR", "message": f"Duplicate run_id values: {', '.join(duplicate_run_ids)}"})
        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if findings else "OK"
        return {
            "status": status,
            "executed_count": len(executed),
            "v2_count": v2_count,
            "legacy_count": legacy_count,
            "missing_receipt_count": missing_receipt_count,
            "hash_verified_count": hash_verified_count,
            "hash_mismatch_count": hash_mismatch_count,
            "duplicate_run_id_count": len(duplicate_run_ids),
            "non_auto_policy_count": non_auto_policy_count,
            "mutating_command_count": len(mutating_record_ids),
            "receipt_warning_count": receipt_warning_count,
            "findings": findings,
        }

    def format_readiness_doctor(self) -> str:
        report = self.readiness_doctor_report()
        lines = [
            "Action Run Readiness Doctor",
            f"Status: {report['status']}",
            f"Path: {self.queue_path}",
            "",
            "Summary:",
            f"- total records: {report['total_records']}",
            f"- confirmed records: {report['confirmed_count']}",
            f"- ready confirmed records: {report['ready_count']}",
            f"- executed records: {report['executed_count']}",
            f"- approved but unconfirmed: {report['approved_unconfirmed_count']}",
            f"- old proposed records: {report['old_proposed_count']}",
            f"- malformed records: {report['malformed_count']}",
            "",
            "Findings:",
        ]
        if report["findings"]:
            lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        else:
            lines.append("- [OK] Confirmed proposals satisfy current readiness invariants.")
        lines.extend(
            [
                "",
                "Future execution:",
                "- v1.5 run support is limited to explicit confirmed read-only auto_allowed proposals.",
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; action queue and target stores were not changed.",
            ]
        )
        return "\n".join(lines)

    def readiness_doctor_report(self) -> dict[str, Any]:
        state = self._read_state()
        records = state["records"]
        findings: list[dict[str, str]] = []
        if state["error"]:
            findings.append({"severity": "ERROR", "message": f"Queue unreadable: {state['error']}"})
        if state["malformed_count"]:
            findings.append({"severity": "WARN", "message": f"Malformed JSONL records: {state['malformed_count']}"})
        confirmed = [item for item in records if _execution_state(item) == "confirmed"]
        executed = [item for item in records if _execution_state(item) == "executed"]
        ready_count = 0
        for item in confirmed:
            eligibility = _run_execution_eligibility(item)
            if eligibility["eligible"]:
                ready_count += 1
                continue
            item_id = str(item.get("id") or "unknown")
            for reason in eligibility["reasons"]:
                severity = "ERROR" if _severe_readiness_reason(reason) else "WARN"
                findings.append({"severity": severity, "message": f"{item_id}: {reason}"})
        for item in executed:
            item_id = str(item.get("id") or "unknown")
            for finding in _executed_record_findings(item):
                findings.append({"severity": finding["severity"], "message": f"{item_id}: {finding['message']}"})
        approved_unconfirmed = [
            item for item in records if item.get("status") == "approved" and _execution_state(item) == "unconfirmed"
        ]
        if approved_unconfirmed:
            findings.append(
                {
                    "severity": "WARN",
                    "message": f"Approved but unconfirmed proposals: {len(approved_unconfirmed)}",
                }
            )
        now = datetime.now(UTC)
        old_proposed = [
            item
            for item in records
            if item.get("status") == "proposed" and _is_older_than(str(item.get("created_at") or ""), now, days=30)
        ]
        if old_proposed:
            findings.append({"severity": "WARN", "message": f"Old proposed records: {len(old_proposed)}"})
        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if findings else "OK"
        return {
            "status": status,
            "total_records": len(records),
            "confirmed_count": len(confirmed),
            "ready_count": ready_count,
            "executed_count": len(executed),
            "approved_unconfirmed_count": len(approved_unconfirmed),
            "old_proposed_count": len(old_proposed),
            "malformed_count": state["malformed_count"],
            "findings": findings,
        }

    def confirm(self, proposal_id: str, token: str) -> str:
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _mutation_refused(state)
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        eligible, reason = _confirmation_eligibility(item)
        if not eligible:
            return "\n".join([f"Action confirmation refused: {reason}", "No target command executed."])
        expected = _confirmation_token(item)
        if token.strip() != expected:
            return "\n".join(["Action confirmation refused: token mismatch.", "No target command executed."])
        if _execution_state(item) == "confirmed":
            return "\n".join([f"Action proposal already confirmed: {proposal_id}", "No target command executed."])
        now = _utc_now()
        item.update(
            {
                "execution_state": "confirmed",
                "confirmed_at": now,
                "unconfirmed_at": None,
                "confirmation_method": "explicit_token",
                "confirmation_token_used": expected,
                "unconfirmed_reason": "",
                "updated_at": now,
                "no_execution": True,
            }
        )
        self._write_records(state["records"])
        return "\n".join(
            [
                "Action proposal confirmed:",
                f"  id: {proposal_id}",
                "  execution_state: confirmed",
                f"  confirmed_at: {now}",
                "Confirmation recorded in action_queue.jsonl only.",
                "No target command executed.",
            ]
        )

    def unconfirm(self, proposal_id: str, *, reason: str = "") -> str:
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _mutation_refused(state)
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        if _execution_state(item) != "confirmed":
            return "\n".join([f"Action unconfirm refused: proposal is not confirmed: {proposal_id}", "No target command executed."])
        now = _utc_now()
        item.update(
            {
                "execution_state": "unconfirmed",
                "unconfirmed_at": now,
                "confirmation_method": "",
                "confirmation_token_used": "",
                "unconfirmed_reason": _strip_quotes(reason.strip()),
                "updated_at": now,
                "no_execution": True,
            }
        )
        self._write_records(state["records"])
        lines = [
            "Action proposal unconfirmed:",
            f"  id: {proposal_id}",
            "  execution_state: unconfirmed",
            f"  unconfirmed_at: {now}",
        ]
        if item["unconfirmed_reason"]:
            lines.append(f"  reason: {item['unconfirmed_reason']}")
        lines.extend(["Queue metadata only was changed.", "No target command executed."])
        return "\n".join(lines)

    def set_status(self, proposal_id: str, status: str, *, reason: str = "") -> str:
        proposal_id = proposal_id.strip()
        if not proposal_id:
            return f"Usage: /action {status_to_command(status)} <id>" + (" [reason]" if status == "rejected" else "")
        state = self._read_state()
        if state["error"] or state["malformed_count"]:
            return _mutation_refused(state)
        item = _find_by_id(state["records"], proposal_id)
        if not item:
            return f"Action proposal not found: {proposal_id}"
        if item.get("status") == "archived" and status != "archived":
            return f"Archived action proposal cannot change status: {proposal_id}"
        now = _utc_now()
        item["status"] = status
        item["updated_at"] = now
        if status == "approved":
            item["approved_at"] = now
        elif status == "rejected":
            item["rejected_at"] = now
            item["reason"] = _strip_quotes(reason.strip())
        elif status == "archived":
            item["archived_at"] = now
        self._write_records(state["records"])
        lines = [
            f"Action proposal {status}:",
            f"  id: {proposal_id}",
            f"  strictest_policy: {item.get('strictest_policy', 'unknown')}",
        ]
        if reason and status == "rejected":
            lines.append(f"  reason: {item.get('reason')}")
        if status == "approved" and item.get("strictest_policy") in {"operator_only", "blocked"}:
            lines.append("  warning: approval is recordkeeping only; this proposal is not executable under current policy.")
        lines.append("No target command executed.")
        return "\n".join(lines)

    def format_doctor(self) -> str:
        report = self.doctor_report()
        lines = [
            "Action Proposal Queue Doctor",
            f"Status: {report['status']}",
            f"Path: {self.queue_path}",
            "",
            "Summary:",
            f"- exists: {report['exists']}",
            f"- readable: {report['readable']}",
            f"- total records: {report['total_records']}",
            f"- malformed records: {report['malformed_count']}",
            f"- status counts: {_format_counter(report['status_counts'])}",
            "",
            "Findings:",
        ]
        if report["findings"]:
            lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
        else:
            lines.append("- [OK] Action proposal lifecycle, confirmation, and execution receipt invariants are healthy.")
        lines.extend(
            [
                "",
                "Execution audit:",
                "- Use /action run-audit for receipt hashes, run ids, policy drift, and execution history checks.",
                "",
                "Mutation policy:",
                "- Read-only diagnostics only; queue and target stores were not changed.",
            ]
        )
        return "\n".join(lines)

    def doctor_report(self) -> dict[str, Any]:
        state = self._read_state()
        findings: list[dict[str, str]] = []
        records = state["records"]
        if state["error"]:
            findings.append({"severity": "ERROR", "message": f"Queue unreadable: {state['error']}"})
        if state["malformed_count"]:
            findings.append({"severity": "WARN", "message": f"Malformed JSONL records: {state['malformed_count']}"})
        ids = [str(item.get("id") or "") for item in records if item.get("id")]
        duplicates = sorted(item_id for item_id, count in Counter(ids).items() if count > 1)
        if duplicates:
            findings.append({"severity": "WARN", "message": f"Duplicate proposal ids: {', '.join(duplicates)}"})
        now = datetime.now(UTC)
        for index, item in enumerate(records, start=1):
            item_id = str(item.get("id") or f"record#{index}")
            missing = sorted(field for field in REQUIRED_ACTION_FIELDS if field not in item)
            if missing:
                findings.append({"severity": "WARN", "message": f"{item_id} missing required fields: {', '.join(missing)}"})
            if item.get("status") not in VALID_ACTION_STATUSES:
                findings.append({"severity": "WARN", "message": f"{item_id} has invalid status: {item.get('status')}"})
            if item.get("input_type") not in VALID_INPUT_TYPES:
                findings.append({"severity": "WARN", "message": f"{item_id} has invalid input_type: {item.get('input_type')}"})
            if item.get("resolved_target") not in VALID_RESOLVED_TARGETS:
                findings.append({"severity": "WARN", "message": f"{item_id} has invalid resolved_target: {item.get('resolved_target')}"})
            if item.get("strictest_policy") not in VALID_POLICY_CLASSES:
                findings.append({"severity": "WARN", "message": f"{item_id} has invalid policy: {item.get('strictest_policy')}"})
            execution_state = _execution_state(item)
            if item.get("execution_state") is not None and execution_state not in VALID_EXECUTION_STATES:
                findings.append({"severity": "WARN", "message": f"{item_id} has invalid execution_state: {item.get('execution_state')}"})
            if execution_state == "executed":
                for finding in _executed_record_findings(item):
                    findings.append({"severity": finding["severity"], "message": f"{item_id}: {finding['message']}"})
            elif item.get("no_execution") is not True:
                findings.append({"severity": "ERROR", "message": f"{item_id} has no_execution=false without executed state"})
            if item.get("target_execution_performed") is True and execution_state != "executed":
                findings.append({"severity": "ERROR", "message": f"{item_id} performed target execution without executed state"})
            receipt_fields = sorted(field for field in LEGACY_EXECUTION_RECEIPT_FIELDS if field in item)
            if execution_state != "executed":
                receipt_fields.extend(
                    field
                    for field in ("executed_at", "run_policy", "run_result_summary", "run_receipt")
                    if item.get(field)
                )
                receipt_fields = sorted(set(receipt_fields))
            if receipt_fields:
                findings.append({"severity": "ERROR", "message": f"{item_id} contains forbidden execution receipt fields: {', '.join(receipt_fields)}"})
            if item.get("status") == "approved" and item.get("strictest_policy") == "blocked":
                findings.append({"severity": "WARN", "message": f"Approved blocked proposal requires manual review: {item_id}"})
            if item.get("status") == "proposed" and _is_older_than(str(item.get("created_at") or ""), now, days=30):
                findings.append({"severity": "WARN", "message": f"Old proposed item: {item_id}"})
            commands = item.get("commands") if isinstance(item.get("commands"), list) else []
            for command in commands:
                if not isinstance(command, str) or match_registered_command(command) is None:
                    findings.append({"severity": "WARN", "message": f"{item_id} command missing from registry: {command}"})
            current_policy = classify_command_bundle(commands)["policy_class"] if commands else "blocked"
            if execution_state == "confirmed":
                if item.get("status") != "approved":
                    findings.append({"severity": "ERROR", "message": f"Confirmed proposal is not approved: {item_id}"})
                if item.get("no_execution") is not True:
                    findings.append({"severity": "ERROR", "message": f"Confirmed proposal lost no_execution=true: {item_id}"})
                if item.get("strictest_policy") in {"operator_only", "blocked"} or current_policy in {"operator_only", "blocked"}:
                    findings.append({"severity": "ERROR", "message": f"Confirmed proposal has non-confirmable policy: {item_id}"})
                missing_confirmation = [
                    field
                    for field in ("confirmed_at", "confirmation_method", "confirmation_token_used")
                    if not item.get(field)
                ]
                if missing_confirmation:
                    findings.append(
                        {
                            "severity": "WARN",
                            "message": f"{item_id} missing confirmation metadata: {', '.join(missing_confirmation)}",
                        }
                    )
            if item.get("strictest_policy") in VALID_POLICY_CLASSES and item.get("strictest_policy") != current_policy:
                findings.append(
                    {
                        "severity": "WARN",
                        "message": f"{item_id} policy mismatch: stored={item.get('strictest_policy')} current={current_policy}",
                    }
                )
        status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if findings else "OK"
        return {
            "status": status,
            "exists": self.queue_path.exists(),
            "readable": not bool(state["error"]),
            "total_records": len(records),
            "malformed_count": state["malformed_count"],
            "status_counts": Counter(str(item.get("status") or "missing") for item in records),
            "findings": findings,
        }

    def _read_state(self) -> dict[str, Any]:
        state = {"records": [], "malformed_count": 0, "error": ""}
        if not self.queue_path.exists():
            return state
        try:
            lines = self.queue_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            state["error"] = str(exc)
            return state
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                state["malformed_count"] += 1
                continue
            if isinstance(record, dict):
                state["records"].append(record)
            else:
                state["malformed_count"] += 1
        return state

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
        temp_path = self.queue_path.with_name(f".{self.queue_path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(self.queue_path)


def _parse_id_reason(command: str, prefix: str) -> dict[str, str] | str:
    remainder = command[len(prefix) :].strip()
    if not remainder:
        return f"Usage: {prefix} <id> [reason]"
    parts = remainder.split(maxsplit=1)
    return {"id": parts[0], "reason": parts[1] if len(parts) > 1 else ""}


def _parse_runs_options(command: str) -> dict[str, Any] | str:
    remainder = command[len("/action runs") :].strip()
    if not remainder:
        return {"limit": 20, "include_all": False}
    parts = remainder.split()
    if parts == ["--all"]:
        return {"limit": None, "include_all": True}
    if len(parts) == 2 and parts[0] == "--last":
        try:
            limit = int(parts[1])
        except ValueError:
            return "Invalid --last value. Usage: /action runs [--all|--last N]"
        if limit <= 0:
            return "--last must be greater than 0."
        return {"limit": limit, "include_all": False}
    return "Usage: /action runs [--all|--last N]"


def _parse_id_token(command: str) -> dict[str, str] | str:
    remainder = command[len("/action confirm") :].strip()
    parts = remainder.split()
    if len(parts) != 2:
        return "Usage: /action confirm <id> <token>"
    return {"id": parts[0], "token": parts[1]}


def _new_action_id(timestamp: str) -> str:
    stamp = datetime.fromisoformat(timestamp).strftime("%Y%m%d%H%M%S")
    return f"act_{stamp}_{uuid4().hex[:4]}"


def _new_run_id(timestamp: str) -> str:
    stamp = datetime.fromisoformat(timestamp).strftime("%Y%m%d%H%M%S")
    return f"run_{stamp}_{uuid4().hex[:6]}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _find_by_id(records: list[dict[str, Any]], proposal_id: str) -> dict[str, Any] | None:
    return next((item for item in records if item.get("id") == proposal_id), None)


def _preview(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def _short_hash(value: str) -> str:
    return value[:12] if value else "missing"


def _verification_status(findings: list[dict[str, str]]) -> str:
    if any(item["severity"] == "ERROR" for item in findings):
        return "ERROR"
    if findings:
        return "WARN"
    return "VERIFIED"


def _approval_guidance(policy: str) -> str:
    if policy == "auto_allowed":
        return "approval_guidance: advisory-safe, but this queue still cannot execute it."
    if policy == "confirmation_required":
        return "approval_guidance: explicit confirmation would be required by a future execution layer."
    if policy == "operator_only":
        return "approval_guidance: operator-only; approval here is recordkeeping only."
    return "approval_guidance: blocked; approval here cannot make it executable."


def _execution_state(item: dict[str, Any]) -> str:
    return str(item.get("execution_state") or "unconfirmed")


def _execution_state_counts(records: list[dict[str, Any]]) -> Counter[str]:
    return Counter(_execution_state(item) for item in records)


def _confirmation_eligibility(item: dict[str, Any]) -> tuple[bool, str]:
    if item.get("status") != "approved":
        return False, "proposal status must be approved"
    if item.get("no_execution") is not True:
        return False, "proposal violates no_execution=true invariant"
    policy = str(item.get("strictest_policy") or "blocked")
    if policy in {"operator_only", "blocked"}:
        return False, f"policy {policy} is not confirmable for execution"
    if policy not in {"auto_allowed", "confirmation_required"}:
        return False, f"unknown policy {policy} is not confirmable"
    commands = item.get("commands") if isinstance(item.get("commands"), list) else []
    if not commands:
        return False, "proposal has no resolved commands"
    if any(not isinstance(command, str) or match_registered_command(command) is None for command in commands):
        return False, "one or more commands are missing from Command Registry"
    current_policy = classify_command_bundle(commands)["policy_class"]
    if current_policy != policy:
        return False, f"policy changed since proposal: stored={policy}, current={current_policy}"
    if current_policy in {"operator_only", "blocked"}:
        return False, f"current policy {current_policy} is not confirmable"
    return True, f"approved proposal with {current_policy} policy is eligible for metadata-only confirmation"


def _confirmation_token(item: dict[str, Any]) -> str:
    material = json.dumps(
        {
            "id": item.get("id"),
            "approved_at": item.get("approved_at"),
            "commands": item.get("commands"),
            "strictest_policy": item.get("strictest_policy"),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:8].upper()
    short_id = str(item.get("id") or "UNKNOWN").rsplit("_", maxsplit=1)[-1].upper()
    return f"CONFIRM-ACTION-{short_id}-{digest}"


def _run_readiness(item: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    safeguards = [
        "Revalidate queue status, confirmation state, registry metadata, and policy immediately before any future run.",
        "Write an immutable execution receipt with command, timestamps, outcome, and error details.",
        "Keep execution explicit and operator-visible; do not dispatch shell or arbitrary commands.",
    ]
    if item.get("status") != "approved":
        reasons.append("proposal status is not approved")
    if _execution_state(item) != "confirmed":
        reasons.append("execution_state is not confirmed")
    if item.get("no_execution") is not True:
        reasons.append("no_execution must remain true before a future run engine takes control")
    stored_policy = str(item.get("strictest_policy") or "blocked")
    if stored_policy in {"blocked", "operator_only"}:
        reasons.append(f"stored policy {stored_policy} is not eligible for future execution")
    elif stored_policy not in {"auto_allowed", "confirmation_required"}:
        reasons.append(f"stored policy is invalid: {stored_policy}")

    commands = item.get("commands") if isinstance(item.get("commands"), list) else []
    command_details: list[dict[str, Any]] = []
    if not commands:
        reasons.append("command bundle is empty")
    mutating_targets: set[str] = set()
    for index, command in enumerate(commands, start=1):
        if not isinstance(command, str):
            reasons.append(f"command {index} is not a string")
            command_details.append(
                {"command": repr(command), "policy": "blocked", "read_only": "unknown", "mutates": "unknown", "registered": False}
            )
            continue
        spec = match_registered_command(command)
        decision = classify_command(command)
        command_details.append(
            {
                "command": command,
                "policy": decision.policy_class,
                "read_only": spec.read_only if spec else "unknown",
                "mutates": spec.mutates if spec else "unknown",
                "registered": spec is not None,
            }
        )
        if spec is None:
            reasons.append(f"command is not registered: {command}")
        if decision.policy_class in {"blocked", "operator_only"}:
            reasons.append(f"command is {decision.policy_class} under current policy: {command}")
        if spec is not None and (not spec.read_only or spec.mutates != "none"):
            mutating_targets.add(spec.mutates)

    bundle = classify_command_bundle(commands)
    current_policy = str(bundle["policy_class"])
    if current_policy != stored_policy:
        reasons.append(f"policy drift detected: stored={stored_policy}, current={current_policy}")
    if current_policy in {"blocked", "operator_only"} and not any(
        "current policy" in reason or "under current policy" in reason for reason in reasons
    ):
        reasons.append(f"current policy {current_policy} is not eligible for future execution")

    if mutating_targets:
        targets = ", ".join(sorted(mutating_targets))
        safeguards.append(f"Future mutation receipt is required for target store(s): {targets}.")
        safeguards.append("Capture rollback or undo metadata before mutation where the target command supports it.")
        if mutating_targets.intersection({"context", "memory", "skills"}):
            safeguards.append("Context/memory/skills mutations require target record identifiers and rollback guidance in the receipt.")
    ready = not reasons
    display_reasons = reasons or ["All current readiness checks passed; this is still not execution authorization."]
    return {
        "ready": ready,
        "status": "READY" if ready else "NOT READY",
        "reasons": display_reasons,
        "commands": commands,
        "command_details": command_details,
        "stored_policy": stored_policy,
        "current_policy": current_policy,
        "policy_summary": str(bundle["reason"]),
        "safeguards": safeguards,
    }


def _run_execution_eligibility(item: dict[str, Any]) -> dict[str, Any]:
    readiness = _run_readiness(item)
    if _execution_state(item) == "executed":
        return {
            "eligible": False,
            "reasons": ["already executed"],
            "commands": list(readiness["commands"]),
            "readiness": readiness,
        }
    reasons = [] if readiness["ready"] else list(readiness["reasons"])
    stored_policy = str(item.get("strictest_policy") or "blocked")
    if stored_policy != "auto_allowed":
        reasons.append(f"run requires stored policy auto_allowed, got {stored_policy}")
    if readiness["current_policy"] != "auto_allowed":
        reasons.append(f"run requires current policy auto_allowed, got {readiness['current_policy']}")
    for detail in readiness["command_details"]:
        command = detail["command"]
        if detail["registered"] is not True:
            reasons.append(f"run command is not registered: {command}")
        if detail["policy"] != "auto_allowed":
            reasons.append(f"run command is not auto_allowed: {command} ({detail['policy']})")
        if detail["read_only"] is not True:
            reasons.append(f"run command is not read-only: {command}")
        if detail["mutates"] != "none":
            reasons.append(f"run command declares mutation target {detail['mutates']}: {command}")
    return {
        "eligible": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "commands": list(readiness["commands"]),
        "readiness": readiness,
    }


def _executed_record_findings(item: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def add(message: str, severity: str = "ERROR") -> None:
        findings.append({"severity": severity, "message": message})

    if _execution_state(item) != "executed":
        add("execution receipt exists without execution_state=executed")
    if item.get("status") not in {"approved", "archived"}:
        add("executed record must remain approved or archived")
    if item.get("target_execution_performed") is not True:
        add("executed record is missing target_execution_performed=true")
    if item.get("no_execution") is not False:
        add("executed record must have no_execution=false")
    if item.get("strictest_policy") != "auto_allowed":
        add(f"executed record policy is not auto_allowed: {item.get('strictest_policy')}")
    if item.get("run_policy") != "read_only_auto_allowed":
        add(f"executed record has invalid run_policy: {item.get('run_policy')}")
    if not item.get("executed_at"):
        add("executed record is missing executed_at")
    receipt = item.get("run_receipt") if isinstance(item.get("run_receipt"), dict) else None
    if receipt is None:
        add("executed record is missing run_receipt")
    commands = item.get("commands") if isinstance(item.get("commands"), list) else []
    if not commands:
        add("executed record has no commands")
    for command in commands:
        if not isinstance(command, str):
            add(f"executed record contains non-string command: {command!r}")
            continue
        spec = match_registered_command(command)
        decision = classify_command(command)
        if spec is None:
            add(f"executed command is missing from registry: {command}")
            continue
        if decision.policy_class != "auto_allowed":
            add(f"executed command is not auto_allowed: {command} ({decision.policy_class})")
        if spec.read_only is not True:
            add(f"executed command is not read-only: {command}")
        if spec.mutates != "none":
            add(f"executed command declares mutation target {spec.mutates}: {command}")
    if receipt is not None:
        try:
            receipt_version = int(receipt.get("version") or 1)
        except (TypeError, ValueError):
            receipt_version = 0
            add(f"run_receipt has invalid version: {receipt.get('version')}")
        legacy_severity = "WARN" if receipt_version < 2 else "ERROR"
        receipt_commands = receipt.get("commands") if isinstance(receipt.get("commands"), list) else []
        recorded_commands = [entry.get("command") for entry in receipt_commands if isinstance(entry, dict)]
        if recorded_commands != commands:
            add("run_receipt commands do not match proposal commands")
        run_id = str(item.get("run_id") or receipt.get("run_id") or "")
        if not run_id:
            add("executed record is missing run_id", legacy_severity)
        elif item.get("run_id") and receipt.get("run_id") and item.get("run_id") != receipt.get("run_id"):
            add("top-level run_id does not match run_receipt run_id")
        executed_count = item.get("executed_command_count")
        if executed_count is None or (receipt_version < 2 and executed_count == 0 and commands):
            add("executed record is missing executed_command_count", legacy_severity)
        elif executed_count != len(commands):
            add(f"executed_command_count mismatch: stored={executed_count}, commands={len(commands)}")
        receipt_count = receipt.get("executed_command_count")
        if receipt_count is None:
            add("run_receipt is missing executed_command_count", legacy_severity)
        elif receipt_count != len(commands):
            add(f"run_receipt command count mismatch: stored={receipt_count}, commands={len(commands)}")
        metadata_fields = {
            "command",
            "matched_prefix",
            "category",
            "description",
            "risk",
            "policy",
            "read_only",
            "mutates",
            "success",
            "output_chars",
            "output_preview",
            "output_truncated",
        }
        for index, command_receipt in enumerate(receipt_commands, start=1):
            if not isinstance(command_receipt, dict):
                add(f"run_receipt command #{index} is not an object")
                continue
            missing_metadata = sorted(metadata_fields - set(command_receipt))
            if missing_metadata:
                add(
                    f"run_receipt command #{index} missing metadata: {', '.join(missing_metadata)}",
                    legacy_severity,
                )
        stored_hash = str(item.get("receipt_hash") or receipt.get("receipt_hash") or "")
        if not stored_hash:
            add("executed record is missing receipt_hash", legacy_severity)
        else:
            if item.get("receipt_hash") and receipt.get("receipt_hash") and item.get("receipt_hash") != receipt.get("receipt_hash"):
                add("top-level receipt_hash does not match run_receipt receipt_hash")
            expected_hash = _receipt_hash(receipt)
            if stored_hash != expected_hash:
                add("receipt_hash does not match canonical run_receipt JSON")
    if _run_execution_eligibility(item)["eligible"]:
        add("executed record remains runnable despite run-once guard")
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for finding in findings:
        key = (finding["severity"], finding["message"])
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def _receipt_preview(output: str, limit: int = 2000) -> str:
    compact = " ".join(output.split())
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def _receipt_hash(receipt: dict[str, Any]) -> str:
    canonical = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _severe_readiness_reason(reason: str) -> bool:
    severe_prefixes = (
        "proposal status",
        "execution_state",
        "no_execution",
        "stored policy",
        "stored policy is invalid",
        "current policy",
        "command bundle is empty",
        "command is not registered",
        "command is blocked",
        "command is operator_only",
        "command 1 is not",
    )
    return reason.startswith(severe_prefixes)


def _mutation_refused(state: dict[str, Any]) -> str:
    if state["error"]:
        return f"Action Proposal Queue mutation refused: storage error: {state['error']}"
    return f"Action Proposal Queue mutation refused: malformed entries present: {state['malformed_count']}"


def _is_older_than(value: str, now: datetime, *, days: int) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed < now - timedelta(days=days)


def _format_counter(counter: Counter[str]) -> str:
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter)) or "none"


def _oldest_proposed_age(records: list[dict[str, Any]]) -> str:
    created: list[datetime] = []
    for item in records:
        if item.get("status") != "proposed":
            continue
        parsed = _parse_timestamp(str(item.get("created_at") or ""))
        if parsed is not None:
            created.append(parsed)
    if not created:
        return "none"
    age = max(datetime.now(UTC) - min(created), timedelta())
    if age.days:
        return f"{age.days}d"
    hours = int(age.total_seconds() // 3600)
    return f"{hours}h"


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _export_record(item: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "status",
        "original_input",
        "input_type",
        "resolved_target",
        "commands",
        "strictest_policy",
        "no_execution",
        "created_at",
        "updated_at",
        "approved_at",
        "rejected_at",
        "archived_at",
        "execution_state",
        "confirmed_at",
        "unconfirmed_at",
        "confirmation_method",
        "confirmation_token_used",
        "unconfirmed_reason",
        "executed_at",
        "run_id",
        "executed_command_count",
        "run_policy",
        "run_result_summary",
        "run_receipt",
        "target_execution_performed",
        "receipt_hash",
        "reason",
        "rationale",
    )
    return {field: item.get(field) for field in fields}


def _format_export_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Proto-Mind Action Proposal Queue Export",
        "",
        f"Generated: {payload['generated_at']}",
        f"Source: `{payload['source_queue_path']}`",
        f"Total records: {payload['total_records']}",
        "",
        "## Summary",
        "",
        f"- Status counts: {_format_mapping(payload['counts_by_status'])}",
        f"- Policy counts: {_format_mapping(payload['counts_by_strictest_policy'])}",
        "- Safety: records only; no target commands were executed.",
        "",
        "## Records",
        "",
    ]
    records = payload["records"]
    if not records:
        lines.append("No action proposals.")
    for item in records:
        lines.extend(
            [
                f"### {item.get('id') or 'unknown'}",
                "",
                f"- Status: {item.get('status')}",
                f"- Input: {_markdown_inline(str(item.get('original_input') or ''))}",
                f"- Input type: {item.get('input_type')}",
                f"- Resolved target: {item.get('resolved_target')}",
                f"- Strictest policy: {item.get('strictest_policy')}",
                f"- Execution state: {item.get('execution_state') or 'unconfirmed'}",
                f"- Confirmed: {item.get('confirmed_at') or ''}",
                f"- Unconfirmed: {item.get('unconfirmed_at') or ''}",
                f"- Confirmation method: {item.get('confirmation_method') or ''}",
                f"- Executed: {item.get('executed_at') or ''}",
                f"- Run id: {item.get('run_id') or ''}",
                f"- Executed command count: {item.get('executed_command_count') if item.get('executed_command_count') is not None else ''}",
                f"- Run policy: {item.get('run_policy') or ''}",
                f"- Run result: {item.get('run_result_summary') or ''}",
                f"- Target execution performed: {item.get('target_execution_performed') is True}",
                f"- Receipt hash: {item.get('receipt_hash') or ''}",
                f"- No execution: {item.get('no_execution')}",
                f"- Created: {item.get('created_at')}",
                f"- Updated: {item.get('updated_at')}",
                "- Commands:",
            ]
        )
        commands = item.get("commands") if isinstance(item.get("commands"), list) else []
        lines.extend(f"  - `{_markdown_inline(str(command))}`" for command in commands)
        if not commands:
            lines.append("  - none")
        receipt = item.get("run_receipt") if isinstance(item.get("run_receipt"), dict) else None
        if receipt is not None:
            lines.append("- Run receipt outputs:")
            receipt_commands = receipt.get("commands") if isinstance(receipt.get("commands"), list) else []
            for record in receipt_commands:
                if isinstance(record, dict):
                    lines.append(
                        f"  - `{_markdown_inline(str(record.get('command') or ''))}`: "
                        f"success={record.get('success')} preview={_markdown_inline(str(record.get('output_preview') or ''))}"
                    )
            warnings = receipt.get("warnings") if isinstance(receipt.get("warnings"), list) else []
            if warnings:
                lines.append(f"- Run warnings: {_markdown_inline('; '.join(str(item) for item in warnings))}")
        lines.append("")
    lines.extend(
        [
            "## Safety",
            "",
            "This export is an operator-review record. Creating it did not execute, authorize, or apply any target command.",
            "",
        ]
    )
    return "\n".join(lines)


def _format_mapping(values: dict[str, Any]) -> str:
    return ", ".join(f"{key}={values[key]}" for key in sorted(values)) or "none"


def _markdown_inline(value: str) -> str:
    return " ".join(value.split()).replace("`", "\\`")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def status_to_command(status: str) -> str:
    return {"approved": "approve", "rejected": "reject", "archived": "archive"}.get(status, status)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] in {'"', "'", "“", "«"} and value[-1] in {'"', "'", "”", "»"}:
        return value[1:-1].strip()
    return value
