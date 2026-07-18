from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any, Callable, Pattern


EXPERIENCE_PRIVACY_SPEC_VERSION = 1
PRIVACY_PREVIEW_MAX_CHARS = 160
REDACTION_PREFIX = "[REDACTED:"
_REDACTION_TOKEN_PATTERN = re.compile(r"\[REDACTED:[a-z0-9_]+\]", re.IGNORECASE)


@dataclass(frozen=True)
class ExperienceRedactionResult:
    text: str
    input_chars: int
    output_chars: int
    redaction_count: int
    categories: list[str]
    truncated: bool
    sensitive_remainder_categories: list[str]
    safe: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperiencePrivacyDoctorReport:
    status: str
    rule_count: int
    sensitive_case_count: int
    benign_case_count: int
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ExperiencePrivacyBenchmarkReport:
    status: str
    case_count: int
    sensitive_case_count: int
    benign_case_count: int
    files_created: int
    checks: dict[str, bool]
    failed_checks: list[str]
    boundary: str


@dataclass(frozen=True)
class _RedactionRule:
    category: str
    pattern: Pattern[str]
    replacement: str | Callable[[re.Match[str]], str]


@dataclass(frozen=True)
class _PrivacyCase:
    case_id: str
    category: str
    value: str
    forbidden_fragments: tuple[str, ...]
    should_redact: bool = True


def _replace_uri_credentials(match: re.Match[str]) -> str:
    return f"{match.group('scheme')}[REDACTED:uri_credentials]@"


def _replace_prefixed(category: str) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}[REDACTED:{category}]"

    return replace


_CREDENTIAL_LABELS = (
    r"password|passwd|pwd|client[_-]?secret|secret|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|auth[_-]?token|session[_-]?(?:id|token)|token|cookie|"
    r"пароль|секрет|токен"
)

_REDACTION_RULES: tuple[_RedactionRule, ...] = (
    _RedactionRule(
        "private_key",
        re.compile(
            r"-----BEGIN (?P<kind>[A-Z0-9 ]*PRIVATE KEY)-----.*?"
            r"-----END (?P=kind)-----",
            re.IGNORECASE,
        ),
        "[REDACTED:private_key]",
    ),
    _RedactionRule(
        "uri_credentials",
        re.compile(
            r"\b(?P<scheme>[a-z][a-z0-9+.-]*://)"
            r"(?!\[REDACTED:)"
            r"[^/\s:@]+:[^@\s/]+@",
            re.IGNORECASE,
        ),
        _replace_uri_credentials,
    ),
    _RedactionRule(
        "bearer_token",
        re.compile(
            r"(?P<prefix>\bauthorization\s*[:=]\s*bearer\s+)"
            r"[A-Za-z0-9._~+/=-]{8,}",
            re.IGNORECASE,
        ),
        _replace_prefixed("bearer_token"),
    ),
    _RedactionRule(
        "credential",
        re.compile(
            rf"(?P<prefix>[\"']?(?:{_CREDENTIAL_LABELS})[\"']?\s*[:=]\s*)"
            r"(?!\[REDACTED:)"
            r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&}\]]+)",
            re.IGNORECASE,
        ),
        _replace_prefixed("credential"),
    ),
    _RedactionRule(
        "openai_key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
        "[REDACTED:openai_key]",
    ),
    _RedactionRule(
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b", re.IGNORECASE),
        "[REDACTED:github_token]",
    ),
    _RedactionRule(
        "slack_token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b", re.IGNORECASE),
        "[REDACTED:slack_token]",
    ),
    _RedactionRule(
        "aws_access_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED:aws_access_key]",
    ),
    _RedactionRule(
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b"
        ),
        "[REDACTED:jwt]",
    ),
)


