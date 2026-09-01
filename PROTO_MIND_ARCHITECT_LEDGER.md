# Proto-Mind Architect Ledger v1.0

Purpose: compact architectural memory for future Codex prompts. Keep this file short, current, and operator-readable so future tasks do not need to restate the whole project history.

Last updated: 2026-09-01

## Current Stable State

- Proto-Mind is a local-first cognitive architecture prototype, not a model-training project, consciousness claim, unbounded autonomous agent, or polished consumer chatbot.
- Current operator direction: personal native macOS app, Codex-inspired workspace, preserved cognitive core, local Ollama plus opted-in Codex subscription inference and an explicitly selected Full Mac foreground tool mode. No commercial roadmap or background scheduler. See `NATIVE_MACOS_ROADMAP.md`.
- Curated future direction: `PROTO_MIND_EVOLUTION_ROADMAP.md` maps the external August 31 blueprint to the actual implementation. Prioritize reliable Native work sessions, context/artifact/verification UX and honest scoped tooling; screen capture/OCR, voice, learning UI and local extensions remain proposed increments. Explicit saved-image input is now delivered below. No new permissions or runtime features are enabled merely by the review.
- Primary CLI launch: `scripts/run_cli.sh`.
- Direct Python fallback: `/opt/homebrew/opt/python@3.11/bin/python3.11 -m proto_mind.main`.
- Desktop launch paths:
  - Native SwiftUI/AppKit foundation: `scripts/build_native_app.sh`, `scripts/run_native.sh`, separate `dist/Proto-Mind Native.app`.
  - Tkinter fallback: `scripts/run_desktop_mock.sh`, `scripts/run_desktop_ollama.sh`.
  - PySide6 UI: `scripts/run_pyside_mock.sh`, `scripts/run_pyside_ollama.sh`.
  - Local macOS launcher: `dist/Proto-Mind.app`.
- Python 3.11+ is required. `proto_mind.main` exits cleanly on unsupported Python.
- Reasoner backend is selected by env/config:
  - default mock backend.
  - Ollama via `PROTO_MIND_REASONER=ollama`, `PROTO_MIND_OLLAMA_MODEL`, `PROTO_MIND_OLLAMA_URL`.
- Normal prompts go through observer, retrieval, reasoner, memory evaluation, self-reflection, grounding audit, and session logging.
- Persona Engine 0.1 adds a strict single-Brother kernel and a bounded, immutable, hashed `PersonaSnapshot` compiler over read-only Identity projection, already-selected provenanced memories, task context and actual runtime authority facts. It is not wired into normal prompts or Native UI yet; it performs no retrieval/model call/write, exposes no facets or trait controls, grants no authority and leaves Context Injection disabled.
- Local Cognitive Turn Envelope v3.6a projects that completed result once into detached typed data; Cognitive Turn Card v3.6b consumes it in PySide without repeating reasoning, persistence, or capture. CLI/tkinter retain text output.
- Slash/operator commands bypass normal cognitive turns and should not become cognitive session log turns.
- Supervised Experience Pilot v3.3a observes consented turns; v3.3b projects episodes; v3.3c previews candidates; v3.3d captures decisions; v3.3e reviews selected-scope eligibility; v3.3f records proposals; v3.3g revalidates apply readiness; v3.4a permits one separately confirmed, atomic, verified memory lesson; v3.4b embeds restart-safe compact provenance; v3.4c permits only verified learned lessons into recall; v3.4d reviews later outcomes; v3.4e records an exact operator lifecycle decision; v3.4f revalidates that decision; v3.4g permits one separately confirmed keep/reject/supersede transition; v3.4h reconstructs and audits durable lifecycle state after restart; v3.5a projects an active verified lesson into a read-only procedural skill contract; v3.5b records exact operator-authored fields in a bounded restart-expiring receipt; v3.5c revalidates that receipt and current Skill Library; v3.5d permits one separately confirmed atomic verified non-executable skill record per process; v3.5e embeds restart-safe skill provenance and audits it read-only; v3.5f reviews exact manual-use outcome lineage; v3.5g separately confirms and captures that operator-reported evidence; v3.5h records an exact operator keep/revise/archive decision over confirmed evidence; v3.5i revalidates that decision against current evidence, provenance, skill bytes, and decision-specific future safeguards; v3.5j permits one separately confirmed keep no-op or legacy archive transition; v3.5k reconstructs durable procedural skill state after restart without inventing archive cause; v3.5l locks a hashed archive envelope; v3.5m binds a current archive decision to its exact writer blueprint; v3.5n permits one separately confirmed atomic durable archive and restart-safe verification; v3.5o design-locks restore by embedding the complete prior archive envelope; v3.5p blocks generic status mutations; v3.5q blocks generic payload/tag/use mutations; v3.5r binds restore authorization; v3.5s permits one exact-token, run-once, atomic durable restore with fixed receipt and restart-safe verification; v3.5t reconstructs and audits only the receipt evidence that survived in the durable restore envelope; v3.5u requires exact new restore-bound manual evidence before any later lifecycle decision; v3.5v binds the future post-restore capture blueprint to consent, current skill/store/provenance/restore hashes, exact event fields, and a fixed receipt contract without creating authority. Review/proposal/decision/detailed-receipt state remains bounded and process-memory-only; no automatic, batch, revision, or procedure execution exists.
- Build Week submission provenance uses the July 11 pre-contest archive SHA-256 plus generated baseline/current/delta manifests; prior work and contest work are explicitly separated.
- Primary Build Week Codex `/feedback` Session ID is `019d73be-1d7e-7401-8efe-f5e165736db4`.
- Repository privacy review excludes local cognitive/runtime stores, removes user-specific checkout paths from public artifacts, and documents synthetic credential fixtures and publication boundaries.
- Public source licensing is Apache License 2.0; no runtime store or export is licensed or published because those paths remain Git-ignored.
- Context Injection v1.2 is disabled by default and only applies to normal prompts after explicit operator enablement.
- Native cloud consent is a separate device-local opt-in, persisted only after operator authorization and revoked on logout. ChatGPT subscription models compute at OpenAI; only Ollama/Mock are offline. Native history/preferences and the isolated Codex profile live outside core stores in `~/Library/Application Support/ProtoMindNative`.
- Native workspace binding points to the actual selected project folder, with manual refresh and explicit preview/hash-checked file excerpts only. It does not copy/sync a checkout, execute Git hooks, grant model tools, or change core stores.
- Native Memory/Goals/Skills screens read fixed core stores through bounded typed library RPCs, independently of model/retrieval/command paths. Search, history filters, source hashes, and detail cards never update usage, initialize files, save navigation, or attach records to a prompt.
- Native v4.0d introduced the explicit per-conversation/folder Full Mac grant held only in bridge/UI memory. Native 0.14.0 now adds the installed signed OpenAI Computer Use service to that same grant. Normal chat retains OS isolation, no MCP and no screen tools. Full Mac has user-level shell/file/network/screen authority beyond the working folder; no per-action approvals, root grant, automatic retry or rollback.
- Native v4.0e adds a quieter conversation layout and a display-only public work timeline: commentary, plans, observed tools and elapsed time, never private reasoning or internal prompts. It is stored as an optional history v3 field, separate from the final answer and excluded from model replay/core evaluation. No new commands, permissions, automatic injection or core-store migration.
- Native v4.0f adds a translucent macOS sidebar, 14/12-point system/code typography and real per-conversation model/effort selection. Catalog capabilities drive the menu; both chat and Full Mac validate the current selection before sending `turn/start.effort`. Defaults are catalog-derived, unsupported choices do not silently fall back, and neither picker changes access grants or core settings.
- Native 0.7.0 delivers EV-01: common hover feedback plus private versioned work-session evidence, a cooperative writer, pre-dispatch persistence, truthful unknown outcomes and visible recovery cards. Only explicit Send starts a new continuation turn; no provider-thread resume, auto-replay, restored grants, new slash commands or core-store migration. Journal reads are separate from commands/LLMs; normal-turn recording does not activate the cognitive Experience pilot.
- Native 0.8.0 delivers EV-02's text-first context/artifact desk and fixes model-menu hover width/height. The pre-send desk shows exact selected excerpts/history, stale hashes, cloud destination and shared-core scope without invoking recall/models. Journal Results links observed files/diff/output to a run and captured completion hashes where available. New normal runs extend private evidence only; views do not write or grant permissions.
- Native 0.9.0 adds optional operator criteria before Send and explicit manual acceptance/needs-work assessment in the journal. Criteria are frozen, observed files/source bytes revalidated and up to 12 earlier review receipts retained. Only explicit draft Save or private run review writes; no model self-acceptance, automatic verification, core write, execution grant or repaired unknown outcome.
- Native 0.10.0 adds explicit PNG/JPEG selection through the composer, local preview, hash-checked Codex image input and metadata-only history v4/context/work-session evidence. Up to three images, 4 MiB each / 8 MiB total, 24 megapixels each. No disk image cache, automatic old-image replay, screenshot capture, OCR, redaction or new grant; cloud and current model image capability are checked before sending. Ollama/Mock image input is refused. PDF/local vision and project-memory isolation remain follow-ups.
- Native 0.10.1 fixes saved-image split-layout overflow and Finder-launched Codex/Node startup, and adds local drag/drop to chat/composer. A bounded, conversation/workspace-bound batch preview reuses the existing readers; explicit Attach saves image/file metadata together, never sends a turn. Invalid/stale batches fail without partial attachment. Historical errors, drafts and private run records remain unchanged by recovery; no auto-retry, new grants or core mutation.
- Native 0.10.2 adds explicit hide/show for historical run banners as bounded, revision-bound conversation display preferences. Journal outcomes remain unchanged; new/changed evidence and storage diagnostics still warn. Banner navigation selects the affected run. Acceptance explains unavailable states; completed replies without criteria offer rework-with-comment, preserving existing backend confirmation/evidence gates. No automatic acknowledgement, retry, repair, grant or core write.
- Native 0.11.0 adds local selected PDF page text: one PDF up to 8 MiB/300 pages, eight explicitly selected pages, 3,000 characters/page. A fixed timed PDFKit subprocess denies network/file writes. Separate PDF drop/picker, exact text preview, page selection, draft chip and context desk precede Send-time source/text SHA revalidation. Codex/Ollama receive only selected text, with existing permissions; Mock disclaims analysis. History v5/journal store metadata, not PDF bytes/text; v1-v4 load without rewriting. No OCR, scanned/visual/password PDF, automatic replay, grants, core schema or Registry change.
- Native 0.12.0 introduced durable Codex continuity with one private conversation-to-thread binding. Native 0.14.1 supersedes that mapping with separate `chat` and `full_access` bindings because provider developer instructions persist across `thread/resume`. Each mode has its own one-time bounded local-history bootstrap and restart-safe resume. Legacy v1 bindings remain historical and are not automatically assigned to a mode. Resume failure/workspace drift still fail closed; reset removes local bindings only. Separate Codex `save-all` rollouts can contain private prompts/replies/tool output and are not covered by project backups or automatic retention.
- Native 0.13.0 adds live Codex Web Search only inside the existing explicit Full Mac grant. Ordinary chat remains tool-free with Web Search disabled. The activity/receipt path keeps a bounded query, action type and sanitized HTTP(S) page location; URL credentials, query/fragment data and opaque result payloads are not persisted. Search pages are untrusted input and prompts forbid sending local file contents or secrets as queries. This is not an interactive browser or Computer Use grant.
- Native 0.14.0 adds optional Full Mac Computer Use through the canonical locally installed OpenAI service. `native_computer_use.py` verifies fixed service/client bundle IDs, OpenAI Developer ID team `2DC432GLL2`, executable path and version before use. Strict Codex config loads one required MCP with ten enabled tools; unexpected/missing inventory fails before generation. Proto-Mind receipts keep only action type, bounded app name, status and a privacy note, never screenshots, UI trees, coordinates, typed/selected values or raw MCP results. The grant remains explicit, in-memory and conversation/workspace-bound.
- Native 0.14.1 fixes cross-mode provider continuity: Chat and Full Mac never resume each other's thread, so a durable no-tools Chat instruction cannot suppress Full Mac tools and Full Mac authority cannot enter isolated Chat. The v2 binding store migrates only when a new binding is written, preserves legacy IDs as `legacy_unknown`, and exposes mode sessions in Settings. No authority, tool, core schema, dependency or Context Injection behavior changes.
- Native 0.14.2 makes Computer Use observation restart-safe at the turn boundary: the first state read per app requests `disableDiff=true`, because Proto-Mind does not replay raw UI trees into later turns. This current guidance is injected even into older durable Full Mac threads. A timed-out state read is not retried under an alias and the strict MCP timeout is 30 seconds. No fallback action or new authority is added.
- Native 0.15.0 freezes a deterministic Full Mac agent contract before provider startup, then validates the connected Computer Use inventory against it. Contract/hash/inventory are bounded evidence, not automatic verification or acceptance. Six local eval cases cover authority drift and the macOS `-1743` path. Automation onboarding is explicit through the Native error UI and bundle purpose string; Proto-Mind cannot grant itself TCC permission or retry automatically. The existing subscription Codex app-server remains the provider; no Agents SDK, API key or Platform connector is added.
- Native 0.16.0 adds exact private-stdio `search` and `fetch` contracts over the read-only Native Library. Inputs reject undeclared fields; results contain validated structured data, one text fallback and explicit local/no-network/no-model/no-write metadata. Public work logs gain a monotonic display-state version with stale same-run rejection. Verified Computer Use config now installs the signed client's official `turn-ended` notify hook so normal completion releases active UI/capture state; Proto-Mind does not kill or own the shared desktop service. No slash command, public MCP, dependency, core schema, provider authority or Context Injection change is added.
- Personal native setup (2026-08-31): current project bound, cloud permission explicitly enabled, official browser sign-in completed, separate ChatGPT Plus profile connected. Two real Codex turns passed: plain text and one explicitly previewed `native/Info.plist` attachment. Core Context Injection stays disabled.

