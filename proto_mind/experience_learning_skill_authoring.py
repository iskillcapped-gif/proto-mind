from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import shlex
from threading import RLock
from typing import Any

from proto_mind.experience_learning_skill_contract import (
    PROCEDURAL_SKILL_CONTRACT_SCHEMA,
    PROCEDURAL_SKILL_STORAGE_SCHEMA,
    ProceduralSkillContractBuilder,
    ProceduralSkillContractError,
)
from proto_mind.models import utc_now_iso


PROCEDURAL_SKILL_AUTHORING_VERSION = 1
PROCEDURAL_SKILL_AUTHORING_MODE = "exact_operator_authored_process_memory_receipt"
PROCEDURAL_SKILL_AUTHORING_MAX_RECEIPTS = 16
PROCEDURAL_SKILL_WRITER_INSTALLED = False
PROCEDURAL_SKILL_EXECUTION_INSTALLED = False

_SINGLE_FLAGS = {"--name": "name", "--summary": "summary", "--trigger": "trigger"}
_REPEATED_FLAGS = {
    "--precondition": "preconditions",
    "--step": "steps",
    "--permission": "permissions",
    "--verify": "verification",
    "--failure": "known_failure_modes",
}
_REQUIRED_FIELDS = (
    "trigger",
    "preconditions",
    "steps",
    "permissions",
    "verification",
    "known_failure_modes",
)
_LIST_LIMITS = {
    "preconditions": 8,
    "steps": 16,
    "permissions": 8,
    "verification": 8,
    "known_failure_modes": 8,
}
_MAX_COMMAND_CHARS = 12_000
_MAX_ITEM_CHARS = 800
_MAX_AUTHORED_CHARS = 8_000


@dataclass(frozen=True)
class ProceduralSkillAuthoringRequest:
    memory_id: str
    name: str
    summary: str
    trigger: str
    preconditions: list[str]
    steps: list[str]
    permissions: list[str]
    verification: list[str]
    known_failure_modes: list[str]


@dataclass(frozen=True)
class ProceduralSkillAuthoringBlueprint:
    source_lesson_id: str
    source_provenance_id: str
    source_apply_id: str
    source_record_hash: str
    base_contract_id: str
    base_contract_hash: str
    contract_schema: str
    storage_schema: str
    authored_contract: dict[str, Any]
    storage_projection: dict[str, Any]
    authoring_hash: str
    authoring_fields_complete: bool = True
    operator_authored: bool = True
    executable: bool = False
    promotion_allowed: bool = False
    skill_write_allowed: bool = False
    skill_mutation_performed: bool = False
    persistence_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillAuthoringReceipt:
    id: str
    created_at: str
    source_lesson_id: str
    source_provenance_id: str
    source_apply_id: str
    source_record_hash: str
    base_contract_id: str
    base_contract_hash: str
    contract_schema: str
    storage_schema: str
    authored_contract: dict[str, Any]
    storage_projection: dict[str, Any]
    authoring_hash: str
    confirmation_method: str
    confirmation_token_hash: str
    operator_confirmation_recorded: bool = True
    authoring_fields_complete: bool = True
    process_memory_only: bool = True
    restart_expiring: bool = True
    future_apply_ready: bool = False
    executable: bool = False
    promotion_allowed: bool = False
    skill_write_allowed: bool = False
    skill_mutation_performed: bool = False
    memory_mutation_performed: bool = False
    experience_mutation_performed: bool = False
    persistence_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProceduralSkillAuthoringDoctorReport:
    status: str
    receipt_count: int
    current_count: int
    drifted_count: int
    issues: list[str]
    warnings: list[str]


class ProceduralSkillAuthoringError(RuntimeError):
    pass


