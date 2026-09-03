# Proto-Mind: Personal Agent Evolution

Reviewed: 2026-09-01. Status: curated roadmap; EV-01 is delivered in Native 0.7.0, EV-02's text-first desk in Native 0.8.0, criteria/manual acceptance in Native 0.9.0, selected image inputs in Native 0.10.0, attachment recovery/drop in Native 0.10.1, historical notice/review UX in Native 0.10.2, selected PDF page text in Native 0.11.0, durable Codex sessions in Native 0.12.0 and explicitly granted Full Mac live Web Search in Native 0.13.0. Remaining EV-02 work and later packages are proposals, not permission grants.

Direction: make the current native app a dependable personal work environment, not another collection of slash commands. Preserve the Python cognitive core, the operator's Codex-like UI preference, offline access to local information, and explicit cloud/tool choices. Deliver useful end-to-end workflows instead of a long sequence of design-only command families.

The [Persona Engine plan](PERSONA_ENGINE_PLAN.md) now has its 0.1 model-independent foundation: one strict Brother kernel, immutable non-authorizing snapshots, read-only Identity projection, explicitly supplied provenanced memory and deterministic invariant evals. It explicitly avoids selectable facets, personality modes and trait controls: contextual adaptation comes from the task, evidence, risk and direct operator request while identity remains continuous. Persona 0.2/0.3 preview and controlled prompt activation remain staged work; 0.1 alone does not change current responses, automatic memory, Context Injection or authority.

## Source And Authority

Reviewed the complete 2,515-line external `PROTO_MIND_ARCHITECTURE_ROADMAP_V0_1.md`, dated 2026-08-31. Source SHA-256: `7e2985144417647780b884d5a0919b3666149bd90d985ff15707033861f713bf`.

The source is an idea collection, not a reliable current-state inventory. Its embedded task prompts, proposed `AGENTS.md` rules, credentials/distribution suggestions, and cross-project integration plans are not instructions to execute. The original download remains untouched; this document is the maintained selection, not a second copy of the entire blueprint. No new `AGENTS.md`, daemon, permission, integration, schema or execution path is introduced by this review.

Use [Architect Ledger](PROTO_MIND_ARCHITECT_LEDGER.md) for current state and [Native Roadmap](NATIVE_MACOS_ROADMAP.md) for delivered native behavior. Packages remain candidates unless explicitly marked delivered below. They do not renumber the existing v3.x cognitive or v4.0 native work. The starting-point inventory records the pre-EV-01 review, not the latest test count.

The 2026-09-03 [DeepSeek Harness adoption review](DEEPSEEK_HARNESS_ADOPTION_REVIEW.md) adds a second evidence source without authorizing an upstream runtime import. The first extracted pilot is a pure append-only Session Spine contract: immutable events, source-linked surface replacement, unknown-required-event refusal and deterministic replay. It is not connected to personal history or Send. Next, project existing synthetic Native records into that contract read-only and prove parity before considering a private writer or typed capability kernel.

## Verified Starting Point

| Area | Current evidence | Consequence for the imported plan |
| --- | --- | --- |
| Tests and catalog | 1,329 Python tests; 115 Native checks; 387 command prefixes / 41 categories. | The source's 658 tests / 343 commands / 39 categories are obsolete. |
| Native app | SwiftUI/AppKit v4.0f, Native 0.6.0, including the sidebar-height fix. [WorkspaceView](native/Sources/WorkspaceView.swift). | The shell is already usable, not a greenfield UI project. |
| Cognitive continuity | Russian/English intent rules, compact user-input memory, pure retrieval by default, grounding and deterministic continuity/verified-lesson benchmarks. [Observer](proto_mind/observer.py), [MemoryKeeper](proto_mind/memory_keeper.py), [write governance](proto_mind/memory_governance.py). | Do not repeat the old memory-correctness milestone. Add missing language/scope/evaluation cases instead. |
| Experience and skills | Typed provenance events, explicit in-memory capture, supervised lesson/skill promotion, durable provenance and narrow lifecycle/restore gates already exist. [Experience vocabulary](proto_mind/experience_ledger.py), [skill contract](proto_mind/experience_learning_skill_contract.py), [restore follow-up readiness](proto_mind/experience_learning_skill_restore_capture_readiness.py). | Extend these systems; do not introduce a competing learning ledger or silently enable capture. Procedure execution and general live Experience persistence are not implemented. |
| Provider integration | Official Codex app-server, separate profile, catalog-driven model/effort, Ollama/Mock alternatives, public progress and bounded receipts. [Codex adapter](proto_mind/native_codex.py), [public events](proto_mind/native_progress.py). | No need to replace terminal scraping: the native adapter does not use it. Persistent provider-thread resume is still missing. |
| Native execution | One active turn, ephemeral Full Mac grant, per-turn thread, 15-minute / 64-observed-item stop limits; receipts saved with completed/interrupted Native messages. [Agent adapter](proto_mind/native_agent.py), [bridge](proto_mind/native_bridge.py). | Completed UI history is not a crash-safe execution journal; a finished model turn is not verified task success. |
| Safety | Isolated Chat default; Full Mac explicitly permits broad user-level shell/file/network access. Core Registry/Policy and the fixed read-only runner do not sandbox that shell. | A universal Capability Broker is a future capability, not an existing guarantee. |
| Warnings/config | 12 accepted findings: dangling_ref=1, legacy=5, policy_drift=5, queue_hygiene=1; 0 unknown. Context Injection is disabled. | Accepted debt stays visible. Disabled injection is an intentional setting, not a defect to repair. |
| Source state | Reviewed working tree on `main`, HEAD `a323949`, with existing uncommitted native work. | This review is not a new release tag, clean-clone certificate, merge or publication. |

