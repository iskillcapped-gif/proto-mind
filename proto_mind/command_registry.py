from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from proto_mind.natural_commands import NATURAL_COMMAND_ROUTES


VALID_CATEGORIES = {
    "acceptance",
    "activation",
    "action",
    "agenda",
    "baseline",
    "capabilities",
    "closure",
    "commands",
    "confirm",
    "consolidation",
    "context",
    "data",
    "daily",
    "experience",
    "experiments",
    "focus",
    "exports",
    "goals",
    "identity",
    "loop",
    "memory",
    "memory-card",
    "milestone",
    "natural",
    "policy",
    "plan",
    "prechange",
    "proto",
    "reflection",
    "runner",
    "runner-candidates",
    "runner-exec",
    "runner-mvp",
    "sandbox",
    "session",
    "showcase",
    "skills",
    "system",
    "tasks",
    "world",
    "warnings",
}
VALID_RISKS = {"low", "medium", "high"}
VALID_MUTATES = {"none", "memory", "skills", "tasks", "goals", "world", "identity", "context", "queue", "exports", "session", "multiple"}


@dataclass(frozen=True)
class CommandSpec:
    prefix: str
    category: str
    description: str
    read_only: bool
    mutates: str
    risk: str
    available_in_natural_router: bool = False
    notes: str = ""


def _spec(
    prefix: str,
    category: str,
    description: str,
    *,
    read_only: bool = True,
    mutates: str = "none",
    risk: str = "low",
    notes: str = "",
) -> CommandSpec:
    return CommandSpec(prefix, category, description, read_only, mutates, risk, False, notes)


def _read_only_specs(category: str, commands: dict[str, str]) -> list[CommandSpec]:
    return [_spec(prefix, category, description) for prefix, description in commands.items()]