class OperatorReviewedProceduralSkillAuthoringSession:
    """Stores exact operator-authored contracts in bounded process memory only."""

    def __init__(self) -> None:
        self._receipts: dict[str, ProceduralSkillAuthoringReceipt] = {}
        self._lock = RLock()

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(receipt.to_dict()) for receipt in self._receipts.values())

    def get(self, identifier: str) -> ProceduralSkillAuthoringReceipt | None:
        with self._lock:
            direct = self._receipts.get(identifier)
            if direct is not None:
                return direct
            return next(
                (
                    receipt
                    for receipt in self._receipts.values()
                    if identifier in {receipt.id, receipt.source_lesson_id}
                ),
                None,
            )

    def create(
        self,
        blueprint: ProceduralSkillAuthoringBlueprint,
        *,
        token: str,
    ) -> ProceduralSkillAuthoringReceipt:
        with self._lock:
            if token != procedural_skill_authoring_confirmation_token(blueprint):
                raise ProceduralSkillAuthoringError("Skill authoring confirmation token mismatch.")
            if blueprint.source_lesson_id in self._receipts:
                raise ProceduralSkillAuthoringError(
                    "Source lesson already has a process-memory skill authoring receipt."
                )
            if len(self._receipts) >= PROCEDURAL_SKILL_AUTHORING_MAX_RECEIPTS:
                raise ProceduralSkillAuthoringError(
                    "Process-memory skill authoring receipt limit reached."
                )
            if not blueprint.authoring_fields_complete:
                raise ProceduralSkillAuthoringError("Authored contract fields are incomplete.")
            if any(
                (
                    blueprint.executable,
                    blueprint.promotion_allowed,
                    blueprint.skill_write_allowed,
                    blueprint.skill_mutation_performed,
                    blueprint.persistence_performed,
                )
            ):
                raise ProceduralSkillAuthoringError(
                    "Blueprint violates the no-writer/no-execution authoring boundary."
                )
            receipt = ProceduralSkillAuthoringReceipt(
                id=f"skillauth_{blueprint.authoring_hash[:16]}",
                created_at=utc_now_iso(),
                source_lesson_id=blueprint.source_lesson_id,
                source_provenance_id=blueprint.source_provenance_id,
                source_apply_id=blueprint.source_apply_id,
                source_record_hash=blueprint.source_record_hash,
                base_contract_id=blueprint.base_contract_id,
                base_contract_hash=blueprint.base_contract_hash,
                contract_schema=blueprint.contract_schema,
                storage_schema=blueprint.storage_schema,
                authored_contract=deepcopy(blueprint.authored_contract),
                storage_projection=deepcopy(blueprint.storage_projection),
                authoring_hash=blueprint.authoring_hash,
                confirmation_method="exact_source_and_authored_contract_token",
                confirmation_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            )
            self._receipts[receipt.source_lesson_id] = receipt
            return receipt

    def doctor(
        self,
        builder: ProceduralSkillContractBuilder,
    ) -> ProceduralSkillAuthoringDoctorReport:
        receipts = self.snapshot()
        issues: list[str] = []
        warnings: list[str] = []
        current_count = 0
        drifted_count = 0
        if len(receipts) > PROCEDURAL_SKILL_AUTHORING_MAX_RECEIPTS:
            issues.append("Process-memory skill authoring receipt limit is exceeded.")
        ids = [str(receipt.get("id") or "") for receipt in receipts]
        lesson_ids = [str(receipt.get("source_lesson_id") or "") for receipt in receipts]
        if any(not value for value in ids) or any(count > 1 for count in Counter(ids).values()):
            issues.append("Skill authoring receipt id is missing or duplicated.")
        if any(not value for value in lesson_ids) or any(
            count > 1 for count in Counter(lesson_ids).values()
        ):
            issues.append("Skill authoring source lesson id is missing or duplicated.")

        for receipt in receipts:
            label = str(receipt.get("id") or "<missing>")
            authoring_hash = str(receipt.get("authoring_hash") or "")
            if len(authoring_hash) != 64 or label != f"skillauth_{authoring_hash[:16]}":
                issues.append(f"Receipt {label} has invalid authoring hash identity.")
            if _receipt_authoring_hash(receipt) != authoring_hash:
                issues.append(f"Receipt {label} authored contract hash does not verify.")
            if receipt.get("contract_schema") != PROCEDURAL_SKILL_CONTRACT_SCHEMA:
                issues.append(f"Receipt {label} contract schema is invalid.")
            if receipt.get("storage_schema") != PROCEDURAL_SKILL_STORAGE_SCHEMA:
                issues.append(f"Receipt {label} storage schema is invalid.")
            if not _valid_authored_contract(receipt.get("authored_contract")):
                issues.append(f"Receipt {label} authored contract is incomplete or malformed.")
            if not _valid_storage_projection(
                receipt.get("storage_projection"), receipt.get("authored_contract")
            ):
                issues.append(f"Receipt {label} storage projection is malformed or drifted.")
            if (
                receipt.get("confirmation_method")
                != "exact_source_and_authored_contract_token"
                or receipt.get("operator_confirmation_recorded") is not True
                or len(str(receipt.get("confirmation_token_hash") or "")) != 64
            ):
                issues.append(f"Receipt {label} lacks exact operator confirmation evidence.")
            if any(
                receipt.get(field) is not expected
                for field, expected in {
                    "authoring_fields_complete": True,
                    "process_memory_only": True,
                    "restart_expiring": True,
                    "future_apply_ready": False,
                    "executable": False,
                    "promotion_allowed": False,
                    "skill_write_allowed": False,
                    "skill_mutation_performed": False,
                    "memory_mutation_performed": False,
                    "experience_mutation_performed": False,
                    "persistence_performed": False,
                }.items()
            ):
                issues.append(f"Receipt {label} violates the process-memory no-writer boundary.")

            try:
                review = builder.review(str(receipt.get("source_lesson_id") or ""))
            except (ProceduralSkillContractError, OSError, TypeError, ValueError) as exc:
                warnings.append(f"Receipt {label} current source cannot be reviewed: {exc}")
                drifted_count += 1
                continue
            contract = review.contract
            if (
                review.eligible_for_operator_authoring
                and contract is not None
                and contract.id == receipt.get("base_contract_id")
                and contract.contract_hash == receipt.get("base_contract_hash")
                and contract.source_record_hash == receipt.get("source_record_hash")
            ):
                current_count += 1
            else:
                drifted_count += 1
                warnings.append(
                    f"Receipt {label} is historical: source lifecycle, provenance, hash, or duplicate state changed."
                )

        if PROCEDURAL_SKILL_WRITER_INSTALLED or PROCEDURAL_SKILL_EXECUTION_INSTALLED:
            issues.append("A forbidden procedural skill writer or execution engine is installed.")
        status = "ERROR" if issues else "WARN" if warnings else "OK"
        return ProceduralSkillAuthoringDoctorReport(
            status=status,
            receipt_count=len(receipts),
            current_count=current_count,
            drifted_count=drifted_count,
            issues=_dedupe(issues),
            warnings=_dedupe(warnings),
        )


