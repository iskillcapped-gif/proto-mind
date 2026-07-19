# Proto-Mind

Proto-Mind is a local-first cognitive architecture prototype.

For compact architectural handoff context, see `PROTO_MIND_ARCHITECT_LEDGER.md`.

## OpenAI Build Week Disclosure

Proto-Mind existed before the OpenAI Build Week submission period and is submitted as a meaningfully extended existing project, not as a project created entirely during the event. The accepted pre-contest baseline is the timestamped July 11 checkpoint with SHA-256 `50a39b36aca72e1ae74ad8afe80004bfac1fe1eb3c66a2f168519246a680d4df`.

- [`BUILD_WEEK_PROVENANCE.md`](BUILD_WEEK_PROVENANCE.md) separates prior work from Build Week additions.
- [`CODEX_COLLABORATION.md`](CODEX_COLLABORATION.md) explains operator decisions and Codex/GPT-5.6 contributions.
- [`contest/README.md`](contest/README.md) documents reproducible baseline/current SHA-256 manifests and the contest delta.
- [`LICENSE`](LICENSE) releases the source under the Apache License 2.0.

The comparison excludes private runtime stores, exports, logs, backups, and secrets. The actual primary Codex `/feedback` Session ID is recorded in the provenance and collaboration documents; it was supplied by the operator from the feedback result rather than inferred or fabricated.

Repository publication boundaries, resolved path leaks, intentional redaction fixtures, and remaining pre-publication decisions are documented in [`REPOSITORY_PRIVACY_REVIEW.md`](REPOSITORY_PRIVACY_REVIEW.md).

## License

Proto-Mind is licensed under the [Apache License 2.0](LICENSE), including its explicit patent grant and notice-preservation requirements.

## Python

Proto-Mind requires Python 3.11+.

Recommended local commands:

```bash
scripts/run_cli.sh
scripts/run_tests.sh
scripts/which_python.sh
```

Direct fallback:

```bash
/opt/homebrew/opt/python@3.11/bin/python3.11 -m proto_mind.main
```

If an older `python3` is used, `proto_mind.main` exits with a clear Python 3.11+ requirement message instead of a traceback.

## System Overview

Proto Status / Doctor v1.0 provides a deterministic read-only top-level view:

```bash
/proto status
/proto doctor
/proto next
/proto warnings
/proto warnings-explain
/proto cleanup-preview
/proto snapshot
/proto snapshot-export
/proto snapshot-status
/proto snapshot-list
/proto snapshot-diff <old_json_path_or_name> <new_json_path_or_name>
/proto snapshot-diff-latest
/proto snapshot-diff-export <old_json_path_or_name> <new_json_path_or_name>
/proto snapshot-diff-export-latest
/proto snapshot-diff-status
```

`status` summarizes identity, focus, memory, context injection, health, and action state. `doctor` aggregates the major data, loop, memory, consolidation, router, registry, policy, and action doctors. `next` combines Operating Loop, action proposal, and consolidation signals into suggested manual commands.

Proto Warning Triage v1.1 adds compact warning classification, explanations for known legacy/reference/policy/data warning types, and a cleanup preview ordered as export, inspect, then optional lifecycle cleanup. It does not suppress, repair, archive, reject, or execute anything. All `/proto` commands leave stores, queues, context settings, audit files, and session logs unchanged.

Proto Snapshot Export v1.2 assembles the same deterministic state into a compact operator report and matching Markdown/JSON exports under `proto_mind/exports/proto_snapshots/`. Snapshot status and preview are read-only; snapshot export writes only its report files. JSON includes `no_mutation: true` plus structured doctor, warning, action, consolidation, next, and cleanup sections.

Proto Snapshot Diff v1.3 lists JSON snapshot history and compares two explicit files or the newest pair. It reports structural changes across status, doctors, warning categories, action/consolidation state, context injection, memory/tasks/focus, and Registry count. Diff is read-only, ignores Markdown and generation-time-only changes, and performs no semantic/LLM analysis.

Proto Snapshot Diff Export v1.4 writes the same structured comparison as human-readable Markdown and valid JSON under `proto_mind/exports/proto_snapshot_diffs/`. JSON contains old/new snapshot metadata, `diff_status`, `changed_sections`, structured per-field changes, and `no_mutation: true`. Failed exports create no files; successful exports never modify source snapshots or core stores.

## Export Retention

Export Retention / Cleanup Preview v1.5 provides read-only visibility across all seven known export directories:

```bash
/exports status
/exports inventory
/exports cleanup-preview
/exports doctor
```

Inventory reports counts, formats, sizes, oldest/newest files, and newest JSON validity. Doctor detects missing directories, malformed JSON, incomplete Markdown/JSON pairs, and large histories. Cleanup preview gives descriptive export-first and off-project archival guidance only; it never emits executable deletion/move commands or modifies files.

## Daily Agent Layer

Operating Loop v2 / Daily Agent Layer v1 provides a deterministic local daily brief without autonomous execution:

```bash
/daily status
/daily brief
/daily doctor
/daily next
```

Status summarizes Registry, exports, latest snapshots/diffs, Context Injection, and the test baseline stored in the Architect Ledger. Brief reuses existing read-only doctors, warning triage, Export Retention, and Operating Loop signals. Doctor validates Daily Layer safety invariants. Next suggests manual operator steps only; no LLM/API call, scheduler, background task, command execution, or state mutation is introduced.

## Session Rituals

Operating Loop v2.1 / Session Rituals v1 adds live, copyable operator reports around a work session:

```bash
/session start-brief
/session end-summary
/session checkpoint-advice
/session handoff-brief
```

Start/end reports reuse Daily, Export Retention, Proto warning, and snapshot/diff signals. Checkpoint advice never creates a checkpoint or runs tests. Handoff brief prints project, milestone, safety commands, warnings, and Rule 0 guidance without writing a file or touching the clipboard. All four commands are deterministic and read-only.

## Milestone Tracker

Operating Loop v2.2 / Milestone Tracker v1 adds deterministic local roadmap awareness:

```bash
/milestone status
/milestone list
/milestone current
/milestone next
/milestone doctor
```

The tracker reads accepted module/milestone text from `PROTO_MIND_ARCHITECT_LEDGER.md`, reports local `MILESTONE_*.md` sources, distinguishes detected facts from inferred phase labels, and suggests manual warning/test/snapshot steps. Parsing is intentionally partial and never invents missing milestones. Runtime commands do not persist milestone state or execute suggestions.

## Legacy Warning Inspector

Legacy Warning Inspector v1 adds read-only diagnostics over the existing Proto warning triage:

```bash
/warnings status
/warnings list
/warnings inspect
/warnings doctor
```

The inspector assigns deterministic diagnostic IDs, classifies known historical versus unknown findings, maps action/consolidation warnings to likely local source files, and explains runtime/data-integrity impact plus manual options. It never repairs receipts, rewrites references, creates reports, executes inspect suggestions, or mutates warning state.

Known Warnings Ledger v1 adds `/warnings accepted`, `/warnings accepted-ledger`, and `/warnings unknown`. Narrow rules match the documented historical queue/action IDs and signatures in `KNOWN_WARNINGS_LEDGER.md`; a new record with the same broad category remains unknown until reviewed. Accepted findings remain visible in the original list, inspection, and doctor output.

## Operator Agenda

Operating Loop v2.3 / Operator Agenda v1 provides a live, non-persistent next-work queue:

```bash
/agenda status
/agenda next
/agenda list
/agenda doctor
```

Agenda prioritizes unknown warnings, then accepted-known WARN baselines, snapshot/diff review, tests, milestone selection, and optional session handoff. Every item includes priority, reason, safety note, and a command for manual use. Agenda never executes suggestions, creates tasks, persists queue state, or changes Context Injection.

## Pre-Change Ritual

Operating Loop v2.4 / Snapshot Hygiene and Pre-Change Ritual v1 adds:

```bash
/prechange status
/prechange checklist
/prechange doctor
/prechange handoff
```

Status computes conservative OK/WARN/BLOCKED readiness from accepted/unknown warnings, blockers, Agenda/Export health, Context Injection, and snapshot/diff metadata. Checklist and handoff print Rule 0, allowed/forbidden write, verification, smoke, and SHA-256 guidance only. The layer never creates a backup or snapshot, runs commands, persists checklist state, or writes runtime data.

## Focus Mode

Operating Loop v2.5 / Work Session Plan and Focus Mode v1 adds:

```bash
/focus status
/focus plan
/focus checklist
/focus doctor
/focus handoff
```

Focus Mode turns the inspected baseline into one small deterministic manual work plan. Unknown warnings take priority; otherwise the plan starts with Pre-Change review, manual milestone selection, one scoped Codex task, verification, smoke, SHA comparison, and session handoff. It never executes commands, persists focus/session state, creates backups/snapshots, or calls an LLM/API.

## Acceptance Review

Operating Loop v2.6 / Acceptance Review Ritual v1 adds:

```bash
/acceptance status
/acceptance checklist
/acceptance criteria
/acceptance decision-guide
/acceptance doctor
/acceptance handoff
```

Acceptance Review prints a reusable human decision framework for ACCEPT, ACCEPT WITH NOTES, REJECT / NEEDS FIX, or HOLD / NEEDS MORE INFO. It lists required evidence, hard blockers, safety invariants, documentation expectations, and a copyable review handoff. It does not parse external reports, score evidence, persist a decision, or accept/reject automatically.

## Snapshot Baseline Registry

Snapshot Baseline Registry v1 adds:

```bash
/baseline status
/baseline current
/baseline latest
/baseline checklist
/baseline doctor
/baseline handoff
```

Baseline Registry reads the Architect Ledger, Acceptance readiness, accepted/unknown warnings, Context Injection settings, and existing snapshot/diff metadata to describe the currently detectable accepted baseline. It never creates a snapshot/checkpoint, persists baseline state, executes a suggestion, or writes runtime stores/exports.

## Post-Acceptance Closure

Operating Loop v2.7 / Post-Acceptance Handoff and Session Closure v1 adds:

```bash
/closure status
/closure summary
/closure next
/closure handoff
/closure doctor
```

Closure composes the accepted baseline, warning counts, snapshot/diff signals, safety invariants, and next-session guidance into live operator text. It never closes or logs a session autonomously, persists closure state, writes a handoff file, manipulates the clipboard, or executes the suggested next milestone.

## Operator Memory Card

Operating Loop v2.8 / Operator Memory Card and Project State Card v1 adds:

```bash
/memory-card status
/memory-card short
/memory-card full
/memory-card codex
/memory-card doctor
```

The short card is a compact new-chat summary, the full card includes layers, command families, invariants, verification, and limitations, and the Codex card is a reusable task header. Cards are generated locally on demand and are never stored, copied to the clipboard, injected into prompts, or treated as authorization to execute commands.

## Command Capability Map

Operating Loop v2.9 / Command Family Index and Capability Map v1 adds:

```bash
/capabilities status
/capabilities list
/capabilities map
/capabilities safety
/capabilities doctor
/capabilities handoff
```

The index derives family counts, read-only/mixed modes, workflow phases, and advisory policy classes from the current Command Registry. It marks unknown behavior as UNKNOWN rather than safe, prints manual safety gates, and never executes or authorizes a listed command.

## Dry-Run Action Plan

Operating Loop v2.10 / Proposed Action Plan and Dry-Run Intent Layer v1 adds:

```bash
/plan status
/plan next
/plan dry-run
/plan gates
/plan doctor
/plan handoff
```

Plan Layer proposes one conservative manual next action and prints a reusable intent/commands/gates/evidence/stop-conditions template. It does not parse free text, persist plans, authorize or execute commands, create approval state, or bypass Registry and Action Policy classifications.

## Confirmation Vocabulary

Operating Loop v2.11 / Confirmation Gate and Authorization Vocabulary v1 adds:

```bash
/confirm status
/confirm policy
/confirm levels
/confirm requirements
/confirm doctor
/confirm handoff
```

The layer defines advisory `NONE`, `READ_ONLY_MANUAL`, `CONFIRM_REQUIRED`, `ELEVATED_CONFIRM_REQUIRED`, `OPERATOR_ONLY`, and `BLOCKED` labels and the gates a future execution-capable design would have to satisfy. It does not parse or capture confirmation, grant authorization, persist approval state, or execute commands; Context Injection remains unchanged and disabled by default.

## Execution Sandbox Blueprint

Operating Loop v2.12 / Execution Sandbox Design and Command Runner Blueprint v1 adds:

```bash
/sandbox status
/sandbox blueprint
/sandbox boundaries
/sandbox allowlist
/sandbox denied
/sandbox doctor
/sandbox handoff
```

The layer documents a possible future structured runner pipeline, project/path boundaries, conservative `FUTURE_CANDIDATE` read-only commands, denied operation classes, evidence requirements, and handoff gates. It is architecture text only: there is no runner, subprocess/shell/eval/exec path, approval capture, authorization state, queue, background work, or runtime store/export write.