## Current Verification Baseline

- Current test command: `scripts/run_tests.sh`.
- Current test count: 1533 unit tests OK (1517 previous + 16 Persona Engine foundation regressions).
- Native checks: `scripts/test_native.sh` passes 355 checks, adding structured local capability envelopes and monotonic work-log event ordering to the previous Full Mac Web Search/Computer Use, durable-session, PDF/history, notice, attachment-drop/layout, image, criteria/manual-review, context/artifact, work-session, hover, typography, catalog, library and grant coverage. Real stdio checks use code-only temporary fixtures without full Xcode/XCTest.
- Native 0.14.0 acceptance: installed Codex 0.151.0 accepts the strict Full Mac configuration with the signed OpenAI Computer Use service `26.828.1000919`. Model-free calls through the authenticated Codex app-server expose exactly ten allowlisted tools, list applications, read Calculator state, press a harmless key, re-read state and clear the input without printing screen/application result content; the runtime refuses a direct unauthenticated call. Full suite, Native checks, release build, plist, application signature and personal-app relaunch pass. All 48 core/export files, three personal Native history/settings/binding files and seven private work-session records retain their pre-change SHA-256 values. Context Injection remains disabled and Registry remains 387/41.
- Native 0.14.1 verification covers separate Chat/Full Mac threads, same-mode resume, one-time local bootstrap, v1 read-only compatibility, explicit v2 migration and refusal to reuse a misleading legacy `last_mode`. Full suite and Native checks pass; a private pre-migration history checkpoint excludes credentials and the Codex profile.
- Native 0.14.1 live acceptance creates a distinct Full Mac binding from the affected v1 row. Computer Use invokes `list_apps`/`get_app_state`; the service protects ChatGPT's own state, while a resumed second turn reads Finder state successfully without UI or file mutation. All 48 core/export, conversation, preference and eight work-session hashes remain unchanged; only the binding registry changes by design.
- Native 0.14.2 diagnosis records two Safari `get_app_state` calls failing at the exact former 90-second timeout. The same signed service reads Safari in under one second with a fresh state. Final live acceptance uses an ordinary Russian request, resumes the existing Full Mac thread and completes exactly one read-only `get_app_state` in 334 ms without retry or UI mutation.
- Native 0.16.0 verification covers exact capability descriptors/envelopes, unknown-input and widened-boundary refusal, real private-stdio search/fetch rendering, positive monotonic work-log versions, stale Swift event rejection and exact Computer Use notify scoping. Full suite and Native checks pass; release plist/signature and personal-app relaunch pass. The already-stale shared helper from the old build was terminated once after remaining near 20% CPU and disappeared without stopping ChatGPT or Proto-Mind. New runtime code never kills that shared service.
- Persona Engine 0.1 verification covers exact kernel/snapshot/change-candidate schemas, one continuous identity across provider changes, provenance-required memory projection, external-content isolation, unsupported authority refusal, deterministic hashes and bounded omission. The invariant eval passes 7/7 with zero model calls/store writes; all 355 Native checks and release build remain green. All 48 project `data`/`exports` files match the Rule 0 checkpoint by SHA-256, Registry remains 387/41 and Context Injection remains disabled.
- Native 0.10.2 isolated UI smoke passes banner navigation, hide/show/X and restart persistence, active rework-with-comment and declared-criteria confirmation previews, and no-write cancellation. All 48 core/export, two personal conversations/preferences and four private journal file hashes are unchanged. The old personal failed-run banner is not silently acknowledged; the operator can hide it explicitly. No cloud/model/tool call, automatic repair, retry or acceptance; Context Injection disabled and Registry 387/41.
- Native 0.10.1 UI smoke reproduces the hidden sidebar/composer from a saved large-image draft and verifies the fix without discarding it. Real local drag gestures into chat/editor open previews; attachment/cancel and the original + picker work on disposable synthetic state. A temporary drag source was removed before the final build; Finder cross-window automation was inconclusive. A separate real tool-free Sol low-effort adapter call describes a 3.7 MB synthetic PNG with Finder's minimal PATH. No personal image/history/memory was sent. All 48 core/export hashes, personal conversations/preferences and the now-existing private failed-run journal remain unchanged; no automatic retry or repair. This is narrow transport/UI evidence, not a general vision benchmark.
- Codex runtime updated from npm CLI 0.136.0 to stable 0.151.0 on 2026-08-31 after side-by-side compatibility probes. The same Native account now advertises 5.6 Sol (default), Terra and Luna, with Sol Max/Ultra available in the real menu. Tool-free Sol medium/max/ultra responses and one temporary-folder `printf` tool smoke pass through the unchanged adapter. Subagents remain disabled; this does not claim Desktop Ultra behavior. Earlier selected-file acceptance remains historical evidence; other models/quotas and live Ollama were not re-tested. All 48 core/export hashes and Native history/preferences hashes are unchanged; see `NATIVE_MACOS_ROADMAP.md`.
- Full Mac acceptance adds a real account-default adapter turn on disposable files: checkpoint, patch, two successful terminal checks, three projected tool activities. Separate UI smoke validates the permission sheet, command/diff rendering, operator bypass and signed-out failure/revocation; it does not reuse personal stores or claim the loaded UI receipt re-executed those tools. Native history/preferences and all 48 core/export file hashes are unchanged by these checks.
- v3.6a adds 21 envelope regressions, including byte-identical old/new API output and memory/session-log files across eight Russian continuity turns, one model/update/log call per turn, and one consented Experience capture.
- v3.6b adds 20 card/worker/UI regressions for escaped and bounded evidence, full answers, exact notices, missing/stale/malformed data, Debug/fallback, single-call/capture behavior, operator bypass, and existing status/stop/exit paths. A separate offscreen Qt smoke exercises the real QThread/window with temporary stores and a scripted reasoner.
- Compile check: `python -m compileall proto_mind` via `scripts/run_tests.sh` OK.
- Pytest: optional; currently not installed and skipped cleanly.