_BASE_REGISTRY = [
    *_read_only_specs(
        "session",
        {
            "/session self-check": "Run combined session health and diagnostic checks.",
            "/session doctor": "Diagnose recent session-log signals.",
            "/session health": "Check session-log subsystem health.",
            "/session review": "Summarize recent session-log activity.",
            "/session log status": "Show session operator-log status.",
            "/session log path": "Show the session operator-log path.",
            "/session log tail": "Show recent compact session-log entries.",
            "/session log inspect": "Inspect recent session-log entries.",
            "/session log warnings": "List warning-bearing session-log entries.",
            "/session log search": "Search session-log text deterministically.",
            "/session start-brief": "Show a read-only start-of-session operator brief.",
            "/session end-summary": "Show a live read-only end-of-session summary.",
            "/session checkpoint-advice": "Advise whether a manual checkpoint is useful without creating one.",
            "/session handoff-brief": "Print a copyable read-only handoff brief without writing files.",
        },
    ),
    _spec("/session log export", "session", "Export recent session-log entries.", read_only=False, mutates="exports", risk="medium"),
    *_read_only_specs(
        "memory",
        {
            "/memory status": "Show explicit-memory status.",
            "/memory list": "List explicit memories.",
            "/memory inspect": "Inspect an explicit memory.",
            "/memory why": "Explain and verify durable provenance for a persistent memory.",
            "/memory search": "Search explicit memories by substring.",
            "/memory doctor": "Run deterministic memory diagnostics.",
            "/memory write-policy": "Show deterministic memory write and retrieval-side-effect policy.",
            "/memory quality-preview": "Preview legacy response-coupled or oversized memory records without mutation.",
            "/memory active": "List active layered memories.",
            "/memory decisions": "List decision memories.",
            "/memory preferences": "List preference memories.",
            "/memory history": "List inactive memory history.",
            "/memory working": "List working memory.",
            "/memory persistent": "List persistent memory.",
            "/memory summary": "Show memory summary counts.",
            "/memory hygiene": "Preview conservative memory hygiene.",
            "/memory hygiene-preview": "Preview memory cleanup actions.",
            "/memory cleanup-preview": "Preview memory cleanup actions.",
            "/memory repair-preview": "Preview memory-reference repairs.",
            "/memory references-preview": "Preview memory-reference repairs.",
        },
    ),
    _spec("/memory remember", "memory", "Create an explicit operator memory.", read_only=False, mutates="memory", risk="medium"),
    _spec("/memory forget", "memory", "Soft-forget an explicit memory.", read_only=False, mutates="memory", risk="medium"),
    _spec("/memory backup", "memory", "Create a timestamped project backup archive.", read_only=False, mutates="exports", risk="medium", notes="Writes under backups/ rather than cognitive memory."),
    _spec("/memory cleanup-apply", "memory", "Apply conservative memory cleanup.", read_only=False, mutates="memory", risk="high"),
    _spec("/memory repair-apply", "memory", "Apply memory-reference repairs.", read_only=False, mutates="memory", risk="high"),
    _spec("/system checkpoint", "system", "Create a timestamped project backup archive.", read_only=False, mutates="exports", risk="medium"),
    *_read_only_specs(
        "reflection",
        {
            "/reflection status": "Show reflection-journal status.",
            "/reflection list": "List recent reflection records.",
            "/reflection inspect": "Inspect a reflection record.",
        },
    ),
    _spec("/reflection now", "reflection", "Create a deterministic reflection from recent sessions.", read_only=False, mutates="multiple", risk="medium", notes="Mutates reflection_journal.jsonl only."),
    _spec("/reflection last", "reflection", "Create a deterministic reflection from recent sessions.", read_only=False, mutates="multiple", risk="medium", notes="Alias of reflection now."),
    *_read_only_specs(
        "experience",
        {
            "/experience episodes": "List compact cognitive-turn episodes from bounded process-memory evidence.",
            "/experience episode": "Show one Observe-to-Verify cognitive-turn episode and its provenance.",
            "/experience learning": "Inspect evidence-backed candidates, supervised lifecycle state, and procedural skill authoring/readiness reports.",
            "/experience events": "List bounded process-memory Experience pilot events.",
            "/experience inspect": "Explain one process-memory Experience event and its provenance.",
            "/experience doctor": "Diagnose the supervised process-memory Experience pilot.",
        },
    ),
    _spec(
        "/experience learning decide",
        "experience",
        "Capture an explicit candidate accept/reject or lesson lifecycle outcome decision.",
        read_only=False,
        mutates="session",
        risk="medium",
        notes="Process-memory review receipt only; performs no promotion, lifecycle apply, or persistence.",
    ),
    _spec(
        "/experience learning propose",
        "experience",
        "Capture an exact-token promotion or operator-authored procedural contract proposal receipt.",
        read_only=False,
        mutates="session",
        risk="medium",
        notes="Bounded process-memory proposal only; performs no promotion, skill write, apply, execution, queue write, or persistence.",
    ),
    _spec(
        "/experience learning apply",
        "experience",
        "Apply one fresh exact-token memory lesson or one revalidated lifecycle transition.",
        read_only=False,
        mutates="memory",
        risk="medium",
        notes="Single-record supervised pilots; lifecycle apply is run-once with atomic verification/rollback; skills, batch, shell, and arbitrary dispatch remain disabled.",
    ),
    _spec(
        "/experience status",
        "experience",
        "Show supervised Experience pilot state and process-memory bounds.",
        read_only=False,
        mutates="session",
        risk="low",
        notes="May initialize process-memory-only pilot state; writes no file.",
    ),
    _spec(
        "/experience preview",
        "experience",
        "Preview exact session consent, scope, privacy, and bounds.",
        read_only=False,
        mutates="session",
        risk="medium",
        notes="Moves only process-memory consent state to previewed.",
    ),
    _spec(
        "/experience consent",
        "experience",
        "Submit the exact session-bound Experience pilot consent phrase.",
        read_only=False,
        mutates="session",
        risk="medium",
        notes="Enables bounded normal-turn process-memory capture for this process session only.",
    ),
    _spec(
        "/experience stop",
        "experience",
        "Stop Experience pilot capture for the remainder of the process session.",
        read_only=False,
        mutates="session",
        risk="medium",
        notes="Retains existing bounded process-memory previews until process exit.",
    ),
    *_read_only_specs(
        "showcase",
        {
            "/showcase status": "Show contest-demo readiness and current safe presentation state.",
            "/showcase demo": "Render the live continuity, experience, governance, and bounded-action story.",
            "/showcase script": "Print a deterministic three-minute operator demo script.",
            "/showcase doctor": "Diagnose Showcase dependencies and safety boundaries without running demo steps.",
        },
    ),
    *_read_only_specs("goals", {"/goals status": "Show goal-stack status.", "/goals list": "List goals.", "/goals inspect": "Inspect a goal."}),
    *[
        _spec(prefix, "goals", description, read_only=False, mutates="goals", risk="medium")
        for prefix, description in {
            "/goals add": "Create an active goal.",
            "/goals focus": "Set the single focused goal.",
            "/goals pause": "Pause a goal.",
            "/goals complete": "Complete a goal.",
            "/goals cancel": "Cancel a goal.",
            "/goals reopen": "Reopen a goal.",
        }.items()
    ],
    *_read_only_specs("tasks", {"/tasks status": "Show task-queue status.", "/tasks list": "List tasks.", "/tasks next": "Show the deterministic next task.", "/tasks inspect": "Inspect a task."}),
    *[
        _spec(prefix, "tasks", description, read_only=False, mutates="tasks", risk="medium")
        for prefix, description in {
            "/tasks add": "Create an open task.",
            "/tasks start": "Mark a task in progress.",
            "/tasks block": "Block a task with a reason.",
            "/tasks unblock": "Return a blocked task to open.",
            "/tasks done": "Complete a task and optionally record a result.",
            "/tasks cancel": "Cancel a task.",
            "/tasks reopen": "Reopen a task.",
        }.items()
    ],
    *_read_only_specs("experiments", {"/experiments status": "Show experiment-journal status.", "/experiments list": "List experiments.", "/experiments inspect": "Inspect an experiment."}),
    *[
        _spec(prefix, "experiments", description, read_only=False, mutates="multiple", risk="medium", notes="Mutates experiments.jsonl only.")
        for prefix, description in {
            "/experiments start": "Create an experiment.",
            "/experiments hypothesis": "Set an experiment hypothesis.",
            "/experiments predict": "Set an experiment prediction.",
            "/experiments method": "Set an experiment method.",
            "/experiments run": "Mark an experiment running.",
            "/experiments result": "Record an experiment result.",
            "/experiments reflect": "Record an experiment reflection.",
            "/experiments lesson": "Record an experiment lesson.",
            "/experiments complete": "Complete an experiment.",
            "/experiments inconclusive": "Mark an experiment inconclusive.",
            "/experiments cancel": "Cancel an experiment.",
            "/experiments reopen": "Reopen an experiment.",
        }.items()
    ],
    *_read_only_specs("skills", {"/skills status": "Show skill-library status.", "/skills list": "List skills.", "/skills inspect": "Inspect a skill.", "/skills search": "Search skills deterministically."}),
    *[
        _spec(prefix, "skills", description, read_only=False, mutates="skills", risk="medium")
        for prefix, description in {
            "/skills add": "Create a skill.",
            "/skills update": "Update a skill summary.",
            "/skills body": "Replace a skill body.",
            "/skills append": "Append to a skill body.",
            "/skills tag": "Add a skill tag.",
            "/skills untag": "Remove a skill tag.",
            "/skills use": "Retrieve a skill and increment usage metadata.",
            "/skills archive": "Archive a skill.",
            "/skills restore": "Restore a skill.",
        }.items()
    ],
    *_read_only_specs("world", {"/world status": "Show world-model status.", "/world list": "List world predictions.", "/world inspect": "Inspect a world prediction.", "/world stats": "Show deterministic prediction statistics."}),
    *[
        _spec(prefix, "world", description, read_only=False, mutates="world", risk="medium")
        for prefix, description in {
            "/world predict": "Create a prediction record.",
            "/world expect": "Set an expected signal.",
            "/world observe": "Record an observed outcome.",
            "/world score": "Score an observed prediction.",
            "/world lesson": "Record a prediction lesson.",
            "/world archive": "Archive a prediction.",
            "/world reopen": "Reopen a prediction.",
        }.items()
    ],
    *_read_only_specs(
        "loop",
        {
            "/loop status": "Show cross-module operating-loop status.",
            "/loop morning": "Show a morning operating report.",
            "/loop morning-plan": "Show the detailed morning plan.",
            "/loop evening": "Show an evening operating report.",
            "/loop evening-review": "Show the detailed evening review.",
            "/loop capture-today": "Show a read-only daily capture checklist.",
            "/loop next": "Show the deterministic next action.",
            "/loop doctor": "Diagnose cross-module operating consistency.",
        },
    ),
    *_read_only_specs("identity", {"/identity history": "Show identity change history.", "/identity doctor": "Diagnose identity structure."}),
    *[
        _spec(prefix, "identity", description, read_only=False, mutates="identity", risk="medium", notes=notes)
        for prefix, description, notes in (
            ("/identity status", "Show identity status.", "May initialize conservative defaults when missing."),
            ("/identity show", "Show the current identity profile.", "May initialize conservative defaults when missing."),
            ("/identity set", "Update an allowed identity profile field.", ""),
            ("/identity add-value", "Add an identity value.", ""),
            ("/identity add-principle", "Add an operating principle.", ""),
            ("/identity add-boundary", "Add a safety boundary.", ""),
            ("/identity archive", "Archive an identity item.", ""),
            ("/identity restore", "Restore an identity item.", ""),
        )
    ],
    *_read_only_specs(
        "context",
        {
            "/context status": "Show context-pack module status.",
            "/context build": "Build a fresh read-only context pack report.",
            "/context show": "Build and show a fresh context pack.",
            "/context doctor": "Diagnose context-pack readiness.",
            "/context prompt-preview": "Build a prompt-ready context preview.",
            "/context prompt-doctor": "Diagnose prompt-preview readiness.",
            "/context injection audit": "Show recent injection audit events.",
            "/context injection last": "Show latest injection audit state.",
            "/context injection audit-status": "Show injection audit health.",
            "/context injection audit-doctor": "Diagnose the injection audit file.",
        },
    ),
    _spec("/context export", "context", "Export a context pack.", read_only=False, mutates="exports", risk="medium"),
    _spec("/context prompt-export", "context", "Export a prompt-ready context preview.", read_only=False, mutates="exports", risk="medium"),
    _spec("/context injection status", "context", "Show context-injection settings.", read_only=False, mutates="context", risk="low", notes="May initialize default disabled settings when missing."),
    _spec("/context injection enable", "context", "Explicitly enable preview-safe context injection.", read_only=False, mutates="context", risk="medium"),
    _spec("/context injection disable", "context", "Disable context injection.", read_only=False, mutates="context", risk="medium"),
    _spec("/context injection set-max", "context", "Set the context-injection size limit.", read_only=False, mutates="context", risk="medium"),
    _spec("/context injection preview", "context", "Preview injected context without calling the LLM.", read_only=False, mutates="context", risk="low", notes="Writes a compact audit event only."),
    _spec("/context injection doctor", "context", "Diagnose context-injection readiness.", read_only=False, mutates="context", risk="low", notes="Writes a compact audit event only."),
    *_read_only_specs(
        "consolidation",
        {
            "/consolidation status": "Show consolidation source status.",
            "/consolidation preview": "Preview manual consolidation candidates.",
            "/consolidation export-status": "Show consolidation export status.",
            "/consolidation doctor": "Diagnose consolidation candidates.",
            "/consolidation queue-status": "Show consolidation-queue status.",
            "/consolidation queue-list": "List consolidation-queue items.",
            "/consolidation queue-inspect": "Inspect a consolidation-queue item.",
            "/consolidation queue-apply-receipt": "Show an apply receipt.",
            "/consolidation queue-apply-preview": "Preview whether an approved item can apply.",
            "/consolidation queue-undo-preview": "Show a manual rollback suggestion.",
            "/consolidation queue-doctor": "Diagnose consolidation-queue health.",
            "/consolidation queue-cleanup-preview": "Preview manual queue cleanup.",
        },
    ),
    _spec("/consolidation export", "consolidation", "Export consolidation preview reports.", read_only=False, mutates="exports", risk="medium"),
    _spec("/consolidation queue-export", "consolidation", "Export consolidation queue reports.", read_only=False, mutates="exports", risk="medium"),
    _spec("/consolidation queue-add", "consolidation", "Add a pending consolidation candidate.", read_only=False, mutates="queue", risk="medium"),
    _spec("/consolidation queue-approve", "consolidation", "Approve a queue item without applying it.", read_only=False, mutates="queue", risk="medium"),
    _spec("/consolidation queue-reject", "consolidation", "Reject a queue item.", read_only=False, mutates="queue", risk="medium"),
    _spec("/consolidation queue-archive", "consolidation", "Archive a queue item.", read_only=False, mutates="queue", risk="medium"),
    _spec("/consolidation queue-apply", "consolidation", "Apply one approved allowlisted memory/skill command.", read_only=False, mutates="multiple", risk="high"),
    *_read_only_specs("data", {"/data status": "Show data-store status.", "/data inventory": "Inventory known stores and exports.", "/data doctor": "Diagnose local data integrity.", "/data refs": "Inventory cross-store references.", "/data refs-doctor": "Diagnose cross-store references."}),
    *_read_only_specs("daily", {"/daily status": "Show compact read-only daily operating status.", "/daily brief": "Build a deterministic local daily operating brief.", "/daily doctor": "Diagnose Daily Layer registration and safety invariants.", "/daily next": "Suggest safe manual next steps without execution."}),
    *_read_only_specs("milestone", {"/milestone status": "Show compact read-only roadmap status.", "/milestone list": "List locally documented milestone records without invention.", "/milestone current": "Show detected facts and inferred current operating phase.", "/milestone next": "Suggest safe manual milestone actions without execution.", "/milestone doctor": "Diagnose milestone-layer sources and safety invariants."}),
    *_read_only_specs("warnings", {"/warnings status": "Show compact read-only warning status and classifications.", "/warnings list": "List current doctor findings with deterministic diagnostic ids.", "/warnings inspect": "Explain warning impact and manual options without repair.", "/warnings accepted": "Summarize findings matching narrow accepted-known warning rules.", "/warnings accepted-ledger": "Print the local accepted-known warning documentation without updating it.", "/warnings unknown": "List current findings not matched by accepted-known rules.", "/warnings doctor": "Diagnose warning-inspector dependencies and safety invariants."}),
    *_read_only_specs("agenda", {"/agenda status": "Show live read-only operator-agenda readiness.", "/agenda next": "Suggest one conservative manual next action without execution.", "/agenda list": "Build a short live manual work queue without persistence.", "/agenda doctor": "Diagnose Agenda dependencies and read-only safety invariants."}),
    *_read_only_specs("prechange", {"/prechange status": "Show deterministic read-only pre-change readiness.", "/prechange checklist": "Print the manual Rule 0 and verification checklist without execution.", "/prechange doctor": "Diagnose pre-change dependencies and safety invariants.", "/prechange handoff": "Print a copyable pre-change task header without writing files."}),
    *_read_only_specs("focus", {"/focus status": "Show planning-only focus readiness.", "/focus plan": "Generate a deterministic local focused-session plan without execution.", "/focus checklist": "Print a focused manual work checklist without persistence.", "/focus doctor": "Diagnose Focus Mode dependencies and safety invariants.", "/focus handoff": "Print a copyable focused-session handoff without writing files."}),
    *_read_only_specs("acceptance", {"/acceptance status": "Show human-review-only acceptance readiness.", "/acceptance checklist": "Print the manual implementation-result review checklist.", "/acceptance criteria": "Print reusable acceptance blockers, evidence, and safety criteria.", "/acceptance decision-guide": "Print the deterministic human decision framework without inspecting a report.", "/acceptance doctor": "Diagnose Acceptance Review dependencies and safety invariants.", "/acceptance handoff": "Print copyable acceptance-review instructions without writing files."}),
    *_read_only_specs("baseline", {"/baseline status": "Show read-only accepted-baseline awareness and readiness.", "/baseline current": "Show detected and inferred current baseline facts without persistence.", "/baseline latest": "Show latest existing snapshot and diff baseline signals.", "/baseline checklist": "Print the manual post-acceptance baseline checklist without execution.", "/baseline doctor": "Diagnose Baseline Registry dependencies and safety invariants.", "/baseline handoff": "Print a copyable accepted-baseline handoff without writing files."}),
    *_read_only_specs("closure", {"/closure status": "Show read-only post-acceptance closure readiness.", "/closure summary": "Print a live milestone/session closure summary without persistence.", "/closure next": "Suggest one safe manual post-acceptance action without execution.", "/closure handoff": "Print copyable context for the next operator session.", "/closure doctor": "Diagnose Closure Layer dependencies and safety invariants."}),
    *_read_only_specs("memory-card", {"/memory-card status": "Show read-only Operator Memory Card readiness.", "/memory-card short": "Print a compact project-state card for a new chat session.", "/memory-card full": "Print a structured project-state card without persistence.", "/memory-card codex": "Print a concise reusable Codex context header.", "/memory-card doctor": "Diagnose Memory Card dependencies and safety invariants."}),
    *_read_only_specs("capabilities", {"/capabilities status": "Show read-only capability-map readiness and family counts.", "/capabilities list": "List registered command families and Registry-derived modes.", "/capabilities map": "Map operator command families to manual workflow phases.", "/capabilities safety": "Explain Registry and Action Policy safety classifications.", "/capabilities doctor": "Diagnose Capability Map dependencies and safety invariants.", "/capabilities handoff": "Print copyable command-family and safety-gate context."}),
    *_read_only_specs("plan", {"/plan status": "Show read-only dry-run planning readiness.", "/plan next": "Propose one conservative manual next-action plan without execution.", "/plan dry-run": "Print a reusable deterministic dry-run action template.", "/plan gates": "Print required gates before future execution-capable work.", "/plan doctor": "Diagnose Plan Layer dependencies and safety invariants.", "/plan handoff": "Print copyable dry-run planning requirements and evidence fields."}),
    *_read_only_specs("confirm", {"/confirm status": "Show read-only confirmation-vocabulary readiness.", "/confirm policy": "Print advisory confirmation and authorization policy rules.", "/confirm levels": "Print future authorization-level vocabulary without granting access.", "/confirm requirements": "Print class-specific confirmation requirements and gates.", "/confirm doctor": "Diagnose Confirmation Vocabulary dependencies and safety invariants.", "/confirm handoff": "Print copyable authorization-design constraints without approval capture."}),
    *_read_only_specs("sandbox", {"/sandbox status": "Show read-only execution-sandbox design readiness.", "/sandbox blueprint": "Print the future command-runner architecture without execution code.", "/sandbox boundaries": "Print advisory future filesystem and operation boundaries.", "/sandbox allowlist": "List conservative FUTURE_CANDIDATE commands without activation.", "/sandbox denied": "List denied future runner command and operation classes.", "/sandbox doctor": "Diagnose Sandbox Blueprint dependencies and safety invariants.", "/sandbox handoff": "Print copyable future runner design constraints without execution."}),
    *_read_only_specs("runner", {"/runner status": "Show read-only no-op runner-contract readiness.", "/runner contract": "Print future runner request/response fields and fixed no-op invariants.", "/runner noop": "Print a sample no-op response without executing its command candidate.", "/runner evidence": "Print the future evidence model with current NOT_AVAILABLE_NOOP values.", "/runner disabled": "Explain why runner execution and allowlisting remain disabled.", "/runner doctor": "Diagnose No-Op Runner Contract dependencies and safety invariants.", "/runner handoff": "Print copyable future runner interface constraints without execution."}),
    *_read_only_specs("runner-candidates", {"/runner-candidates status": "Show read-only future runner-candidate readiness.", "/runner-candidates list": "List static FUTURE_CANDIDATE commands without activation.", "/runner-candidates explain": "Explain candidate Registry/Policy metadata and limitations.", "/runner-candidates denied": "List commands and operations excluded from the candidate set.", "/runner-candidates gates": "Print gates required before any future candidate activation.", "/runner-candidates doctor": "Diagnose candidate-set metadata and no-activation invariants.", "/runner-candidates handoff": "Print copyable candidate-set constraints without activation."}),
    *_read_only_specs("activation", {"/activation status": "Show read-only future runner activation-design readiness.", "/activation preconditions": "Print mandatory preconditions for a separately approved future runner.", "/activation checklist": "Print a non-persistent operator checklist for future runner design.", "/activation blockers": "Distinguish current design blockers from actual-execution blockers.", "/activation forbidden": "List actions forbidden before a separately approved runner milestone.", "/activation doctor": "Diagnose activation-precondition dependencies and no-activation invariants.", "/activation handoff": "Print copyable future activation constraints without enabling execution."}),
    *_read_only_specs("runner-mvp", {"/runner-mvp status": "Show read-only MVP design-lock readiness.", "/runner-mvp design": "Print the locked future read-only runner architecture without implementation.", "/runner-mvp allowlist": "Print five proposed inactive MVP allowlist candidates.", "/runner-mvp confirmation": "Print command-specific future confirmation rules without capture.", "/runner-mvp evidence": "Print the locked future evidence model with design-only values.", "/runner-mvp stop-conditions": "Print fail-closed future runner refusal conditions.", "/runner-mvp doctor": "Diagnose MVP design-lock metadata and no-execution invariants.", "/runner-mvp handoff": "Print copyable future MVP implementation constraints without activation."}),
    *_read_only_specs("runner-exec", {"/runner-exec status": "Show four-command read-only runner status and in-memory evidence availability.", "/runner-exec allowlist": "Show the exact four-command active read-only allowlist.", "/runner-exec dry-run": "Preview an exact allowlisted target without running it.", "/runner-exec evidence": "Show the latest current-process-only runner evidence.", "/runner-exec refusal-matrix": "Show static fail-closed expectations for invalid runner requests without executing them.", "/runner-exec last-refusal": "Show the latest current-process refusal evidence.", "/runner-exec evidence-check": "Validate current-process success/refusal evidence shape, ring bounds, and no-persistence invariants.", "/runner-exec history": "Show the compact process-memory runner evidence ring.", "/runner-exec history-summary": "Summarize compact runner history counts and latest signals.", "/runner-exec history-clear-preview": "Preview clearing process-memory history without mutation.", "/runner-exec history-doctor": "Diagnose evidence ring bounds, compactness, allowlist scope, and no-persistence invariants.", "/runner-exec stability": "Summarize current four-command runner stability and bounded evidence state.", "/runner-exec sequence-plan": "Print a deterministic multi-command smoke sequence without executing it.", "/runner-exec sequence-evidence": "Show bounded current-process multi-command evidence counters and latest records.", "/runner-exec consistency-check": "Validate exact allowlist, confirmation, callback, evidence, and context consistency without execution.", "/runner-exec soak": "Summarize four-command soak readiness, bounded evidence counts, and safety limits.", "/runner-exec soak-plan": "Print a deterministic four-command safety soak sequence without executing it.", "/runner-exec soak-report": "Show bounded current-process soak results and per-command latest successes.", "/runner-exec drift-check": "Validate that allowlist, callbacks, confirmations, evidence, context, and no-write policy have not drifted.", "/runner-exec doctor": "Diagnose exact allowlist, confirmation, evidence, transport, consistency, drift, history, and no-write invariants.", "/runner-exec handoff": "Print copyable four-command runner usage and safety constraints."}),
    _spec("/runner-exec run", "runner-exec", "Execute one exact fixed internal allowlisted target after command-specific confirmation.", read_only=True, mutates="none", risk="medium", notes="Four-command pilot; dedicated zero-argument callbacks and in-memory evidence only."),
    *_read_only_specs("exports", {"/exports status": "Show compact export retention status.", "/exports inventory": "Inventory known export directories and file health.", "/exports cleanup-preview": "Preview descriptive export retention actions without mutation.", "/exports doctor": "Diagnose export JSON validity, pairing, size, and availability."}),
    *_read_only_specs("natural", {"/natural status": "Show natural-router status.", "/natural list": "List exact natural phrases.", "/natural explain": "Explain an exact natural phrase.", "/natural suggest": "Suggest close exact natural phrases without execution.", "/natural doctor": "Diagnose natural-route safety."}),
    *_read_only_specs("commands", {"/commands status": "Show command-registry status.", "/commands list": "List registered commands.", "/commands explain": "Explain command metadata by longest prefix.", "/commands doctor": "Diagnose command-registry consistency."}),
    *_read_only_specs("policy", {"/policy status": "Show advisory action-policy status.", "/policy explain": "Explain the safety class of a slash command.", "/policy doctor": "Diagnose action-policy invariants."}),
    *_read_only_specs("proto", {"/proto status": "Show the top-level Proto-Mind system overview.", "/proto doctor": "Aggregate major read-only subsystem doctors.", "/proto next": "Show aggregated deterministic next-step signals.", "/proto warnings": "Triage major subsystem warnings without repair.", "/proto warnings-explain": "Explain known warning types and manual inspection paths.", "/proto cleanup-preview": "Preview ordered manual warning cleanup without mutation.", "/proto snapshot": "Build a read-only structured system snapshot.", "/proto snapshot-status": "Show Proto snapshot export status without creating files.", "/proto snapshot-list": "List exported Proto snapshot JSON files.", "/proto snapshot-diff": "Compare two Proto snapshot JSON files without mutation.", "/proto snapshot-diff-latest": "Compare the two newest Proto snapshot JSON exports.", "/proto snapshot-diff-status": "Show snapshot diff export status without creating files."}),
    _spec("/proto snapshot-export", "proto", "Export a Proto system snapshot as Markdown and JSON.", read_only=False, mutates="exports", risk="medium"),
    _spec("/proto snapshot-diff-export", "proto", "Export one structured snapshot diff as Markdown and JSON.", read_only=False, mutates="exports", risk="medium"),
    _spec("/proto snapshot-diff-export-latest", "proto", "Export the newest snapshot pair diff as Markdown and JSON.", read_only=False, mutates="exports", risk="medium"),
    *_read_only_specs("action", {"/action status": "Show action-preview status.", "/action preview": "Resolve a command or exact natural phrase without execution.", "/action doctor": "Diagnose action-preview invariants."}),
    *_read_only_specs(
        "action",
        {
            "/action proposals": "List action proposals.",
            "/action inspect": "Inspect stored action proposal metadata.",
            "/action queue-status": "Show action proposal queue status.",
            "/action cleanup-preview": "Preview manual action queue cleanup without mutation.",
            "/action confirm-preview": "Preview metadata-only confirmation eligibility and token.",
            "/action run-preview": "Preview future run readiness without execution.",
            "/action run-receipt": "Inspect a stored read-only action execution receipt.",
            "/action runs": "List executed action proposal receipts.",
            "/action run-verify": "Verify one executed action receipt.",
            "/action run-audit": "Audit all action execution receipts.",
            "/action readiness-doctor": "Diagnose confirmed proposal run readiness.",
            "/action queue-doctor": "Diagnose the action proposal queue.",
        },
    ),
    _spec("/action queue-export", "action", "Export action proposal queue reports.", read_only=False, mutates="exports", risk="medium"),
    _spec("/action run", "action", "Execute one confirmed read-only auto-allowed proposal.", read_only=False, mutates="queue", risk="high"),
    *[
        _spec(prefix, "action", description, read_only=False, mutates="queue", risk="medium")
        for prefix, description in {
            "/action propose": "Store an action preview for operator review.",
            "/action approve": "Approve an action proposal for recordkeeping only.",
            "/action reject": "Reject an action proposal.",
            "/action archive": "Archive an action proposal.",
            "/action confirm": "Confirm an approved proposal as queue metadata only.",
            "/action unconfirm": "Remove confirmation state from an action proposal.",
        }.items()
    ],
]