## No-Op Runner Contract

Operating Loop v2.13 / Read-only Runner Interface Spec and No-Op Executor Contract v1 adds:

```bash
/runner status
/runner contract
/runner noop
/runner evidence
/runner disabled
/runner doctor
/runner handoff
```

The contract defines future request/response fields, a sample no-op response, required evidence, disabled-execution reasons, and implementation handoff gates. Every current response remains `execution_enabled=false` and `executed=false`; there is no active allowlist, approval capture, authorization engine, execution engine, subprocess/shell/eval/exec path, or runner-state persistence.

## Runner Candidate Set

Operating Loop v2.14 / Read-only Command Runner Candidate Set v1 adds:

```bash
/runner-candidates status
/runner-candidates list
/runner-candidates explain
/runner-candidates denied
/runner-candidates gates
/runner-candidates doctor
/runner-candidates handoff
```

The layer documents 13 Registry-verified low-risk read-only candidates for a possible future runner. Every item is marked `FUTURE_CANDIDATE`, `NOT_ACTIVE`, and `NOT_EXECUTABLE_BY_RUNNER_YET`; commands outside the set and all mutating/high-risk/operator-only/unknown/destructive/external operation classes remain excluded. There is still no active allowlist or execution/approval/authorization engine.

## Runner Activation Preconditions

Operating Loop v2.15 / Runner Activation Preconditions v1 adds:

```bash
/activation status
/activation preconditions
/activation checklist
/activation blockers
/activation forbidden
/activation doctor
/activation handoff
```

The layer distinguishes whether a future v3.x design discussion may be considered from whether execution is possible today. Current design review is safe under the known baseline, but actual execution remains blocked because active allowlisting, approval capture, authorization, execution, and evidence implementations are absent. The commands are read-only guidance and do not activate candidates or persist checklist/activation state.

## Runner MVP Design Lock

v3.0a / Read-only Runner MVP Design Lock adds:

```bash
/runner-mvp status
/runner-mvp design
/runner-mvp allowlist
/runner-mvp confirmation
/runner-mvp evidence
/runner-mvp stop-conditions
/runner-mvp doctor
/runner-mvp handoff
```

The layer locks a possible future MVP to five Registry-verified read-only candidates, internal Proto-Mind handler transport, exact one-run confirmation, fail-closed evidence, and explicit refusal conditions. Every candidate remains `MVP_ALLOWLIST_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_YET`; no allowlist activation, confirmation capture, evidence collection, dispatch, or execution implementation is introduced.

## Real Read-only Runner MVP

v3.0b adds the first deliberately narrow execution-capable surface:

```bash
/runner-exec status
/runner-exec allowlist
/runner-exec dry-run
/runner-exec dry-run /daily doctor
/runner-exec dry-run /exports doctor
/runner-exec dry-run /capabilities safety
/runner-exec run
/runner-exec run CONFIRM RUN READONLY: /warnings unknown
/runner-exec run CONFIRM RUN READONLY: /daily doctor
/runner-exec run CONFIRM RUN READONLY: /exports doctor
/runner-exec run CONFIRM RUN READONLY: /capabilities safety
/runner-exec evidence
/runner-exec refusal-matrix
/runner-exec last-refusal
/runner-exec evidence-check
/runner-exec history
/runner-exec history-summary
/runner-exec history-clear-preview
/runner-exec history-doctor
/runner-exec stability
/runner-exec sequence-plan
/runner-exec sequence-evidence
/runner-exec consistency-check
/runner-exec soak
/runner-exec soak-plan
/runner-exec soak-report
/runner-exec drift-check
/runner-exec doctor
/runner-exec handoff
```

v3.0b initially activated exactly `/warnings unknown`. A confirmed run uses a fixed zero-argument internal callback, captures current-process-only evidence, and compares SHA-256 manifests for `proto_mind/data` and `proto_mind/exports`. Missing or mismatched confirmation, Context Injection, blockers, Registry/Policy drift, callback failure, or detected writes fail closed. There is no shell, subprocess, eval/exec, free-form dispatch, persistent evidence, network/background work, snapshot, or backup path in this runner.

v3.0c hardens evidence and refusal behavior. `refusal-matrix` prints eight static refusal expectations without running them; `last-refusal` preserves the latest current-process refusal even after a later success; `evidence-check` validates required fields, boolean flags, allowlist consistency, and no-persistence invariants. Mismatched confirmations are stored only as length plus a short SHA-256 fingerprint, never as a persistent approval or evidence record.

v3.0d expands the active allowlist by exactly one command: `/daily doctor`. Both allowlisted commands use dedicated zero-argument callbacks and command-specific exact confirmations. `/runner-exec dry-run /daily doctor` is non-executing; outside, near-miss, broad, suffixed, and cross-command requests fail closed. No general router, arbitrary command string, or third callback is exposed.

v3.0e adds exactly `/exports doctor` through a third dedicated zero-argument callback. Its evidence includes the parsed export doctor status, while SHA-256 checks prove the doctor did not write to data or exports. The active allowlist is exactly three commands; no generic string dispatcher or fourth target is exposed.

v3.0f adds a read-only stability review over that unchanged allowlist. `stability` summarizes current modes and limits, `sequence-plan` prints but never runs a recommended smoke sequence, `sequence-evidence` exposes bounded in-memory counters/latest references, and `consistency-check` validates exact config/callback/evidence/context invariants without invoking a callback.

v3.0g adds exactly `/capabilities safety` through a fourth dedicated zero-argument callback. Evidence records a compact Registry/Policy classification summary, while stability and consistency reports validate the exact four-command map. `/confirm policy` remains outside the runner; there is no generic dispatcher or fifth executable target.

v3.0h adds a read-only safety soak layer without expanding execution. `soak-plan` prints the recommended success/refusal sequence, `soak-report` shows bounded current-process results, and `drift-check` validates exact callbacks/confirmations/evidence plus `/confirm policy` exclusion and no-write indicators. No soak command invokes a callback or persists a report.

v3.0i adds a compact process-memory evidence ring without expanding execution. The ring retains at most 20 safe success/refusal summaries, evicts the oldest event, stores no confirmation text or full target output, and disappears on restart. `history-clear-preview` never clears state, and no evidence/log/approval/history file is created.

## Bilingual Cognitive Baseline

v3.1a moves development back into the cognitive core. `Observer`, topic extraction, and durable preference/decision detection now recognize deterministic Russian and English signals for continuity, memory inventory, preferences, decisions, and overrides. Canonical topic tags are selected before generic tokens so retrieval keeps meaningful concepts under the eight-tag limit.