## Major Modules And Versions

- Persona Engine 0.1 / Model-independent foundation: `persona_engine.py`, strict `persona/brother-0.1.0.json`, seven-case deterministic evals and `PERSONA_ENGINE_MIGRATION_MAP.md`. One Brother identity only; immutable non-authorizing snapshots, read-only Identity projection and explicitly supplied provenanced memory. No production prompt/UI integration, store writer, model call, Context Injection or new permission.
- Native Local Capability Contracts And Computer Use Lifecycle / Native 0.16.0: `local_knowledge_capabilities.py`, private bridge callbacks and strict Swift envelope rendering; monotonic public work-log versions; official signed-client `turn-ended` notification. No model tool, public MCP, store mutation, service kill or authority expansion.
- Native Computer Use Fresh-State Guard / Native 0.14.2: current per-turn guidance in `native_agent.py` plus a 30-second strict MCP tool timeout in `native_codex.py`. First app state is complete, timed-out alias retries are forbidden, and durable provider threads require no reset. No tool, permission, command or core schema change.
- Native Mode-bound Codex Continuity / Native 0.14.1: `native_codex_threads.py` v2 bindings, mode-aware bridge/status integration and Settings disclosure. Separate Chat/Full Mac provider instruction contexts; legacy v1 IDs are historical only. No new command, tool, permission, dependency or core schema.
- Native Full Mac Computer Use / Native 0.14.0: `native_computer_use.py` verifies and discovers the separately installed signed OpenAI service; strict Full Mac config exposes only ten known GUI tools. `native_agent.py`, `native_progress.py`, `native_work_sessions.py` and Swift views project privacy-reduced action evidence. No new slash command, dependency, core schema, copied proprietary runtime, saved grant or background execution.
- Native Full Mac Live Web Search / Native 0.13.0: strict Codex configuration enables live Web Search only for an in-memory explicitly granted Full Mac session; bounded public search evidence excludes raw result payloads. This remains available inside 0.14.0.
- Native Durable Codex Sessions / Native 0.12.0: `native_codex_threads.py`, durable `thread/start`/`thread/resume` integration in `native_codex.py`, bridge status/reset RPCs and Swift Settings/Context Desk controls. Private binding IDs only; provider rollouts remain in the isolated profile. No new slash commands, dependencies, core schemas, automatic retry or sticky permissions.
- Native Selected PDF Page Text EV-02 / Native 0.11.0: `native_pdf.py`, `PDFAttachments.swift`, fixed `native/PDFHelper` executable and read-only `pdf_preview` RPC; explicit history-v5 PDF metadata and per-run hashes only. Existing byte-reader boundary, cloud opt-in, protected paths and operator bypass remain. No new dependencies, Registry prefixes or core-store migration.
- Native Run Notices And Review Availability / Native 0.10.2: `WorkSessionNotices.swift`, optional compatible history-v4 display preferences and targeted journal selection; `TaskReviewView.swift` explains unavailable review states and starts no-criteria completed replies at rework. No backend review gate, run/core schema, command or permission changes.
- Native Attachment Recovery And Drop / Native 0.10.1: `AttachmentDrop.swift`, bounded SwiftUI/AppKit input, existing read-only image/text previews, atomic explicit private attachment save, split-layout recovery and Codex runtime PATH/EOF diagnostics. No new commands, grants, core schema or image format.
- Native Selected Image Inputs EV-02 / Native 0.10.0: `native_images.py`, `ImageAttachments.swift`, read-only `image_preview`, explicit metadata-only private history-v4 attachments, bounded Send-time SHA/model validation and Codex image payloads. No OCR, local-provider vision, new commands, core-store schema or tool permission.
- Native Criteria And Manual Acceptance EV-02 / Native 0.9.0: `native_review.py`, `TaskReviewView.swift`, optional private history-v3 criteria, frozen per-run contract, read-only `review_preview` and explicitly confirmed one-run `review_save`. Receipt history remains distinct from automatic goal verification; no new slash commands, tools, core schemas or permissions.
- Native Context And Artifact Desk EV-02 / Native 0.8.0 (text-first): `native_desk.py`, `ContextArtifactDesk.swift`, three read-only Native RPCs; optional per-run compact context manifest and up to 24 completion-hash artifacts. Same protected text reader, no original copies/restore or automated goal acceptance. Registry still 387 / 41.
- Native Reliable Work Sessions EV-01 / Native 0.7.0: `native_work_sessions.py`, `WorkSessionsView.swift`, shared `NativeInteractions.swift`, bridge/model integration, optional history-v3 draft reference. Private per-run JSON (`native_work_session.v1`), 500-run / 256 KiB-record limits, no pruning or automatic acceptance. Core Registry remains 387 / 41.
- Native Material / Model Controls v4.0f / Native 0.6.0: translucent sidebar with accessibility fallback, shared 14/12 typography, hierarchical model/effort selectors, per-chat settings and protocol forwarding. Current runtime: Codex CLI 0.151.0 with verified Sol access. No model/effort is advertised solely because it appears in a screenshot.
- Native Conversation UI / Public Work Timeline v4.0e / Native 0.5.0: calmer grouped sidebar, compact composer, explicit public progress/final separation, persisted optional work log with duration and Stop/failure state. Legacy history, local library, core rules and Full Mac boundaries are preserved.
- Native Agent Tools v4.0d / Native 0.4.0: opt-in Full Mac shell/edit mode, session-only grants, activity/partial-failure receipts, visible access controls and unchanged chat isolation. Preserves the v4.0c read-only library, v4.0b workspace/attachments, existing core command gates and separate subscription profile. No Registry growth or store migration; native unrestricted shell is a new, explicit authority outside those core command gates.
- Python 3.11 Environment Guard v1.0: stable Python selector scripts and early runtime guard.
- CLI/shared handler: `proto_mind.main`, reused by CLI, tkinter desktop, and PySide desktop.
- Tkinter Desktop v0.5: compact/debug chat, system panel, clipboard fixes, transcript export, prefs.
- PySide6 Cognitive Control Room v2.3.0: intentional amber/teal desktop UI, single-call Cognitive Turn Card with full-answer/evidence views, four exact fail-closed typed operator cards, live local/context/capability indicators, the original 12-action Control tab, and a 12-step contest Demo Runway with preview-gated exact consent/runner buttons; Debug/text fallback, local macOS `.app` launcher, and Desktop shortcut helper remain intact.
- Session Control Room: `/session self-check`, `/session health`, `/session doctor`, `/session review`, `/session log ...`, plus Session Rituals v1 read-only start/end/checkpoint/handoff briefs.
- Natural Command Router v2.3: exact routes plus policy-aware registry metadata in `/natural explain|list|doctor`, with suggestions still non-executing.
- Command Registry v1.0: metadata for 387 slash-command prefixes across 41 categories with mutation/risk labels and Natural Router consistency checks.
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
- Durable Skill Provenance Inspection v3.5e: embedded `skill.procedure.provenance.v1` evidence plus read-only `/skills why|provenance-doctor`; no skill execution or second writer.
- Procedural Skill Outcome Review v3.5f: exact provenance-bound manual-use lineage produces advisory success/failure/mixed/insufficient-evidence states; usage telemetry is ignored and no capture, score update, or execution path exists.
- Supervised Manual Skill Outcome Capture v3.5g: exact session consent plus a second provenance/evidence token records one bounded process-memory manual-use outcome batch; no procedure or persistent-store mutation occurs.
- Supervised Procedural Skill Outcome Decision v3.5h: decisive review plus confirmed capture receipts and a second exact token produce one terminal keep/revise/archive process receipt; no apply readiness or skill mutation.
- Procedural Skill Lifecycle Apply Readiness v3.5i: read-only current decision/evidence/capture/provenance/skill-byte revalidation plus keep/archive/revise future safeguards; readiness itself generates no token and invokes no writer.
- Supervised Procedural Skill Lifecycle Apply Pilot v3.5j: one second exact token permits a byte-stable keep receipt or one atomic archive with post-write verification and rollback; revise and skill execution remain unavailable.
- Durable Procedural Skill Lifecycle Audit v3.5k: read-only status/history/inspect/Doctor views recover current durable skill state and leave archive cause explicitly ambiguous when no supported lifecycle evidence survived restart.
- Durable Skill Lifecycle Metadata Design Lock v3.5l: pure canonical envelope builder/verifier plus existing status/Doctor integration, with no writer, migration, or Registry expansion.
- Durable Skill Lifecycle Writer Readiness v3.5m: optional `--durable` readiness/plan binds current archive evidence to fixed metadata, mutation, receipt, and rollback requirements without a new command prefix or writer.
- Durable Skill Lifecycle Metadata Apply Pilot v3.5n: mandatory `--durable` apply preview/token permits one atomic archive envelope, exact three-field verification and byte rollback; lifecycle audit recovers `archived_verified` after restart.
- Durable Skill Lifecycle Restore Design Review v3.5o: read-only restore contract/readiness/plan embeds the complete verified archive envelope and locks future mutation/receipt/rollback scope without a token or writer.
- Direct Lifecycle Status Guardrail v3.5p: generic archive/restore fails closed for lifecycle-managed or corrupt records before timestamp/write while legacy/operator records remain compatible.
- Lifecycle-Managed Skill Payload Guardrail v3.5q: summary/body/tag/use mutations fail closed for lifecycle-managed or corrupt records before callback/timestamp/write while pre-lifecycle/operator records remain compatible.
- Durable Restore Authorization Readiness v3.5r: exact current restore hashes, immutable fields, confirmation/run-once scope, future receipt, and rollback are bound read-only with no token, state, engine, or writer.
- Supervised Durable Restore Apply Pilot v3.5s: one exact hash-bound token can atomically reactivate one `archived_verified` skill per process by changing only `lifecycle/status/updated_at`; the fixed 21-field receipt proves archive retention, immutable provenance/payload, unchanged memory, restart-safe `active_restored_verified`, and exact-byte rollback readiness.
- Durable Restore Receipt Audit v3.5t: read-only reconstruction hashes ten provable receipt fields from the embedded restore envelope/current record, compares a live process receipt when available, flags legacy/orphan/mismatched receipts, and prints copyable JSON without persisting or inventing the original 21-field receipt.
- Restored Skill Re-evaluation Design v3.5u: read-only review excludes pre-restore and unbound evidence, requires exact provenance/restore/evidence hashes on new manual-use anchors, and blocks legacy capture/decision paths for restored skills until a separate writer exists.
- Supervised Post-Restore Outcome Capture Readiness v3.5v: read-only future-capture blueprint binds exact session consent, current Skill Library/record/provenance hashes, restore metadata/evidence, outcome evidence, required four-event fields, and fixed receipt scope; token generation, event append, writer, and procedure execution remain absent.
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
- Local Capability Contract v1: transport-free typed contracts for the exact four-command read-only runner allowlist, with zero-argument schemas, conservative MCP-style annotations, a three-channel local result envelope, and Capability Doctor drift checks; no server, network, external host, dependency, or runner expansion.
- Local Typed ViewModel v1: pure PySide presentation projection for those exact four contracts, with escaped full-report cards, local-boundary validation, and fail-closed text fallback; shared routing, CLI, tkinter, stores, and runner scope remain unchanged.
- Local Cognitive Turn Envelope v3.6a: optional immutable normal-turn projection of the existing `InteractionResult` through an additive single-call runtime API; exact text fallback, bounded recalled-memory previews, explicit evidence limits, no extra model/store/log/Experience effects.
- Cognitive Turn Card v3.6b: pure local view model and PySide renderer over the single completed envelope, full escaped answer, bounded retrieved-memory/warning/hint views, UNKNOWN audits, preserved injection/Experience notices, and original Debug/text fallback without retry or new authority.
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
- v3.4f / Learning Lifecycle Apply Readiness: read-only revalidation binds the lifecycle receipt to current lesson provenance, exact outcome evidence, persistent-store SHA-256, a valid replacement contract, and the registered memory mutation gate without invoking the writer.
- v3.4g / Supervised Lesson Lifecycle Apply Pilot: one fresh exact lifecycle token permits keep as a byte-stable no-op or reject/supersede as an atomic one-record soft transition with immutable provenance, post-write verification, and exact-byte rollback.
- v3.4h / Lifecycle Transition Audit: read-only durable-state reconstruction classifies learned lessons and checks provenance, lifecycle shape/timestamps, replacement integrity, unique IDs, and acyclic links after restart.
- v3.5a / Procedural Skill Contract: read-only source-bound authoring templates require explicit trigger, preconditions, steps, permissions, verification, and failure modes, while synthesis, storage, promotion, and execution remain unavailable.
- v3.5b / Procedural Skill Authoring Receipt: exact visible author fields and current source hashes are bound to a maximum of 16 immutable process-memory receipts through the existing proposal gate, without skill persistence or execution.
- v3.5c / Procedural Skill Apply Readiness: read-only current receipt/source/global duplicate/store-hash revalidation plus a fixed future atomic receipt and rollback contract, with no writer or token generation.
- v3.5d / Supervised Procedural Skill Apply Pilot: one second exact token permits one atomic verified `skill.procedure.v1` append per process; receipt, exact-byte rollback, unchanged-memory proof, and non-execution boundaries are mandatory.
- v3.5e / Durable Skill Provenance Inspection: new supervised skills retain restart-safe source, contract, payload, and confirmation hashes; read-only why/Doctor views detect tamper, source history, current payload drift, and legacy gaps.
- v3.5f / Procedural Skill Outcome Review: exact current-process manual-use lineage and verified operator-reported outcomes produce advisory success/failure candidates, while mixed or absent evidence remains inconclusive and all stores stay unchanged.
- v3.5g / Supervised Manual Skill Outcome Capture: active pilot consent plus an exact skill/provenance/outcome/evidence token appends one fixed process-memory evidence batch, with bounded receipts and no procedure execution.
- v3.5h / Supervised Procedural Skill Outcome Decision: success maps to keep, failure/mixed maps to revise/archive, and one exact terminal receipt binds current review plus all confirmed capture evidence without applying the choice.
- v3.5i / Procedural Skill Lifecycle Apply Readiness: current decision, evidence, capture hashes, provenance, exact skill record, and Skill Library bytes are revalidated against a decision-specific future contract without generating authorization.
- v3.5j / Supervised Procedural Skill Lifecycle Apply Pilot: one exact current keep/archive decision can cross a separate confirmation gate; keep is byte-stable and archive changes only status/updated_at with immutable provenance and exact rollback.
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