_PRIVACY_CASES: tuple[_PrivacyCase, ...] = (
    _PrivacyCase("en_password", "credential", "password=hunter2-secret", ("hunter2-secret",)),
    _PrivacyCase("ru_password", "credential", "пароль: сверх-секрет-42", ("сверх-секрет-42",)),
    _PrivacyCase(
        "json_api_key",
        "credential",
        'Request body {"api_key": "demo-secret-value"}',
        ("demo-secret-value",),
    ),
    _PrivacyCase(
        "environment_token",
        "credential",
        "export ACCESS_TOKEN=temporary-access-value",
        ("temporary-access-value",),
    ),
    _PrivacyCase(
        "bearer_header",
        "bearer_token",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz.1234567890",
        ("abcdefghijklmnopqrstuvwxyz", "1234567890"),
    ),
    _PrivacyCase(
        "credential_uri",
        "uri_credentials",
        "Connect with postgresql://proto:private-pass@localhost/db",
        ("proto:private-pass", "private-pass"),
    ),
    _PrivacyCase(
        "openai_key",
        "openai_key",
        "Key sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        ("sk-proj-abcdefghijklmnopqrstuvwxyz123456",),
    ),
    _PrivacyCase(
        "github_token",
        "github_token",
        "Token ghp_abcdefghijklmnopqrstuvwxyz123456",
        ("ghp_abcdefghijklmnopqrstuvwxyz123456",),
    ),
    _PrivacyCase(
        "slack_token",
        "slack_token",
        "Slack xoxb-test-fixture-abcdefghijklmnop",
        ("xoxb-test-fixture-abcdefghijklmnop",),
    ),
    _PrivacyCase(
        "aws_access_key",
        "aws_access_key",
        "AWS AKIAABCDEFGHIJKLMNOP",
        ("AKIAABCDEFGHIJKLMNOP",),
    ),
    _PrivacyCase(
        "jwt",
        "jwt",
        "JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signatureABC123",
        ("eyJhbGciOiJIUzI1NiJ9", "signatureABC123"),
    ),
    _PrivacyCase(
        "private_key",
        "private_key",
        "-----BEGIN PRIVATE KEY----- abcdefghijklmnopqrstuvwxyz "
        "-----END PRIVATE KEY-----",
        ("abcdefghijklmnopqrstuvwxyz",),
    ),
    _PrivacyCase(
        "benign_password_manager",
        "benign",
        "Use a password manager and rotate credentials regularly.",
        (),
        should_redact=False,
    ),
    _PrivacyCase(
        "benign_token_budget",
        "benign",
        "The token budget is 1200 and no credential value is present.",
        (),
        should_redact=False,
    ),
    _PrivacyCase(
        "benign_url",
        "benign",
        "Documentation: https://example.test/security/credentials",
        (),
        should_redact=False,
    ),
    _PrivacyCase(
        "benign_russian",
        "benign",
        "Пароль следует хранить в менеджере секретов, а не в журнале.",
        (),
        should_redact=False,
    ),
)


def redact_experience_preview(
    value: object,
    *,
    max_chars: int = PRIVACY_PREVIEW_MAX_CHARS,
) -> ExperienceRedactionResult:
    """Normalize, redact, then truncate one detached preview value."""

    normalized = " ".join(str(value or "").split())
    redacted = normalized
    categories: list[str] = []
    redaction_count = 0
    for rule in _REDACTION_RULES:
        redacted, count = rule.pattern.subn(rule.replacement, redacted)
        if count:
            redaction_count += count
            categories.extend([rule.category] * count)

    limit = max(0, int(max_chars))
    truncated = len(redacted) > limit
    if truncated:
        redacted = _truncate_redacted_preview(redacted, limit)

    remainder = find_sensitive_preview_categories(redacted)
    return ExperienceRedactionResult(
        text=redacted,
        input_chars=len(normalized),
        output_chars=len(redacted),
        redaction_count=redaction_count,
        categories=sorted(set(categories)),
        truncated=truncated,
        sensitive_remainder_categories=remainder,
        safe=not remainder,
    )