The 12 known findings are not evidence that all possible defects are known. Existing response-coupled legacy memories also remain subject to the separate preview-only migration path; prevention of new contamination is not historical cleanup.

## What To Reuse And What Is New

| Blueprint area | Reuse now | Valuable missing increment |
| --- | --- | --- |
| Workspace / Project / Thread / Run | Native conversation UUIDs, folder binding, core goals/tasks, `native_agent_run.v1`. | A provider-neutral durable Run linked to a conversation and actual project, with recovery and verification state. |
| App / daemon / RPC | Existing private stdio bridge and shared core handler. | Versioned shared contracts and capability negotiation first; a user daemon/socket only when background or multiple-client ownership is justified. |
| Provider abstraction | Existing Codex/Ollama/Mock adapters and public event projection. | Explicit capability matrix, supported resume/cancel semantics, provider-session mapping, usage/limit data only when actually supplied. |
| Native work UI | Sidebar, chat, inspector, command catalog, model/access controls, public work timeline. | Task/run view, plan/approval/verification/artifact cards, better keyboard navigation and a unified command palette. |
| Files and artifacts | Hash-checked UTF-8 previews, explicit attachments, observed diff/output previews. | Selected image/PDF/table inputs, drag-and-drop, side-by-side diff, provenance-linked outputs, original/derivative versions and manual restore review. |
| Context | Core retrieval, Context Pack/Preview, completed-turn evidence. | A pre-send "Why this context?" manifest: origins, sources, scope, selection reason, bounds and cloud destination. Bound-file scope and memory scope must be distinct. |
| Memory | Verified lesson recall, supersession/provenance, read-only Native library. | Explicit project/workspace memory policy, Ukrainian/mixed-language/negative-constraint evals, contradiction/expiry review and precise UI links to existing why/lifecycle gates. |
| Learning and skills | Evidence-linked candidates, exact manual approvals, non-executable procedural records. | Native candidate review and Skill Studio, later a reviewed `SKILL.md` import/draft/replay workflow. One successful run must not automatically publish a skill. |
| Permissions | Existing cloud opt-in, grant revocation and core safety metadata. | Additive project-scoped tool mode, exact action/resource grants, approval center, revocation and a local Pause/AI Off control. Keep Full Mac's actual broad authority explicit. |
| Tools / plugins / MCP | Four local typed capability contracts, existing registered commands. | A small local-first MCP client/tool host, schemas, per-tool scope, explicit install/enable/revoke, bounded subprocess isolation. The four contracts are not already an MCP client. |
| Computer Use | Nothing in Native currently grants Accessibility or screen control. | Selected-window capture and observe-only preview, then semantic app actions with fresh before/after evidence, user takeover and a visible stop control. |
| Images / Photo Lab | Text attachments and tool activity are not binary image input. | Local OCR, screenshot annotations/redaction preview, non-destructive crop/resize/metadata removal and before/after viewer. Preserve originals; advanced generative/photo search features remain optional. |
| Browser / research | Codex shell networking is not a native browser integration. | Selected-tab/text import, DOM/API-first navigation, citation artifacts, explicit external-submit boundaries; do not export cookies or read password fields. |
| Voice / Quick Capture | Ordinary text composer. | Push-to-talk into an editable draft, TTS, selected-window Appshot-like capture. Recording indicators and explicit local/cloud choice; no always-listening default. |
| Multi-agent / automation | One foreground turn and manual operator reports. | Bounded task graph, isolated worktrees, one writer per resource, verifier role, then explicit schedules/triggers/quiet hours/budgets and failure pause. |
| Reliability / privacy | Checksums, bounded output, known warning ledger, isolated fixtures. | Crash/disk-full/duplicate-event tests, restore drills, origin-aware event forwarding, redaction boundaries and local structured operational metrics. |
| Distribution / remote node | Personal ad-hoc-signed build and existing contest/source provenance. | Better local runtime discovery and private-state backup first. Notarization/updater, Pacta/mobile approvals and ecosystem features are conditional later work, not this project's immediate goal. |

## Proposed Work Packages

### EV-01: Reliable Work Sessions