Persona Engine 0.1 / Model-independent foundation:

- Rule 0: `backups/proto_mind_backup_2026-09-01_20-24-14.tar.gz`; Native 0.16.0 was first committed and pushed as checkpoint `2204800` before Persona implementation.
- Added one exact Brother 0.1.0 kernel plus immutable kernel, identity, selected-memory, task/runtime, snapshot and soft-change contracts. Invalid schema, facets/modes, untraceable memories, external identity instructions, unsupported capabilities and permission-change candidates fail closed.
- Snapshot compilation is read-only and model-independent: Identity reads do not initialize missing stores, memory retrieval is outside the compiler, runtime authority is factual and non-authorizing, absolute workspace paths are not embedded, and hashes bind canonical payloads. Production reasoner/Codex prompts and Native UI are unchanged pending Persona 0.2/0.3.
- Sixteen regressions bring the Python suite to 1533; Persona evals pass 7/7 with `model_calls=0` and `store_writes=0`; all 355 Native checks, release build, compileall and imports pass. All 48 project `data`/`exports` files match the checkpoint by SHA-256, Registry remains 387/41 and Context Injection remains disabled.

Previous milestone, Local Capability Contracts And Computer Use Lifecycle / Native 0.16.0:

- Rule 0: `backups/proto_mind_backup_2026-09-01_18-32-25.tar.gz`; no credential/provider-profile checkpoint and no core-store migration.
- The Native Library now uses two exact typed local callbacks, `search` and `fetch`. Python owns the detached structured result; Swift validates the envelope and page/detail schema before rendering. Unknown inputs, widened network/write/model metadata and stale async display state fail closed. Legacy direct read methods remain only as method-absence compatibility for a rolling local rebuild.
- Public work-log snapshots carry positive monotonic `state_version` values; same-run stale events cannot replace newer UI state. Existing unversioned saved logs remain readable without rewrite, and no private reasoning is added to the public projection.
- The Computer Use diagnosis found that Proto-Mind closed its Full Mac app-server but configured `notify=[]`, while the official signed client expects `turn-ended` to release active desktop-managed capture/UI state. Eligible turns now install that exact hook. Ordinary Chat and Full Mac without verified Computer Use retain an empty notify list; Proto-Mind does not terminate the shared ChatGPT service itself.
- Seven Python regressions bring the suite to 1517; all 355 Native checks, six local agent evals, release build, plist/signature validation and personal-app relaunch pass. Version is 0.16.0 build 20. All 48 project `data`/`exports` files match the Rule 0 checkpoint by SHA-256, Registry remains 387/41 and Context Injection remains disabled. No slash prefix, public MCP endpoint, dependency, Platform/API-key path, target-store writer, new authority or runtime service-kill path is introduced.