def build_procedural_skill_authoring_blueprint(
    builder: ProceduralSkillContractBuilder,
    request: ProceduralSkillAuthoringRequest,
) -> ProceduralSkillAuthoringBlueprint:
    review = builder.review(request.memory_id)
    if not review.eligible_for_operator_authoring or review.contract is None:
        details = "; ".join([*review.issues, *review.warnings])
        raise ProceduralSkillAuthoringError(
            f"Source lesson is not eligible for skill authoring ({review.status})."
            + (f" {details}" if details else "")
        )
    contract = review.contract
    authored_contract = _authored_contract(request, contract.name, contract.summary)
    _validate_authored_contract(authored_contract)
    storage_projection = _storage_projection(authored_contract)
    material = {
        "source_lesson_id": contract.source_lesson_id,
        "source_provenance_id": contract.source_provenance_id,
        "source_apply_id": contract.source_apply_id,
        "source_record_hash": contract.source_record_hash,
        "base_contract_id": contract.id,
        "base_contract_hash": contract.contract_hash,
        "contract_schema": contract.schema,
        "storage_schema": contract.storage_schema,
        "authored_contract": authored_contract,
        "storage_projection": storage_projection,
    }
    return ProceduralSkillAuthoringBlueprint(
        **material,
        authoring_hash=_hash_json(material),
    )


