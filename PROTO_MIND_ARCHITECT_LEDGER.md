# Proto-Mind Architect Ledger v1.0

Purpose: compact architectural memory for future Codex prompts. Keep this file short, current, and operator-readable so future tasks do not need to restate the whole project history.

Last updated: 2026-07-19

## Current Stable State

- Proto-Mind is a local-first cognitive architecture prototype, not a model-training project, consciousness claim, autonomous agent, or polished consumer chatbot.
- Primary CLI launch: `scripts/run_cli.sh`.
- Direct Python fallback: `/opt/homebrew/opt/python@3.11/bin/python3.11 -m proto_mind.main`.
- Desktop launch paths:
  - Tkinter fallback: `scripts/run_desktop_mock.sh`, `scripts/run_desktop_ollama.sh`.
  - PySide6 UI: `scripts/run_pyside_mock.sh`, `scripts/run_pyside_ollama.sh`.
  - Local macOS launcher: `dist/Proto-Mind.app`.
- Python 3.11+ is required. `proto_mind.main` exits cleanly on unsupported Python.
- Reasoner backend is selected by env/config:
  - default mock backend.
  - Ollama via `PROTO_MIND_REASONER=ollama`, `PROTO_MIND_OLLAMA_MODEL`, `PROTO_MIND_OLLAMA_URL`.
- Normal prompts go through observer, retrieval, reasoner, memory evaluation, self-reflection, grounding audit, and session logging.
- Slash/operator commands bypass normal cognitive turns and should not become cognitive session log turns.
- Supervised Experience Pilot v3.3a observes consented turns; v3.3b projects episodes; v3.3c previews candidates; v3.3d captures decisions; v3.3e reviews selected-scope eligibility; v3.3f records proposals; v3.3g revalidates apply readiness; v3.4a permits one separately confirmed, atomic, verified memory lesson; v3.4b embeds restart-safe compact provenance; v3.4c permits only verified learned lessons into recall; v3.4d reviews later outcomes; v3.4e records an exact operator lifecycle decision without mutating the lesson. Review/proposal/lifecycle/detailed-receipt state remains bounded and process-memory-only; no automatic apply exists.
- Build Week submission provenance uses the July 11 pre-contest archive SHA-256 plus generated baseline/current/delta manifests; prior work and contest work are explicitly separated.
- Primary Build Week Codex `/feedback` Session ID is `019d73be-1d7e-7401-8efe-f5e165736db4`.
- Repository privacy review excludes local cognitive/runtime stores, removes user-specific checkout paths from public artifacts, and documents synthetic credential fixtures and publication boundaries.
- Public source licensing is Apache License 2.0; no runtime store or export is licensed or published because those paths remain Git-ignored.
- Context Injection v1.2 is disabled by default and only applies to normal prompts after explicit operator enablement.

## Current Verification Baseline

- Current test command: `scripts/run_tests.sh`.
- Current test count: 937 unit tests OK.
- Compile check: `python -m compileall proto_mind` via `scripts/run_tests.sh` OK.
- Pytest: optional; currently not installed and skipped cleanly.

## Major Modules And Versions