Delivered first slice, 2026-08-31, Native 0.7.0: private atomic per-run evidence, cooperative single writer, dispatch/recovery states, journal cards and explicit new-turn continuation. Verification/acceptance remain explicitly unassessed/unrecorded; provider-thread resume is not implemented. See the Native Roadmap for bounds and failure evidence. EV-02's text-first follow-up is now delivered below.

User outcome: reopen Proto-Mind and see what a task actually did, what was verified, and what needs review, without guessing or replaying tool actions.

- Introduce a small versioned Native Run contract linked to existing conversation/project identity. Keep provider thread/turn IDs as adapter references, not primary domain IDs. Distinguish provider completion, verification result, interruption, unknown outcome and operator acceptance.
- Persist bounded public run intent/evidence in private Native state with an explicit single-writer strategy. Do not turn the opt-in cognitive Experience buffer into automatic execution logging or copy complete prompts/tool streams into it.
- Record the dispatch boundary before requesting a turn. A lost reply or interrupted tool observation means "outcome unknown; inspect", not "nothing ran". Deduplicate events and continuation requests; never automatically retry side effects.
- Add a task/run card and manual recovery action. Saved credentials or prior Full Mac access must not recreate a grant on restart. Revalidate workspace identity, mode, source state and provider capabilities before any new turn.
- First recover evidence and support an explicit new continuation turn. Evaluate real `thread/resume` separately against the installed runtime; reconstruction from bounded context must be labelled reconstruction, not provider-thread resume.
- Keep the private child bridge for this first delivery. No LaunchAgent, background work, parallel agents, global store migration, automatic memory promotion or new slash-command family is required.

Acceptance: synthetic interruption before/during/after dispatch, duplicate notifications, disk-full/corrupt-state handling and restart all preserve truthful evidence; pending/unknown work never becomes success or repeats automatically. The operator sees a useful recovery card in the actual app. Core stores, existing history fixtures, Chat isolation and consent gates retain regression coverage. New durable state requires its own versioning, backup and rollback test before use with personal history.

### EV-02: Context And Artifact Desk

Delivered text-first slice, 2026-08-31, Native 0.8.0: local pre-send source/history/destination desk, shared-memory scope disclosure, stale attachment warnings, and run-bound artifact/diff/current-file inspection. New normal runs save compact context manifests and bounded completion hash observations; views never mutate or call a model. Original hashes are linked only when a same-path input attachment exists; no old file copies or restore are invented.