def procedural_skill_authoring_confirmation_token(
    blueprint: ProceduralSkillAuthoringBlueprint,
) -> str:
    return f"CONFIRM-SKILL-AUTHOR-{blueprint.authoring_hash[:12].upper()}"


def format_procedural_skill_authoring_command(
    command: str,
    *,
    builder: ProceduralSkillContractBuilder,
    session: OperatorReviewedProceduralSkillAuthoringSession,
) -> str | None:
    raw = command.strip()
    normalized = " ".join(raw.lower().split())
    prefixes = (
        "/experience learning skill-authoring-status",
        "/experience learning skill-authoring-confirm-preview",
        "/experience learning skill-authoring-receipts",
        "/experience learning skill-authoring-receipt",
        "/experience learning skill-authoring-doctor",
        "/experience learning propose skill-contract",
    )
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in prefixes):
        return None
    if len(raw) > _MAX_COMMAND_CHARS:
        return _authoring_error("Command exceeds the bounded authoring input limit.")
    if any(marker in raw for marker in ("\n", ";", "&&", "||")):
        return _authoring_error("Command chaining and multi-command input are not allowed.")
    try:
        tokens = shlex.split(_normalize_cli_quotes(raw))
    except ValueError as exc:
        return _authoring_error(f"Invalid quoted input: {exc}")

    try:
        if normalized == "/experience learning skill-authoring-status":
            return format_procedural_skill_authoring_status(session.doctor(builder))
        if normalized == "/experience learning skill-authoring-receipts":
            return format_procedural_skill_authoring_receipts(session)
        if normalized == "/experience learning skill-authoring-doctor":
            return format_procedural_skill_authoring_doctor(session.doctor(builder))
        if normalized == "/experience learning skill-authoring-receipt":
            return "Usage: /experience learning skill-authoring-receipt <receipt_id|memory_id>"
        if normalized.startswith("/experience learning skill-authoring-receipt "):
            if len(tokens) != 4:
                return "Usage: /experience learning skill-authoring-receipt <receipt_id|memory_id>"
            return format_procedural_skill_authoring_receipt(session.get(tokens[3]), tokens[3])
        if normalized == "/experience learning skill-authoring-confirm-preview":
            return _authoring_usage("skill-authoring-confirm-preview")
        if normalized.startswith("/experience learning skill-authoring-confirm-preview "):
            request = parse_procedural_skill_authoring_request(tokens[3:])
            blueprint = build_procedural_skill_authoring_blueprint(builder, request)
            return format_procedural_skill_authoring_preview(blueprint)
        if normalized == "/experience learning propose skill-contract":
            return _authoring_usage("propose skill-contract")
        if normalized.startswith("/experience learning propose skill-contract "):
            if len(tokens) < 7:
                return _authoring_usage("author skill")
            request = parse_procedural_skill_authoring_request([tokens[4], *tokens[6:]])
            blueprint = build_procedural_skill_authoring_blueprint(builder, request)
            receipt = session.create(blueprint, token=tokens[5])
            return format_procedural_skill_authoring_created(receipt)
    except (ProceduralSkillAuthoringError, ProceduralSkillContractError) as exc:
        return _authoring_error(str(exc))
    return None