- Python 3.11 Environment Guard v1.0: stable Python selector scripts and early runtime guard.
- CLI/shared handler: `proto_mind.main`, reused by CLI, tkinter desktop, and PySide desktop.
- Tkinter Desktop v0.5: compact/debug chat, system panel, clipboard fixes, transcript export, prefs.
- PySide6 Desktop UI v1.5.2: dark UI, worker thread, Stop skeleton, markdown rendering, local macOS `.app` launcher, Desktop shortcut helper.
- Session Control Room: `/session self-check`, `/session health`, `/session doctor`, `/session review`, `/session log ...`, plus Session Rituals v1 read-only start/end/checkpoint/handoff briefs.
- Natural Command Router v2.3: exact routes plus policy-aware registry metadata in `/natural explain|list|doctor`, with suggestions still non-executing.
- Command Registry v1.0: metadata for 363 slash-command prefixes across 41 categories with mutation/risk labels and Natural Router consistency checks.
- Action Safety Policy v1.0: read-only advisory classification into auto-allowed, confirmation-required, operator-only, or blocked without execution/enforcement.
- Action Preview v1.0: read-only slash/natural resolution into registry- and policy-aware execution plans without command execution.
- Action Proposal Queue v1.5.2: run-once read-only execution plus receipt history, verification, and global audit.
- Memory v2.0 Explicit Memory Control: `/memory status/list/remember/inspect/search/forget`.
- Memory v2.1 Doctor: deterministic read-only memory health diagnostics.
- Reflection Journal v1.0: deterministic session-log reflections in `proto_mind/data/reflection_journal.jsonl`.
- Goal Stack v1.0: local goals in `proto_mind/data/goals.jsonl`, one focused goal at a time.
- Task Queue v1.0: local tasks in `proto_mind/data/tasks.jsonl`, optional `goal_id` link, deterministic `/tasks next`.
- Experiment Journal v1.0: hypothesis/prediction/method/result/reflection/lesson cycle in `proto_mind/data/experiments.jsonl`.
- Skill Library v1.0: procedural memory in `proto_mind/data/skills.jsonl`, retrieve-and-mark-used only.
- World Model Lite v1.0: prediction-vs-reality records in `proto_mind/data/world_model.jsonl`, 0..5 scoring.
- Operating Loop v1.1: read-only cross-module reports, deterministic next-action suggestions, and daily capture workflow commands.
- Memory Consolidation Preview v1.3.1: read-only suggestions, Markdown/JSON exports, safe queue, queue doctor/cleanup preview, approved-only allowlisted apply, structured apply receipts, and undo preview.
- Identity / Values v1.0: inspectable profile/values/principles/boundaries/history in `proto_mind/data/identity.json`.
- Context Pack v1.0: read-only context assembly and Markdown/JSON export.
- Context Prompt Preview v1.1: prompt-ready preview/export with safety footer, no automatic injection.
- Context Injection v1.2: manual preview-safe normal-prompt injection, disabled by default.
- Context Injection Audit v1.2.1: compact JSONL flight recorder for injection events in `proto_mind/data/context_injection_audit.jsonl`.
- Data Integrity Doctor v1.1: top-level read-only `/data status|inventory|doctor|refs|refs-doctor` checks for local stores and cross-store references.
- Proto Status / Doctor v1.4: top-level overview/triage plus snapshot and snapshot-diff Markdown/JSON exports, listing, status, and deterministic comparison commands.
- Export Retention / Cleanup Preview v1.5: read-only `/exports status|inventory|cleanup-preview|doctor` over all seven known export directories.
- Operating Loop v2 / Daily Agent Layer v1: deterministic read-only `/daily status|brief|doctor|next` over registry, exports, snapshots, warnings, context state, and existing operating-loop signals.
- Operating Loop v2.1 / Session Rituals v1: deterministic live `/session start-brief|end-summary|checkpoint-advice|handoff-brief` reports with no persistence, command execution, or state mutation.
- Operating Loop v2.2 / Milestone Tracker v1: deterministic read-only `/milestone status|list|current|next|doctor` roadmap awareness from existing Ledger/docs, with facts/inference separation and manual-only guidance.
- Legacy Warning Inspector v1: read-only `/warnings status|list|inspect|doctor` over existing Proto doctor findings, with deterministic IDs, classification, source hints, and no repairs.
- Known Warnings Ledger v1: docs-only `KNOWN_WARNINGS_LEDGER.md` plus read-only `/warnings accepted|accepted-ledger|unknown`; narrow accepted rules do not hide source warnings or mutate queues.
- Operating Loop v2.3 / Operator Agenda v1: live read-only `/agenda status|next|list|doctor` with conservative unknown-warning-first priority and no persistent queue or command execution.
- Operating Loop v2.4 / Pre-Change Ritual v1: read-only `/prechange status|checklist|doctor|handoff` for Rule 0, readiness, verification, smoke, and runtime SHA guidance without backup/snapshot creation.
- Operating Loop v2.5 / Focus Mode v1: read-only `/focus status|plan|checklist|doctor|handoff` for one scoped manual work block with no execution or persisted focus/session state.
- Operating Loop v2.6 / Acceptance Review v1: read-only `/acceptance status|checklist|criteria|decision-guide|doctor|handoff` for human result review with no automatic decision or persisted review state.
- Snapshot Baseline Registry v1: read-only `/baseline status|current|latest|checklist|doctor|handoff` for accepted-baseline awareness from local Ledger, Acceptance, warning, Context Injection, and existing snapshot/diff signals without runtime persistence.
- Operating Loop v2.7 / Post-Acceptance Closure v1: read-only `/closure status|summary|next|handoff|doctor` for live milestone closure, next-session transfer through Memory Card, and manual v2.9 selection without persisted closure state.
- Operating Loop v2.8 / Operator Memory Card v1: read-only `/memory-card status|short|full|codex|doctor` for compact chat continuity, structured project review, and reusable Codex task context without persistent card state.
- Operating Loop v2.9 / Command Capability Map v1: read-only `/capabilities status|list|map|safety|doctor|handoff` for Registry-derived family discovery, workflow phases, policy-aware safety classification, and copyable capability context leading into dry-run planning.
- Operating Loop v2.10 / Dry-Run Intent Layer v1: read-only `/plan status|next|dry-run|gates|doctor|handoff` for deterministic manual action proposals, mandatory gates, verification evidence, and stop conditions without execution or authorization.
- Operating Loop v2.11 / Confirmation Gate and Authorization Vocabulary v1: read-only `/confirm status|policy|levels|requirements|doctor|handoff` for advisory authorization classes and future execution gates without confirmation capture, approval persistence, authorization, or execution.
- Operating Loop v2.12 / Execution Sandbox Design and Command Runner Blueprint v1: read-only `/sandbox status|blueprint|boundaries|allowlist|denied|doctor|handoff` for future runner architecture, strict boundaries, design-only candidates, denied classes, evidence, and gates without an execution path.
- Operating Loop v2.13 / Read-only Runner Interface Spec and No-Op Executor Contract v1: read-only `/runner status|contract|noop|evidence|disabled|doctor|handoff` for deterministic future request/response and evidence shapes with execution permanently false in this layer.
- Operating Loop v2.14 / Read-only Command Runner Candidate Set v1: read-only `/runner-candidates status|list|explain|denied|gates|doctor|handoff` for 13 Registry-verified future candidates that remain explicitly inactive and non-executable.
- Operating Loop v2.15 / Runner Activation Preconditions v1: read-only `/activation status|preconditions|checklist|blockers|forbidden|doctor|handoff` distinguishing safe future design consideration from actual execution, which remains blocked.
- v3.0a / Read-only Runner MVP Design Lock: read-only `/runner-mvp status|design|allowlist|confirmation|evidence|stop-conditions|doctor|handoff` locking a five-command future MVP design without implementation or activation.
- v3.0b / Real Read-only Runner MVP: `/runner-exec status|allowlist|dry-run|run|evidence|doctor|handoff` activates exactly `/warnings unknown` behind exact per-run confirmation, fixed internal dispatch, SHA-256 no-write evidence, and fail-closed gates.
- v3.0c / Runner Evidence Hardening: read-only `/runner-exec refusal-matrix|last-refusal|evidence-check` adds deterministic refusal documentation, separate current-process success/refusal evidence, redacted mismatch fingerprints, and evidence-shape validation without expanding execution.
- v3.0d / Daily Doctor Runner Pilot: expands the active allowlist by exactly `/daily doctor`, using a second dedicated zero-argument callback and command-specific exact confirmation while preserving all v3.0c evidence/refusal gates.
- v3.0e / Exports Doctor Runner Pilot: expands the active allowlist by exactly `/exports doctor`, using a third dedicated zero-argument callback and recording `export_doctor_status` without adding generic dispatch.
- v3.0f / Runner Multi-Command Stability Review: adds read-only stability, sequence-plan, bounded sequence-evidence, and consistency-check reports without changing the three-command execution allowlist.
- v3.0g / Capabilities Safety Runner Pilot: expands the active allowlist by exactly `/capabilities safety`, using a fourth dedicated zero-argument callback and compact Registry/Policy evidence summary.
- v3.0h / Runner Four-Command Safety Soak: adds read-only soak, soak-plan, soak-report, and drift-check diagnostics over the unchanged four-command allowlist.
- v3.0i / Runner Evidence History Ring Buffer: adds read-only history, summary, clear-preview, and doctor commands over a compact 20-event process-memory ring without expanding execution or persistence.
- v3.1a / Bilingual Cognitive Baseline: deterministic Russian/English observer, canonical topic extraction, durable preference/decision handling, and a 10-case no-LLM benchmark without changing commands, schemas, runner scope, or Context Injection.
- v3.1b / Memory Write Governance: pure retrieval by default, explicit usage telemetry, compact user-input-only automatic memory, and read-only policy/migration-preview commands without cleanup or schema changes.
- v3.1c / Bilingual Grounding and Reflection: shared English/Russian response signals, source-aware grounding evidence, and a 20-case observer-plus-response benchmark without new commands, schemas, or store writes.
- v3.1d / Cognitive Continuity Soak: deterministic 25-turn Coordinator scenario with bounded temporary memory, 21/21 byte-stable read-only turns, recall/override/history/correction checks, and no live-state access.
- v3.2a / Experience Ledger Foundation: typed compact cognitive events, explicit provenance graph, privacy/ordering doctor, and 180-event in-memory soak trace without live persistence.
- v3.2b / Experience Ledger Persistence Policy: temporary-only atomic JSONL append, SHA-256 hash chain, fail-closed corruption handling, and live data path refusal.
- v3.2c / Experience Ledger Live Capture Gate: read-only missing-config defaults, status/preview/doctor reports, and a hard absent-hook boundary without command expansion.
- v3.2d / Experience Event Vocabulary v2: typed goal/plan/tool/outcome/correction/reflection/lesson/promotion evidence with central payload and provenance contracts.
- v3.2e / Experience Trace Explainability: immutable event index, source-chain traversal, entity lookup, trace maps, and safety-aware deterministic “why” reports.
- v3.2f / Experience Episode Projection: compact read-only goal/plan/action/outcome/reflection/lesson episodes with verified terminal states and exact source-event provenance.
- v3.2g / Experience Learning Candidate Review: deterministic review eligibility, evidence, confirmation, and exact-duplicate classification with automatic apply permanently disabled.
- v3.2h / Session Capture Design Review: `KEEP_DISABLED` design lock for explicit per-session consent, privacy, retention, bypass, and failure isolation with implementation authorization false.
- v3.2i / Learning Review Input Adapter: explicit-ID detached active memory/skill snapshots for deterministic duplicate review without retrieval, telemetry, automatic selection, or mutation.
- v3.2j / Session Consent State Machine Spec: stateless preview/exact-consent/stop/expiry modeling with normal-prompt-only scope and a fail-closed refusal matrix, without stored consent or capture.
- v3.2k / Experience Privacy Redaction Benchmark: deterministic credential-like filtering before preview truncation, stable placeholders, benign controls, and Doctor enforcement without live capture or persistence.
- v3.2l / Experience Capture Bounded-Growth Soak: bounded 36-turn consent/redaction simulation with fail-closed per-turn, event, and byte limits, no files, and no activation authorization.
- v3.2m / Experience Capture Activation Readiness Review: ten-source evidence matrix that clears a separate supervised in-memory pilot design while runtime capture remains disabled and unauthorized.
- v3.3a / Supervised In-Memory Experience Pilot: explicit preview/exact-consent process-session observation of normal turns into a redacted 256-event/512-KiB buffer, with visible evidence, provenance inspection, stop, and fail-closed behavior but no persistence or automatic learning.
- v3.3b / Cognitive Turn Episode View: read-only `/experience episodes` and `/experience episode [latest|<turn_id>]` connect observation, intent, recall, response, memory decision, reflection, grounding, and exact provenance without persistence or summarization.
- v3.3c / Operator-Reviewed Learning Bridge Preview: read-only `/experience learning status|preview [latest|<turn_id>]|doctor` turns only explicit redacted correction/reflection/grounding findings into bounded, evidence-linked review candidates; clean turns create none, and confirmation/apply/promotion/persistence remain unavailable.
- v3.3d / Learning Candidate Confirmation Design: one process-memory `/experience learning decide` prefix records terminal accept/reject receipts; exact candidate tokens, a 64-receipt cap, restart expiry, tamper checks, and `executable=false` promotion previews keep persistence and apply unavailable.
- v3.3e / Learning Promotion Eligibility Review: read-only target-specific exact duplicate checks over accepted candidates and operator-selected detached memory/skill IDs, with explicit selected-scope limits and no retrieval, promotion, apply, or persistence.
- v3.3f / Learning Promotion Proposal Receipt: fixed target schemas, selected-scope SHA-256 binding, exact tokens, and immutable 32-item process-memory proposal receipts without apply readiness, execution, or domain persistence.
- v3.3g / Learning Promotion Apply Readiness Review: read-only current-evidence/hash revalidation plus future atomic receipt and rollback requirements, with no apply command, engine, mutation, or persistence.
- v3.4a / Supervised Memory Lesson Promotion Pilot: one fresh exact-token `memory.lesson.v1` apply per process, bound to current store SHA, with global exact-duplicate defense, atomic write, verified receipt, run-once guard, and rollback suggestion.
- v3.4b / Durable Learning Provenance: embedded hashed candidate-to-proposal evidence in applied lessons, read-only `/memory why <id>`, restart survival, and Memory Doctor tamper detection without another persistence path.
- v3.4c / Verified Lesson Recall: provenance-gated active lesson retrieval, compact grounding evidence, fail-closed legacy/tamper filtering, and a byte-stable English/Russian restart benchmark without command or writer expansion.
- v3.4d / Learning Outcome Review: exact post-apply Experience lineage produces advisory keep/reject/supersede candidates or insufficient evidence without Registry expansion, apply, or mutation.
- v3.4e / Supervised Lesson Lifecycle Decision: exact current-outcome tokens capture one terminal keep/reject/supersede receipt per lesson in bounded process memory, with no lesson/store/event mutation or lifecycle apply.
- Build Week Provenance Pack v1: July 11 baseline archive, SHA-256 manifests, objective contest delta, honest prior/new disclosure, and Codex collaboration record without private runtime data.
- Contest Showcase v1: read-only live continuity/experience/governance/action presentation, deterministic three-minute script, dependency doctor, and submission guide without command execution or pilot activation.