Delivered follow-up, Native 0.9.0: optional operator criteria are visible before Send and frozen in the private run; a separate checklist/preview/confirmation records manual accepted/needs-work receipts in that run only. Previously captured files and source bytes are revalidated, earlier assessments are retained, and unknown outcomes cannot become successful. Automatic verification stays unassessed. No model-authored acceptance, tool permission or core memory promotion is added. See [criteria and manual-assessment contract](NATIVE_MACOS_ROADMAP.md#ev-02-criteria-and-manual-acceptance--native-090).

Delivered follow-up, Native 0.10.0: explicit PNG/JPEG selection, local ImageIO preview, thumbnail/metadata chips, Context manifest and hash-revalidated image transport through a catalog-confirmed Codex model. Cloud consent and tool modes are unchanged. History v4 and the private journal save metadata only; old pixels are never automatically reattached or replayed. A live 5.6 Sol synthetic-image probe passed without personal files or tool use. Ollama vision, PDF, OCR and screen capture are not implied by this delivery. See [selected-image boundaries](NATIVE_MACOS_ROADMAP.md#ev-02-selected-image-inputs--native-0100).

Delivered usability follow-up, Native 0.10.1: bounded saved-attachment layout, Finder/Node startup recovery and local drag/drop previews for existing PNG/JPEG and workspace-text inputs. Confirmation attaches metadata only; dropping never sends, changes workspace or grants tools. Existing failed runs and drafts are preserved, not repaired or retried. See [recovery and drop evidence](NATIVE_MACOS_ROADMAP.md#attachment-recovery-and-drop--native-0101).

Delivered usability follow-up, Native 0.10.2: explicitly hide/show a historical unfinished-run banner as a local display preference, with restart persistence and changed-evidence resurfacing. The journal keeps the original outcome; Acceptance explains unavailable states and keeps completed no-criteria reviews rework-only. This is not failure reconciliation, automatic retry or relaxed acceptance. See [notice and review evidence](NATIVE_MACOS_ROADMAP.md#run-notices-and-review-availability--native-0102).

Delivered follow-up, Native 0.11.0: a separate PDF drop/picker opens an explicit bounded page-text selector. Apple PDFKit extraction is local, in a timed network/file-write-denied worker; only selected text reaches Codex/Ollama on Send with source and text hash revalidation. Private history v5 and journal preserve metadata, not PDF copies or extracted text. No scans/OCR, layout/visual analysis, encrypted-document bypass, automatic old-page replay or new authority. See [PDF boundaries](NATIVE_MACOS_ROADMAP.md#ev-02-selected-pdf-page-text--native-0110).

Delivered Codex-parity follow-up, Native 0.12.0: one Native conversation now owns one durable Codex provider thread across chat, explicitly granted Full Mac turns and process restarts. Local history bootstraps only the first thread; resume is fail-closed on identity/workspace/policy drift, and Settings exposes status plus an explicit binding reset. Provider rollouts persist in the separate private Codex profile and can contain sensitive turn/tool content. This adds continuity, not background work, sticky permissions, automatic retry, transcript migration or a provider-history deletion UI. See [durable-session boundaries](NATIVE_MACOS_ROADMAP.md#durable-codex-sessions--native-0120).

Delivered Codex-parity follow-up, Native 0.13.0: the explicit Full Mac grant enables official live Web Search alongside terminal/network tools. Ordinary Chat remains offline/tool-free. The work timeline and durable journal save only bounded query/action/page metadata and discard opaque result payloads. Search content is untrusted and cannot grant authority. No interactive browser, cookie/session import, Accessibility, Screen Recording, Computer Use or background navigation is added. See [internet-search boundaries](NATIVE_MACOS_ROADMAP.md#full-mac-live-web-search--native-0130).

Remaining acceptance work: scanned/visual PDF and other-format inputs, local-provider vision, richer artifact/original/derivative actions and project-memory isolation. Current slices make shared scope visible; they do not claim isolation or automatic verification. The full package's acceptance below is not closed by text-fixture tests, a narrow visual probe or manual assessment alone. See [Native desk contract and verification](NATIVE_MACOS_ROADMAP.md#ev-02-context-and-artifact-desk--native-080).

User outcome: see the exact files/context used, inspect the result next to the conversation, and understand why the agent considers a task verified.

- Build on the current file reader and completed-turn inspector. Add explicit file/image/PDF selection and bounded previews, a source/origin/scope manifest, stale-source detection, and visible cloud disclosure before sending.
- Define project/workspace memory boundaries before selecting memories from multiple projects. A conversation's folder binding currently does not create a separate memory store. Existing Context Injection stays unchanged unless separately requested.
- Add an Artifact card with producing run, source reference/hash, media type, preview, verification and original/derivative links. Start with text/code/diff and selected images/PDFs; table/media/isolated HTML previews can follow.
- Separate declared success criteria, observed test/build/output evidence, model claims and manual acceptance. Copy/open/reveal/restore are distinct operator actions; preview must not execute HTML/scripts or overwrite originals.
- Quick Capture and drag-and-drop should make everyday use easier without silently importing clipboard, screenshots, whole folders or conversation transcripts.

Acceptance: one explicit task produces a readable diff/artifact and concrete verification evidence. Changed source files are visibly stale. No cross-project memory leakage, unchosen cloud attachment, preview-time write or inferred rollback success.

### EV-03: Scoped Tools And Approval Center

Delivered hardening slice, Native 0.15.0: every explicit Full Mac turn now freezes a deterministic authority/limit/stop contract before provider startup and validates the actual Computer Use inventory against it. The contract and hash are evidence only; no policy broker, project fence, automatic verification or new approval authority is claimed. Six dependency-free local evals exercise guardrail drift and known permission failure paths. The subscription Codex app-server remains in place; Agents SDK/API key/Platform integration is explicitly deferred.

User outcome: choose a project-limited working mode or explicitly broad Full Mac, see the real difference, and stop/revoke work locally.

- Reuse core risk vocabulary, but define enforcement at the actual tool boundary: exact subject/run, operation, resource, network scope, expiry, approval and verifier.
- Add a project-only mode with backend-supported restrictions and tested refusal of escapes. Preserve the operator's existing Full Mac option; do not silently narrow it or pretend it is confined to the bound folder.
- Introduce a provider capability/enforcement matrix. Codex-owned built-in shell cannot be claimed to pass through a Proto-Mind broker unless the adapter demonstrably mediates every relevant path. Unsupported enforcement is refused or displayed as unavailable, not simulated with prompt text.
- Add approval/revocation UI and a local Pause/AI Off path independent of an LLM. Stop new work, revoke temporary grants and request interruption; show partial effects and unresolved detached processes instead of promising rollback or instantaneous universal cancellation.
- Secrets should use supported provider credential storage or scoped Keychain handles when a new connector needs them. Do not migrate existing official Codex credentials, import Desktop tokens, or expose secret values to prompts/logs.

Acceptance: tests cover escaped paths, symlinks, expired/replayed grants, changed resources, denied external sends, duplicate dispatch and pause/failure handling. Every claimed restriction is backed by enforcement tests, not Registry metadata or a safety footer.

### EV-04: Native Memory And Skill Workshop

Delivered local-contract slice, Native 0.16.0: the existing Native Library is now exposed to its Swift renderer through two exact private-stdio capabilities, `search` and `fetch`, with narrow input schemas, safe read-only annotations, structured result envelopes and strict local/no-network/no-model/no-write metadata. This is an internal interface discipline, not public MCP/plugin activation or a model tool. Legacy direct-read RPCs remain only for rolling local app/bridge compatibility.

Delivered first cognitive loop slice, Native 0.20.0: memory detail now reuses the durable lesson-provenance verifier and exposes verified, unavailable-legacy or invalid/tampered evidence without retrieval or mutation. The response inspector can navigate from a selected memory ID to its exact record. A separate Memory Workshop projects only an already-running, explicitly consented process-memory Experience pilot, displays existing correction/reflection/grounding candidates and prepares current review commands without executing them. It neither starts capture nor changes consent, decisions, proposals, memory or skills. Selected workspace identity is shown, while the global legacy store scope and absent project isolation remain explicit blockers rather than inferred guarantees. Russian negative-constraint/current-decision coverage joins the deterministic benchmark.

User outcome: inspect why Proto-Mind knows something, review a proposed lesson, and maintain a personal skill without memorizing CLI sequences.

Delivered supervised lesson slice, Native 0.21.0: a candidate opens a three-stage Native review screen over the existing core decision/proposal/apply sessions. Read-only evidence and reference selection precede separate exact confirmations; only the final explicitly acknowledged shared-memory apply appends one verified lesson. Private bridge RPCs are not commands or model tools. The Native process-wide one-apply guard, 15-minute proposal window, current-source hashes, duplicate checks, byte-preserving legacy append and conditional exact-byte failure restoration remain explicit. Accepted candidates and detailed receipts are not made durable; applied provenance is. No skill lifecycle writer or new capture consent is added.

Delivered supervised skill slice, Native 0.22.0: an active durable verified lesson opens a bounded operator-authored form without a live Experience pilot. Separate exact authoring and apply confirmations reuse the existing procedural skill contracts; only final acknowledged apply writes one non-executable record to the shared Skill Library. Source/form/store/workspace drift and process-wide replay fail closed. Saved skill provenance and its source link remain independently inspectable after restart; transient drafts/receipts do not. No procedure execution, automatic authoring, permission grant, model call or new persistent schema is introduced.

Delivered skill-inspection slice, Native 0.23.0: the selected skill opens a read-only result/lifecycle sheet. Existing core validators distinguish verified apply/archive/restore facts from missing legacy history and current-conversation manual-use outcomes. Restore evidence survives restart without inventing an original process receipt; pre-restore and unbound later results cannot become fresh success. The source lesson is directly reachable. This UI does not enable capture, make decisions, archive/restore, execute a procedure or modify any store.

Delivered manual-outcome slice, Native 0.24.0: the operator can report an already-performed manual success or failure/correction for an eligible skill. Existing separate Experience consent, a current exact blueprint token and explicit operator-reported acknowledgement precede one four-event process-memory capture and receipt. The form does not run the skill or persist its report; source/form/consent/scope drift and exact replay fail closed. Receipts link to the existing inspector, where contradictory evidence stays mixed. Archived/restored/unprovenanced skills remain refused; the post-restore capture writer is not enabled.

Delivered outcome-decision slice, Native 0.25.0: the evidence inspector opens the existing keep/revise/archive decision contract. The operator chooses from current permitted options, reviews exact evidence and confirms a separate token/decision-only acknowledgement. One process-memory receipt is recorded without new events or file changes. No automatic selection, application, archive, revision, execution or capture activation occurs. Later evidence marks the immutable receipt historical; replay/replacement, stale previews and unavailable/restored evidence are refused. Durable lifecycle application remains a separate step.

Delivered lifecycle-application slice, Native 0.26.0: a recorded decision opens a separate exact apply review. A new current token and shared-library acknowledgement permit keep as a no-op receipt or one durable archive through the existing core writer. Only `lifecycle/status/updated_at` change; source dependencies and final disk bytes are rechecked, neighboring bytes preserved, and failed verification rolls back only over unchanged self-written bytes. One Native attempt, no auto-retry, no revision/restore/execution or new capture/permission. The detailed receipt is process-only, while archive cause remains independently inspectable after restart. [Contract and evidence](NATIVE_MACOS_ROADMAP.md#ev-04-skill-lifecycle-apply--native-0260).

Delivered restoration slice, Native 0.27.0: the archived-skill inspector exposes the existing separately confirmed durable restore gate. A fresh exact token and shared-library acknowledgement restore availability only; old archive evidence/provenance survive, no procedure or fresh outcome is fabricated. One Native attempt, bounded no-initialization reads, conditional own-byte rollback and independently verified receipts. The next approved slices are explicitly saved historical learning evidence, project-scoped memory and controlled operator task use. [Contract and evidence](NATIVE_MACOS_ROADMAP.md#ev-04-skill-restore--native-0270).

Delivered saved-history slice, Native 0.28.0: explicit immutable private snapshots preserve selected-skill manual outcomes, decisions and detailed lifecycle/restore receipts with exact events and verifiable hashes. Viewing/restart never load archived authority into the pilot, and old missing receipts are not reconstructed. Core/exports remain unchanged; no auto-save, full conversation archive, import or automatic learning. Project memory and controlled operator task use remain next. [Contract and evidence](NATIVE_MACOS_ROADMAP.md#ev-04-saved-learning-history--native-0280).

Delivered explicit project-memory slice, Native 0.29.0: operator-authored, source-labeled notes have exact folder identity, immutable replacements and local deterministic recall. Saving, attaching and sending are distinct; current notes are checked again before the existing provider call. The private run manifest preserves selected-note provenance; legacy shared stores remain untouched and do not acquire guessed project scope. This is not autonomous learning or global memory isolation. Controlled operator task use of verified procedures remains next. [Contract and limits](NATIVE_MACOS_ROADMAP.md#ev-04-explicit-project-memory--native-0290).

Delivered operator-guided task slice, Native 0.30.0: a selected current verified skill opens a goal/criteria/procedure review. Explicit preparation creates an unsent draft with an ephemeral source-bound selection; manual Send rechecks it and uses the existing provider/permission path once. The exact procedure is quoted guidance, not a skill interpreter or grant. The work journal preserves content-free source/version/task provenance and existing observed results; per-criterion manual acceptance remains separate, with automatic verification unassessed. No implicit selection, usage update, learning event, promotion or post-restore capture is added. This closes the approved four-part restore/history/project-memory/guided-task batch, not the entire cognitive roadmap. [Contract and limits](NATIVE_MACOS_ROADMAP.md#ev-04-operator-guided-skill-tasks--native-0300).

Delivered automatic-use slice, Native 0.31.0: the ordinary Codex composer defaults to model-selected guidance from existing active/current-provenance verified skills, with a per-chat off switch and manual override. One bounded tool-free ephemeral selection precedes the unchanged main turn; existing durable conversations are not replaced. No preparation form is needed and no procedure is forced onto a no-match request. The six-case live Sol evaluation covers Russian/English selection, non-matches and one independently checked synthetic CSV task. This automates selection and use-as-guidance, not source verification quality, permission grants, success acceptance, new skill synthesis or memory promotion. At that milestone the personal catalog had no eligible skills; legacy records were not converted to fill the gap.

Delivered starter-set slice, Native 0.32.0: four code-owned, versioned procedures make Auto useful without seeded personal lessons: project orientation, verified change, failure diagnosis and work handoff. A read-only inspector and origin-specific private metadata distinguish bundled guidance from learned experience. Eleven opt-in real Codex fixture cases pass, including a separately verified code change; neither these tests nor a selected template establish general effectiveness or acceptance. No personal skill/memory migration, learning or new execution permission is added.

Delivered automatic project-recall slice, Native 0.33.0: current explicitly saved notes in the exact selected project can enter ordinary Codex turns without manual attachment, bounded to three whole notes / 6000 characters by deterministic informative content-word matching. Per-chat opt-out, manual priority, exact pre-send source display and content-free chat/run provenance remain available. No extra model request, note creation, counter write, legacy migration or tool grant. Changed reviewed sources refuse rather than silently replace; eight live synthetic cases cover RU/EN matches, supersession, scope, unknowns and same-thread updates/opt-out. Shared core memory and provider history remain distinct limitations. Next proposed slice: source-grounded learning suggestions, not automatic promotion. Preserve visible sources and meaningful user override rather than mandatory review forms for every task.

Delivered first source-grounded suggestion slice, Native 0.34.0: explicit operator preferences, decisions, constraints, project facts and lessons can produce up to two local exact-quote cards after a completed Codex turn. A prefilled review, visible source hash and separate acknowledged Save reuse private project memory; no extra model request, automatic note promotion, token copying, supersession or new command family. Source and note state are revalidated, current duplicates excluded, and a per-chat off switch is available. This only covers anchored RU/EN operator assertions; learning from task/tool outcomes, semantic conflict handling and verified automatic consolidation remain separate future work. [Contract and limits](NATIVE_MACOS_ROADMAP.md#ev-04-source-grounded-memory-suggestions--native-0340).

- Surface existing candidate, provenance, apply/readiness, lifecycle and restore contracts as Native cards and exact confirmation flows, not an alternate writer.
- Add Ukrainian and mixed-language benchmarks, project-scoped recall and temporal/negative-constraint cases. Keep lexical/deterministic baselines before evaluating local embeddings; an index must remain disposable and distinct from canonical memory.
- Show explicit evidence limits: retrieved is not necessarily used; operator-reported is not tool-verified; a stored source/hash is not proof of truth. Review contradictions, scope, expiry and supersession without silent cleanup.
- Distinguish the existing non-executable procedural record from a future runnable skill package. `SKILL.md` imports and generalized drafts require provenance, declared inputs/permissions, review and isolated replay tests. Explicit invocation comes before implicit activation.
- Preserve the pending v3.5w/post-restore follow-up boundary. Native UX does not authorize that writer or turn one episode into an automatically accepted procedure.

Acceptance: Native covers provenance/outcome/lifecycle inspection, separately confirmed candidate-to-lesson and durable-lesson-to-skill paths, exact manual outcome capture, process-only decisions, separately confirmed archive/restore, explicitly saved historical snapshots, scoped operator notes with bounded automatic recall and manual/automatic procedure guidance. Built-ins remain separate from learned experience. Automatic lesson promotion, skill revision, pending post-restore outcome capture and executable skill packages remain undelivered. Rejected/stale/token-mismatch paths still refuse; simply viewing the library, context desk, evidence/review sheets, Workshop or starter set remains read-only.

### EV-05: Small Local Tool / MCP Extension Surface

User outcome: add one useful local capability, understand its permissions, and disable it cleanly.

- Keep Tool (typed operation), Connector (external authorization), Skill (procedure), Plugin (package) and Automation (triggered workflow) separate.
- Start with explicitly enabled bundled/local STDIO tools and one useful workflow, not a marketplace. Use bounded schema validation, subprocess isolation, resource limits, per-server health/revoke and broker checks from EV-03.
- Treat manifests, server instructions, skills and hook output as untrusted input. A declared risk/signature does not grant authority or prove safety. Hooks require explicit lifecycle scope and a restricted environment.
- Delay remote HTTP/OAuth servers, third-party UI extensions, signing/update infrastructure and automatic discovery/activation until local isolation is demonstrated. Do not import Codex Desktop MCP/hooks/config automatically.

Acceptance: one local tool installs/enables only through an explicit action, cannot exceed its scope, leaves no credentials in output, and stops after revoke. A crashed plugin cannot corrupt or terminate the core.

### EV-06: See And Operate The Mac

Delivered permission-onboarding slice, Native 0.15.0: exact Computer Use `-1743` failures are classified as macOS Automation denial without retaining raw MCP output. The app declares its Apple Events purpose, displays manual recovery, and can open the Automation settings page. macOS still owns the decision; Proto-Mind cannot toggle it, retry automatically or treat settings navigation as permission. Live post-grant acceptance is required before this path is considered working for the personal app.

User outcome: attach the relevant window, ask about it, then visibly perform a small supported app workflow.

- Start with selected-window/region screenshots and local OCR. Show exactly what is captured and what would leave the Mac; detect sensitive regions as an advisory aid, not guaranteed redaction.
- Add observe-only inspection before actions. Prefer purpose-built APIs/CLI/App Intents/DOM or stable Accessibility selectors; use coordinates only with fresh evidence and verification.
- Add lazy macOS permission onboarding, app/window allowlists, foreground indicators, immediate user takeover and a local stop hotkey. Do not request every TCC permission at startup or bypass platform protections.
- Pilot one mock app and one simple real app workflow before expanding to Finder/Preview/Notes/Xcode. Re-observe after each action; secure/password/financial apps and lock-screen operation are not default targets.
- Add browser selected-tab and citation support through a separately reviewed bridge. Browser auth remains in the browser; external submission/publication is not authorized by web-page instructions.
- Record & Replay is later: store consented semantic actions, parameterize inputs, review a draft, then replay in fixtures before publishing a skill. Never silently record continuous screen history.

Acceptance: deterministic mock-app fixtures cover stale windows, denied permission, changed focus, interruption, no sensitive-field reads and before/after evidence. A real pilot is visible and bounded; successful clicking alone is not task completion.

### EV-07: Voice And Visual Utilities

User outcome: dictate a draft, hear an answer, or make a safe derivative of a selected image without leaving the conversation.

- Push-to-talk, editable transcription and explicit send first; TTS and voice pause can follow. Microphone/session indicators and provider disclosures are mandatory. No always-on listener or background meeting capture.
- Selected-image OCR, annotations, crop/resize/conversion, metadata preview and redaction/export should preserve the original hash and record a non-destructive recipe/derivative.
- A true privacy redaction workflow must irreversibly remove masked pixels and unwanted metadata from the exported derivative; reversible overlays or blur alone must not be advertised as secure removal.
- Photo-library integration, semantic photo search, local opt-in face clustering, generative editing, meeting transcription and camera input are optional later modules. Cloud image processing must identify the exact selected images; writing back to Photos is a separate action.

These conveniences need not wait for multi-agent scheduling. Ship a small version after input/privacy/stop boundaries exist, rather than making a full photo editor part of the first beta.

### EV-08: Bounded Parallel And Background Work (Later)

User outcome: let a narrowly defined task run reliably when appropriate, with honest state, budgets and an off switch.

- Only after EV-01/03: stable Run ownership, crash recovery, resource locks and actual enforcement. Existing JSON stores have no cross-process transaction manager; do not simply enable parallel writers.
- Coordinator/Builder/Researcher/Verifier are roles, not necessarily separate models. Child work gets a scoped context, one resource owner, budget, verification and no uncontrolled child spawning. Isolated worktrees require explicit base state and merge/review policy.
- A user LaunchAgent/private authenticated socket becomes justified by an actual background/multi-client requirement, not by diagram aesthetics. Keep root helpers out; require version negotiation, local peer authentication, bounded queues and reconnect tests before exposing a listener.
- Explicit schedules/triggers need quiet hours, opt-in notification policy, max runs/duration/cost where measurable, idempotency, startup catch-up rules, repeated-failure pause and a visible disable path. Unknown external outcomes require reconciliation, never blind retries or an unsupported exactly-once promise.
- Native state backup/restore, runtime discovery and compatibility diagnostics precede broad distribution. Developer ID/notarization, updater channels, marketplace and remote-node infrastructure are not prerequisites for this personal Mac.
- Pacta/PactaOS integration remains an optional independent proposal: separate identity, room-scoped disclosure, revocable remote approvals and transport-only exchange. This review neither inspects those projects nor authorizes access to their stores, credentials or production systems.

## Delivery Order And Explicit Deferrals

Recommended sequence: EV-01 -> EV-02; EV-03 before new executable integrations; reuse existing learning for EV-04; then one local extension or Computer Use pilot. Voice/selected-image utilities can be small independent increments after the relevant permission boundaries. EV-08 comes last.

Do not copy the source's entire PM-M0..PM-M15 schedule into active tasks. In particular:

- No new baseline freeze/tag or giant architecture rewrite: the Ledger, maps, checks and backups already exist. Record current evidence, not obsolete test counts.
- No mandatory database switch, repo-wide move or Swift core rewrite. New storage choices need a concrete durability/concurrency requirement and a separately tested migration; SQLite is not an assumed current store.
- No replacement of the working official Codex bridge just to satisfy a generic "App Server adapter" milestone. Catalog parity with Desktop is a separate compatibility task, not permission to fabricate models or reuse credentials.
- No global broker/sandbox claim while Full Mac built-in tools remain unrestricted. A hash chain is not a cryptographic signature or tamper-proof audit.
- No automatic Context Injection enablement, legacy cleanup, warning suppression, memory promotion or skill execution.
- No import of raw/private reasoning into event cards, notifications or handoffs. Public progress and observed action evidence are sufficient; notification routing must exclude internal/foreign workers and authentication payloads.
- No public/commercial beta requirements, mobile client, unrestricted remote control, root helper, automatic plugin installation or full Photo Lab as blockers to everyday usefulness.
- Keep the familiar native appearance. The blueprint's aesthetic preferences do not override the operator's explicit request for a Codex-like interface.

Core maintenance remains worthwhile but should be incremental and separately verified: `test_flow.py` currently has 29,044 lines; command dispatch is still a linear formatter chain. Split by real domain boundaries and migrate command families one at a time, preserving output, consent, persistence and narrow runner semantics. Do not make this refactor a prerequisite for the first useful Native Run card.

## First Practical Acceptance Story

1. Open an existing project/thread and ask for one scoped task with visible success criteria.
2. Inspect the source/context and actual tool mode; no implicit new permission is granted.
3. Observe public progress, tool outcomes and a producing Run ID.
4. Interrupt/reopen the app and inspect durable evidence, including unknown or partial effects.
5. Explicitly choose whether to continue after fresh scope/permission checks; nothing is replayed automatically.
6. Review the resulting diff/artifact and concrete verification, with model completion separate from task success.
7. Optionally review a source-linked lesson through the existing learning gates. No automatic learning is required to complete the workflow.

This story builds on the current app and core. Computer Use, plugins, a daemon and multi-agent scheduling are not required to prove the first useful increment.

## Review Verification And Limits

- Rule 0 checkpoint: `backups/proto_mind_backup_2026-08-31_11-57-38.tar.gz`.
- Read current source, native architecture/history contracts and the entire external blueprint. No task prompt from the file was executed.
- `scripts/which_python.sh`: Python 3.11.15; Proto-Mind and PySide6 imports OK.
- `scripts/run_tests.sh`: 1,329 tests OK; compileall OK; optional pytest unavailable and explicitly skipped.
- `scripts/test_native.sh`: 115 checks OK, including a real bridge on code-only temporary fixtures. No live model/API request, UI redesign or release rebuild is part of this docs-only review.
- CLI read-only inspection confirms 387 commands / 41 categories, 12 accepted warnings / 0 unknown, and disabled Context Injection.
- Registry, Policy, Natural, Warning and Daily doctors remain OK; Milestone Doctor retains the known system-health WARN. All 28 local Markdown links/anchors validate. SHA-256 is unchanged for all 48 core/export files, Native conversation/preferences files and the original external download.
- No implementation, dependency, settings, core schema, grant, background task or runtime store change. Existing native/core behavior and historical evidence ceilings remain as documented in the linked current-state files.

The proposed capabilities have not been implemented or security-certified by writing this roadmap. Third-party/runtime APIs, platform permissions, model availability and distribution requirements must be checked at the point of the relevant implementation, not assumed from this external blueprint.