def _natural_targets() -> set[str]:
    targets: set[str] = set()
    for target in NATURAL_COMMAND_ROUTES.values():
        if isinstance(target, str):
            targets.add(target)
        else:
            targets.update(target)
    return targets


_NATURAL_TARGETS = _natural_targets()
COMMAND_REGISTRY = tuple(
    replace(spec, available_in_natural_router=spec.prefix in _NATURAL_TARGETS)
    for spec in _BASE_REGISTRY
)


def format_commands_command(command: str) -> str | None:
    stripped = command.strip()
    normalized = " ".join(stripped.lower().split())
    if not normalized.startswith("/commands"):
        return None
    if normalized == "/commands status":
        return format_command_status()
    if normalized == "/commands list":
        return format_command_list()
    if normalized == "/commands doctor":
        return format_command_doctor()
    if normalized.startswith("/commands explain"):
        query = stripped[len("/commands explain") :].strip()
        if not query:
            return "Usage: /commands explain <slash command>"
        return format_command_explain(query)
    return "Usage:\n  /commands status\n  /commands list\n  /commands explain <slash command>\n  /commands doctor"


def format_command_status(registry: Iterable[CommandSpec] = COMMAND_REGISTRY) -> str:
    specs = list(registry)
    categories = Counter(spec.category for spec in specs)
    risks = Counter(spec.risk for spec in specs)
    read_only_count = sum(1 for spec in specs if spec.read_only)
    lines = [
        "Command Registry Status",
        f"registered_commands: {len(specs)}",
        f"read_only: {read_only_count}",
        f"mutating: {len(specs) - read_only_count}",
        "category_counts:",
    ]
    lines.extend(f"- {name}: {categories[name]}" for name in sorted(categories))
    lines.append("risk_counts:")
    lines.extend(f"- {name}: {risks[name]}" for name in sorted(risks))
    lines.extend(["", "Available commands:", "- /commands status", "- /commands list", "- /commands explain <slash command>", "- /commands doctor"])
    return "\n".join(lines)