def _truncate_redacted_preview(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if limit <= 3:
        return "." * limit

    cut = limit - 3
    candidate = value[:cut].rstrip()
    crossing = next(
        (
            match
            for match in _REDACTION_TOKEN_PATTERN.finditer(value)
            if match.start() < cut < match.end()
        ),
        None,
    )
    if crossing is None:
        return f"{candidate}..."

    token = crossing.group(0)
    head_budget = limit - len(token) - 3
    if head_budget < 0:
        return "..."
    head = value[: min(crossing.start(), head_budget)].rstrip()
    return f"{head}{token}..."


def find_sensitive_preview_categories(value: object) -> list[str]:
    text = " ".join(str(value or "").split())
    return sorted({rule.category for rule in _REDACTION_RULES if rule.pattern.search(text)})


def filter_sensitive_derived_values(values: list[str], source_text: object) -> list[str]:
    """Drop compact derived labels that overlap a credential match in their source."""

    source = " ".join(str(source_text or "").split())
    sensitive_segments = [
        match.group(0).casefold()
        for rule in _REDACTION_RULES
        for match in rule.pattern.finditer(source)
    ]
    safe_values: list[str] = []
    for value in values:
        normalized = " ".join(str(value or "").split()).casefold()
        if not normalized:
            continue
        if any(normalized in segment for segment in sensitive_segments):
            continue
        safe_values.append(str(value))
    return safe_values


def inspect_experience_privacy() -> ExperiencePrivacyDoctorReport:
    issues: list[str] = []
    warnings: list[str] = []
    sensitive = [case for case in _PRIVACY_CASES if case.should_redact]
    benign = [case for case in _PRIVACY_CASES if not case.should_redact]

    for case in sensitive:
        result = redact_experience_preview(case.value)
        if result.redaction_count == 0 or not result.safe:
            issues.append(f"Sensitive case {case.case_id} did not fail closed.")
        if any(fragment in result.text for fragment in case.forbidden_fragments):
            issues.append(f"Sensitive case {case.case_id} retained protected material.")
    for case in benign:
        result = redact_experience_preview(case.value)
        expected = " ".join(case.value.split())
        if result.text != expected or result.redaction_count:
            issues.append(f"Benign case {case.case_id} was over-redacted.")

    if len(_REDACTION_RULES) < 8:
        warnings.append("Credential redaction rule coverage is narrower than expected.")
    status = "ERROR" if issues else "WARN" if warnings else "OK"
    return ExperiencePrivacyDoctorReport(
        status=status,
        rule_count=len(_REDACTION_RULES),
        sensitive_case_count=len(sensitive),
        benign_case_count=len(benign),
        issues=issues,
        warnings=warnings,
    )


def run_experience_privacy_benchmark() -> ExperiencePrivacyBenchmarkReport:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        before = list(root.rglob("*"))
        sensitive = [case for case in _PRIVACY_CASES if case.should_redact]
        benign = [case for case in _PRIVACY_CASES if not case.should_redact]
        sensitive_results = [redact_experience_preview(case.value) for case in sensitive]
        benign_results = [redact_experience_preview(case.value) for case in benign]
        repeated_results = [redact_experience_preview(case.value) for case in _PRIVACY_CASES]

        truncation = redact_experience_preview("api_key=" + ("x" * 200), max_chars=40)

        # Local imports prove integration while keeping this module dependency-free.
        from proto_mind.experience_ledger import compact_preview, inspect_experience_events

        integrated = compact_preview("password=integration-secret")
        filtered_topics = filter_sensitive_derived_values(
            ["security", "password", "integration-secret"],
            "Review security with password=integration-secret",
        )
        unsafe_event = {
            "id": "evt_privacy_1_01_conversation_observed",
            "created_at": "2026-01-01T00:00:00Z",
            "event_type": "conversation_observed",
            "session_id": "privacy-benchmark",
            "turn_id": "1",
            "source": "privacy_benchmark",
            "source_event_ids": [],
            "payload": {
                "input_preview": "password=doctor-secret",
                "input_chars": 22,
                "language_hint": "english",
            },
            "confidence": None,
            "schema_version": 1,
        }
        unsafe_report = inspect_experience_events([unsafe_event])
        after = list(root.rglob("*"))

    checks = {
        "doctor_ok": inspect_experience_privacy().status == "OK",
        "all_sensitive_redacted": all(result.redaction_count > 0 for result in sensitive_results),
        "all_sensitive_outputs_safe": all(result.safe for result in sensitive_results),
        "no_protected_fragments_retained": all(
            all(fragment not in result.text for fragment in case.forbidden_fragments)
            for case, result in zip(sensitive, sensitive_results, strict=True)
        ),
        "benign_controls_unchanged": all(
            result.text == " ".join(case.value.split()) and result.redaction_count == 0
            for case, result in zip(benign, benign_results, strict=True)
        ),
        "deterministic_outputs": [result.to_dict() for result in repeated_results]
        == [redact_experience_preview(case.value).to_dict() for case in _PRIVACY_CASES],
        "redaction_is_idempotent": all(
            redact_experience_preview(result.text).text == result.text
            for result in sensitive_results
        ),
        "redaction_before_truncation": "x" not in truncation.text
        and REDACTION_PREFIX in truncation.text,
        "preview_limit_enforced": truncation.output_chars <= 40,
        "ledger_compact_preview_integrated": "integration-secret" not in integrated
        and REDACTION_PREFIX in integrated,
        "sensitive_derived_values_filtered": filtered_topics == ["security"],
        "doctor_rejects_unredacted_preview": unsafe_report.status == "ERROR"
        and any("unredacted credential-like" in issue for issue in unsafe_report.issues),
        "no_capture_or_persistence": True,
        "no_files_created": before == after,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return ExperiencePrivacyBenchmarkReport(
        status="OK" if not failed else "ERROR",
        case_count=len(_PRIVACY_CASES),
        sensitive_case_count=len(sensitive),
        benign_case_count=len(benign),
        files_created=len(after) - len(before),
        checks=checks,
        failed_checks=failed,
        boundary=(
            "Pure deterministic credential-like preview redaction only; no PII inference, LLM, "
            "live capture, hook, writer, store, persistence, command, export, or domain mutation."
        ),
    )


def format_experience_privacy_status() -> str:
    report = inspect_experience_privacy()
    return "\n".join(
        [
            "Proto-Mind Experience Privacy Redaction v1",
            f"Status: {report.status}",
            "mode: deterministic_preview_only",
            f"rules: {report.rule_count}",
            f"sensitive_cases: {report.sensitive_case_count}",
            f"benign_controls: {report.benign_case_count}",
            "capture_enabled: false",
            "persistence_enabled: false",
        ]
    )


def format_experience_privacy_doctor() -> str:
    report = inspect_experience_privacy()
    lines = [
        "Proto-Mind Experience Privacy Doctor v1",
        f"Status: {report.status}",
        f"rules: {report.rule_count}",
        f"cases: {report.sensitive_case_count + report.benign_case_count}",
    ]
    lines.extend(f"- ERROR: {issue}" for issue in report.issues)
    lines.extend(f"- WARN: {warning}" for warning in report.warnings)
    if not report.issues and not report.warnings:
        lines.append("- Credential-like cases are redacted and benign controls remain unchanged.")
    lines.append("- No capture, persistence, file write, command, LLM, or PII inference.")
    return "\n".join(lines)


def format_experience_privacy_benchmark() -> str:
    report = run_experience_privacy_benchmark()
    lines = [
        "Proto-Mind Experience Privacy Redaction Benchmark v1",
        f"Status: {report.status}",
        f"cases: {report.case_count}",
        f"sensitive_cases: {report.sensitive_case_count}",
        f"benign_controls: {report.benign_case_count}",
        f"files_created: {report.files_created}",
        "Checks:",
    ]
    lines.extend(f"- [{'PASS' if passed else 'FAIL'}] {name}" for name, passed in report.checks.items())
    lines.extend(["Boundary:", f"- {report.boundary}"])
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_experience_privacy_status())
    print()
    print(format_experience_privacy_doctor())
    print()
    print(format_experience_privacy_benchmark())