Previous milestone, Agent Contract And Automation Onboarding / Native 0.15.0:

- Rule 0: `backups/proto_mind_backup_2026-09-01_16-21-07.tar.gz`; no credential/provider-profile backup or core-store migration.
- A deterministic contract is frozen before the Full Mac process starts and binds provider, model/effort, workspace identity, tool allowlist, limits, stop conditions and criteria digest. Runtime Computer Use tools are verified separately; provider completion remains `verification:not_assessed` and operator acceptance remains separate.
- Exact `Computer Use server error -1743` is projected as a bounded macOS Automation denial with manual recovery guidance. `NSAppleEventsUsageDescription` and an **Open Automation** UI action enable normal TCC onboarding, but the app never toggles permission or retries.
- Official OpenAI Developers patterns adopted locally: explicit agent contract, narrow schemas and dependency-free evals. Explicitly excluded: Agents SDK runtime, API key, Platform/Deployment Manager, provider replacement, background work and new authority.
- Eight regressions bring the Python baseline to 1510; the six-case local eval, all 349 Native checks and the release build/plist/signature pass. Version is 0.15.0 build 19 and the personal app relaunches successfully. All 48 core/export files plus conversations, preferences, thread bindings and 12 work-session records remain byte-identical; only the separate provider model catalog cache refreshes on normal relaunch. Registry remains 387/41 and Context Injection remains disabled. Live post-permission Proto-Mind Computer Use acceptance is still required after the operator approves macOS Automation.

Previous milestone, Computer Use Fresh-State Guard / Native 0.14.2:

- Rule 0: `backups/proto_mind_backup_2026-09-01_15-42-53.tar.gz`; private checkpoint `backups/proto_mind_native_history_2026-09-01_15-47-13_safari_timeout.tar.gz`, no credentials or provider profile.
- The personal Safari failure was two sequential `get_app_state` calls of about 90 seconds each. Direct service state and a one-call Proto-Mind control both read Safari in under one second when requesting a complete fresh state, isolating the bug to stale/diff observation behavior.
- Every Computer Use-capable turn now carries current guidance to use `disableDiff=true` for the first state of each app, including pre-existing durable Full Mac threads. Timeout alias retries are forbidden and the strict tool timeout is 30 seconds. No automatic screenshot/shell fallback or UI action was added.
- Two regressions bring the Python baseline to 1502; Native remains 349 checks. Version is 0.14.2 build 18. Registry remains 387/41 and Context Injection remains disabled.
- Live acceptance with ordinary Safari wording resumed the existing Full Mac provider thread, issued exactly one `get_app_state` and completed in 334 ms. No click, typing, scrolling, shell command or file action was observed.

Previous milestone, Mode-bound Codex Continuity / Native 0.14.1:

- Rule 0: `backups/proto_mind_backup_2026-09-01_15-11-25.tar.gz`; private pre-migration checkpoint `backups/proto_mind_native_history_2026-09-01_15-23-34_mode_threads.tar.gz`, no credentials or provider profile.
- A real failure showed `access_mode=full_access` and Computer Use availability but zero tool activity: the resumed thread had originated in Chat and retained its durable no-tools developer instruction. The working folder was not a Full Mac fence; the model's refusal came from incompatible provider-thread instructions.
- `codex_threads.json` v2 binds provider threads to `(conversation_id, instruction_mode)`. Chat and Full Mac each start/resume only their own thread and receive bounded local history once on first creation. Legacy v1 rows stay readable and preserved as `legacy_unknown`, but are never guessed or resumed as either mode.
- Live read-only acceptance invokes `list_apps`/`get_app_state`, then resumes the new Full Mac thread and successfully reads Finder state. The Computer Use runtime protects ChatGPT's own application state; this is a service safety boundary, not another workspace-only failure. No clicks, typing, scrolling or file actions were requested or observed.
- Three regressions bring the Python baseline to 1500; Native remains 349 checks. Version is 0.14.1 build 17. All 48 core/export, conversation, preference and eight work-session hashes remain unchanged; only `codex_threads.json` migrates intentionally. Registry remains 387/41; no new tool, permission, dependency, core/session schema or Context Injection behavior was added.

Previous milestone, Full Mac Computer Use / Native 0.14.0:

- Rule 0: `backups/proto_mind_backup_2026-09-01_09-12-48.tar.gz`.
- Full Mac now discovers the canonical installed OpenAI Computer Use app/client, verifies both Developer ID signatures, team/bundle identities and version, and gives Codex exactly ten known GUI tools through one required MCP server. The proprietary runtime is not copied into the repository.
- Ordinary chat still has an empty MCP map, `features.computer_use=false`, no shell and no Web Search. The Full Mac permission remains explicit, conversation/workspace-bound, process-memory-only and revoked on restart/provider/folder/cloud boundaries.
- Real model-free readiness, application inventory, Calculator state and harmless keyboard calls pass through the authenticated Codex 0.151.0 path and OpenAI Computer Use 26.828.1000919. The local receipt excludes screenshot/UI-tree/result payloads, coordinates and typed/selected values. Screen content can still be processed by OpenAI during an active turn; Stop/Esc is interruption, not rollback.
- Six regressions bring the Python baseline to 1497; Native remains 349 checks. No Registry prefix/category, dependency, core schema, Context Injection behavior, arbitrary MCP/plugin or background execution was added.