def format_command_list(registry: Iterable[CommandSpec] = COMMAND_REGISTRY) -> str:
    specs = list(registry)
    lines = ["Command Registry"]
    for category in sorted({spec.category for spec in specs}):
        lines.extend(["", f"{category}:"])
        for spec in sorted((item for item in specs if item.category == category), key=lambda item: item.prefix):
            mode = "read-only" if spec.read_only else f"mutates={spec.mutates}"
            natural = " natural" if spec.available_in_natural_router else ""
            lines.append(f"- {spec.prefix} [{mode} risk={spec.risk}{natural}] — {spec.description}")
    return "\n".join(lines)


def match_registered_command(query: str, registry: Iterable[CommandSpec] = COMMAND_REGISTRY) -> CommandSpec | None:
    normalized = " ".join(query.strip().lower().split())
    matches = [spec for spec in registry if normalized == spec.prefix or normalized.startswith(spec.prefix + " ")]
    return max(matches, key=lambda spec: len(spec.prefix), default=None)


def format_command_explain(query: str) -> str:
    spec = match_registered_command(query)
    if spec is None:
        return "\n".join(["Command Registry Explain", f"input: {query}", "matched: False", "Command not registered.", "No command executed."])
    return "\n".join(
        [
            "Command Registry Explain",
            f"input: {query}",
            "matched: True",
            f"command_prefix: {spec.prefix}",
            f"category: {spec.category}",
            f"description: {spec.description}",
            f"read_only: {spec.read_only}",
            f"mutates: {spec.mutates}",
            f"risk: {spec.risk}",
            f"available_in_natural_router: {spec.available_in_natural_router}",
            f"notes: {spec.notes or 'none'}",
            "No command executed.",
        ]
    )