def parse_procedural_skill_authoring_request(
    tokens: list[str],
) -> ProceduralSkillAuthoringRequest:
    if not tokens or not tokens[0].strip():
        raise ProceduralSkillAuthoringError("A source lesson memory id is required.")
    memory_id = tokens[0].strip()
    if memory_id.startswith("--") or any(char.isspace() for char in memory_id):
        raise ProceduralSkillAuthoringError("Source lesson memory id is invalid.")
    singles = {field: "" for field in _SINGLE_FLAGS.values()}
    repeated: dict[str, list[str]] = {field: [] for field in _REPEATED_FLAGS.values()}
    index = 1
    while index < len(tokens):
        flag = tokens[index].lower()
        if flag not in _SINGLE_FLAGS and flag not in _REPEATED_FLAGS:
            raise ProceduralSkillAuthoringError(f"Unknown authoring flag {tokens[index]!r}.")
        if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
            raise ProceduralSkillAuthoringError(f"Flag {flag} requires one quoted value.")
        value = _clean_value(tokens[index + 1], flag)
        if flag in _SINGLE_FLAGS:
            field = _SINGLE_FLAGS[flag]
            if singles[field]:
                raise ProceduralSkillAuthoringError(f"Flag {flag} may be provided only once.")
            singles[field] = value
        else:
            field = _REPEATED_FLAGS[flag]
            repeated[field].append(value)
            if len(repeated[field]) > _LIST_LIMITS[field]:
                raise ProceduralSkillAuthoringError(
                    f"Field {field} exceeds its {_LIST_LIMITS[field]} item limit."
                )
        index += 2
    for field in _REQUIRED_FIELDS:
        present = singles.get(field) or repeated.get(field)
        if not present:
            raise ProceduralSkillAuthoringError(f"Required operator field {field} is missing.")
    return ProceduralSkillAuthoringRequest(
        memory_id=memory_id,
        name=singles["name"],
        summary=singles["summary"],
        trigger=singles["trigger"],
        preconditions=repeated["preconditions"],
        steps=repeated["steps"],
        permissions=repeated["permissions"],
        verification=repeated["verification"],
        known_failure_modes=repeated["known_failure_modes"],
    )


def format_procedural_skill_authoring_status(
    report: ProceduralSkillAuthoringDoctorReport,
) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Authoring Status v1",
            f"Status: {report.status}",
            f"mode: {PROCEDURAL_SKILL_AUTHORING_MODE}",
            f"receipts: {report.receipt_count}/{PROCEDURAL_SKILL_AUTHORING_MAX_RECEIPTS}",
            f"current_receipts: {report.current_count}",
            f"drifted_receipts: {report.drifted_count}",
            f"skill_writer_installed: {str(PROCEDURAL_SKILL_WRITER_INSTALLED).lower()}",
            f"skill_execution_installed: {str(PROCEDURAL_SKILL_EXECUTION_INSTALLED).lower()}",
            "Commands: skill-authoring-confirm-preview | propose skill-contract | skill-authoring-receipts|receipt|doctor",
            *_authoring_boundary(),
        ]
    )


def format_procedural_skill_authoring_preview(
    blueprint: ProceduralSkillAuthoringBlueprint,
) -> str:
    contract = blueprint.authored_contract
    lines = [
        "Proto-Mind Procedural Skill Authoring Confirmation Preview v1",
        "Status: CONFIRMABLE",
        f"source_lesson_id: {blueprint.source_lesson_id}",
        f"source_provenance_id: {blueprint.source_provenance_id}",
        f"base_contract_id: {blueprint.base_contract_id}",
        f"base_contract_hash: {blueprint.base_contract_hash}",
        f"authoring_hash: {blueprint.authoring_hash}",
        f"name: {contract['name']}",
        f"summary: {contract['summary']}",
        f"trigger: {contract['trigger']}",
        f"preconditions: {len(contract['preconditions'])}",
        f"steps: {len(contract['steps'])}",
        f"permissions: {len(contract['permissions'])}",
        f"verification: {len(contract['verification'])}",
        f"known_failure_modes: {len(contract['known_failure_modes'])}",
        "authoring_fields_complete: true",
        "future_apply_ready: false",
        "executable: false",
        "Exact authored contract:",
        *[f"- precondition[{index}]: {value}" for index, value in enumerate(contract["preconditions"], 1)],
        *[f"- step[{index}]: {value}" for index, value in enumerate(contract["steps"], 1)],
        *[f"- permission[{index}]: {value}" for index, value in enumerate(contract["permissions"], 1)],
        *[f"- verification[{index}]: {value}" for index, value in enumerate(contract["verification"], 1)],
        *[f"- failure[{index}]: {value}" for index, value in enumerate(contract["known_failure_modes"], 1)],
        f"Confirmation token: {procedural_skill_authoring_confirmation_token(blueprint)}",
        "Re-run /experience learning propose skill-contract with the exact token and identical authored flags.",
    ]
    lines.extend(_authoring_boundary())
    return "\n".join(lines)