## Project Principles

- Rule 0: checkpoint first before changes.
- Local-first by default.
- No external dependencies unless explicitly approved.
- No session log JSONL format changes unless explicitly requested.
- No hidden memory edits.
- No autonomous shell/external-world actions.
- Prefer deterministic diagnostics before auto-fixes.
- Prefer small reversible patches over broad rewrites.
- Keep CLI, PySide, tkinter, natural routing, and tests stable.
- Read-only operator reports should suggest commands, not silently mutate state.
- Context injection must remain manual, inspectable, reversible, size-limited, and normal-prompts-only.

## Last Completed Milestone

v3.4e / Supervised Lesson Lifecycle Decision:

- Added read-only outcome confirmation/list/inspect/doctor reports and exact-token `/experience learning decide outcome <keep|reject|supersede> <memory_id> <token>` through the existing registered process-decision gate; Registry remains 363 commands across 41 categories.
- The token binds the current lesson ID, verified provenance, applied timestamp, outcome status, selected evidence signal, all compact signal IDs, and replacement memory ID when superseding.
- Only `KEEP_CANDIDATE`, `REJECT_CANDIDATE`, or `SUPERSEDE_CANDIDATE` can be confirmed, and the supplied decision must exactly match the deterministic outcome; weak, missing, stale-token, mismatched, chained, and repeated decisions fail closed.
- At most 32 immutable terminal receipts live in current process memory and expire on restart. Doctor detects malformed evidence identity, forbidden mutation claims, and historical evidence drift.
- The eight-check benchmark proves exact keep/reject/supersede decisions, wrong-token and inconclusive refusal, run-once behavior, restart expiry, and no-mutation claims.
- No lesson, memory, skill, Experience event, queue, export, session log, model prompt, or Context Injection setting is changed; there is no lifecycle apply path.
- Nine focused regressions were added; the full suite passes 937 tests.