Run the local benchmark without an LLM, API, store, or session-log write:

```bash
python -m proto_mind.cognitive_benchmark
```

The baseline now contains twenty English/Russian scenarios and must report `20/20`: ten observer/topic cases plus ten response-level grounding/reflection cases. Russian preferences and decisions are stored as compact operator text, while recall retrieves the saved preference through the existing memory pipeline. This milestone does not change Context Injection, command routing, runner execution scope, or store schemas.

## Memory Write Governance

v3.1b makes normal retrieval read-only by default and separates usage telemetry into an explicit internal API. New automatic preference, decision, project, and insight records store only the compact user input; generated responses are no longer embedded into memory content.

```bash
/memory write-policy
/memory quality-preview
```

Both commands are read-only. `write-policy` explains the active side-effect and content-source rules. `quality-preview` detects existing response-coupled, recursive, oversized, or empty records and suggests manual review, but performs no archive, deletion, compaction, migration, counter update, or schema change.

## Bilingual Grounding And Reflection

v3.1c extends Cognitive Continuity beyond input classification. `cognitive_signals` normalizes English/Russian current-state, historical, rejected-alternative, decision-override, and memory-claim phrases for both `SelfReflector` and `GroundingAuditor`.

The response audit now detects Russian active-decision contradictions, treats superseded decisions as historical when phrased that way, catches unsupported Russian memory claims, and enforces Russian concise-answer preferences. Grounding evidence includes the supporting memory id, type, source, and compact preview. These checks remain deterministic and local; they do not rewrite responses, create reflections, promote memory, call an LLM, or change any store.

## Cognitive Continuity Soak

v3.1d adds a deterministic 25-turn English/Russian soak over the real `Coordinator` pipeline and a temporary isolated memory store:

```bash
python -m proto_mind.cognitive_soak
```

The soak verifies preference and goal recall, current and historical decisions, one intentional contradiction, one-turn correction-hint carry-forward, compact user-input-only memories, explicit-only retrieval telemetry, resolved superseding references, and bounded growth. Its contract is four explicit writes, 21/21 byte-stable read-only turns, four working records, three persistent records, and four unique contents.

The soak also fixes three continuity gaps: explicit `Проверь/Повтори текущее решение` recall imperatives no longer become new decisions, generic architecture explanations no longer require memory grounding, and active insights appear in memory inventory output. Continuity references such as `как мы обсуждали раньше` no longer activate historical-state bias unless the query actually asks for past state. No live store, export, session log, Context Injection, command, LLM/API, or external action participates in the soak.

## Experience Ledger Foundation

v3.2a adds `proto_mind.experience_ledger`, a typed schema and provenance doctor for compact cognitive events. A turn can now be represented as linked `conversation_observed`, `intent_detected`, `memory_retrieved`, `response_generated`, `memory_evaluated`, `memory_recorded`, `reflection_evaluated`, `grounding_evaluated`, and correction-guidance events.

The 25-turn continuity soak builds this trace in process memory and verifies 180 events with 332 ordered provenance edges. Payloads use whitespace-normalized previews capped at 160 characters and exclude full user inputs, responses, injected context, and hidden/system prompts. v3.2a creates no ledger file, adds no slash command, and does not connect event persistence to the live `Coordinator`:

```bash
python -m proto_mind.experience_ledger
python -m proto_mind.cognitive_soak
```

v3.2b adds the persistence policy without enabling live capture. `TemporaryExperienceLedgerStore` accepts isolated temporary paths only, validates complete event batches, refuses duplicates or unhealthy existing files, and performs a logical append through atomic temp-file replacement. Each JSONL envelope has a contiguous sequence, `previous_hash`, and SHA-256 `entry_hash`; the doctor detects malformed JSONL, broken provenance, sequence drift, and tampering.

Retention remains operator-controlled: there is no automatic deletion, truncation, compaction, or migration. The full 180-event continuity trace is covered by a temporary persistence test with 180/180 verified hashes. Any path inside live `proto_mind/data` is rejected while `LIVE_EXPERIENCE_PERSISTENCE_ENABLED` is false.

v3.2c adds `proto_mind.experience_capture`, a read-only live-capture gate:

```bash
python -m proto_mind.experience_capture
```

Missing settings resolve to safe disabled defaults without creating a config file. Even a manually supplied `enabled: true` remains ineffective because no live writer hook is installed and live persistence policy is disabled. The gate reports status, schema preview, and doctor diagnostics; corrupt settings, full-content requests, alternate paths, and unexpected live ledger files fail closed or warn. It exposes no activation/write method and deliberately adds no slash commands, keeping the Registry at 345 commands across 39 categories.

v3.2d adds `proto_mind.experience_vocabulary`, a typed lifecycle adapter for experience beyond conversation turns:

```bash
python -m proto_mind.experience_vocabulary
```

The vocabulary covers goal creation, plans, modeled tool calls and outcomes, task completion, operator corrections, reflections, lesson candidates, and memory-promotion evidence. Required payload fields and predecessor event types are validated centrally. The local benchmark builds an eight-event success trace and a seven-event failure/correction trace, then verifies all 15 envelopes in an isolated SHA-256 chain.

These adapters only describe evidence. They never execute a tool, complete a real task, create a goal, promote memory, or call an LLM. `memory_promoted` explicitly records that operator confirmation is required and that promotion was not performed by the builder.

v3.2e adds `proto_mind.experience_explainability`, an immutable read model over in-memory events or a verified temporary store:

```bash
python -m proto_mind.experience_explainability
```

It provides deterministic event inspection, root-to-event source chains, compact trace maps, exact entity-id lookup, event-type-specific “why” explanations, and an explainability doctor. A memory-promotion trace resolves through eight evidence stages; an operator correction resolves through five. Tool-call explanations explicitly say they are not execution proof, while lesson and promotion explanations preserve confirmation boundaries. Missing or broken provenance produces clean diagnostics without repair or mutation.

v3.2f adds `proto_mind.experience_episode`, a compact read-only projection over validated lifecycle evidence:

```bash
python -m proto_mind.experience_episode
```

The projector groups events by session and turn, then exposes goal, expectation, plan, actions, observed outcomes, task result, corrections, reflections, lesson candidates, promotion evidence, and exact source event IDs. A successful trace is `completed_verified` only when both tool outcome and task completion are verified; a corrected failure remains `failed_corrected`. Lesson candidates remain pending and memory-promotion evidence retains its operator-confirmation/no-auto-promotion markers. The benchmark projects two episodes from 15 events and verifies all 15 temporary SHA-chain envelopes without LLM summarization, episode persistence, live capture, tool execution, domain mutation, commands, or exports.