def format_procedural_skill_authoring_created(
    receipt: ProceduralSkillAuthoringReceipt,
) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Authoring Receipt v1",
            "Status: OPERATOR AUTHORING RECORDED",
            f"receipt_id: {receipt.id}",
            f"created_at: {receipt.created_at}",
            f"source_lesson_id: {receipt.source_lesson_id}",
            f"authoring_hash: {receipt.authoring_hash}",
            "process_memory_only: true",
            "restart_expiring: true",
            "future_apply_ready: false",
            "executable: false",
            "skill_mutation_performed: false",
            "- Exact operator-authored fields were recorded; no skill was created.",
            *_authoring_boundary(),
        ]
    )


def format_procedural_skill_authoring_receipts(
    session: OperatorReviewedProceduralSkillAuthoringSession,
) -> str:
    receipts = session.snapshot()
    lines = [
        "Proto-Mind Procedural Skill Authoring Receipts v1",
        f"Status: {'EMPTY' if not receipts else 'OK'}",
        f"receipts: {len(receipts)}/{PROCEDURAL_SKILL_AUTHORING_MAX_RECEIPTS}",
    ]
    for receipt in receipts:
        contract = receipt.get("authored_contract") or {}
        lines.append(
            f"- {receipt.get('id')} | lesson={receipt.get('source_lesson_id')} | "
            f"name={contract.get('name')} | future_apply_ready=false | executable=false"
        )
    if not receipts:
        lines.append("- No process-memory authoring receipt exists.")
    lines.extend(_authoring_boundary())
    return "\n".join(lines)


def format_procedural_skill_authoring_receipt(
    receipt: ProceduralSkillAuthoringReceipt | None,
    identifier: str,
) -> str:
    if receipt is None:
        return _authoring_error(f"No process-memory skill authoring receipt matches {identifier!r}.")
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Authoring Receipt Inspect v1",
            "Status: OK",
            json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            *_authoring_boundary(),
        ]
    )


def format_procedural_skill_authoring_doctor(
    report: ProceduralSkillAuthoringDoctorReport,
) -> str:
    lines = [
        "Proto-Mind Procedural Skill Authoring Doctor v1",
        f"Status: {report.status}",
        f"receipts: {report.receipt_count}",
        f"current_receipts: {report.current_count}",
        f"drifted_receipts: {report.drifted_count}",
        f"skill_writer_installed: {str(PROCEDURAL_SKILL_WRITER_INSTALLED).lower()}",
        f"skill_execution_installed: {str(PROCEDURAL_SKILL_EXECUTION_INSTALLED).lower()}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append(
            "- Receipt bounds, hashes, current source, exact confirmation, and no-writer boundary are healthy."
        )
    lines.extend(_authoring_boundary())
    return "\n".join(lines)


def _authored_contract(
    request: ProceduralSkillAuthoringRequest,
    default_name: str,
    default_summary: str,
) -> dict[str, Any]:
    return {
        "name": request.name or default_name,
        "summary": request.summary or default_summary,
        "trigger": request.trigger,
        "preconditions": list(request.preconditions),
        "steps": list(request.steps),
        "permissions": list(request.permissions),
        "verification": list(request.verification),
        "known_failure_modes": list(request.known_failure_modes),
    }


def _validate_authored_contract(contract: dict[str, Any]) -> None:
    if not _valid_authored_contract(contract):
        raise ProceduralSkillAuthoringError("Authored contract is incomplete or malformed.")
    if len(json.dumps(contract, ensure_ascii=False)) > _MAX_AUTHORED_CHARS:
        raise ProceduralSkillAuthoringError("Authored contract exceeds the bounded payload limit.")
    for field in _REPEATED_FLAGS.values():
        normalized = [" ".join(value.casefold().split()) for value in contract[field]]
        if len(normalized) != len(set(normalized)):
            raise ProceduralSkillAuthoringError(f"Field {field} contains duplicate items.")