## Next Candidate Tasks

- Submission Readiness: keep the public repository and provenance manifests current, finalize English Devpost copy, and record the sub-three-minute video.
- v3.4f / Learning Lifecycle Apply Readiness: revalidate lifecycle receipts against current lesson/evidence state and specify explicit keep/reject/supersede transition safeguards without adding a mutation path.
- Memory Migration Plan: design deterministic compaction/archive rules for the 8 previewed legacy candidates; no apply step without separate approval.
- Command Dispatch Architecture v2: replace the linear formatter chain with typed incremental family registration while preserving exact command behavior and runner isolation.
- Test Suite Structure v1: split the 15k-line flow suite by domain without changing test semantics or commands.
- Any expansion beyond the exact `/warnings unknown` pilot requires a separate explicit checkpointed task, new tests, exact confirmation scope, and fresh no-write evidence.
- Architect Ledger maintenance automation: command to print or refresh this file from current module state.
- Data Integrity Doctor polish: optional export/report snapshot and thresholds config.
- Consolidation queue polish: add optional preview-to-queue helper and receipt export filtering.
- Context Injection UI indicator in PySide: show enabled/disabled and latest audit summary.
- Context Injection safe compact output: avoid mock backend echoing the full injected prompt in normal CLI debug displays.
- Context Pack relevance ranking: deterministic scoring for memories/tasks/skills without embeddings.
- Task/Experiment/World integration views in PySide System Panel.
- Reflection-to-skills manual promotion helper.
- Cross-store reference export or compact PySide status indicator.
- Audit log rotation or export for context injection audit.
- Context injection per-session toggle in desktop prefs, still disabled by default.
- Optional export of the natural-route catalog/doctor/suggestion report for operator documentation.
- Command Registry maintenance helper to compare static metadata with formatter usage blocks.
- Future execution expansion must remain separately approved; v1.5.2 adds audit only, not mutating commands, retries, batch runs, shell, or autonomous dispatch.
- Compact PySide route/policy inspector could expose `/natural explain` without changing routing behavior.
- Optional PySide Action Preview panel could display plans without adding execution controls.
- Action Proposal Queue filtering or retention thresholds could be added later without introducing execution.
- Proto overview export or a compact PySide System Panel card could be added without changing the read-only core.
- Daily brief export/history could be added later; there is no scheduler, background loop, autonomous execution, LLM planning, or automatic state mutation.