v3.2g adds `proto_mind.experience_learning`, a deterministic candidate-review boundary over projected episodes:

```bash
python -m proto_mind.experience_learning
```

Each lesson is classified as `eligible_for_review`, `needs_more_evidence`, `duplicate`, or `blocked`. Eligibility requires a verified completed episode, confidence of at least `0.8`, valid source-event provenance, and an explicit operator-confirmation boundary. Exact normalized duplicate checks can use explicitly supplied active-memory and active-skill snapshots; the module does not open or change live stores itself. Promotion evidence must link back to the lesson event and preserve `promotion_performed_by_builder=false`. Every result has `auto_apply_allowed=false`, and no command, queue, memory promotion, skill creation, persistence, or live capture is added.

v3.2h adds `proto_mind.experience_capture_design`, an executable-free design lock before any live session capture can be considered:

```bash
python -m proto_mind.experience_capture_design
```

The decision is `KEEP_DISABLED` with `implementation_authorized=false`. The design requires explicit opt-in for one current process session, expiry on restart, normal cognitive turns only, slash/natural/internal-report bypass, no historical backfill, 160-character typed previews, no full or injected context payloads, deterministic secret-redaction tests, separately approved persistence/retention policy, and fail-closed session disablement on write/hash/provenance errors. Its benchmark creates zero files and exposes no activate, enable, capture, append, persist, run, or write method. A future writer remains a separate checkpointed milestone, not an implied consequence of this review.

v3.2i adds `proto_mind.experience_learning_input`, an explicit-ID adapter between existing memory/skill stores and the read-only Learning Reviewer:

```bash
python -m proto_mind.experience_learning_input
```

The adapter accepts only caller-supplied memory and skill IDs, includes only active records, and returns detached snapshots. It performs no query, relevance ranking, automatic selection, usage telemetry, use increment, or write. Missing/inactive/archived IDs are visible warnings; ambiguous IDs and malformed stores fail closed. `SkillLibrary.read_snapshot()` provides a detached public read path without exposing mutation. Formatter output uses compact previews, while exact selected content is passed in memory only for deterministic duplicate comparison. The isolated benchmark selects one memory and one skill, excludes two records, reports two missing IDs, detects two duplicates, and preserves every source byte and usage field.

v3.2j adds `proto_mind.experience_consent`, a pure in-memory specification for future session consent transitions:

```bash
python -m proto_mind.experience_consent
```

The stateless evaluator models `disabled`, `previewed`, `consented`, `stopped`, and `expired`. Consent requires a preview followed by an exact phrase bound to one normalized session ID. Broad, modified, chained, cross-session, premature, stopped, expired, unknown, and invalid-state cases fail closed. Slash commands, natural-routed commands, internal reports, and historical backfill remain out of scope even after simulated consent. Stop or capture failure disables the remainder of the session, while restart/session end expires consent. Transition results never retain the supplied phrase and always report `capture_performed=false`, `persistence_performed=false`, and `implementation_authorized=false`; no state, config, hook, command, or file exists.

v3.2k adds `proto_mind.experience_privacy`, a deterministic credential-like redaction boundary for compact Experience previews:

```bash
python -m proto_mind.experience_privacy
```

Redaction runs before the existing 160-character limit and covers labeled English/Russian credentials, bearer headers, credential-bearing URIs, private keys, JWTs, and common provider-token formats. Stable `[REDACTED:*]` placeholders are idempotent, and benign password/token discussion remains unchanged. `ExperienceTraceBuilder` receives the protection through `compact_preview` and drops observer topic tags derived from a matched sensitive segment; Experience Doctor now rejects unredacted credential-like values in `*_preview` and `*_previews`. The isolated benchmark contains 12 sensitive cases and four benign controls, creates zero files, and adds no broad PII inference, live capture, hook, writer, persistence, command, export, or Context Injection change. Capture remains disabled.

v3.2l adds `proto_mind.experience_capture_soak`, a bounded process-memory simulation over the still-disabled capture design:

```bash
python -m proto_mind.experience_capture_soak
```

The soak models preview-before-consent, wrong-token refusal, exact session consent, 36 bilingual normal turns, all four bypass classes, explicit stop, fail-closed capture failure, and restart expiry. A detached `BoundedExperiencePreviewBuffer` accepts validated event batches only while per-turn, total-event, and canonical-JSON byte limits remain satisfied; overflow decisions leave its snapshot unchanged. The current fixture holds 252/256 events and 140274/524288 bytes with 30 redaction markers. It creates zero files and performs no LLM call, runtime capture, consent storage, hook, writer, temporary/live persistence, command, export, Context Injection change, or domain mutation. This is soak evidence only, not activation authorization.

v3.2m adds `proto_mind.experience_activation_review`, a read-only decision artifact over all capture preconditions:

```bash
python -m proto_mind.experience_activation_review
```

The review reuses the design lock, 14-case consent benchmark, 16-case privacy benchmark, bounded-growth soak, temporary SHA-chain continuity soak, disabled live gate, absent paths, Context Injection setting, preview-only persistence policy, and Registry surface. The current matrix is 10/10 READY and reports `SUPERVISED_IN_MEMORY_PILOT_AVAILABLE_PERSISTENCE_DISABLED`; its durable runtime decision remains `KEEP_DISABLED`, with `runtime_activation_allowed=false` and `implementation_authorized=false`. Enabled/malformed persistent capture settings or enabled Context Injection block readiness without repair. The benchmark creates zero files and installs no persistence hook, writer, config, or live ledger.

## Supervised In-Memory Experience Pilot

v3.3a adds an explicit operator-controlled pilot over the shared CLI/tkinter/PySide normal-turn path:

```text
/experience status
/experience preview
/experience consent <exact phrase from preview>
/experience episodes
/experience episode [latest|<turn_id>]
/experience learning status
/experience learning preview [latest|<turn_id>]
/experience learning doctor
/experience learning decisions
/experience learning decision <candidate_id>
/experience learning confirm-preview <candidate_id>
/experience learning decide accept <candidate_id> <exact token>
/experience learning decide reject <candidate_id> [reason]
/experience learning promotion-preview <candidate_id>
/experience learning decision-doctor
/experience learning eligibility <candidate_id> --target memory|skill [--memory <id>]... [--skill <id>]...
/experience learning eligibility-doctor <candidate_id> --target memory|skill [--memory <id>]... [--skill <id>]...
/experience learning proposal-preview <candidate_id> --target memory|skill [--memory <id>]... [--skill <id>]...
/experience learning propose <candidate_id> <exact token> --target memory|skill [--memory <id>]... [--skill <id>]...
/experience learning proposals
/experience learning proposal <proposal_id|candidate_id>
/experience learning proposal-doctor
/experience learning apply-readiness <proposal_id|candidate_id>
/experience learning apply-plan <proposal_id|candidate_id>
/experience learning apply-preview <proposal_id|candidate_id>
/experience learning apply <proposal_id|candidate_id> <exact token>
/experience learning apply-status
/experience learning apply-receipt <apply_id|proposal_id|candidate_id>
/experience learning apply-doctor
/experience events [--last N]
/experience inspect <event_id>
/experience doctor
/experience stop
```