def _valid_authored_contract(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {
        "name",
        "summary",
        "trigger",
        "preconditions",
        "steps",
        "permissions",
        "verification",
        "known_failure_modes",
    }:
        return False
    if not all(isinstance(value[field], str) and value[field].strip() for field in ("name", "summary", "trigger")):
        return False
    for field, limit in _LIST_LIMITS.items():
        items = value.get(field)
        if (
            not isinstance(items, list)
            or not 1 <= len(items) <= limit
            or any(not isinstance(item, str) or not item.strip() for item in items)
        ):
            return False
    return True


def _storage_projection(contract: dict[str, Any]) -> dict[str, Any]:
    body = "\n".join(
        [
            "Trigger:",
            contract["trigger"],
            "",
            "Preconditions:",
            *[f"- {value}" for value in contract["preconditions"]],
            "",
            "Steps:",
            *[f"{index}. {value}" for index, value in enumerate(contract["steps"], 1)],
            "",
            "Permissions:",
            *[f"- {value}" for value in contract["permissions"]],
            "",
            "Verification:",
            *[f"- {value}" for value in contract["verification"]],
            "",
            "Known failure modes:",
            *[f"- {value}" for value in contract["known_failure_modes"]],
        ]
    )
    return {
        "schema": PROCEDURAL_SKILL_STORAGE_SCHEMA,
        "name": contract["name"],
        "summary": contract["summary"],
        "body": body,
        "status": "active",
        "category": "workflow",
        "source": "experience_learning_skill_authoring",
        "tags": ["experience", "operator_authored", "procedural_contract"],
    }


def _valid_storage_projection(value: object, contract: object) -> bool:
    if not isinstance(value, dict) or not isinstance(contract, dict):
        return False
    try:
        return value == _storage_projection(contract)
    except (KeyError, TypeError, ValueError):
        return False


def _receipt_authoring_hash(receipt: dict[str, Any]) -> str:
    material = {
        key: receipt.get(key)
        for key in (
            "source_lesson_id",
            "source_provenance_id",
            "source_apply_id",
            "source_record_hash",
            "base_contract_id",
            "base_contract_hash",
            "contract_schema",
            "storage_schema",
            "authored_contract",
            "storage_projection",
        )
    }
    return _hash_json(material)


def _clean_value(value: str, flag: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ProceduralSkillAuthoringError(f"Flag {flag} value must not be empty.")
    if len(cleaned) > _MAX_ITEM_CHARS:
        raise ProceduralSkillAuthoringError(f"Flag {flag} value exceeds {_MAX_ITEM_CHARS} characters.")
    if any(ord(char) < 32 for char in cleaned):
        raise ProceduralSkillAuthoringError(f"Flag {flag} value contains a control character.")
    return cleaned


def _authoring_usage(command: str) -> str:
    token = " <exact_token>" if command == "propose skill-contract" else ""
    return (
        f"Usage: /experience learning {command} <memory_id>{token} "
        "[--name \"...\"] [--summary \"...\"] --trigger \"...\" "
        "--precondition \"...\" --step \"...\" --permission \"...\" "
        "--verify \"...\" --failure \"...\""
    )


def _authoring_error(message: str) -> str:
    return "\n".join(
        [
            "Proto-Mind Procedural Skill Authoring Error",
            "Status: ERROR",
            f"- {message}",
            *_authoring_boundary(),
        ]
    )


def _authoring_boundary() -> list[str]:
    return [
        "Boundary:",
        "- Process-memory operator authoring only; no skill was accepted, stored, promoted, or executed.",
        "- No lesson, memory, Skill Library, Experience event, queue, export, session log, or Context Injection changed.",
        "- Receipt expires on restart; no writer, shell, arbitrary dispatch, model/API call, auto-apply, or background action exists.",
    ]


def _normalize_cli_quotes(value: str) -> str:
    return value.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"}))


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