## Open Risks

- Real `python3` on macOS may still be older than 3.11; prefer project scripts.
- PySide6 remains optional and local-environment dependent.
- Local `.app` launcher is not portable, signed, notarized, or packaged.
- MockReasoner echoes injected prompt content, which can make debug/session response previews noisy during injection tests.
- Context Injection Audit stores only simple input previews; it does not perform advanced secret redaction.
- Context Injection quality depends on Context Pack quality; no LLM summarization or embeddings.
- Session log, memory files, and JSONL journals are local files; corruption handling exists but no full database-level recovery.
- Cross-store reference validation is id/schema based and cannot infer semantic links that were never recorded.
- Natural routing uses exact normalized phrases; variants outside the allowlist intentionally remain normal prompts.
- Bilingual cognitive support is deterministic and finite; known English/Russian response signals are covered, but nuanced free-form claims and morphology can still be missed without LLM classification.
- The continuity soak is deterministic and representative rather than exhaustive; it does not test live Ollama variability, process restart/resume, or long-term memory aging.
- Existing response-coupled project memories remain until a separately approved migration; v3.1b prevents new ones but intentionally performs no repair.
- Suggestions are character-similarity hints only and do not provide semantic intent understanding.
- Command Registry is descriptive metadata, not runtime authorization or policy enforcement; formatter additions require an explicit registry update.
- Action Safety Policy is advisory classification only and is not yet wired as an execution gate or authorization system.
- Natural policy labels are introspection-only; exact context-enable phrases still execute immediately under existing v2 routing behavior.
- Action Preview is not an execution planner or approval engine; plans reflect static registry/policy metadata only.
- Action run is intentionally narrow and run-once; receipt hashes detect local inconsistency but are not signatures, authentication, or tamper-proof storage.
- No true streaming or real Stop cancellation yet for blocking Ollama calls.

## Standard Codex Brief Template

Use this compact prompt for future work:

```text
Ты работаешь в проекте Proto-Mind.

cd /path/to/proto_mind

Rule 0: before changes run:
scripts/run_cli.sh
then /memory backup

Current state is summarized in PROTO_MIND_ARCHITECT_LEDGER.md.

Constraints:
- no new deps unless explicitly approved
- no core reasoning rewrite unless requested
- do not change session log JSONL format
- do not break CLI, PySide, tkinter, natural router, or tests
- use scripts/run_tests.sh for verification

Task:
<describe one focused task>

Report:
- backup path
- files changed
- behavior changed
- tests result
- limitations/next steps
```

## Standard Verification

```bash
cd /path/to/proto_mind
scripts/which_python.sh
scripts/run_tests.sh
```