The pilot starts disabled and requires preview-before-consent with a generated process-session ID. After exact consent it converts only successful normal cognitive turns into compact typed Experience events. Slash commands, Natural Router matches, empty input, internal reports, and backfill are excluded. Credential-like text is redacted before truncation; a batch is admitted atomically only while the 12-events-per-turn, 256-event, and 512-KiB bounds remain satisfied. Context Injection must remain disabled: an injected normal turn stops pilot capture fail-closed.

Experience evidence exists only in process memory and is visible through `events`, `inspect`, and the normal-response capture indicator. Stop is terminal until process restart. There is no Experience file, live writer, export, backfill, automatic learning, or session-log schema change. The persistent capture gate remains `KEEP_DISABLED`; the separate v3.4a operator-confirmed lesson pilot may write exactly one verified memory record from a current proposal.

v3.3b adds a read-only cognitive-turn episode view over that same bounded snapshot. `/experience episodes` lists captured turns, while `/experience episode latest` connects Observe, Interpret, Recall, Respond, Memory decision, Reflect, Verify, and exact event provenance in one compact report. The projector validates the existing Experience trace, preserves redacted previews, labels missing stages as incomplete, performs no LLM summarization, and changes neither process evidence nor any file or store.

v3.3c adds an operator-reviewed learning bridge over those current-process episodes. `/experience learning preview` derives at most eight compact candidates from exact redacted correction, reflection, and grounding evidence; identical findings are merged while preserving every source event ID. A clean successful turn creates no candidate. Correction guidance requires operator review, warning-only findings require more evidence, and incomplete episodes remain blocked. Every preview keeps `operator_confirmation_required=true`, `promotion_ready=false`, `auto_apply_allowed=false`, and `persistence_performed=false`. There is no LLM summarization, queue, apply, promotion, memory/skill write, file write, or Context Injection change.

v3.3d adds an explicit process-memory decision gate without enabling promotion. `/experience learning confirm-preview <candidate_id>` prints a candidate-specific SHA-256 token; `/experience learning decide accept <candidate_id> <token>` accepts only complete `operator_review_required` evidence, while `decide reject` records a redacted terminal rejection. Up to 64 compact receipts retain the candidate digest and exact evidence IDs until process restart. `/experience learning promotion-preview <candidate_id>` requires acceptance but remains `executable=false` with promotion, apply, and persistence all false. Decision inspection and Doctor commands are read-only, and no memory, skill, queue, file, session log, model, or Context Injection state is changed.

v3.3e adds a target-specific promotion eligibility review without enabling promotion. After an accepted process-memory decision, the operator supplies exact memory and/or skill IDs; the existing detached input adapter reads only those active records and checks exact normalized content for the declared `memory` or `skill` target. Results distinguish `ELIGIBLE IN SELECTED SCOPE`, `DUPLICATE`, `INCOMPLETE`, `NOT CHECKED`, `NOT ELIGIBLE`, and `ERROR`. The receipt explicitly states that scope is limited and no global duplicate search, retrieval ranking, usage telemetry, mutation, execution, promotion, apply, persistence, or automatic target inference occurred.

v3.3f adds a bounded promotion proposal receipt without enabling apply. A clean selected-scope eligibility review produces a deterministic `memory.lesson.v1` or `skill.procedure.v1` blueprint, hashes the exact candidate, accepted decision, eligibility receipt, selected-record snapshot, target schema, and payload, then prints a proposal-specific token. Only `/experience learning propose` with that exact token retains an immutable receipt, capped at 32 for the current process. Selected-record drift invalidates the token. Proposal list, inspection, and Doctor are read-only; every receipt remains `future_apply_ready=false`, `executable=false`, and performs no memory/skill/queue/file write, promotion, apply, global novelty claim, or Context Injection change.

v3.3g adds read-only apply readiness over current process proposals. `/experience learning apply-readiness` rebuilds the candidate, accepted decision, explicit-ID eligibility, selected-record hash, fixed target payload, and proposal digest from current state; any drift or missing evidence returns `NOT READY`, while unsafe receipts and unreadable stores return `ERROR`. `/experience learning apply-plan` prints receipt, atomic-write/run-once, and rollback requirements. These readiness commands remain read-only after the v3.4a pilot is installed.

v3.4a adds the first supervised learning write, deliberately limited to one fresh `memory.lesson.v1` proposal per process. `/experience learning apply-preview` performs current-evidence revalidation, a full persistent-memory exact-duplicate check, proposal-age and deterministic-record-ID checks, then emits a token bound to the proposal and current memory-store SHA-256. Only `/experience learning apply` with that exact token writes one record through `MemoryStore` atomic replace and immediately verifies count, fields, record hash, and resulting store hash. A run-once process receipt exposes `/memory forget <created_id>` as a manual rollback suggestion. Skill apply, batch apply, shell/arbitrary dispatch, automatic promotion, Context Injection changes, and writes to any other store remain disabled.

v3.4b makes the compact origin of that one lesson restart-safe without adding another writer. The same atomic memory-record write now embeds a hashed `memory.lesson.provenance.v1` envelope containing the candidate, decision, eligibility, proposal, selected-scope, and redacted evidence-event identifiers. `/memory why <id>` reads and verifies the envelope after restart; Memory Doctor reports tampered provenance as an error. The existing receipt rollback command can soft-forget only an explicit memory or a lesson with verified provenance, while retaining the lesson's audit chain. Legacy/operator memories return `UNAVAILABLE` rather than receiving an invented source chain. Detailed process receipts still expire, full prompts/responses are not embedded, and the one-per-process apply, skill/batch refusal, exact token, and no-autonomy boundaries remain unchanged.

