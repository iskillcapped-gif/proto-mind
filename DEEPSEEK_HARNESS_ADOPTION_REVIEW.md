# DeepSeek Harness Adoption Review

Reviewed: 2026-09-03  
Upstream: [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)  
Reviewed commit: [`76fda729799fe9b3848dbe2c211d4b231032b81e`](https://github.com/deepseek-ai/deepseek-harness/commit/76fda729799fe9b3848dbe2c211d4b231032b81e)  
Observed package version: `0.1.2-rc.1`  
Upstream license: MIT

## Decision

Do not embed, install, or wrap DeepSeek Harness inside Proto-Mind. Its Node/Cordis runtime,
browser client, provider configuration, plugin loader, persistence stack, and agent loop
would become a second application architecture beside the existing Python core, native
SwiftUI client, and subscription Codex adapter.

Adopt selected contracts independently where they improve Proto-Mind. Keep the current
subscription Codex app-server, private Native bridge, local stores, explicit Full Mac mode,
and SwiftUI product. No DeepSeek endpoint, API key, npm dependency, remote plugin, new
permission, or background process is introduced by this review.

No upstream source code was copied in this milestone. The Session Spine pilot is a clean
Python implementation of general event-sourcing ideas, with a smaller contract chosen for
Proto-Mind. If source is copied later, retain the applicable MIT notice and audit the
upstream third-party notices before distribution.

## What The Harness Confirms

| Area | DeepSeek Harness | Proto-Mind today | Decision |
| --- | --- | --- | --- |
| Composition | Services and capabilities are plugins mounted into scoped Cordis contexts. | Python modules, a static command registry, a long formatter chain, and fixed Native RPC dispatch. | Do not import Cordis. Move toward one typed local capability declaration in small pilots. |
| Sessions | One append-only event log is the source of truth; transcript, model surface, outline, telemetry, and other views are projections. | Native chat history, work-session evidence, provider-thread bindings, and core cognitive logs are separate durable views. | Highest-value idea. Stage a Session Spine before changing persistence. |
| History replacement | A surface replacement cites every shadowed event while the original log remains intact. | Old messages and evidence remain, but there is no general source-linked compaction surface. | Adopt for future local compaction and context views; never rewrite historical facts silently. |
| Tool execution | Parsed JSON arguments are frozen, policy is monotonic, guards may only reduce authority, and durable presentation is distinct from execution-local values. | Core commands have Registry/Policy metadata; Full Mac execution is delegated to the official Codex app-server under a frozen turn contract. | Build a typed kernel only for capabilities Proto-Mind itself owns. Do not claim interception of provider-internal tools. |
| Approval | One closed allowed-once/rejected/cancelled/unavailable result is linked to an existing call identity and logged. | Core mutation pilots use exact tokens; Native Full Mac is a broad process-memory session grant with Codex approval policy `never`. | Reuse one-shot semantics if Proto-Mind later owns a mutating tool. Do not add fake approvals around delegated calls. |
| Skills | Layered providers expose complete/incomplete catalogs, explicit model/user invocation policy, invalidation, and source precedence. | Shared core procedures, private history, built-in starter skills, manual selection, and bounded automatic selection already exist. | Later add explicit provider origin and complete/incomplete snapshots; keep current verification and no automatic promotion. |
| Long jobs | Job IDs are predictable; authorization comes from owner/session fencing. Start requires a controller capable of reading/stopping the job; disposal drains owned work. | No general background job runtime. Full Mac remains one foreground turn. | Required design before any background autonomy. Do not add jobs first and lifecycle later. |
| Loop hygiene | Exact canonical tool repetitions are tracked per agent and receive bounded advisory reminders at configured thresholds. | Time/item limits and Computer Use timeout guidance exist, but there is no host-injected mid-turn repeat reminder. | Valuable after a supported same-turn context channel exists. Avoid a prompt-only claim or unsafe hard stop. |
| Persistence | JSONL append commits are fsynced, torn tails are distinguished from corrupt committed prefixes, and interrupted calls recover as unknown rather than success. | Work sessions use bounded atomic per-run records and preserve unknown outcomes; chat remains an atomic whole-file archive. | Reuse crash semantics in a future spine store, without importing zstd or Node. |
| Runtime diagnostics | Each package owns observable invariant checks; checks are registered and attributable. | Many strong doctors exist, but ownership and runtime dispatch coverage are distributed. | Make future capability definitions own their invariants instead of growing another unrelated doctor family. |
| Product shell | Local web UI, model/provider settings, jobs, subagents, workflows, and plugin inventory. | Native macOS SwiftUI product optimized for one operator and subscription Codex. | Keep Native. Borrow interaction ideas only when they reduce real operator friction. |

## Extracted Priorities

### P0: Session Spine Contract

Delivered as a non-integrated pilot in `proto_mind/session_spine.py`:

- immutable events with bounded canonical JSON data, bounded provenance and monotonic sequence identities;
- explicit surface-only `append` or `replace` operations;
- every replacement must cite all surface nodes it shadows;
- unknown required events refuse replay, while explicitly informational unknown events may be retained and skipped;
- deterministic SHA-256 over the complete original event log;
- pure replay and visible-event projection with no storage, provider, command, UI, or mutation path.

This is a design lock, not a new history format. Existing Native and core records are not
migrated, read, rewritten, or duplicated.

### P1: Existing-State Projection And Parity

Delivered as a pure read-only adapter in `proto_mind/native_session_spine.py`:

- the caller explicitly pairs one Native user message, optional assistant message, and an
  already-inspected work-session view; the adapter never scans or guesses across archives;
- exact operator input plus displayed and raw assistant text are preserved through bounded,
  hash-verified chunks rather than truncated event payloads;
- work-session input hashes/previews, completed-answer preview, stable run state, public tool
  evidence, public work-log digest, and source-bound memory suggestions are revalidated;
- tool results are evidence-only and non-replayable; no provider call, command, tool, model,
  file read, store read, event append, or migration occurs;
- stopped or partial runs remain `unknown` or `not_started` with no assistant success, while
  active `preparing`/`running` views are rejected as unstable projection sources.

Nineteen synthetic regressions prove deterministic projection, exact Unicode parity, closed
public evidence, tamper refusal, uncertainty and no input mutation/file access. This stage is
not a writer or an authoritative history source. Native work sessions retain only a bounded
answer preview, so full-answer parity depends on the explicit caller pairing; archive-wide
reconciliation remains intentionally unavailable.

### P2: Private Session Spine Store

P1 is accepted. Any P2 design remains a separate checkpointed decision; it must provide:

- one writer per session and explicit owner identity;
- durable append commit boundaries and torn-tail tests;
- restart-safe reconstruction of interrupted turns;
- versioned pure projections for chat, work timeline, turn outline, memory candidates, and telemetry;
- bounded retention/export before any compaction;
- migration preview and byte-preserving rollback for existing personal history.

Do not make the new store authoritative until old/new parity is proven on isolated fixtures
and a separate private backup is created.

### P3: Typed Capability Execution Kernel

Replace metadata/dispatch duplication one family at a time. One declaration should own:

`name`, input schema, result schema, handler, scope, mutation class, risk, timeout,
presentation, verification, and invariant checks. Pre-execution policy may only narrow
authority. Start with one local read-only capability; do not place the delegated Codex Full
Mac tool loop behind a wrapper that cannot actually enforce its claims.

### P4: Agent Hygiene And Owned Jobs

Add exact-repeat observation only when Proto-Mind can deliver source-labelled context into
the same active agent turn. Before any background work, require owner/session fencing,
bounded output, cancellation, terminal first-wins settlement, completion notification, and
drain-on-owner-disposal. Predictable job IDs are never authorization.

### P5: Scoped Skill Providers

Evolve current skill discovery into project, operator, built-in, and future remote-provider
layers with explicit precedence and completeness. An incomplete refresh may keep a last-good
catalog for display, but must not silently grant model invocation or replace a verified
source. This follows, rather than replaces, the current source/version revalidation.

## Explicitly Not Adopted

- No replacement of subscription Codex with DeepSeek or another API-key provider.
- No `npm`, `pnpm`, Cordis, browser frontend, Python Harness SDK, or bundled Harness runtime.
- No third-party plugin installation or model-facing dynamic plugin loader.
- No autonomous subagents, workflows, schedules, background jobs, or remote clients.
- No zstd session migration, full chat rewrite, or automatic compaction.
- No relaxation of Full Mac consent, Context Injection, memory review, or skill verification.
- No claim that DeepSeek Harness is production-secure. Its own safety notice describes the
  project as unaudited Developer Preview software and recommends least privilege and
  disposable environments.

## Upstream References

- [Repository and Developer Preview notice](https://github.com/deepseek-ai/deepseek-harness)
- [Safety notice](https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md)
- [Core agent/session/tool architecture](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/core.md)
- [Session event and surface model](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/session.md)
- [Session projections](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/session-projection.md)
- [Tool registry and policy pipeline](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/tools.md)
- [Skills](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md)
- [Background jobs](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/jobs.md)
- [Repeat-tool reminder](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/guard/repeat-tool-reminder)
- [JSONL session persistence](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/session/session-persistence-jsonl)
- [MIT license](https://github.com/deepseek-ai/deepseek-harness/blob/master/LICENSE)