def command_registry_doctor(registry: Iterable[CommandSpec] = COMMAND_REGISTRY) -> dict[str, Any]:
    specs = list(registry)
    findings: list[dict[str, str]] = []
    prefixes = [spec.prefix for spec in specs]
    duplicates = sorted(prefix for prefix, count in Counter(prefixes).items() if count > 1)
    if duplicates:
        findings.append({"severity": "ERROR", "message": f"Duplicate command prefixes: {', '.join(duplicates)}"})
    for index, spec in enumerate(specs, start=1):
        label = spec.prefix or f"entry#{index}"
        if not spec.prefix.startswith("/"):
            findings.append({"severity": "ERROR", "message": f"Command prefix must start with '/': {label}"})
        if not spec.description.strip():
            findings.append({"severity": "ERROR", "message": f"Empty command description: {label}"})
        if spec.category not in VALID_CATEGORIES:
            findings.append({"severity": "ERROR", "message": f"Invalid category for {label}: {spec.category}"})
        if spec.risk not in VALID_RISKS:
            findings.append({"severity": "ERROR", "message": f"Invalid risk for {label}: {spec.risk}"})
        if spec.mutates not in VALID_MUTATES:
            findings.append({"severity": "ERROR", "message": f"Invalid mutates value for {label}: {spec.mutates}"})
        if spec.read_only and spec.mutates != "none":
            findings.append({"severity": "ERROR", "message": f"Read-only command declares mutation: {label}"})
        if not spec.read_only and spec.mutates == "none":
            findings.append({"severity": "ERROR", "message": f"Mutating command has mutates=none: {label}"})
        if spec.available_in_natural_router and spec.risk == "high":
            findings.append({"severity": "ERROR", "message": f"High-risk command exposed to natural router: {label}"})

    by_prefix = {spec.prefix: spec for spec in specs}
    for target in sorted(_NATURAL_TARGETS):
        spec = by_prefix.get(target)
        if spec is None:
            findings.append({"severity": "ERROR", "message": f"Natural router target missing from registry: {target}"})
            continue
        if not spec.available_in_natural_router:
            findings.append({"severity": "ERROR", "message": f"Natural router target not marked available: {target}"})
        if target in {"/context injection enable", "/context injection disable"} and (spec.read_only or spec.mutates == "none"):
            findings.append({"severity": "ERROR", "message": f"Mutating natural route not explicitly marked mutating: {target}"})

    status = "ERROR" if any(item["severity"] == "ERROR" for item in findings) else "WARN" if findings else "OK"
    return {"status": status, "registered_commands": len(specs), "findings": findings}


def format_command_doctor() -> str:
    report = command_registry_doctor()
    lines = ["Command Registry Doctor", f"Status: {report['status']}", f"Commands checked: {report['registered_commands']}", "", "Findings:"]
    if report["findings"]:
        lines.extend(f"- [{item['severity']}] {item['message']}" for item in report["findings"])
    else:
        lines.append("- [OK] Registry metadata and natural-router references are consistent.")
    lines.extend(["", "Mutation policy:", "- Read-only diagnostics only; no commands were executed and no stores were changed."])
    return "\n".join(lines)