v3.4c closes the first supervised learning loop by allowing only an active lesson with verified durable provenance to participate in normal retrieval after restart. `MemoryKeeper` filters tampered or unprovenanced lesson records fail-closed and keeps the refusal visible in the existing retrieval trace; inactive verified lessons remain outside current-state recall unless the query is historical. When a verified lesson supports a response, its grounding evidence carries the compact provenance status and ID. `proto_mind.lesson_recall_benchmark` proves the path in English and Russian with fresh Coordinator instances, temporary stores, byte-stable retrieval, unchanged `usage_count`/`last_used`, and no model/API call, automatic write, learning apply, command expansion, or Context Injection.

v3.4d adds read-only later-outcome review for those provenanced lessons. `/experience learning outcome-review <memory_id>` accepts evidence only when the exact lesson ID appears in a valid Experience retrieval after its `applied_at`. Clean grounded reuse yields `KEEP_CANDIDATE`; an explicit downstream `user_corrected` event yields `REJECT_CANDIDATE`; a correction lineage ending at a different newer active provenance-verified lesson yields `SUPERSEDE_CANDIDATE`. Weak or mixed evidence remains `NEEDS_MORE_EVIDENCE`, and `/experience learning outcome-doctor` checks trace/provenance health. These are review candidates, not truth or authorization: the layer performs no memory/event mutation, apply, promotion, model call, capture, or Context Injection change.

v3.4e adds an explicit operator lifecycle decision after that review. `/experience learning outcome-confirm-preview <memory_id>` prints a token bound to the exact current lesson, provenance, outcome signal, and verified replacement when applicable; `/experience learning decide outcome <keep|reject|supersede> <memory_id> <token>` records one terminal receipt in bounded process memory. `/experience learning outcome-decisions|outcome-decision <id>|outcome-decision-doctor` keeps the decision inspectable. The decision itself expires on restart and never mutates a lesson.

v3.4f adds read-only `/experience learning lifecycle-readiness|lifecycle-plan <memory_id|receipt_id>` plus `lifecycle-readiness-doctor`. It revalidates the receipt against the active persistent lesson, durable provenance, exact current outcome evidence, selected signal, replacement contract, current store SHA-256, and the existing confirmation-required memory Registry gate. Readiness remains `executable=false` and never invokes the writer.

v3.4g adds the separately confirmed supervised lifecycle writer. `/experience learning lifecycle-apply-preview <memory_id|receipt_id>` rebuilds the exact v3.4f checks and emits a second token bound to the decision receipt, review hash, lesson/replacement IDs, decision, and current store SHA-256. `/experience learning apply lifecycle <id> <token>` reuses the existing registered `/experience learning apply` memory gate and permits one transition per process: `keep` is a byte-stable no-op; `reject` soft-deactivates the exact lesson; `supersede` soft-deactivates only the old lesson after verifying an unchanged active replacement. Atomic rewrite, exact-record diff, immutable provenance verification, process receipt hash, run-once guard, and byte-exact rollback are mandatory. Existing lifecycle fields survive restart; detailed receipts do not. No batch, skill/event write, automatic decision/apply, shell, arbitrary dispatch, model/API call, or Context Injection change is available.

## Contest Showcase

Contest Showcase v1 turns the existing architecture into one read-only live presentation:

```text
/showcase status
/showcase demo
/showcase script
/showcase doctor
```

`/showcase demo` presents four connected layers: cognitive continuity, consented Experience evidence, visible governance, and bounded read-only action. When evidence exists it shows the latest cognitive episode summary and links to `/experience episode latest`; it never creates consent or captures a turn itself. `/showcase script` prints a deterministic three-minute operator sequence, while `/showcase doctor` checks Registry coverage, the exact four-command runner contract, disabled Context Injection, zero unknown warnings/blockers, and absence of persistent Experience commands.

The full recording guide, Mermaid architecture, narration, recovery path, and non-claims are in [`CONTEST_SHOWCASE.md`](CONTEST_SHOWCASE.md). Showcase commands call no model, execute no capability, create no snapshot/export, and mutate no store or runtime evidence. Contest hardening also guarantees that preview truncation cannot split a complete `[REDACTED:<category>]` placeholder into a Doctor-invalid partial token.

## Desktop

Tkinter fallback:

```bash
scripts/run_desktop_mock.sh
scripts/run_desktop_ollama.sh
```

PySide desktop:

```bash
scripts/run_pyside_mock.sh
scripts/run_pyside_ollama.sh
```

The local macOS `.app` launcher remains a machine-local wrapper, not a portable signed bundle.

## Natural Commands

Natural Command Router v2.3 maps an exact, conservative Russian/English allowlist to existing safe operator commands. Examples:

```text
проверь систему
что делать дальше
начать день
закрыть день
включи контекст
выключи контекст
что стоит запомнить
инвентаризация данных
```

Health and evening workflows return separated command bundles. Natural routes bypass LLM intent classification, context injection, and cognitive session logging. Only explicit context enable/disable phrases change state; the remaining v2 routes are read-only.

Read-only introspection:

```bash
/natural status
/natural list
/natural explain проверь систему
/natural suggest проверь системму
/natural doctor
```

The doctor checks normalized phrase uniqueness, target/bundle validity, exact command allowlisting, required bundle members, and rejection of shell-like or chained commands. `/natural explain` now includes Command Registry category/read-only/mutation/risk fields and Action Safety Policy classification for every target; bundles show their strictest policy, and `/natural list` includes compact policy labels. `/natural suggest` still never executes. These labels are introspection only and do not enforce confirmation or alter route execution.

## Command Registry

Command Registry v1.0 provides read-only metadata and diagnostics for Proto-Mind slash commands:

```bash
/commands status
/commands list
/commands explain /data doctor
/commands explain /memory remember hello
/commands doctor
```

The registry describes command category, mutation behavior, risk, Natural Router availability, and notes. Explain uses longest-prefix matching but never executes the command. The doctor checks duplicate/invalid metadata and verifies every Natural Router target is registered and not high-risk.

## Action Safety Policy

Action Safety Policy v1.0 provides deterministic, read-only advisory classification over Command Registry metadata:

```bash
/policy status
/policy explain /data doctor
/policy explain /context injection enable
/policy explain /memory remember hello
/policy doctor
```

Read-only low-risk commands are `auto_allowed`; mutating commands require confirmation; high-risk commands are `operator_only`; unknown, shell-like, and chained inputs are `blocked`. Bundles use their strictest member policy. This layer never executes commands and is not an enforcement or authorization engine.

## Action Preview

Action Preview v1.0 resolves slash commands and exact natural phrases into read-only execution plans:

```bash
/action status
/action preview /data doctor
/action preview /memory remember hello
/action preview проверь систему
/action preview включи контекст
/action doctor
```