Previous milestone, Full Mac Live Web Search / Native 0.13.0:

- Rule 0: `backups/proto_mind_backup_2026-09-01_08-37-08.tar.gz`.
- The existing explicit, conversation/workspace-bound Full Mac grant now starts Codex with `web_search=live`, the Web Search tool enabled and the existing unrestricted shell/file authority. Ordinary chat still starts with Web Search, shell and unified execution disabled. The grant remains process-memory-only and is not restored on restart.
- Public activity and durable private work-session evidence retain only a bounded search query, recognized action type and sanitized HTTP(S) page location. URL credentials, query strings, fragments, opaque result objects and unknown provider fields are discarded. A receipt explicitly records whether network access occurred and how many Web Search items were observed.
- The agent contract treats search results as untrusted data, forbids using local file contents, credentials or secrets in search queries/URLs, and asks for source links when web material informs the answer. These instructions are defense in depth, not a data-loss-prevention engine.
- This historical 0.13.0 milestone did not enable interactive screen control; Native 0.14.0 adds the separately documented signed Computer Use path above.
- No Registry prefix, core store, Context Injection, session-log schema, model selection, image/PDF boundary or provider-thread mapping changes were introduced. The official configuration basis is the [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

Previous milestone, Durable Codex Sessions / Native 0.12.0:

- Rule 0: `backups/proto_mind_backup_2026-09-01_07-47-09.tar.gz`; private conversations/preferences/work-session checkpoint `backups/proto_mind_native_history_2026-09-01_0749_durable_threads.tar.gz`, no credentials/profile copied.
- At the 0.12.0 milestone, each Native conversation started one non-ephemeral Codex thread and attempted to resume it across Chat/Full Mac modes and bridge restarts. Native 0.14.1 supersedes that cross-mode assumption with separate mode-bound threads because provider developer instructions persist. Workspace/policy drift and resume failure still stop without fallback; explicit Settings reset removes local bindings only.
- 1488 Python / 348 Native checks cover atomic bounded storage, corruption/symlink/disk failure, restart, no history replay, resume refusal, policy/workspace drift, mode changes and local status/reset/context UI contracts. Registry remains 387/41; core/session schemas and Context Injection behavior are unchanged.
- Provider history now persists under the separate Native Codex profile and may include sensitive prompts, responses, selected inputs and tool output. There is no retention/delete/export UI, cross-device sync, transcript import or live two-turn personal-account acceptance in this milestone. Full Mac remains session-only.

Previous milestone, Selected PDF Page Text / Native 0.11.0:

- Rule 0: `backups/proto_mind_backup_2026-08-31_20-19-00.tar.gz`; separate private checkpoint `backups/proto_mind_native_history_2026-08-31_20-23-37_pdf_input.tar.gz`, excluding credentials.
- PDF no longer falls into the workspace UTF-8 refusal path. Drop one separately or use + > PDF; select/review pages, attach metadata, then explicitly Send. No original upload/cache or automatic cloud/tool grant.
- Timed local PDFKit worker and exact source/text hash checks; missing text, encrypted/corrupt PDF and changed selections refuse without fallback. PDF text is untrusted source data, not instructions or authorization. Context desk and private run metadata preserve page provenance.
- 1471 Python / 346 Native checks, compileall, imports and release build pass. Isolated release UI validates page selection, compact draft, context desk, restart and explicit Mock Send. Finder-style pasteboard/AppKit drop is integration-tested; physical cross-window drag and live model document quality are not separately certified. Registry 387/41, no new dependencies. No user PDF was used.
- Personal profile reopened after smoke. All 48 core/export files and six personal history/preferences/work-session files retain pre-change SHA-256; Context Injection remains disabled. Existing legacy warnings are untouched.
- Remaining: scans/OCR, visual layout/tables, local image models and project-memory isolation. Normal answers can quote PDF text and remain in ordinary chat history; metadata-only attachment storage is not a redaction guarantee.

Previous milestone, Run Notices And Review Availability / Native 0.10.2:

- Rule 0: `backups/proto_mind_backup_2026-08-31_18-44-41.tar.gz`; separate private history/preferences/work_sessions checkpoint `backups/proto_mind_native_history_2026-08-31_18-48-18_notice_review.tar.gz`, no credentials.
- Old unfinished banners have X and journal Hide/Show controls; display preferences survive restart without modifying run status/evidence. New/changed records warn again, source diagnostics remain visible, and opening a banner selects its affected run.
- Acceptance replaces disabled forms with state-specific explanations. Completed no-criteria replies offer rework-with-comment; criteria acceptance still requires existing evidence checks and explicit confirmation. No completion invented for unknown runs.
- 1454 Python / 299 Native checks, compileall, imports, release build and isolated UI smoke pass. All 48 core/export and six personal history/preferences/journal file SHA-256 values remain unchanged. Injection disabled, Registry 387/41; no model/tool calls or repairs to existing legacy warnings. Personal notice dismissal remains an operator choice.

Previous milestone, Attachment Recovery And Drop / Native 0.10.1:

- Rule 0: `backups/proto_mind_backup_2026-08-31_17-31-52.tar.gz`; separate private history/preferences/work_sessions checkpoint `backups/proto_mind_native_history_2026-08-31_17-33_attachment_fix.tar.gz`, no credentials.
- Saved-image notices no longer expand minimum-width split layout beyond the window; attachment strips are height-bounded and the picker is nonblocking. Finder's minimal PATH gains known runtime directories so the npm Codex launcher can find Node. Early transport exit has an honest startup diagnostic.
- Drag local PNG/JPEG or supported workspace UTF-8 files into chat/editor, review locally, explicitly attach, then separately Send. Max three images/three text files, existing hash/type/size/path checks, no automatic folder binding, URL import or conversion. Stale/invalid batches and failed saves leave the draft intact.
- 1453 Python / 267 Native checks, compileall, imports and release build pass. Isolated UI covers restored image layout, text/image drag gestures, cancel/attach and picker; live tool-free Sol handles a synthetic 3.7 MB image with Finder PATH. Core/export, personal history/preferences and private failed-run evidence remain byte-identical; Context Injection disabled, Registry 387/41. Existing 12 accepted-known warnings are not repaired.
- No auto-send/retry, image-history replay, tools, scope expansion, PDF/local vision or core migration. The wider EV-02 roadmap remains open.

Previous milestone, EV-02 Selected Image Inputs / Native 0.10.0:

- Checkpoint: `backups/proto_mind_backup_2026-08-31_15-34-04.tar.gz`; private conversations/preferences: `backups/proto_mind_native_history_2026-08-31_15-35_ev02_images.tar.gz`. Both private; personal work_sessions absent, credentials excluded.
- Composer + opens a local PNG/JPEG preview; separate Attach saves only bounded path/hash/dimension/type metadata. Context exposes readiness/destination, Send rechecks source bytes and current Codex model image capability. Existing chat isolation, cloud opt-in and separate Full Mac grant remain unchanged. No image bytes/data URLs in Native history or journal; previous images are not automatically read/resent.
- History v4 reads versions 1/2/3 without startup migration. Older apps reject v4 rather than silently dropping images. Changed files, protected paths, arbitrary links, malformed/oversized images, unsupported providers/models and stale UI selections fail visibly. Originals and embedded metadata remain untouched; there is no automatic redaction or full Python image codec.
- 1448 Python / 218 Native checks, compileall, release build and isolated UI smoke pass. One live 5.6 Sol tool-free request correctly identifies colors/shapes in a generated test PNG. All 48 core/export hashes and personal Native conversations/preferences are unchanged; Context Injection disabled, Registry 387/41, accepted findings 12 / unknown 0.
- Remaining EV-02: PDF/local-provider vision, richer artifacts and real project-memory isolation. No screen/clipboard capture, OCR, restore, new tools, automatic acceptance or background work.

Previous milestone, EV-02 Criteria And Manual Acceptance / Native 0.9.0:

- Checkpoint: `backups/proto_mind_backup_2026-08-31_14-30-48.tar.gz`; private history/preferences: `backups/proto_mind_native_history_2026-08-31_14-33_ev02_acceptance.tar.gz`. Personal work_sessions was absent; no credentials copied.
- Composer checklist lets the operator explicitly save up to eight criteria, inspect them in Context and freeze them with normal Send. Only native reasoner requirements change when criteria are supplied; original Observer/log input, operator bypass and core memory rules are preserved. Empty criteria preserve existing prompt behavior; failed/operator sends do not consume the draft.
- Journal Manual Acceptance separates checked criteria, operator decision, model completion and unassessed automatic verification. A fresh preview plus second explicit confirmation uses the cooperative lock/byte-CAS private writer. Stale evidence/replayed confirmations, wrong scope, concurrent writes, partial or unknown outcomes refuse; later assessments preserve prior receipts (limit 12). No target command/model/tool, repair or promotion runs during review.
- 1424 Python / 196 Native checks, compileall, release build and disposable-window smoke pass. The window uses one synthetic run backed by two local assertions and one actual Mock message, not a live model benchmark. All 48 core/export hashes and personal Native history/preferences remain unchanged. Context Injection disabled; Registry 387/41; accepted-known warnings 12 / unknown 0.
- EV-02 remains partial: image/PDF inputs, richer artifact actions and real project-memory isolation are next. Manual acceptance is not an automated verifier, signed identity or filesystem freeze. Known legacy warnings remain visible and untouched.

Previous milestone, EV-02 Context And Artifact Desk, text-first slice / Native 0.8.0:

- Checkpoint: `backups/proto_mind_backup_2026-08-31_13-42-39.tar.gz`; separate private history/preferences: `backups/proto_mind_native_history_2026-08-31_13-43_ev02.tar.gz`, no credentials.
- Fixed intrinsic model-menu hover geometry. The composer Context desk exposes eligible UTF-8 excerpts/hashes, bounded history, destination/consent and shared core versus workspace scope. Changed attachments require manual review; no preview-time recall, LLM, permission grant or execution.
- Journal Results shows bounded run/tool-linked artifacts, captured versus current SHA, known original attachment SHA, diff/command output, model answer and explicit unassessed verification/unrecorded acceptance. Unknown/legacy evidence is not upgraded. Private metadata is added only to new ordinary runs through the existing writer; views never rewrite files.
- 1387 Python / 170 Native checks, compileall, release build and isolated UI smoke pass. UI evidence is synthetic with an actual two-case local fixture check, not a live model run. Core/export SHA remains unchanged for all 48 files, personal Native history/preferences unchanged, Injection disabled, Registry 387/41, accepted warnings 12 / unknown 0.
- Remaining EV-02: explicit image/PDF input, structured success criteria/manual acceptance and project-memory isolation. No restore, broker, new model tools, background tasks or automatic evidence-based success claim was introduced.

Previous milestone, EV-01 Reliable Work Sessions / Native 0.7.0:

- Checkpoint: `backups/proto_mind_backup_2026-08-31_12-37-51.tar.gz`; separate conversations/preferences backup: `backups/proto_mind_native_history_2026-08-31_12-38_hover_sessions.tar.gz`, without credentials.
- Unified hover/press treatment and a toolbar work-journal view. New normal turns save compact public evidence under private Native `work_sessions/`, before and during dispatch; no full prompt stream, raw reasoning or automatic permission reuse. Completed response, unknown side effects, verification and acceptance are distinct.
- Failure/restart/disk-full/corruption/duplicate/CAS/lock/backup-restore fixtures pass. Manual continuation refuses overwritten drafts, changed parent/folder/source evidence and a second child; only explicit Send can process the new draft. Read-only journal/recovery RPCs never execute a model or mutate core stores. Existing core/session schemas, injection and cognitive write rules are unchanged.
- 1356 Python tests, 139 Native checks, compileall, release build and isolated Native window smoke pass. UI smoke uses synthetic interrupted evidence plus one explicit local Mock continuation; no live cloud generation or real-project tool action was performed for this milestone. All 48 core/export hashes and personal Native history/preferences hashes are preserved, with Context Injection disabled.
- Next: EV-02 context/artifact desk, not a daemon, auto-retry, provider-thread resume or generalized tool-permission expansion. See `NATIVE_MACOS_ROADMAP.md` for private backup/restore instructions and evidence limits.

Previous milestone, Native Material / Model Controls v4.0f:

- Runtime follow-up (2026-08-31): Codex CLI 0.136.0 -> 0.151.0 restores real 5.6 Sol/Terra/Luna discovery without adapter changes or auth migration. Project checkpoint `backups/proto_mind_backup_2026-08-31_12-17-45.tar.gz`, Native history/preferences checkpoint `backups/proto_mind_native_history_2026-08-31_codex_upgrade.tar.gz`, old CLI archive `backups/codex_cli_0.136.0_before_upgrade_2026-08-31.tar.gz`. 1329 Python / 115 Native checks, Sol chat/tool probes and actual UI menu smoke pass; preserved hashes and disabled Context Injection verified.
- Sidebar overflow fix (2026-08-31): navigation, library disclosure, search and conversations now share a height-bounded scroll area; the header/footer stay fixed. Expansion cannot increase the split view's minimum height or push the chat/composer out of the window. Six layout/read-only regressions and a normal/short-window UI smoke pass. Checkpoints: `backups/proto_mind_backup_2026-08-31_11-42-58.tar.gz` and `backups/proto_mind_native_history_2026-08-31_11-44-26_sidebar.tar.gz` (history/preferences only).
- Project checkpoint: `backups/proto_mind_backup_2026-08-31_11-07-24.tar.gz`. Native conversations/preferences checkpoint: `backups/proto_mind_native_history_2026-08-31_11-07-42_model_ui.tar.gz`; no credentials copied.
- Separate checked Model/Effort menus, shared Settings controls, reset, and a visible model/effort composer label. Selection persists only after operator action; legacy history loads without rewriting. Unsupported effort on a manually selected model resets with a notice; stale catalog choices are refused before generation, not silently substituted.
- 13 Python regressions and 17 Native checks added. Isolated UI smoke covers picker selection, end-to-end `effort=xhigh` request, restart, incompatible model reset, and Settings consistency. A real tool-free GPT-5.5 chat adapter turn with `effort=high` returned the exact requested verification line; no personal prompt/history/core turn was involved.
- Registry remains 387 commands / 41 categories. All 48 core/export files and personal Native conversation/preferences SHA-256 remain unchanged. Context Injection remains disabled; no cloud permission, Full Mac grant, service tier, core schema, or legacy desktop behavior changed.

Previous milestone, Native Conversation UI / Public Work Timeline v4.0e:

- Project checkpoint: `backups/proto_mind_backup_2026-08-31_09-55-03.tar.gz`. History/preferences-only checkpoint: `backups/proto_mind_native_history_2026-08-31_09-55-17_chat_ui.tar.gz`; no credential copy.
- New chat layout follows the operator's screenshots: workspace-grouped conversations, right-aligned user bubbles, open answer typography, compact model/access composer and optional diagnostics. Work timeline displays only public commentary/plans and observed tools with elapsed time, separate from the answer.
- 16 Python public-stream tests and 13 Swift work-log/grouping checks added. An isolated real-window fixture verifies streaming, expandable tool output, Stop and restart persistence without executing its synthetic commands. A separate real account-default chat adapter probe returned public commentary plus the exact final answer in one turn without tools or private project context.
- All 48 core/export files and personal Native conversation/preferences bytes remain unchanged; Context Injection stays disabled. No raw reasoning, new grant, model-effort setting, automatic injection, core replay, or store migration. Work logs are bounded display evidence, not crash-durable or secret-redacted audits.

Previous milestone, Native Agent Tools v4.0d:

- Project checkpoint: `backups/proto_mind_backup_2026-08-31_09-04-11.tar.gz` (native/scripts/docs coverage verified). History/preferences-only checkpoint: `backups/proto_mind_native_history_2026-08-31_09-09-49.tar.gz`; no credential copy.
- Explicit Full Mac mode in the composer enables official Codex built-ins only after cloud consent and a live conversation/folder grant. Login, workspace binding, library navigation and history loading do not grant tools. Grant resets on restart; provider/folder/cloud changes, disable and failed turns discard UI access.
- Live separate-profile adapter smoke on 2026-08-31: temporary `message.txt` checkpoint, before-to-after edit, two actual terminal commands, all successful with visible diff/output. Personal core/export SHA-256 values remain unchanged; no personal files used as tool targets. Native-history v1/v2 loads without rewrite, while future saves use v3 for receipts.
- This 0.4.0 milestone made no claim of sandboxing Full Mac, complete side-effect auditing, rollback, detached-process termination, crash-safe run journal, or native Computer Use. Native 0.14.0 adds the separately documented signed Computer Use path without changing those broader evidence limits. The foreground loop is time/item bounded and does not auto-retry.

Previous milestone, Native Library Views v4.0c:

- Native sidebar and welcome entry open Memory/Goals/Skills without executing slash commands. Read-only views have literal search, current/history/all filters, pagination, detail cards, stored metadata, and source hashes.
- `native_library.py` uses bounded fixed-path reads rather than `MemoryStore` initialization or unbounded legacy loaders. Missing/corrupt data and duplicate IDs are diagnosed; unknown states, truncation, and source drift are visible. Provenance/lifecycle presence is not a new verification or execution grant.
- Tests and live synthetic-data UI smoke confirm no core-store, usage, focus, skill, native-history/settings, or session-log mutation from viewing. All 48 personal core/export SHA-256 values remain unchanged; Context Injection is still disabled. No cloud probe or new authority is needed for library browsing.
- Checkpoint: `backups/proto_mind_backup_2026-08-31_08-17-42.tar.gz`; native history/preferences also backed up separately, without copying credentials. Details and bounds: `NATIVE_MACOS_ROADMAP.md`.
- Backup coverage caveat found during verification: that initial CLI archive covered the Python/data package and selected docs, not the new root `native/` tree. It is not a full pre-v4.0c Swift rollback. A later current-worktree archive was added at `backups/proto_mind_worktree_2026-08-31_08-51-17.tar.gz` before repairing backup coverage. Future `/memory backup` checkpoints include native source/tests/scripts/docs, exclude caches, publish complete private archives, and never replace an earlier same-second archive. No legacy data was repaired or migrated.
- Verified updated CLI checkpoint: `backups/proto_mind_backup_2026-08-31_08-55-52.tar.gz`; its member list includes Swift library/model/tests, scripts, root docs, and the Python/data package, with private `0600` permissions.

Previous native milestone, Everyday Workspace v4.0b:

- Separate native `.app` over the existing single-call cognitive handler. The 387-command / 41-category core, session schemas, learning gates, and old desktop remain available.
- Search/rename/archive/restore, per-chat drafts, Markdown/code copy controls, local evidence/history, exact operator command confirmation, persisted explicit cloud permission, and optional isolated official ChatGPT/Codex login/streaming adapter. No implicit first-launch connection, API-key fallback, or silent Mock substitution.
- Same-folder project binding with manual refresh, bounded source preview, explicit attachments, and SHA-256 revalidation. Model tools remain disabled; only selected text enters the reasoner adapter, not Observer/session-log user input. Native history v1 remains readable and is upgraded to v2 only on a later save; missing/corrupt settings do not authorize cloud or trigger a rewrite.
- Cloud is explicitly opt-in and not offline. Codex shell/code/browser/extensions/hooks/MCP are disabled, server tool requests denied, and non-chat events refused. An outer macOS process sandbox restricts personal file reads/writes, including built-in image readers; missing isolation fails closed. No model-to-Proto-Mind-command execution path exists. Existing successful normal-turn memory rules remain in effect.
- Live subscription acceptance completed on 2026-08-31 after the operator's browser login. The actual native UI received a plain reply and correctly read version/bundle ID from one explicit hash-checked source attachment. Project/UI-history checkpoints, evidence limits, and remaining tool boundaries are recorded in `NATIVE_MACOS_ROADMAP.md`.

Previous local foundation, Cognitive Turn Card v3.6b:

- PySide worker calls the envelope runtime API once and carries both unchanged text and typed turn data to the UI; no second model call, memory update, log append, or consented Experience capture.
- Compact card preserves the complete answer and exact injection/Experience notices, then shows actual memory decisions, grounding/reflection signals, up to three retrieved-memory previews, and bounded warnings/hints with omitted counts.
- Data is escaped and schema/answer-bound; missing audits stay UNKNOWN. Retrieved does not mean used or verified, and storage requests without stored IDs are not reported as successful writes.
- Debug preserves the full original trace. Invalid/stale payloads or rendering failures fall back to the existing text path with a generic notice and no retry. Enable Debug before the turn; earlier messages are not re-rendered.
- The presentation is read-only, but normal-turn effects continue under existing rules. Full answers/previews are local display content, not redacted publication data. CLI/tkinter, session-log schema, injection behavior, and four-command runner scope are unchanged.
- UI/launcher version is v2.3.0. No new slash commands; Registry stays 387 commands across 41 categories. Context Injection remains disabled locally.

## Next Candidate Tasks

- Persona 0.2 / Visible Persona Preview: expose the validated snapshot in a bounded read-only Native inspector with identity/kernel version, selected sources, actual provider/tools/permissions and omission notices. Do not expose private chain-of-thought, activate production prompts, add modes/facets, perform retrieval, write stores or grant authority.
- Native next: continue daily use to identify the next highest-friction Codex-parity gap. Keep Full Mac explicit/session-only, respect protected Computer Use surfaces and keep provider-thread reset manual. Defer Ollama expansion, scanned-document OCR and new autonomy until the Codex workflow is dependable.
- v3.6c / Cognitive Turn Inspection: evaluate a bounded per-message raw trace and read-only memory-reference inspection without replaying turns, rereading stores during rendering, persistence, or new authority.
- Local Typed Card Expansion Review: evaluate one additional read-only report at a time only after an explicit contract, output schema, local-boundary test, and text-fallback fixture exist.
- Local Contract Expansion Review: evaluate additional read-only commands one at a time with explicit schemas and doctor fixtures; do not infer safety from Registry membership alone.
- Submission Readiness: keep the public repository and provenance manifests current, finalize English Devpost copy, and record the sub-three-minute video.
- v3.5w / Supervised Post-Restore Outcome Capture Authorization Readiness: design one exact session-bound token and run-once receipt gate over an unchanged v3.5v blueprint; no event append or writer before separate review.
- Memory Migration Plan: design deterministic compaction/archive rules for the 8 previewed legacy candidates; no apply step without separate approval.
- Command Dispatch Architecture v2: replace the linear formatter chain with typed incremental family registration while preserving exact command behavior and runner isolation.
- Test Suite Structure v1: split the current 29,044-line flow suite by domain without changing test semantics or commands; do not block the first useful Native Run workflow on a repo-wide refactor.
- Any expansion beyond the exact `/warnings unknown` pilot requires a separate explicit checkpointed task, new tests, exact confirmation scope, and fresh no-write evidence.
- Architect Ledger maintenance automation: command to print or refresh this file from current module state.
- Data Integrity Doctor polish: optional export/report snapshot and thresholds config.
- Consolidation queue polish: add optional preview-to-queue helper and receipt export filtering.
- Cognitive Control Room follow-up: add an optional compact latest Context Injection audit summary without changing settings or normal-prompt behavior.
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

- Native subscription mode sends explicitly selected conversation/context to OpenAI; it is not an offline substitute for Ollama. OAuth/model availability and quotas belong to the account/installed Codex CLI. Do not reuse Codex Desktop tokens or hooks.
- Native UI state is outside the existing project backup scope and can contain private chat/evidence. Back up conversations/preferences and the new `work_sessions/` directory separately before an archive upgrade; never publish Application Support state. No transcript import, automatic history/journal rotation, or independent runtime packaging yet. Journal capacity/corruption blocks new normal turns for manual review rather than silently dropping evidence.
- Native uses durable Codex thread bindings and bounded EV-01 dispatch/evidence checkpoints, not a complete filesystem audit, transactional rollback or global exactly-once guarantee. Attachments are bounded inputs, not a full-project index or secret detector. Full Mac shell and Computer Use can read/change content beyond those previews. Computer Use receipts intentionally omit screenshots, UI trees, coordinates and entered text, so they are not forensic audit logs. Stop/Esc cannot undo side effects or guarantee cleanup of detached processes; unknown historical outcomes remain visible. No automatic sync, voice or background execution yet.
- Native library is a bounded view, not a migration or semantic verifier. Over-limit records are omitted with a warning; snapshots are best-effort reads without cross-process locking. Stored provenance is shown but not revalidated here, and some low-level diagnostics remain in English.
- Existing JSON stores lack cross-process transaction locking; avoid concurrent writes from CLI/PySide/native clients.
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
- Lifecycle-managed payload and usage telemetry are frozen outside explicit future versioned/supervised contracts; no revision writer exists, and pre-lifecycle provenanced records can still drift under legacy edit commands.
- Durable restore is intentionally one-per-process and receipt details are process-local; restart-safe evidence lives in the embedded restore envelope, while re-archive/revision and cross-process receipt persistence remain unavailable.
- No true streaming or real Stop cancellation yet for blocking Ollama calls.
- Cognitive cards are presentation only: deterministic audits do not prove correctness, Debug affects subsequent turns, and per-message inspection remains future work. Qt smoke uses a scripted local reasoner, not live Ollama.

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