Plans show registry metadata and Action Safety Policy per step; natural bundles show their strictest policy. Unknown natural phrases suggest `/natural suggest`, while unknown slash commands are blocked in the preview. Every report states `No command executed.` Preview does not call command formatters, change context, or mutate stores.

Action Proposal Queue v1.5.2 stores preview snapshots for operator review in `proto_mind/data/action_queue.jsonl`, with confirmation, readiness diagnostics, narrowly constrained read-only execution, run-once guardrails, and execution audit:

```bash
/action propose /data doctor
/action propose включи контекст
/action propose проверь систему
/action proposals
/action inspect <id>
/action approve <id>
/action confirm-preview <id>
/action confirm <id> <token>
/action unconfirm <id> "reason"
/action run-preview <id>
/action run <id>
/action run-receipt <id>
/action runs [--all|--last N]
/action run-verify <id>
/action run-audit
/action readiness-doctor
/action reject <id> "not needed"
/action archive <id>
/action queue-status
/action queue-export
/action cleanup-preview
/action queue-doctor
```

Proposal status is `proposed|approved|rejected|archived`; confirmation is a separate `execution_state`. Only approved `auto_allowed` or `confirmation_required` proposals can be confirmed with the exact token from `confirm-preview`; blocked/operator-only proposals are refused. Confirmation and unconfirmation mutate queue metadata only, preserve `no_execution=true`, and never execute or authorize the target. Queue export includes confirmation metadata, while cleanup preview recommends unconfirming before archiving confirmed records.

`run-preview` revalidates confirmed proposals against current Command Registry and Action Safety Policy metadata, rejects missing/drifted/shell-like/chained targets, and lists future receipt/rollback safeguards for mutations. `readiness-doctor` diagnoses the whole queue. `READY` remains advisory; these two diagnostic commands never execute a target.

`run` is the only execution entry point and accepts one confirmed `READY` proposal only when every command is currently `auto_allowed`, registered, `read_only=true`, and `mutates=none`. It dispatches through existing internal formatters, never through a shell, then stores bounded output previews in `run_receipt`; `run-receipt` is read-only. Confirmation-required, mutating, unknown, shell/chained, operator-only, blocked, and mixed bundles are refused before any command runs.

Executed proposals cannot run again. v1.5.1 receipts include `run_id`, command count, policy/registry metadata snapshots, output previews, and a SHA-256 integrity hash over canonical receipt JSON. Queue Doctor validates hashes and counts; legacy v1 receipts without guardrail fields produce warnings rather than destructive migration.

v1.5.2 adds read-only execution history and verification. `/action runs` lists executed records, `/action run-verify` recomputes one receipt hash and checks current Registry/Policy metadata, and `/action run-audit` aggregates v2/legacy/missing receipts, hash results, duplicate run ids, warnings, policy drift, and forbidden mutating commands. Audit never invokes target commands or rewrites queue records.

## Identity / Values

Identity / Values v1.0 stores an inspectable local profile at `proto_mind/data/identity.json`.

Commands:

```bash
/identity status
/identity show
/identity set style clear, careful, local-first
/identity add-value Local-first by default.
/identity add-principle Create checkpoint before structural changes.
/identity add-boundary No hidden memory edits.
/identity history
/identity doctor
```

This layer is not injected into reasoning yet and does not enforce autonomous policy.

## Context Pack

Context Pack v1.0 assembles inspectable read-only context from existing local modules.

```bash
/context status
/context build
/context doctor
/context export
/context prompt-preview
/context prompt-doctor
/context prompt-export
/context injection status
/context injection enable --max-chars 2540
/context injection disable
/context injection audit
/context injection last
/context injection audit-status
```

Exports are written under `proto_mind/exports/context_packs/` as Markdown and JSON. Context packs are not automatically injected into model prompts.

Prompt previews are written under `proto_mind/exports/context_prompts/` as plain text when exported. They include a safety footer and remain manual/inspectable only.

Context Injection v1.2 is disabled by default. When manually enabled, it wraps normal prompts only with preview-safe context; slash/operator commands bypass injection.

Context Injection Audit v1.2.1 records compact local events in `proto_mind/data/context_injection_audit.jsonl`, including enable/disable, preview, injected normal prompts, and skipped commands. It stores short input previews and injected character counts, not full injected prompts by default.

## Operating Loop

Operating Loop v1.1 provides read-only daily workflow reports:

```bash
/loop status
/loop morning-plan
/loop evening-review
/loop capture-today
/loop next
/loop doctor
```

These commands suggest next actions and capture commands, but do not mutate goals, tasks, experiments, world records, memory, skills, or reflections.

## Data Integrity

Data Integrity Doctor v1.1 provides top-level read-only checks of local JSON/JSONL stores and their recorded references:

```bash
/data status
/data inventory
/data doctor
/data refs
/data refs-doctor
```

It inventories memory, reflection, goals, tasks, experiments, skills, world model, identity, context injection, context injection audit, consolidation queue, action proposal queue, session log, export directories, and backups. Cross-store checks validate task/experiment/world links, focused-goal state, terminal-goal tasks, and applied consolidation receipts pointing to memory or skills. It performs no repairs and rewrites no files.

## Consolidation Preview

Memory Consolidation Preview v1.0 provides read-only suggestions for manual memory and skill promotion:

```bash
/consolidation status
/consolidation preview
/consolidation export
/consolidation export-status
/consolidation doctor
/consolidation queue-status
/consolidation queue-add memory "Remember useful finding" --command "/memory remember Useful finding"
/consolidation queue-list
/consolidation queue-approve <id>
/consolidation queue-apply-preview <id>
/consolidation queue-apply <id>
/consolidation queue-apply-receipt <id>
/consolidation queue-undo-preview <id>
/consolidation queue-export
/consolidation queue-doctor
/consolidation queue-cleanup-preview
```

It scans reflections, done task results, experiment lessons, world lessons, skills, and active explicit memories. It only prints suggested commands and does not write memory or skills automatically. `/consolidation export` writes read-only Markdown and JSON reports under `proto_mind/exports/consolidation/`. Consolidation Queue v1.3.1 stores pending manual candidates in `proto_mind/data/consolidation_queue.jsonl`; approval still does not execute suggested commands. `/consolidation queue-apply <id>` is explicit, approved-only, and limited to safe internal commands: `/memory remember`, `/skills add`, and `/skills body`. Applied items store structured receipts with applied command/kind/record id and an undo suggestion when safely detectable. Undo preview never rolls back automatically. It does not run shell commands, arbitrary slash commands, or command chains.
