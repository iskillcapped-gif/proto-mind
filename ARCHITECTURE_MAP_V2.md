# Proto-Mind Architecture Map v2

Proto-Mind is a local-first cognitive architecture prototype for memory-aware reasoning. It is not a model training project, not a consciousness simulation, and not a polished chatbot product. The current system explores how an LLM-facing runtime can organize observation, memory, retrieval, reasoning, hygiene, and self-reflection around each turn.

The core distinction from a simple RAG wrapper is that memory is treated as part of the turn pipeline: incoming input is classified, memory need is estimated, memories are selected and scored, the reasoner receives structured memory context, memory updates are evaluated after the response, and a self-reflection layer inspects whether the response stayed faithful to active memory.

For short future Codex handoffs, use `PROTO_MIND_ARCHITECT_LEDGER.md` as the compact project brief.

Future capabilities are tracked separately in [Personal Agent Evolution](PROTO_MIND_EVOLUTION_ROADMAP.md). EV-01's bounded work sessions, EV-02's context/artifact desk, explicit manual assessment, selected PNG/JPEG/PDF inputs, durable Codex continuity, Full Mac live Web Search and signed OpenAI Computer Use are delivered. Remaining rich-document/project-scope work and later broker, arbitrary-plugin and daemon work remain proposals. The module map below describes implemented behavior, not those proposed capabilities.

## Current Module Map

`proto_mind/session_spine.py` + `proto_mind/native_session_spine.py` + `proto_mind/session_spine_store.py` + `proto_mind/session_spine_transfer.py` + `proto_mind/session_spine_composition.py` + `proto_mind/session_spine_composition_transfer.py` + `proto_mind/session_spine_archive_copy.py` + `proto_mind/session_spine_private_backup.py` + `proto_mind/session_spine_forward.py` + `proto_mind/session_spine_handshake.py` (DeepSeek Harness extraction / Session Spine v0.1, Native projection P1, private store P2a, fixture transfer P2b, ordered composition P2c, private composition evidence P2d, archive-copy compatibility P2e, explicit private-backup acceptance P2f, isolated forward writer/read P2g, detached commit/recovery handshake P2h)

- Independent pure event/surface contract reviewed against official DeepSeek Harness commit `76fda729799fe9b3848dbe2c211d4b231032b81e`. Canonical bounded event data/provenance, contiguous sequence replay, append/replace surface operations, complete shadow provenance, unknown-required-event refusal and a schema-separated deterministic log fingerprint.
- The P1 adapter projects one explicitly paired synthetic Native user/assistant/work-session turn. Hash-verified chunks preserve exact input and separate displayed/raw answers; existing public tool sanitizers produce evidence-only, non-replayable results; stable unknown/not-started states never invent an assistant success; memory suggestions retain exact message/run/quote lineage.
- P2a adds an explicit-path-only private store contract with canonical prepare/commit pairs, two fsync boundaries, commit hash chaining, private bounded files, catalog/session locks, exact readback and stale-fingerprint fencing. Readers replay only committed pairs and report torn/uncommitted/open-turn state as unknown without mutation; committed corruption fails closed. A pure retention preview cannot compact or delete.
- P2b accepts one explicit canonical Native fixture, revalidates P1, builds the candidate with the shared P2a byte contract and proves exact replay parity. It can create only a new private export bundle containing exact source/candidate bytes, optional exact rollback preimage and a hashed manifest written last. Migration and rollback remain read-only previews; conflicts block rather than overwrite.
- P2c accepts two to 64 immutable canonical fixtures plus the caller's exact ordered SHA-256 tuple and expected conversation ID. It refuses mixed conversations, duplicate source identities and overlapping/reversed times instead of sorting. Only event sequences, source references and replacement boundaries are offset; canonical event payloads and source IDs remain exact. Full replay, per-turn visible-surface parity, metadata-only lineage and the shared P2a candidate bytes are proven in memory.
- P2d accepts only a validated P2c preview and an explicit absolute private export root. It independently rederives the preview before creating a run-once bundle, writes ordered exact fixtures, exact candidate bytes and a content-free parity dossier, then writes the self-hashed manifest as the completion marker. Verification reads without mutation, enforces private regular files and a closed file set, and repeats P1 -> P2c -> P2a from exported bytes. Tamper, order, permission, symlink, partial-write and metadata drift fail closed. The bundle is private and not publication-safe; its unkeyed self-hash is not an authenticity signature.
- P2e accepts one whole caller-supplied Native history copy and the exact sorted filename/SHA-256 manifest for zero to 500 copied work-session records. It validates only immutable bounded bytes, uses exact immediate `turnReference` identities, current durable receipt validation and P1 projection, then reports compatible turns plus visible legacy, missing, invalid, duplicate and orphaned evidence without retaining source text. It never opens a filesystem path, searches personal state, falls back to a nearby/latest run, writes/export/migrates data or authorizes a writer. Exact manifest parity cannot prove that an unseen source directory was copied completely.
- P2f reads one operator-supplied absolute gzip-tar copy through no-follow file access, requires its exact SHA-256, rejects duplicate/traversal/link/special/unknown members and sends only the exact allowed history/run bytes to P2e without disk extraction. It does not discover backups or open live Native state. The authorized acceptance copy reports 30 legacy unlinked assistant turns, 26 completed legacy runs and one incomplete run, with zero invalid/incompatible/orphan findings. This evidence rules out inferred backfill and favors a future forward-only writer. The outer private archive's `0644` mode remains a visible warning, not an automatic chmod.
- P2g adds a forward-only owner-bound pilot over newly exact-linked turns. Preview independently verifies the work-session fingerprint, immediate message pair and Turn Lineage receipt, then binds a complete rebased P1 turn to an opaque explicit-store scope, exact preimage SHA-256 and candidate SHA-256. Apply uses the existing no-follow locked store rather than shell/filesystem shortcuts, commits one turn batch, checks exact replay and supports lost-response idempotency. Ordinary in-process partial writes are truncated and fsynced back to the exact preimage; a crash/power loss is not claimed atomic and remains visible as `UNKNOWN`. Dual-read evidence compares exact conversation/run/message identities while preserving legacy rows separately and treating source-copy incompleteness as WARN, not invented corruption.
- P2h adds an installation-stable, non-authorizing Native owner identity and a content-free handshake over exact saved-history readback, canonical Work Session bytes, stable Turn Lineage and one P2g CAS plan. Recovery is a closed state machine: missing assistant history never reconstructs full text from a bounded run preview; source/preimage drift blocks stale apply; torn tails require a separate manual task; exact completed turns replay without writing. Post-commit operator review may change the whole-run fingerprint while the immutable turn receipt continues to prove lineage. Before commit, the same drift requires a newly prepared handshake.
- `proto_mind/tests/test_session_spine.py`, `proto_mind/tests/test_native_session_spine.py`, `proto_mind/tests/test_session_spine_store.py`, `proto_mind/tests/test_session_spine_transfer.py`, `proto_mind/tests/test_session_spine_composition.py`, `proto_mind/tests/test_session_spine_composition_transfer.py`, `proto_mind/tests/test_session_spine_archive_copy.py`, `proto_mind/tests/test_session_spine_private_backup.py`, `proto_mind/tests/test_session_spine_forward.py` and `proto_mind/tests/test_session_spine_handshake.py` prove the detached contracts. Writes use only disposable explicit test directories. There is no default location, inferred pairing/backfill, production bridge/UI/command caller, durable handshake journal, personal-history migration, automatic repair, delete/compaction, provider/model call or permission integration. The spine is not an authoritative history source. See `DEEPSEEK_HARNESS_ADOPTION_REVIEW.md` for the comparison, license boundary, priorities and explicit non-adoptions.

`proto_mind/native_memory_suggestions.py` + `native/Sources/MemorySuggestion*.swift` (EV-04 Source-grounded Memory Suggestions / Native 0.34.0)

- After a completed ordinary Codex turn, deterministic anchored RU/EN rules examine only the original operator text. Up to two whole quotes, 600 characters each, from inputs up to 12,000 characters; no assistant/tool/attachment/history fact extraction, extra LLM, automatic promotion, background job or source-store initialization. Exact current scoped duplicates are omitted. Conservative quoted/hypothetical/obvious-secret filters are heuristics, not semantic understanding or comprehensive redaction.
- Optional private chat metadata keeps run ID/fingerprint, folder identity, input/quote SHA-256, Unicode offsets and kind, not duplicate quote bodies. Independent Native validation binds it to the original user message and completed run; metadata is not model replay. The existing work journal is a source, not a new suggestion queue or write target. Opt-out is per conversation and defaults on for the local suggestion layer only.
- Two fixed private RPCs review and explicitly save one source-bound suggestion. They recheck the completed source, exact workspace, disabled Context, duplicates and existing note snapshot; the existing `NativeProjectMemory.save` remains the only writer. An acknowledgement plus explicit Save sends the exact preview token, with no free-form body or replacement ID accepted by these RPCs. Only `project_memory/` gains one immutable note/lock; no core, export, journal, permission or command-registry mutation. Assertions are operator-reviewed, not independently verified; source hashes are integrity checks, not signatures or a cross-store transaction.

`proto_mind/native_project_recall.py` + `native_knowledge.py` + `native/Sources/ProjectRecall.swift` (EV-04 Automatic Project Recall / Native 0.33.0)

- Normal Codex Send and local `context_preview` reuse the fixed private project-note reader, exact launch-root/workspace path/device/inode scope and immutable supersession rules. Informative Unicode content-token overlap ranks current notes deterministically; basis text is not a relevance signal. Up to three whole notes / 6000 content-plus-basis characters, no LLM selector, embedding, file crawler, new RPC or command prefix.
- Per-chat default-on recall is independent of skills and permissions; explicit notes override it. Operator routes, local providers and opt-out bypass it. Missing notes do not initialize storage; unreadable/unsafe initial sources/config are visibly unavailable and add no notes. The source snapshot is revalidated before main dispatch and provider invocation; an already reviewed snapshot is bound at Send. Drift refuses without reselection/retry. Current notes are quoted untrusted assertions, never system authority or verified truth.
- `native_knowledge_context.v2` adds closed content-free `project_recall` provenance; old v1 remains readable without rewrite. Swift verifies source text hashes, counts, IDs, task/scope/mode, and journal linkage; the context desk, chat and journal show the result. The private namespace is bounded at 200 records and scanned across scopes before filtering, not physically isolated per-folder storage. Snapshot hashes identify canonical records, not formatting or a filesystem lock. Legacy core recall remains shared. No note/usage/learning write, new consent, Context Injection change, background job or additional provider generation.

`proto_mind/native_starter_skills.py` + `starter_skills.json` + `native/Sources/StarterSkillsView.swift` (EV-04 Built-in Starter Skills / Native 0.32.0)

- Four fixed, versioned application-authored contracts supply project orientation, verified change, failure diagnosis and handoff guidance. Bounded no-follow reads, closed schema and canonical hashes protect the catalog boundary. A fixed parameter-free `starter_skills` RPC only inspects the pack; it is not a model tool or command dispatcher.
- Auto reserves four of its 32 catalog slots for built-ins and offers the first 28 eligible learned records in stable ID order. Both origins are visible. Core records cannot impersonate `builtin.*` IDs. Existing source/config gates, selected-contract guidance, tool-free selector, main-turn permissions and source revalidation remain in place; pack bytes are rechecked too.
- Optional v2 `auto_skills` metadata identifies bundled pack/version/contract hashes separately from learned lesson/provenance/lifecycle references. v1 history stays readable without rewriting. No fabricated learned experience, core/exports write, automatic promotion, skill interpreter, new slash command or Context Injection change. Eleven opt-in live synthetic cases test selection and four bounded tasks; they do not prove general skill quality.

`proto_mind/native_auto_skills.py` + `native_codex.py` + `native/Sources/AutoSkills.swift` (EV-04 Automatic Skill Guidance / Native 0.31.0)

- Normal Codex Send optionally reads a bounded shared-skill catalog, reusing exactly the manual-task source/lifecycle/contract eligibility boundary. One isolated ephemeral structured-output selector chooses zero to two IDs; no tools, thread-binding changes, credentials copying or Platform API are involved. Manual selection wins; operator routes and local providers bypass it.
- Only current selected contracts become quoted guidance for the existing main turn. Cloud/Full Mac grants, requested main effort, actual tool observations and durable chat continuity are unchanged. Catalog hashes/source bytes are rechecked before selection, after selection, before dispatch and before the provider call. Malformed output, unknown IDs, Stop and drift stop the task without automatic retry.
- Per-chat Auto preference and optional closed `auto_skills` message/run metadata use existing private Native storage. The context desk previews availability without a model call. Selection reasons/checks are public model suggestions, not private reasoning, operator criteria or acceptance. No skill-use counters, lifecycle writes, learning events, core-store migration, embeddings or new slash commands. See the roadmap for the 32-entry catalog cap and independent six-case live fixture evaluation.

`proto_mind/native_skill_tasks.py` + `native_knowledge.py` + `native/Sources/SkillTask*.swift` (EV-04 Operator-Guided Skill Tasks / Native 0.30.0)

- One fixed read-only `skill_task_preview` RPC checks the current active authored procedure and its source lesson, including verified restored skills. The exact task goal, declared criteria, conversation/folder identity, provider/access mode and source hashes bind a non-authorizing preview. Unknown, historical, archived, executable or drifted records cannot prepare a task.
- Explicit draft preparation is ephemeral selection plus the existing private goal/criteria draft, never Send. The ordinary process path revalidates before dispatch and immediately before the existing Codex/Ollama call. Only selected procedure text is quoted as untrusted user guidance; no script interpreter, model-to-slash dispatch, new tool, automatic retry or permission is added.
- Optional content-free `knowledge_context.skill_task` provenance in the existing private run manifest binds the original task/criteria/workspace to its source/version. Existing observations, artifacts and separately confirmed per-criterion operator review stay distinct from automatic verification (`not_assessed`). No automatic skill outcome capture, uses update, memory promotion, lifecycle mutation or post-restore writer is installed. Full Mac remains broad existing authority, not a new project sandbox.

`proto_mind/native_project_memory.py` + `native_knowledge.py` + `native/Sources/ProjectMemory*.swift` (EV-04 Explicit Project Memory / Native 0.29.0)

- Fixed private list/recall/inspect/preview/save RPCs bind operator-authored notes to the selected folder's path/device/inode and launch project. Save appends to private `project_memory/`; explicit supersession does not rewrite older bytes. Read-only pagination and deterministic lexical recall never initialize stores or call a model.
- Explicit attachment is ephemeral and separate from saving. Send revalidates scope/hash/current state; only selected notes enter the existing user-context path, clearly quoted as untrusted operator assertions. The existing Codex/Ollama call, permissions and shared-core recall remain unchanged. Content-free provenance extends private run manifests; slash commands bypass it.
- The original 0.29.0 slice adds no inferred project ownership, legacy migration, global-memory rewrite, embeddings, automatic capture/recall/injection, new command prefix, model call, permission or Context Injection change. Native 0.33.0 adds the separate read-only automatic selection above. Provider-side history may retain context sent in earlier turns.

`proto_mind/native_learning_history.py` + `native_private_records.py` + `native/Sources/SkillHistory*.swift` (EV-04 Saved Learning History / Native 0.28.0)

- Fixed list/preview/save/inspect RPCs archive only an exact selected skill/conversation/workspace snapshot, original manual-outcome/decision/lifecycle/restore receipts and their linked manual events. An explicit fresh hash-bound Save creates immutable private evidence, not a new live pilot or token.
- Closed archive/receipt contracts, SHA-256 and reference checks are repeated on reads. Canonical hash material lets Swift verify original Python event numbers without reserializing them. Integrity/current-state/quality are separate; no old missing receipt or success is invented.
- Fixed-namespace bounded private storage creates nothing on read and never overwrites a prior snapshot. Cooperative lock, exclusive temporary bytes, atomic no-overwrite publication and readback fail closed on corruption/collision/limits. Only explicit Save writes `learning_history/`; no core/export changes, repair, rehydration, capture, model/tool invocation or new permission.

`proto_mind/native_skill_restore.py` + `native/Sources/SkillRestoreModels.swift` + `SkillRestoreModel.swift` + `SkillRestoreView.swift` (EV-04 Skill Restore / Native 0.27.0)

- Three fixed private RPCs reuse the existing process-wide durable restore session. Strict detached source/config/workspace checks and Swift's independently recomputed token bind one archived skill and its prior evidence. No coordinator, consent, outcome capture, command dispatch or model call is created by the screen.
- Explicit confirmation changes only `lifecycle/status/updated_at` of one saved skill; immutable procedure/provenance and neighboring JSONL bytes remain intact. Expected-byte atomic replacement and conditional own-write rollback preserve concurrent edits. Reads no longer initialize missing working memory. This is not a global cross-process transaction lock.
- The fixed hashed receipt is independently validated in Native and links to restart-safe lifecycle evidence. The detailed process receipt is not invented after restart. Restoration grants availability only; no fresh success, post-restore capture writer, task execution, permissions or migration. Registry unchanged at 387/41.

`proto_mind/native_skill_lifecycle.py` + `native/Sources/SkillLifecycleApplyModels.swift` + `SkillLifecycleApplyModel.swift` + `SkillLifecycleApplyView.swift` (EV-04 Skill Lifecycle Apply / Native 0.26.0)

- Fixed private-stdio `skill_lifecycle_review`, `skill_lifecycle_preview` and `skill_lifecycle_confirm` extend an exact existing decision receipt, not arbitrary commands or model tools. Detached bounded no-follow source readers feed the existing lifecycle readiness and keep/durable-archive sessions. Viewing never constructs a pilot, starts capture or changes consent.
- A new exact token and shared-store acknowledgement bind the decision, conversation/workspace identity, skill/memory/config SHA-256 and current process evidence. Swift independently checks the closed envelopes and recomputes the core token. Keep is receipt-only; archive changes one existing record's `lifecycle/status/updated_at`. Revision, restore, pending post-restore capture, procedure execution and new permissions are not exposed.
- The existing durable writer now preserves neighboring JSONL bytes/unknown fields, verifies actual post-write bytes and unchanged source dependencies, and reuses the exclusive-temp/expected-byte atomic replacement primitive. Failure restores original bytes only while the current bytes still match its own payload; concurrent/unreadable changes are preserved for manual review. These guards are not a transaction lock against all external processes.
- The bridge reserves one Native lifecycle attempt, including post-start failure/lost-response paths, across conversations. Existing successful operator lifecycle applies also consume that slot. No automatic retries, receipt persistence, memory/private-file writes or Experience events are added. The exact process receipt links to independently readable durable archive cause; restart expires decisions/authority, not the saved envelope. Registry remains 387/41.

`proto_mind/native_skill_decision.py` + `native/Sources/SkillDecisionModels.swift` + `SkillDecisionModel.swift` + `SkillDecisionView.swift` (EV-04 Skill Outcome Decisions / Native 0.25.0)

- Three fixed private-stdio RPCs (`skill_decision_review`, `skill_decision_preview`, `skill_decision_confirm`) reuse the bounded Native outcome source reader and existing core outcome decision builder/session/doctor. They never dispatch commands, construct a coordinator/pilot, start capture or change consent. Only the selected conversation's existing events and exact capture receipts may support a decision.
- The core's success-to-keep and failure/mixed-to-revise/archive rules remain unchanged. Preview binds choice, exact source/config hashes, workspace/conversation, pilot state, events, captures and decisions. Confirmation requires the current core token and decision-only acknowledgement; stale sources/evidence/scope, unsafe settings, unavailable provenance, restored skills, replay and replacement are refused. Final source/process readback is not a filesystem transaction lock.
- Confirmation appends one terminal process-only decision receipt, with zero new Experience events and no memory/skill/lifecycle/private-file writes. A prior stop does not prevent a new explicitly confirmed decision over retained evidence, but changing pilot state invalidates an older preview and never resumes capture. The core's one-decision-per-skill-per-pilot and 16-decision limits remain unchanged.
- Swift validates the closed envelopes, allowed choices, exact token/blueprint/receipt and no-apply flags. Refresh/edit invalidates confirmation; no choice is automatic. The existing doctor distinguishes receipt integrity from current versus historical evidence. The UI links back to the source inspector and explains that archive/revise are decisions, not applied changes. No persistent schema, Registry growth, permission, model/network/tool call or pending post-restore writer is added.

`proto_mind/native_skill_outcome.py` + `native/Sources/SkillOutcomeModels.swift` + `SkillOutcomeModel.swift` + `SkillOutcomeView.swift` (EV-04 Manual Skill Outcomes / Native 0.24.0)

- Fixed private-stdio `skill_outcome_review`, `skill_outcome_preview` and `skill_outcome_confirm` reuse the existing `ProceduralSkillOutcomeCaptureBuilder` and the selected conversation pilot's capture session. They do not dispatch slash commands, construct stores/coordinators, start a pilot or change consent. The Workshop link only opens existing consent help; the operator must perform that separate existing flow.
- Source snapshots use bounded no-follow reads of `skills.jsonl`, `persistent_memory.json` and `context_injection.json`, rejecting malformed, duplicate, non-finite, missing and over-limit sources. Confirmation binds exact form/conversation/workspace, store SHA-256, existing pilot session/state/events/receipts and the original core blueprint token, plus a manual-result acknowledgement. Source readback detects observed changes; it is not a cross-process filesystem lock.
- Only explicit confirmation may append the core's four-event operator-reported batch and one receipt in bounded process memory. No procedure, model, network call, disk write, usage-counter update, permission grant, learning promotion or lifecycle mutation occurs. The core's 16-receipt/event/byte limits and exact duplicate refusal remain in force. Buffer refusal may stop the pilot fail-closed, never enable it. Restore-bound capture remains undelivered.
- Swift validates the closed response/scope, mutation boundaries, token/blueprint and receipt linkage. Edited or stale forms lose confirmation, closed selections ignore late responses and lost responses are not automatically retried. Existing receipts remain inspectable until process exit; a restart clears this consent/evidence, not the durable skill. Results navigate to the existing read-only inspector, with operator-reported versus independently verified evidence explicitly distinguished.

`proto_mind/native_skill_inspection.py` + `native/Sources/SkillInspectionModels.swift` + `SkillInspectionModel.swift` + `SkillInspectionView.swift` (EV-04 Skill Evidence And Lifecycle / Native 0.23.0)

- One fixed private-stdio `skill_inspection` RPC selects an exact Skill Library ID and, optionally, an existing Native conversation. This is not a Registry command, model tool, capture entry or generic dispatcher. It shares the foreground lock, rejects arbitrary parameters and never creates a coordinator or Experience pilot.
- Bounded no-follow reads use only `skills.jsonl` and `persistent_memory.json`; malformed/duplicate/non-finite/over-limit sources fail closed. The existing lifecycle and restore receipt auditors expose pure record inspection, and post-restore re-evaluation adds a snapshot-only entry. Existing CLI/writer paths retain their behavior. Readback detects observed source changes before publishing a verdict; this is not an atomic cross-process snapshot or filesystem lock.
- The Native card separates verified durable apply/archive/restore facts, source lineage, optional exact process receipt matching, and already-existing process-memory manual-use outcomes from the selected conversation. It does not mine chat, increment `uses`, reconstruct lost receipts or treat pre-restore/unbound events as fresh evidence. Hashes prove consistency, not semantic truth or independently measured skill quality. A failure/mixed result remains advisory.
- Swift checks the closed read-only response, selection, flags, state/count consistency and bounded values. Close or conversation changes invalidate pending UI responses. Refresh and source navigation do not save chat/drafts/preferences. Legacy/ambiguous/corrupt evidence remains visible as such. No lifecycle write controls, post-restore capture writer, project isolation, token, new permission, new persistent schema, Context Injection change or network/model call is introduced.

`proto_mind/native_learning_review.py` + `native/Sources/LearningReviewModels.swift` + `native/Sources/LearningReviewView.swift` (EV-04 Supervised Lesson Review / Native 0.21.0)

- Private `memory_learning_review`/`memory_learning_preview` inspect existing process-memory candidates, exact reference selections and detached fixed-store snapshots; they do not create a pilot, consent, model turn or file. `memory_learning_confirm` permits only fixed accept/reject/propose/apply operations through the existing core sessions, never a generic dispatcher.
- Every confirmed step revalidates current evidence/store hashes, conversation/workspace identity, selection/reason, exact core token and operation scope. Swift discards stale previews and requires a separate shared-global-memory acknowledgement before apply. Accept/reject/propose remain process-memory-only; final apply appends one verified `memory.lesson.v1` record. One successful apply is allowed across the running Native bridge's conversations. No auto-step, batch, skill write, capture activation, grant, Context toggle, history or session-schema change exists.
- The shared `experience_learning_apply.py` writer preserves raw original legacy JSON fields on append, uses bounded no-follow reads and a fsynced atomic replacement, verifies the resulting record/rows/hash, and conditionally restores exact original bytes after failure. Recovery refuses to overwrite a concurrent change or remove a pre-existing temporary file. Native serialization and repeated hash checks do not constitute a cross-process transaction lock.
- Native receipt cards display current verification, before/after hashes, a non-executing rollback suggestion and the stored provenance link. Detailed receipts/decisions/proposals expire at restart; embedded applied provenance remains verifiable in Memory Library. Global legacy stores are not project-isolated, and lineage evidence does not establish semantic truth. Existing CLI/PySide/tkinter routes remain unchanged.

`proto_mind/persona_engine.py` + `proto_mind/persona/brother-0.1.0.json` + `proto_mind/persona_evals.py` + `proto_mind/persona_activation_readiness.py` + `proto_mind/persona_activation_evals.py` + `proto_mind/persona_activation.py` + `proto_mind/persona_runtime_evals.py` + `proto_mind/native_persona.py` + `native/Sources/PersonaInspector.swift` + `native/Sources/NativeSettingsView.swift` (Persona Engine 0.3 / Native 0.19.0)

- Persona 0.1 supplies one strict, versioned Brother kernel and immutable hashed `PersonaSnapshot` values. There is no facet selector, mood mode, trait slider, provider-specific identity fork or hidden permission field.
- `PersonaContextCompiler` reads the existing Identity source without initializing it and projects only explicitly supplied, active, source-linked memory records. It does not retrieve memories, call a model/provider, write a store, toggle Context Injection or authorize an action. Runtime/provider/tool/network/workspace facts remain a separate self-model whose `authorizes_actions` field is always false.
- `PersonaChangeCandidate` permits only bounded soft voice/detail proposals, requires explicit future approval and has no writer. Permission targets, external-content identity changes, malformed provenance and unsupported capabilities fail closed. Seven deterministic evals cover these boundaries. `PERSONA_ENGINE_MIGRATION_MAP.md` maps current prompt sources.
- Persona 0.2 adds exact private-stdio `persona_preview` and a read-only Native sheet. Python validates current provider/model/workspace controls and any Full Mac token before compiling; it selects no memory and exposes no absolute workspace path or token. Swift revalidates the closed envelope, single Brother kernel, non-authorizing snapshot, source bounds and runtime coherence. The inspector calls no model, network, retrieval, command or writer and is not wired into production prompts.
- Native 0.18.0 added exact read-only `persona_readiness` evidence without changing the reasoner path. Its stable activation fingerprint excludes ephemeral timestamps while the full report hash still binds every generated snapshot. Nine fail-closed gates require provider parity, prompt bounds, immutable provider safety layers, no added authority/side effects and disabled Context Injection.
- Native 0.19.0 adds an explicit two-stage local opt-in and visible rollback. `persona_activation.py` compiles one fresh snapshot from the coordinator's already-selected memories and produces a strict per-turn receipt binding the exact final prompt, provenance, readiness, provider/runtime and zero additional retrieval/model/write counters. Codex and Ollama use their existing single provider call; Mock, operator commands, unresolved Codex models, Context drift and stale readiness are refused. The global Native opt-in is stored only in private preferences v2; each Send still revalidates the current provider/model/workspace/access state. Disabling it returns the next turn to the byte-compatible legacy prompt without rewriting durable provider history.

`native/` + `proto_mind/native_bridge.py` + `proto_mind/native_codex.py` + `proto_mind/native_instructions.py` + `proto_mind/native_turn_lineage.py` + `proto_mind/native_session_spine_live.py` + `proto_mind/native_computer_use.py` + `proto_mind/native_codex_threads.py` + `proto_mind/native_agent.py` + `proto_mind/native_agent_contract.py` + `proto_mind/native_agent_evals.py` + `proto_mind/native_progress.py` + `proto_mind/native_workspace.py` + `proto_mind/native_library.py` + `proto_mind/local_knowledge_capabilities.py` + `proto_mind/native_work_sessions.py` + `proto_mind/native_desk.py` + `proto_mind/native_review.py` + `proto_mind/native_images.py` + `proto_mind/native_pdf.py` + `proto_mind/native_persona.py` + `proto_mind/persona_activation_readiness.py` + `proto_mind/persona_activation.py` (Native 0.39.0 / Live Session Spine Preview over the controlled Native workspace)

- Native 0.19.0 is a real SwiftUI/AppKit executable, built as `dist/Proto-Mind Native.app`. Its Codex-inspired workspace includes mode-bound durable conversations, bounded attachments/context/evidence, a private work journal, separately granted Full Mac shell/Web Search and signed OpenAI Computer Use, plus a Persona Inspector and explicitly controlled Brother prompt projection. The old PySide bundle remains a fallback; CLI/PySide/tkinter and non-Native reasoners retain their existing paths.
- `native_computer_use.py` discovers only the canonical per-user OpenAI service, verifies service/client bundle IDs plus Developer ID team `2DC432GLL2`, and exposes no executable path to Swift. `native_codex.py` keeps ordinary chat tool-free, but Full Mac configures one required `computer-use` MCP server with ten exact enabled tools and verifies its bounded inventory before generation. No OpenAI binary/plugin source is copied into Proto-Mind. `native_agent.py` accepts only that server/tool allowlist; the durable projection omits screenshots, UI trees, coordinates, input values and MCP output.
- Native 0.14.2 adds a per-turn Computer Use observation contract outside provider-thread persistence: first app state uses a complete `disableDiff=true` snapshot because raw UI trees are not replayed between turns; a timeout is not retried through an alias. The strict MCP tool timeout is 30 seconds. This changes neither the ten-tool allowlist nor Full Mac authority and adds no screenshot/shell fallback.
- Native 0.15.0 adds a frozen `native_agent_contract.v1` before provider-process startup and verifies the connected Computer Use inventory against it. `native_agent_evals.py` runs six deterministic local guardrail cases without provider or result-store writes. The existing private session schema accepts only the validated public contract/hash/inventory and bounded Automation failure fields; legacy records are not rewritten. `NSAppleEventsUsageDescription` plus an operator-opened settings action enables normal macOS Automation onboarding after exact `-1743`, never a TCC bypass or automatic permission change. No Agents SDK/API key/Platform path is introduced.
- Native 0.16.0 adds two exact read-only local capability declarations, `search` and `fetch`, over the existing private stdio bridge. Input schemas reject unknown properties; result envelopes contain only `structuredContent`, one bounded text fallback and local-only metadata that explicitly denies network, store mutation and model dispatch. Swift validates this boundary before decoding and uses legacy direct-read RPCs only when an older bridge reports the new method absent. These capabilities are not registered slash commands, public MCP tools or model-callable operations.
- The public work-log producer now emits a positive monotonic `state_version`; Swift rejects stale same-run events and the durable public projection preserves valid versions. Legacy unversioned logs remain readable without rewrite. The value orders public display state only and carries no reasoning content.
- Full Mac with verified Computer Use now configures the signed client as Codex's official `turn-ended` notify handler. This closes the provider turn lifecycle so the desktop-managed service can leave active capture/UI state after normal completion. The shared service may remain resident for ChatGPT; Proto-Mind neither kills it nor claims ownership. Ordinary Chat and Full Mac without Computer Use keep an empty notify list.
- `native_codex_threads.py` owns bounded private `codex_threads.json` v3 bindings keyed by Native conversation plus instruction mode (`chat` or `full_access`), exact optional workspace identity and a SHA-256 fingerprint of that mode's static developer-instruction contract. It never stores the instruction text. First use records a non-ephemeral `thread/start`; unchanged contracts resume only the matching mode and revalidate ID, cwd, sandbox, approval policy and instruction sources. A stale v2/current-mode binding is shown locally before Send; the next explicit turn verifies a fresh provider thread, compare-and-swap replaces only that mode's binding and quotes bounded local history once. The former provider rollout is not deleted. Legacy v1 rows remain historical and v1/v2 status reads perform no migration. Corruption, concurrent binding drift, reused provider IDs, resume failure, policy drift or workspace mismatch fails closed without fallback or partial turn. Explicit reset still removes all local mode bindings for one conversation and revokes live agent grants; old Native history/provider rollouts remain. The provider profile uses local `save-all`; it can contain private prompts, replies and tool output and has no automatic pruning UI.
- `native_instructions.py` owns the shared Native local-instruction assembler, strict `native_instruction_preview.v1` projection and content-free `native_instruction_receipt.v1`. Production Codex/Ollama Send and the Context desk use the same builder for legacy or Brother Persona context. Codex projects exact `baseInstructions` plus mode-specific `developerInstructions`; Ollama projects one system message. Layer and canonical projection hashes are independently checked by `ContextArtifactDesk.swift`. Preview may perform deterministic core retrieval with usage tracking disabled, but starts no model/network/provider thread, executes nothing and writes no store. Upstream provider-owned instructions and private reasoning are explicitly unavailable, not reconstructed. Send revalidates and recomputes current state; successful provider turns persist only ordered layer metadata/hashes in the existing private work session. That receipt proves local assembly, not provider delivery or interpretation. Older sessions remain readable without migration; Mock/operator routes receive no invented receipt.
- `native_turn_lineage.py` and `TurnLineage.swift` add a second closed content-free receipt after a successful real-provider response. It binds exact prompt/response/preview hashes to the conversation, work session and Instruction Receipt without storing those texts. An optional Native-history reference binds the original user message and assistant raw response and opens only the matching journal run. Whole-run review fingerprints may evolve independently; missing/tampered lineage is refused rather than guessed. This is compatibility groundwork for read-only live Session Spine projection, not a Session Spine writer, provider proof, task-success verdict, model input, permission or command.
- `native_session_spine_live.py` and `SessionSpinePreview.swift` turn that exact lineage into one ephemeral read-only P1 inspection. The bridge opens only the caller-selected current run reference, revalidates exact history/run/receipt evidence and returns a self-hashed content-free timeline plus folded-surface parity. Native validates it again and renders a bounded sheet from the linked answer. No event/archive/export is written, no tool or command is replayed, and absent/stale evidence has no latest-run fallback. This remains a preview rather than authoritative Session Spine storage.
- `native_pdf.py`, `PDFAttachments.swift` and the fixed bundled `native/PDFHelper` implement explicit text-only PDF input. `pdf_preview` reuses protected no-follow byte reads, passes immutable bytes over stdin to Apple PDFKit in a network/file-write-denied subprocess (12s wall timeout / 8s CPU limit), and returns selected-page text plus source/text hashes. One PDF up to 8 MiB, 300 document pages, eight selected pages and 3,000 Unicode characters/page. Default page 1 is visible; no automatic page search, OCR, original upload, parser fallback or encrypted/copy-restricted bypass. Drag/drop is separate from mixed image/text batches. Explicit Attach writes metadata-only history v5, compatible read-only with v1-v4; Send rereads/extracts and requires exact hashes/metadata. Context desk shows selected text; per-run manifests and history contain no PDF payload. Codex/Ollama wrappers quote only selected text as untrusted data and request page references, not guaranteed citation correctness. Core user input/memory rules, cloud grants and operator bypass stay unchanged. Old PDF text is not reattached, but normal answers quoting it can remain in chat history. No new Registry commands or dependencies.
- `WorkSessionNotices.swift` separates historical notice dismissal from run acceptance: one explicit hide/show saves only an optional bounded conversation-v4 display preference, keyed by run UUID, fingerprint and unknown/not-started state. Opening the banner selects its run; hiding leaves journal/evidence/review bytes unchanged. Changed/new evidence warns again; source diagnostics cannot be dismissed this way. Legacy history loads without rewriting. `TaskReviewView` explains unavailable review states and defaults completed no-criteria replies to rework-with-comment, without weakening backend acceptance/confirmation checks or introducing retry/grant/core writes.
- `AttachmentDrop.swift` accepts bounded local file-URL drops through SwiftUI and the AppKit text editor, reusing read-only image/workspace readers. A conversation/workspace-bound batch preview precedes one explicit metadata-only private-history save; invalid/stale batches, provider timeouts and save failure do not partially attach files or send a turn. Text remains workspace-scoped; selected PNG/JPEG retains existing limits. No new RPC, command, format conversion or grant. Fixed-height strips and a bounded wrapping image notice avoid the minimum-width split-layout expansion that hid the sidebar/composer after restart. Codex's minimal child environment now includes known Homebrew/system runtime paths; private HOME, config isolation and tool policy remain unchanged. EOF is a local transport condition, not a fabricated provider response.
- `NativeInteractions` provides shared hover/press fill/outline for plain buttons, menus and disclosure controls, without hover-time resizing. Disabled controls stay neutral and Reduce Motion is respected. Existing height-bounded sidebar and system typography are preserved.
- `native_images.py` / `ImageAttachments.swift` implement explicit PNG/JPEG input outside the workspace-text reader. Local `image_preview` uses bounded no-follow regular-file reads, protected-path exclusions, SHA-256, container/dimension checks and Native ImageIO decoding. Only verified macOS `/var`/`/tmp` aliases are normalized; arbitrary symlinks are refused. Limits are three images, 4 MiB each / 8 MiB total, 24 megapixels each. Preview/cancel are read-only. Explicit attachment saves metadata in private history v4; v1/v2/v3 still load without rewrite. Image bytes/data URLs never enter that history or work-session manifests, and older-image history explicitly says the pixels are absent. Send rereads/hash-checks the sources and requires an image-capable Codex catalog entry plus existing cloud consent; both adapter modes send immutable in-memory `image` payloads, never a provider-readable local path. Ollama/Mock fail visibly, operators bypass/retain images, and no new tool access, screenshot capture, OCR, redaction or core Injection change occurs. Original embedded metadata is not stripped. Details and live synthetic Sol evidence are in the Native Roadmap.
- `native_desk.py` and `ContextArtifactDesk.swift` add Native-only read-only `context_preview`, `artifact_list` and `artifact_preview` RPCs. Pre-send inspection reuses actual file/hash/history bounds, reports cloud/local destination and shared-core versus workspace scope, and executes neither a command nor a provider turn. Selected sources are not silently refreshed. The local-instruction extension may run the existing deterministic shared-core retrieval with usage tracking disabled; its exact result is shown and never persisted. The desk claims only Proto-Mind-authored instruction bytes, not provider-owned hidden instructions or private reasoning.
- New normal work records optionally store `native_context_manifest.v1` (counts/paths/hashes and declared criteria, not full history/file bodies) and `native_artifacts.v1` (up to 24 observed file-change references and completion hashes). The latter reads only supported text within the unchanged workspace identity using the existing protected no-follow reader. It is not a file transaction, original-copy backup, exclusive authorship proof or an inventory of shell side effects. Reads bind to the saved run ID/fingerprint, project and conversation; changed workspace identity refuses current-file reads. Legacy/interrupted metadata stays missing rather than being repaired. Diff/output remain existing bounded public fragments; HTML/scripts render as plain text and command exit evidence is not goal verification. Restore/permissions are unchanged; manual acceptance is a separate explicit operation below.
- `native_review.py` and `TaskReviewView.swift` add optional operator-authored `native_success_criteria.v1` (8 unique lines, 300 characters each) and `native_operator_review.v1`. Explicitly saved `pendingCriteria` lives in the private history-v3 draft; normal Send freezes it in the run/context manifest and supplies only the native reasoner adapter. Core Observer input, memory-write rules and session-log schema are unchanged; operator commands bypass criteria, and an empty list preserves prior prompt behavior. `review_preview` is local/read-only; `review_save` requires a second exact confirmation and revalidates the run fingerprint, scope, selection and current artifact observations under the existing cooperative lock/byte-CAS writer. Only one private run's assessment history, acceptance and updated time change. Up to 12 hash-linked receipts preserve earlier decisions, note, criterion checks and observed hashes. Accepted means operator-reported on normally completed, fully checked, unchanged captured evidence; it never changes automatic `verification:not_assessed`, repairs unknown outcomes, resumes tools or grants authority. Legacy runs without declared criteria cannot be accepted retroactively. Hashes are not an operator signature or filesystem freeze.
- `NativeTheme` uses 14-point system text, 12-point code, and `NSVisualEffectView` behind-window sidebar material with a Reduce Transparency fallback. Sidebar navigation/disclosure/search/conversations share a height-bounded scroll area, with fixed header/footer so library expansion cannot displace the chat/composer. `CodexModelOptions`/`ModelSelectionMenu` project the provider catalog into separate model/effort selectors. Optional history v3 `reasoningEffort` defaults empty on legacy reads; explicit selection/reset writes Native history only. Both adapter modes re-fetch a bounded catalog, bind its default or the explicit model, validate supported effort, and send the official `turn/start.effort` field. Manual incompatible model changes visibly reset effort; catalog drift alone never rewrites saved choices. No synthetic model availability, service-tier override, core Observer-intent change or new authority.
- `native_progress.py` separates public `agentMessage` commentary from the final answer for both Codex chat and Full Mac. The display-only `native_work_log.v1` projection carries at most 96 ordered commentary/plan/tool-reference/compaction entries plus observed stage/time/status and a monotonic display-state version. Raw reasoning, reasoning-summary payloads, internal prompts and unrelated thread/turn events are excluded. Tool bodies stay in the existing bounded receipt. Swift rejects stale same-run versions and renders an expandable live/persisted timeline; its optional history v3 field is not replayed, evaluated as memory, or a new execution grant. Failed/unfinished work remains explicit; old archives load without rewriting or invented progress.
- A private newline-JSON stdio bridge calls `process_interactive_input_with_envelope` exactly once. It creates no listening port and never dispatches model output as commands. Registered manual operator mutations require native exact-input confirmation plus existing internal gates. Unknown slash input is refused in this new client; legacy CLI behavior is unchanged.
- Read-only bootstrap never initializes missing memory or injection files. Native history is stored atomically outside the project under `~/Library/Application Support/ProtoMindNative`; each conversation gets its own bounded process-session coordinator, while durable core stores remain shared and unchanged in format.
- Model adapters are native-only: loopback Ollama with visible failure/no Mock substitution, explicit Mock, and official Codex subscription authentication. Default Codex chat uses a separate profile/HOME, empty cwd, ephemeral per-turn thread, read-only/no-network tool sandbox, disabled shell/code/browser/extensions/hooks/MCP, denied server requests, bounded context, assistant-only deltas, and no API-key fallback. An outer macOS process sandbox restricts chat-provider file reads to system/runtime files and its own directories, including for built-in image readers. It fails closed if unavailable; it does not sandbox the local Python cognitive core.
- `native_agent.py` supplies ephemeral conversation/folder grants and bounded activity projections. `agent_access` is a native-only explicit confirmation RPC, not a model tool. A grant plus cloud consent permits a separate Codex process with `danger-full-access`/`never`, shell, patch, Web Search and the one verified Computer Use MCP. Effective policy/cwd/instruction sources and Computer Use inventory are checked before generation. Full Mac intentionally removes filesystem isolation; the bound folder is a starting directory, not a fence. Other MCP, hooks, browser/plugins and multi-agent features remain disabled; no Desktop credential/config import occurs.
- Agent events are correlated to the active thread/turn; internal prompts/reasoning and unknown payload fields are not forwarded. Command/file/image/plan metadata and bounded previews form `native_agent_run.v1` receipts saved with Native messages (introduced in history v3; current v5 reads v1-v4 without rewrite). EV-01 separately checkpoints a smaller public projection during new normal turns. Failure/Stop disables the UI grant and never retries or rolls back. Full-access process closes after the turn; 15-minute and 64-observed-item limits are best-effort stop triggers, not atomic execution boundaries. Complete side-effect capture and detached-process cleanup are not guaranteed. No target text is dispatched through the Proto-Mind command catalog.
- `native_work_sessions.py` stores private per-run JSON outside the core, with a versioned ID/conversation/project/workspace contract, prepared/pre-dispatch/response evidence and explicit unassessed verification/unrecorded acceptance. Atomic fsynced writes and a cooperative single-writer lock precede the normal handler; duplicate IDs and continuation parents refuse another dispatch. Public events upsert bounded entries. Startup/read-only `work_sessions` never repairs unfinished states: a missing active writer after dispatch means unknown. Storage failure stops instead of blindly retrying; it cannot undo effects already performed.
- `work_session_continuation` checks a current parent fingerprint, conversation/project/workspace identity and explicit source hashes, then returns a quoted reconstruction draft. Swift refuses to overwrite drafts/attachments, saves only an optional history-v3 `draftContinuation` reference on the user's gesture, and requires separate Send. Send revalidates parent/one-child admission and the existing provider/cloud/tool gates. No provider-thread resume, grant persistence, automatic file reattachment, new commands, core Experience capture or global store lock is added. Journal views are bounded to 30 runs / 2 MiB; storage to 500 runs / 256 KiB per record, without auto-pruning. Private state needs separate backup; previews are not secret-redacted or tamper-proof.
- Cloud consent defaults off and is independent of core Context Injection. In v4.0b an explicit device-local opt-in survives restart; a selected Codex account may then be checked on startup without sending a conversation. Corrupt settings fail closed and cannot be overwritten by toggling. Codex requests may transmit bounded chat history, selected memory, and explicit file excerpts only after this permission. Operator commands bypass the reasoner. No token extraction or existing memory/learning/runner authority change. Live acceptance on 2026-08-31 verified the separate ChatGPT subscription profile, a plain reply, and correct answers from an explicitly attached source file; the two non-durable probes left all 48 core-store/export hashes unchanged and Context Injection disabled.
- Workspace binding uses the same local folder, not a copy, watcher, or sync engine. Operator-only status/list/read operations use bounded UTF-8 regular-file reads, no-follow descriptors and protected-path exclusions. Binding/preview never grants Full Mac. Once separately granted, Full Mac shell and Computer Use are intentionally broader than those preview exclusions; visible screen/app content can be processed remotely and the selected folder is not a safety fence.
- `local_knowledge_capabilities.py` wraps Native Library reads in exact typed `search` / `fetch` contracts over private stdio. `NativeLibrary` still owns the actual bounded read and legacy `library_list` / `library_inspect` remain rolling-upgrade fallback methods, not commands, retrieval, public MCP or model tools. It reads only persistent/working memory, goals, and skills under the launch project's core data directory; it does not construct mutating stores or initialize missing files. No-follow regular-file reads, 16 MiB/source and 5,000-record/source limits, 100-row pages, literal search, and 24,000-character detail blocks keep rendering bounded. Swift validates both envelope and versioned page/detail contracts and discards stale async responses. Missing/corrupt/ambiguous sources and hash drift are diagnostic, never repaired. Navigation, usage counts, focus, skill lifecycle, native history, and prompt context are not written or changed by viewing.
- See `NATIVE_MACOS_ROADMAP.md` for the personal-use direction and explicit portability/privacy limits. No slash prefixes or categories are added.

`proto_mind/backup_utils.py`

- Rule 0 checkpoints now cover `native`, `scripts`, `evals`, root Markdown docs, and existing source/data directories; the older fixed source list omitted the new Swift/eval trees. Build/bytecode caches and external native account/history state are not copied. Archives are written to a private temporary file, closed/fsynced, then published without replacing an existing checkpoint; failures do not publish partial archives. This is backup coverage hardening, not a core-store migration or cognitive behavior change.

`proto_mind/main.py`

- CLI entrypoint.
- Enforces Python 3.11+ at startup and prints a clean recommendation before unsupported Python versions reach imports that require 3.11 APIs.
- Builds the coordinator from config.
- Routes normal user turns through the coordinator.
- Handles backup/checkpoint, memory inspection, cleanup, reference repair, and session log inspection commands.
- Exposes reusable one-input processing for CLI and desktop shells.
- Prints observer output, retrieved memory, retrieval trace, memory decision summary, previous correction hints, and self-reflection output.

`proto_mind/desktop_app.py`

- Tkinter/std-lib desktop chat shell.
- Launches with `scripts/run_desktop_mock.sh`, `scripts/run_desktop_ollama.sh`, or a known Python 3.11+ interpreter.
- Uses the same reusable input handler as the CLI for slash commands, natural command routing, and normal cognitive turns.
- Provides quick buttons for Self-Check, Health, Doctor, Review, and Log Status.
- Defaults to compact chat display for normal turns and exposes a `Debug output` checkbox for full CLI-style traces.
- Shows backend status and Ollama model when launched with `PROTO_MIND_REASONER=ollama`.
- Supports Copy All and explicit Save Transcript to `exports/desktop_chat_transcript_*.md`.
- Supports robust macOS clipboard UX through Command/Ctrl shortcuts, Tk virtual events, app-level shortcut routing, an Edit menu, and context menus.
- Does not create an app bundle or installer.

`proto_mind/pyside_app.py`

- Optional PySide6 desktop shell.
- Launches with `scripts/run_pyside_mock.sh`, `scripts/run_pyside_ollama.sh`, the local `.app` wrapper, or a known Python 3.11+ interpreter when PySide6 is installed.
- If PySide6 is missing, exits cleanly with `python3 -m pip install PySide6` guidance.
- Reuses the same desktop runtime, shared CLI input handler, natural command router, compact/debug formatting helpers, session control room commands, transcript export helper, and `desktop_prefs.json`.
- Provides a left chat area and right System Panel similar to the tkinter shell.
- v1.4 adds safe markdown-lite rendering for normal PySide chat messages: escaped HTML, paragraphs, bullet/numbered lists, inline code, fenced code blocks, bold text, and simple headings without external markdown dependencies.
- v1.5 adds a local macOS `.app` launcher wrapper built by `scripts/build_macos_app_launcher.sh`. The wrapper lives at `dist/Proto-Mind.app`, resolves its project checkout relative to the app bundle, and uses the local Python/PySide/Ollama environment; it is not a fully portable packaged app. v1.5.1 makes Python selection Finder-safe by checking multiple absolute Python candidates and choosing the first one that can import both `proto_mind` and `PySide6`. v1.5.2 adds a generated `ProtoMind.icns` launcher icon, `/tmp/proto_mind_launcher.log` diagnostics, and `scripts/install_macos_app_shortcut.sh` for Desktop shortcuts.
- v1.4.1 isolates each chat message block and closes markdown list/code state so ordered and bullet lists cannot continue numbering into later User/System/Proto-Mind messages.
- v1.3 adds a streaming-ready worker/UI API and a safe Stop/Cancel skeleton. Stop requests set `Runtime: stopping...`, mark the worker as cancellation-requested, and wait for the current blocking operation to finish; true interruption and token streaming are future work.
- v1.2.1 shows explicit runtime state in the System Panel, keeps the bottom status line synchronized with backend/model/debug info, and changes the Send button text to `Thinking...` while a worker is active.
- v1.2 runs user input and operator commands through a QThread worker so long local Ollama calls do not block the GUI. One active worker is allowed at a time; streaming and Stop are not implemented yet.
- v1.1 added Enter-to-send, Shift+Enter newline input behavior, a dark stylesheet, HTML message blocks, monospace report blocks, status badge colors, and PySide geometry persistence.
- Does not make PySide6 a required project dependency.

`scripts/`

- `scripts/run_cli.sh` selects a Python 3.11+ interpreter and launches `-m proto_mind.main`.
- `scripts/run_tests.sh` selects the same Python 3.11+ interpreter, runs `unittest`, runs `compileall`, and skips optional `pytest` cleanly if unavailable.
- `scripts/which_python.sh` prints the selected Python, version, `proto_mind` import health, and PySide6 import health.
- `scripts/build_native_app.sh` builds and ad-hoc signs the separate Swift app; `scripts/run_native.sh` launches it. `scripts/test_native.sh` checks Swift models and real bridge integration on temporary code-only fixtures without XCTest or new dependencies.
- Desktop and PySide run scripts use the same selector so development launch paths do not depend on a random `python3` on `PATH`.

`proto_mind/contest_provenance.py`

- Reads the accepted July 11 pre-contest archive directly without extracting it into the project.
- Hashes a privacy-safe submission scope containing source, tests, scripts, docs, setup metadata, and safe assets.
- Excludes live data, exports, backups, logs, caches, app builds, virtual environments, Git metadata, and generated provenance JSON.
- Atomically writes baseline, current, and delta JSON manifests under `contest/provenance/`.
- Reports added/changed/removed/unchanged files plus test, Registry, category, file, and byte deltas.
- Makes no runtime command, cognitive-store, Context Injection, capture, learning, runner, or session-log change.

`proto_mind/backup_utils.py`

- Implements safe local checkpoint/archive commands.
- Supports `/memory backup` and `/system checkpoint`.
- Creates timestamped archives under `backups/`.
- Does not route through observer/reasoner and does not create memory records.

`proto_mind/config.py`

- Defines `ProtoMindConfig`.
- Reads environment variables:
  - `PROTO_MIND_REASONER`, default `mock`.
  - `PROTO_MIND_OLLAMA_MODEL`, default `qwen3:8b`.
  - `PROTO_MIND_OLLAMA_URL`, default `http://localhost:11434`.
  - `PROTO_MIND_DATA_DIR`, default `proto_mind/data`.

`proto_mind/models.py`

- Defines dataclasses used across the pipeline.
- Includes memory records, observer state, retrieval trace records, interaction result, memory update summary, hygiene preview/apply models, orphan reference repair models, grounding audit models, and self-reflection result models.
- Serialization is explicit through `to_dict()` methods so CLI/API payloads remain JSON-safe.

`proto_mind/coordinator.py`

- Owns the normal turn lifecycle.
- Runs observer, optional retrieval, reasoner, memory update evaluation/application, self-reflection, grounding audit, and next-turn correction hint management.
- Holds ephemeral in-process `pending_correction_hints` for Self-Reflection v2.

`proto_mind/observer.py`

- Classifies user input into query types such as `new_question`, `continuity_followup`, `decision_request`, `personal_context`, `project_context`, `meta_architecture`, and `memory_inventory`.
- Determines whether memory retrieval is needed.
- Estimates importance.
- Extracts topic tags via `topic_utils.extract_topic_tags`.
- Detects memory inventory, continuity, preference behavior, and explicit override/change-of-direction phrasing.

`proto_mind/memory_store.py`

- JSON-backed storage adapter.
- Loads and saves working memory and persistent memory.
- Uses:
  - `proto_mind/data/working_memory.json`
  - `proto_mind/data/persistent_memory.json`
- Supports add, upsert, delete, and list operations.

`proto_mind/memory_provenance.py`

- Builds the compact hashed `memory.lesson.provenance.v1` envelope used only by supervised lesson apply.
- Verifies record payload, candidate/proposal/scope hashes, exact-confirmation markers, evidence IDs, deterministic provenance ID, and provenance hash.
- Formats read-only `/memory why <id>` explanations after process restart and refuses to invent provenance for legacy records.
- Stores no full prompt, response, hidden context, or model-generated provenance narrative.

`proto_mind/lesson_recall_benchmark.py`

- Runs a deterministic English/Russian restart benchmark over temporary memory stores.
- Proves that a valid active learned lesson can be selected and grounded with compact provenance evidence.
- Proves that tampered and unprovenanced lessons fail closed while persistent/working bytes and retrieval usage fields remain unchanged.
- Adds no slash command, live-store access, model/API call, automatic learning, or Context Injection path.

`proto_mind/experience_learning_outcome.py`

- Reviews later compact Experience evidence only after durable lesson provenance, exact memory-ID retrieval, valid event lineage, and post-apply timestamp checks pass.
- Classifies the latest decisive evidence as `KEEP_CANDIDATE`, `REJECT_CANDIDATE`, `SUPERSEDE_CANDIDATE`, or `NEEDS_MORE_EVIDENCE`.
- Requires a newer active provenance-verified replacement record before emitting a supersede candidate.
- Exposes read-only outcome review/doctor formatters under the existing `/experience learning` Registry family and performs no apply or mutation.

`proto_mind/memory_keeper.py`

- Retrieves memories, scores candidates, deduplicates by normalized content, and records retrieval traces.
- Decides whether a turn should be stored.
- Promotes durable decisions/preferences.
- Detects override decisions and marks conflicting active decisions as superseded.
- Decays stale working memories.
- Produces memory decision metadata and promotion/override rationale.

`proto_mind/memory_hygiene.py`

- Implements Memory Hygiene v1.
- Detects exact normalized-content duplicates.
- Produces cleanup previews before mutation.
- Applies conservative duplicate cleanup.
- Repairs `superseded_by` references when duplicate cleanup removes a referenced record in favor of an equivalent kept record.
- Implements orphan `superseded_by` reference preview/apply for broken references that already exist.

`proto_mind/memory_commands.py`

- Read-only CLI memory inspection formatter.
- Supports active memory, decisions, preferences, history, working memory, persistent memory, and summary views.
- Does not mutate memory.

`proto_mind/session_log.py`

- Implements Session Operator Log v1.
- Appends compact normal-turn artifacts to `logs/session_operator_log.jsonl`.
- Formats read-only session log CLI commands.
- Supports status, path, tail, detailed inspect, warning scan, text search, and export views.
- Does not influence reasoning, retrieval, memory updates, self-reflection, or grounding.

`proto_mind/self_reflection.py`

- Rule-based Self-Reflection Layer.
- V1 checks response alignment with selected memory, active decisions, superseded memory, active preferences, and unsupported memory claims.
- V2 generates correction hints and marks whether they should be carried into the next turn.
- Does not call a second LLM.
- Does not rewrite the current response.

`proto_mind/grounding_auditor.py`

- Implements Grounding Auditor v1.
- Audits whether memory-sensitive responses are justified by selected memory and current memory state.
- Checks selected-memory use, active decision contradictions, superseded memory presented as current, unsupported memory/project claims, and current-vs-historical handling.
- Deterministic and non-persistent.

`proto_mind/topic_utils.py`

- Lightweight topic normalization.
- Maps known phrases and tokens into canonical tags such as `storage`, `backend`, `persistence`, `json`, `sqlite`, `response_style`, `future_behavior`, `historical`, and `current`.
- Assigns lower weights to generic tags such as `decision`, `memory`, `project`, and `proto-mind`.
- Computes weighted topic overlap for retrieval scoring.

`proto_mind/reasoners/base.py`

- Defines the `BaseReasoner` interface.
- `respond(...)` receives user input, retrieved memory, observer state, and optional correction hints.

`proto_mind/reasoners/mock_reasoner.py`

- Deterministic mock backend.
- Useful for tests and local inspection without Ollama.
- Produces transparent responses that show how memory affects the answer.
- Receives correction hints as internal guidance, but does not echo them directly into the answer.

`proto_mind/reasoners/ollama_reasoner.py`

- Local Ollama backend.
- Sends chat requests to the configured Ollama URL/model.
- Builds a system prompt containing observer interpretation, reasoning priority, retrieved memory context, and previous self-reflection correction hints.
- Falls back to mock reasoning if Ollama is unavailable or returns invalid output.

`proto_mind/ui/app.py`

- FastAPI inspection UI/API.
- Provides a local pipeline inspection page, not a consumer chat UI.
- `/api/turn` runs the full coordinator pipeline and returns observer output, retrieved memory, retrieval trace, memory summary, grounding audit, self-reflection, previous correction hints, and memory snapshots.
- Also exposes hygiene preview/apply endpoints.

`proto_mind/tests/test_flow.py`

- Main unit test suite.
- Covers observer behavior, retrieval, memory storage/promotion, overrides, historical lookup, preference retrieval, retrieval traces, hygiene cleanup, reference repair, memory commands, self-reflection, and correction hint carry-forward.

## Turn Pipeline

v3.1a adds a deterministic bilingual cognitive baseline before reasoning. `Observer` recognizes English and Russian continuity, recall, preference, decision, and override signals; `topic_utils` maps Russian morphology into the same canonical tags used by retrieval. `proto_mind.cognitive_benchmark` verifies ten local scenarios without LLM/API calls or store writes.

v3.1b adds Memory Write Governance. `MemoryKeeper.retrieve` no longer updates usage metadata unless `record_retrieval_usage` is called explicitly, and new automatic records use user input only rather than coupling generated responses into memory. `memory_governance` exposes read-only policy and migration-preview reports.

v3.1c adds shared bilingual response signals for `SelfReflector` and `GroundingAuditor`. English/Russian current-state, historical, rejected-alternative, memory-claim, and SQLite/JSON override phrases map to the same deterministic checks. The local benchmark now covers ten observer cases and ten response-grounding/reflection cases, while grounding evidence identifies the supporting memory record and source without changing result schemas or stores.

v3.1d adds `proto_mind.cognitive_soak`, a 25-turn Coordinator-level continuity gate using a temporary store and deterministic reasoner. It verifies 21 byte-stable retrieval-only turns, bounded four-content memory growth, preference/goal recall, current-vs-historical decisions, contradiction detection, one-turn correction carry-forward, and no implicit usage telemetry. Observer recall imperatives, grounding scope, insight inventory output, historical-state bias, and MockReasoner active/historical labels were refined from soak findings without changing commands or schemas.

v3.2a adds `proto_mind.experience_ledger` as a persistence-free Experience Ledger foundation. `ExperienceTraceBuilder` converts an existing `InteractionResult` into ordered typed events with explicit `source_event_ids`; its doctor validates schema version, event types, unique IDs, earlier-event provenance, timestamps, and privacy limits. The continuity soak now validates 180 compact events and 332 provenance edges in memory only. No live Coordinator hook, ledger file, session-log change, command, or background writer exists in this milestone.

v3.2b adds a persistence policy and `TemporaryExperienceLedgerStore` for isolated tests only. Valid event batches are logically appended by atomic file replacement and wrapped in a contiguous SHA-256 chain (`sequence`, `previous_hash`, `entry_hash`). Existing corruption, duplicate IDs, forbidden payloads, hash tampering, and every path under live `proto_mind/data` fail closed. Retention is warning-only with no automatic deletion or compaction, and live persistence remains disabled.

v3.2c adds `proto_mind.experience_capture` as a read-only activation boundary rather than another command family. Missing config uses non-persisted disabled defaults; valid local config is read without mutation; corrupt, full-content, and alternate-path requests fail closed. A requested enable remains ineffective because both the Coordinator writer hook and live persistence policy are absent. Status, preview, and doctor reports are available through `python -m proto_mind.experience_capture`; there is no slash command, enable API, config initialization, or event write.

v3.2d adds `proto_mind.experience_vocabulary` and expands the central schema with goal, plan, tool-call/outcome, task-completion, user-correction, reflection, lesson-candidate, and memory-promotion events. Domain builders require compact typed inputs and already-created provenance sources. Central doctor rules enforce lifecycle roots, required payload fields, and source-type links. Success and failure/correction fixtures total 15 events and verify 15/15 temporary hash envelopes without touching domain stores or executing capabilities.

v3.2e adds `proto_mind.experience_explainability`. `ExperienceTraceIndex` deep-copies event input into an immutable read model, resolves deterministic ancestor chains and children, supports exact entity lookup, and renders typed “why” plus safety explanations. It can load an already verified temporary ledger without rewriting it. The benchmark validates an eight-stage promotion lineage, five-stage correction lineage, 15/15 temporary hashes, clean missing-id behavior, and fail-safe broken-source diagnostics.

v3.2f adds `proto_mind.experience_episode`. `ExperienceEpisodeProjector` accepts only trace evidence that passes the existing provenance doctor, groups it by session/turn, and projects compact goal/expectation/plan/action/outcome/task/correction/reflection/lesson/promotion fields while retaining every source event ID. Verified completion requires verified tool and task evidence; corrected failure remains distinct. Learning state reports pending candidates or confirmation-bounded promotion evidence but never performs consolidation. The two-episode benchmark verifies 15/15 temporary hashes and leaves live stores, commands, exports, capture, execution, and Context Injection untouched.

v3.2g adds `proto_mind.experience_learning`. `ExperienceLearningReviewer` consumes detached episode projections plus optional caller-supplied memory/skill snapshots and classifies lesson evidence into reviewable, insufficient-evidence, exact-duplicate, or blocked states. Reviewable candidates require verified completion, confidence `>=0.8`, exact lesson-event provenance, and operator confirmation. Promotion evidence must point to the lesson and retain the no-auto-promotion marker. Results are ephemeral and always deny automatic apply; no live store lookup, semantic similarity, persistence, queue, command, execution, or mutation exists.

v3.2h adds `proto_mind.experience_capture_design` as a design-only safety boundary around the still-disabled capture gate. It locks per-process-session explicit consent, restart expiry, command/internal-report exclusion, no backfill, compact-preview privacy, injected-context denial, required secret-redaction tests, separately approved retention/persistence, and fail-closed failure isolation. The live hook and persistence policy remain false, no settings or ledger are initialized, `implementation_authorized=false`, and the isolated benchmark creates zero files.

v3.2i adds `proto_mind.experience_learning_input`. `ExperienceLearningInputAdapter` resolves only explicit caller-supplied IDs from already-instantiated `MemoryStore` and `SkillLibrary`, filters inactive/archived records, and returns detached snapshots for exact Learning Reviewer duplicate checks. Missing IDs warn; ambiguous IDs, unreadable memory, and malformed skills fail closed. `SkillLibrary.read_snapshot()` is detached and read-only. No relevance search, implicit selection, retrieval trace, usage telemetry, counter/timestamp update, live capture, persistence, command, or mutation exists.

v3.2j adds `proto_mind.experience_consent` as a stateless transition specification, not a runtime consent store. It models preview-before-consent, an exact session-bound phrase, normal-prompt-only scope, command/internal/backfill bypass, explicit stop, fail-closed capture failure, and restart/session expiry. Fourteen refusal fixtures cover broad, cross-session, chained, premature, terminal, unknown, and invalid inputs. Results retain no supplied phrase and can never capture, persist, or authorize implementation; the benchmark creates zero files.

v3.2k adds `proto_mind.experience_privacy` as a pure credential-redaction layer for detached Experience previews. Nine ordered rules cover labeled English/Russian credentials, bearer headers, credential-bearing URIs, private-key blocks, JWTs, and common provider token formats. Redaction happens before truncation, emits stable idempotent placeholders, leaves four benign controls unchanged, and removes observer topic tags derived from matched sensitive segments. `compact_preview` is the shared text integration point, while the existing Experience Doctor now rejects sensitive remnants in preview fields. The 16-case benchmark creates zero files; capture, consent storage, live hooks, persistence, commands, broad PII inference, and Context Injection remain unchanged and disabled.

v3.2l adds `proto_mind.experience_capture_soak` as a synthetic process-memory-only activation-precondition test. It combines the consent state specification, privacy-protected `ExperienceTraceBuilder`, and a detached bounded buffer across 36 bilingual normal turns plus pre-consent, wrong-token, slash/natural/internal/history bypass, stop, failure, and restart cases. Accepted evidence totals 252 events and 140274 canonical JSON bytes under hard 256-event, 512 KiB, and eight-events-per-turn limits. Count, byte, and per-turn overflow are refused without snapshot mutation. No file, runtime consent, live capture, persistence, command, LLM, export, Context Injection change, or domain mutation is introduced.

v3.2m adds `proto_mind.experience_activation_review` as the final read-only pre-pilot decision layer. It aggregates ten existing evidence sources instead of inventing another safety model: design lock, consent, privacy, bounded growth, temporary hash-chain integrity, disabled live gate, absent live paths, disabled Context Injection, preview-only persistence, and absent persistent Experience commands. A clean baseline reports evidence ready while retaining `KEEP_DISABLED` for durable capture; implementation and persistent runtime activation remain false. Requested/malformed capture settings and enabled Context Injection become blockers without automatic repair. The benchmark creates zero files and now distinguishes the available process-memory pilot from forbidden persistence surfaces.

v3.3a adds `proto_mind.experience_pilot` as the first supervised normal-turn bridge. The shared handler exposes preview, exact session consent, status, bounded event listing, provenance inspection, doctor, and terminal stop. Consent state lives only on the current Coordinator object. Successful normal turns are projected through the existing privacy-protected `ExperienceTraceBuilder` into a detached atomic buffer capped at 12 events per turn, 256 total events, and 512 KiB. Slash commands, Natural Router routes, empty input, internal reports, and historical backfill cannot enter the buffer. Active Context Injection, event-build failure, or bounds overflow stops capture fail-closed. No event file, writer, export, apply, promotion, learning mutation, session-log schema change, shell action, or background task exists.

v3.3b adds `proto_mind.experience_turn` as a read-only projection of current-process normal-turn evidence. It validates the existing trace, groups evidence by session/turn, and exposes `/experience episodes` plus `/experience episode [latest|<turn_id>]`. A complete episode connects observation, canonical intent, retrieval, response, memory decision, reflection, grounding, and exact source event IDs; absent required stages remain visibly incomplete. The projection uses no model, creates no summary record, and changes no consent state, process evidence, file, store, or Context Injection setting. Contest Showcase reads only this detached projection to present the latest cognitive path.

v3.3c adds `proto_mind.experience_learning_bridge` as a non-persistent operator-review projection over those episodes. `/experience learning status|preview [latest|<turn_id>]|doctor` extracts only exact compact redacted findings already present in correction, reflection, and grounding events, deduplicates equal text with complete provenance, and caps each turn at eight candidates. Clean turns do not become lessons. Correction evidence is `operator_review_required`, diagnostic-only evidence is `needs_more_evidence`, and incomplete episodes are `blocked`; all candidates deny promotion, automatic apply, and persistence. The bridge performs no model call, semantic inference, queueing, file/store write, consent change, or Context Injection change.

v3.3d adds `proto_mind.experience_learning_decision` as a bounded process-memory authorization boundary over v3.3c candidates. Read-only decision, confirmation-preview, promotion-preview, list, and Doctor views share one immutable candidate digest. The only mutating prefix, `/experience learning decide`, records terminal accept/reject receipts in the current pilot object; acceptance requires complete `operator_review_required` evidence plus an exact candidate-specific SHA-256 token. The 64-receipt cap, restart expiry, redacted rejection reasons, evidence-link/hash Doctor, and `executable=false` dry-run receipt prevent this layer from becoming an apply path. No memory/skill/queue/file/session-log write, model call, promotion, Context Injection change, or external action exists.

v3.4c adds provenance-gated learned-lesson recall to `MemoryKeeper` plus a deterministic restart benchmark. Active `lesson` records must pass the existing embedded provenance verifier before scoring can select them; invalid or missing provenance receives an explicit retrieval-trace filter reason, and inactive verified lessons are excluded from non-historical recall. Grounding evidence identifies supporting lessons with compact verification status and provenance ID. The two-case English/Russian benchmark uses fresh Coordinators and temporary stores and verifies grounded recall, fail-closed rejection, byte stability, unchanged usage telemetry, and zero automatic learning or project-store writes.

v3.4d adds `proto_mind.experience_learning_outcome` as a read-only comparison between one durable learned lesson and later current-process Experience evidence. Exact memory-ID retrieval and valid post-apply lineage are mandatory. Clean grounding, explicit correction, and correction-linked verified replacement records become keep/reject/supersede candidates respectively; absent or insufficient evidence remains inconclusive. The formatter and Doctor sit under the existing read-only `/experience learning` Registry prefix, and the four-case temporary-store benchmark verifies all outcomes plus byte stability without mutation, capture, promotion, model/API access, or Context Injection.

v3.4e adds `proto_mind.experience_learning_lifecycle` as the operator confirmation boundary after outcome review. A deterministic token binds the full compact outcome identity, and the existing registered `/experience learning decide` process-state gate accepts only the exact matching `keep`, `reject`, or `supersede` decision. One terminal receipt per lesson is retained in a 32-item process-memory session, inspected and diagnosed through read-only subcommands, and discarded on restart. The layer has no lesson lifecycle writer, persistence, automatic choice, command execution, or Context Injection path.

v3.4f adds `proto_mind.experience_learning_lifecycle_readiness` as a read-only pre-writer boundary. It revalidates the process receipt against current persistent memory, provenance, exact outcome lineage, store hash, optional replacement lesson, and the existing confirmation-required `/experience learning apply` Registry gate. Any drift fails closed, and readiness itself remains non-executable.

v3.4g adds `proto_mind.experience_learning_lifecycle_apply` as a one-transition supervised writer behind that existing memory gate. A separate exact token binds the current lifecycle receipt, review hash, decision, lesson/replacement IDs, and pre-write store SHA-256. `keep` proves a byte-stable no-op; `reject` and `supersede` atomically update only the old lesson's existing lifecycle fields, preserve its immutable learning provenance, verify exact record scope and replacement stability, and restore the exact original bytes on failure. One hashed detailed receipt lives in process memory; durable `active/superseded_*` state survives restart. Batch apply, automatic decisions, skills/events, shell, arbitrary dispatch, model/API calls, and Context Injection remain outside the path.

v3.4h adds `proto_mind.experience_learning_lifecycle_audit` as a read-only restart boundary over that durable state. It classifies provenance-bearing lessons as active, rejected, superseded, operator-forgotten, inactive-unclassified, or invalid; exposes compact status/history/inspect/Doctor views; and checks provenance, transition shape, timestamps, replacement existence/activity/age, unique IDs, and reference cycles. It reconstructs current record state only and never invents an expired process receipt or append-only history. No repair, reactivation, rollback, write, execution, model/API call, or Context Injection path is introduced.

v3.5a adds `proto_mind.experience_learning_skill_contract` as the first read-only bridge from a verified active lesson to procedural memory design. It produces a deterministic `skill.procedure.contract.v1` draft and a fixed projection into the existing `skill.procedure.v1` storage shape, but leaves trigger, preconditions, steps, permissions, verification, and known failure modes explicitly operator-authored. Source record/provenance hashes, durable lifecycle audit, current Skill Library readability, and exact active-duplicate checks are mandatory. Every draft remains incomplete, non-executable, and non-promotable; no synthesis, confirmation receipt, skill writer, apply command, execution, model/API call, or Context Injection change exists.

v3.5b adds `proto_mind.experience_learning_skill_authoring` as an exact-token process-memory authorization record for the text of that contract, not for persistence or execution. A bounded parser requires all six operator fields, caps item counts and payload size, rejects chaining/unknown/duplicate fields, and binds the full visible contract, source lesson, durable provenance, source record, and base contract hashes. The existing `/experience learning propose` Registry gate records at most one immutable receipt per lesson and 16 per process; restart discards all receipts. Doctor verifies receipt identity, payload/projection hash, exact confirmation evidence, no-writer flags, and current source/duplicate drift. No Registry expansion, Skill Library write, apply readiness, promotion, procedure execution, shell, model/API call, or Context Injection change is introduced.

v3.5c adds `proto_mind.experience_learning_skill_readiness` as the read-only pre-writer boundary. It rebuilds the current v3.5b authoring blueprint, verifies receipt integrity and lifecycle/provenance/source hashes, scans every detached Skill Library record for malformed state, duplicate IDs, deterministic target-ID collision, and active/archived exact field duplicates, then binds the current store SHA-256 and target payload hash. The plan requires one atomic append, a separate confirmation, exact mutation count, post-write record/source verification, a minimum receipt contract, and `/skills archive <created_id>` rollback guidance. The readiness surface itself never invokes the installed writer or emits an apply token.

v3.5d adds `proto_mind.experience_learning_skill_apply` behind the exact Registry prefix `/experience learning apply skill` (`mutates=skills`, `risk=medium`). A second token binds the current authoring receipt, target payload, deterministic target ID, and current Skill Library bytes. One process may append at most one operator-authored `skill.procedure.v1` record through atomic temp-file replacement. Post-write verification requires an exact +1 record delta, logically unchanged prior records, unique IDs, full target equality/hash, unchanged persistent memory, and current source provenance; any failure restores the original bytes. The process receipt is hashed, restart-expiring, non-executable, and includes `/skills archive <created_id>` rollback guidance. `experience_learning_skill_runtime` is the shared capability boundary used by contract, authoring, readiness, and apply diagnostics. No stored procedure execution, batch apply, automatic selection, shell, arbitrary dispatcher, model/API call, or Context Injection change exists.

v3.5e adds `proto_mind.skill_provenance`. Each new v3.5d record embeds one `skill.procedure.provenance.v1` envelope with source lesson/provenance hashes, base and authored contract material, the fixed storage projection, both confirmation-token fingerprints, deterministic IDs, and explicit non-execution flags. `/skills why <id>` revalidates that chain after restart and distinguishes verified, historical-source, current-payload drift, unavailable legacy/operator, and invalid states. `/skills provenance-doctor` audits the complete Skill Library without initializing or rewriting missing stores. Skill archive/restore lifecycle does not invalidate the confirmed original payload; name/summary/body/category/tag edits are visible as drift. Hashes are deterministic tamper evidence, not signatures or protection from a malicious local editor. No skill runner, second writer, migration, repair, or automatic apply exists.

v3.5f adds `proto_mind.experience_learning_skill_outcome` as a read-only review boundary after manual procedural-skill use. An eligible anchor must be an exact current-process `tool_called` event bound to `skill:<skill_id>`, the current verified `skill.procedure.provenance.v1` ID, `manual_operator_use=true`, and `execution_performed_by_proto_mind=false`. Exact linked, operator-reported verified success, failure, or correction events become advisory success/failure signals; mixed, weak, or missing evidence remains inconclusive. Historical source lessons remain reviewable only when the current skill payload still matches its confirmed provenance. `uses` and `last_used_at` are telemetry and never outcome evidence. The reviewer and Doctor write no events or stores, execute no procedures, update no scores, and expose no capture, model/API, shell, automatic selection, or Context Injection path.

v3.5g adds `proto_mind.experience_learning_skill_outcome_capture` as the separately confirmed evidence source for v3.5f. A read-only preview binds the exact current pilot session, active skill ID, verified durable provenance and confirmed payload hashes, success/failure label, and deterministically redacted evidence preview. The mutating `session` gate requires both active exact-session Experience consent and an exact blueprint token, then atomically admits one fixed four-event batch into the existing 256-event/512-KiB process-memory buffer. Each batch states `manual_operator_use=true` and `execution_performed_by_proto_mind=false`; receipts are capped at 16, restart-expiring, hash-inspectable, and exact-blueprint run-once. List/inspect/Doctor views do not write. No skill invocation, persistent Experience writer, Skill Library/memory/session-log mutation, score/usage update, batch capture, model/API call, shell, external action, or Context Injection change exists.

v3.5h adds `proto_mind.experience_learning_skill_outcome_decision` as the operator-choice boundary after review and capture. A confirmable blueprint requires current verified skill provenance/payload, a decisive v3.5f status, and complete signal coverage by hash-valid, exact-confirmation v3.5g receipts. The deterministic allowlist maps success to `keep` and failure/mixed evidence to operator-selected `revise` or `archive`; insufficient evidence and unconfirmed fixtures fail closed. A second exact token records at most one terminal receipt per skill and 16 per process. Receipt hashes bind review, capture IDs/hashes, signal IDs, provenance, and decision; Doctor marks later evidence changes historical. No readiness, apply token, keep no-op, archive, revision, scoring, execution, persistent writer, or Context Injection path exists.

v3.5i adds `proto_mind.experience_learning_skill_lifecycle_readiness` as a read-only boundary after that decision. It rebuilds the exact decision from current evidence and confirmed captures, verifies the terminal receipt hash and safety flags, requires the current active non-executable skill plus its unchanged durable provenance/payload, and binds the report to both the complete skill-record hash and Skill Library SHA-256. The future contract is decision-specific: keep permits no record mutation, archive permits exactly one atomic status transition with restore guidance, and revise forbids direct apply until a separately confirmed versioned replacement exists. Readiness never invokes the separately registered writer, and every report keeps `future_apply_ready=false`, `apply_token_generated=false`, and `executable=false`.

v3.5j adds `proto_mind.experience_learning_skill_lifecycle_apply` as a separate run-once mutation boundary. Preview repeats v3.5i revalidation and binds a second token to the terminal decision, decision hash, exact current record hash, store SHA-256, and expected mutation count. Keep performs and proves a byte-stable no-op; archive uses atomic JSONL replacement, permits only one changed record and the fields `status` plus `updated_at`, verifies unchanged embedded provenance and persistent memory, and rolls back exact bytes on any post-write failure. A hashed process receipt records before/after hashes, state, mutation count, confirmation fingerprint, rollback guidance, and non-execution evidence. Revise is refused until a separate versioned replacement contract exists; one process slot, no generic dispatch, and `PROCEDURAL_SKILL_EXECUTION_INSTALLED=false` remain hard gates.

v3.5k adds `proto_mind.skill_lifecycle_audit` as a read-only restart boundary over current Skill Library records and durable lesson provenance. It classifies active verified/historical, archived ambiguous, drifted, legacy/unprovenanced, and invalid records; exposes `/skills lifecycle-status|lifecycle-history [--all]|lifecycle-inspect <id>|lifecycle-doctor`; and refuses to treat process-memory receipts or unsupported record fields as durable transition evidence. In particular, archive status is observable after restart but an outcome-driven archive cause is not proven by the v3.5j storage shape. The layer performs no write, repair, migration, reactivation, execution, model/API call, or Context Injection change.

v3.5l adds `proto_mind.skill_lifecycle_metadata` as a pure design contract, not a persistence path. The `skill.procedure.lifecycle.v1` envelope has one exact archive transition, canonical identity and metadata SHA-256, bounded compact evidence identifiers/hashes, operator-confirmation fingerprint, and explicit no-replay/no-automatic/no-execution fields. `/skills lifecycle-status --contract` reuses the existing Registry prefix, while lifecycle Doctor runs a deterministic example plus tamper refusal. The live audit deliberately rejects even a hash-valid future envelope while `PROCEDURAL_SKILL_LIFECYCLE_METADATA_WRITER_INSTALLED=false`; no current record is migrated or trusted retroactively.

v3.5m adds `proto_mind.experience_learning_skill_lifecycle_metadata_readiness` behind optional `--durable` on the existing v3.5i readiness/plan prefixes. It reuses current decision/evidence/provenance/store revalidation, then binds a deterministic fixed-field blueprint while leaving ID, transition time, confirmation hash, and final metadata hash explicitly write-time-only. Archive design readiness requires one record mutation over exactly `lifecycle/status/updated_at`, a 21-field receipt, and exact rollback; keep remains byte-stable with no envelope and revise remains outside the contract. The current v3.5j writer remains explicitly non-compatible.

v3.5n adds `proto_mind.experience_learning_skill_lifecycle_metadata_apply` behind the same lifecycle apply prefixes plus mandatory `--durable`. One exact current archive decision may consume the single process slot and atomically persist the self-validating `skill.procedure.lifecycle.v1` envelope while changing only `lifecycle/status/updated_at`. Post-write verification proves one-record scope, immutable skill provenance, unchanged persistent memory, exact receipt hashes, and restart-safe `archived_verified` reconstruction; any failure restores exact prior bytes. Legacy archive without `--durable` fails closed, and there is no migration, durable restore/revise writer, procedure execution, generic dispatcher, batch, model/API call, or Context Injection change.

v3.5o adds `proto_mind.skill_lifecycle_restore` as a pure/read-only restore contract and current-state reviewer. It accepts only `archived_verified` records with current provenance, exact archive-envelope binding, non-executable payload, unique IDs, available store/record hashes, and no active duplicate. The detached `skill.procedure.lifecycle.restore.v1` shape embeds the complete prior archive envelope, binds the current review/record hashes, and constrains a future writer to one record and exactly `lifecycle/status/updated_at`, post-write verification, unchanged memory/provenance, a fixed receipt, and exact-byte rollback. Existing lifecycle status/inspect/Doctor prefixes expose the design through flags without Registry expansion. No token, writer, authorization, migration, mutation, or procedure execution exists.

v3.5p hardens the existing `SkillLibrary.set_status` mutation boundary. Generic archive/restore remains available for operator and legacy provenanced records with no lifecycle field, but any lifecycle-managed or lifecycle-corrupt record fails closed before callback, timestamp, or file write. The refusal identifies current/requested status and routes the operator to lifecycle inspect or restore readiness. Restore Contract/Doctor expose the installed guard, while Registry and Policy retain the existing confirmation-required `mutates=skills` classification. No new command, writer, migration, repair, or execution path is added.

v3.5q extends that low-level boundary to payload and usage telemetry. All summary/body/tag helpers converge on one pre-callback lifecycle check, while `use_skill` performs the same check before incrementing `uses`, `last_used_at`, or `updated_at`. Presence of a lifecycle key is sufficient to fail closed, so malformed or unsupported envelopes cannot bypass the protection. Legacy provenance and ordinary operator records without lifecycle metadata retain existing behavior. Restore Contract/Doctor expose both guards; command prefixes, policy metadata, restore authorization, and execution powers remain unchanged.

v3.5r adds `proto_mind.skill_lifecycle_restore_authorization` as a read-only layer over v3.5o rather than a second store reader. A deterministic 30-field blueprint binds the current skill/store hashes, restore review and metadata blueprint, verified prior archive identity, immutable current fields, exact confirmation vocabulary, future run-once scope, fixed three-field mutation, 21-field receipt, unchanged memory, post-write verification, and exact-byte rollback. Existing lifecycle Registry prefixes expose contract/readiness/plan/Doctor flags. The module deliberately installs no token generator, authorization engine, run-once state, writer, or restore authority.

v3.5s adds `proto_mind.skill_lifecycle_restore_apply` as the only durable restore mutation gate. It reuses v3.5o/v3.5r reviews, generates one exact current-state token, and permits at most one successful restore per process. One atomic JSONL replacement changes only `lifecycle/status/updated_at`; verification requires the full embedded archive envelope, unchanged procedure/provenance and persistent memory, a fixed hashed receipt, and restart reconstruction as `active_restored_verified`. Any wrong/stale/repeated/chained request fails before mutation; any post-write failure restores exact original bytes. The existing `/skills restore` Registry prefix stays medium-risk and confirmation-required, while generic lifecycle status/payload/use routes remain fail-closed. No procedure execution, batch, revision, shell, model/API, external action, Context Injection, queue, export, or session-log behavior is added.

v3.5t adds `proto_mind.skill_lifecycle_restore_receipt_audit` as a pure/read-only cross-process evidence layer. It verifies the embedded restore and prior-archive envelopes, current lifecycle/provenance state, and a deterministic `skill.procedure.lifecycle.restore.receipt.evidence.v1` artifact. Only ten receipt fields preserved by the envelope/current record are reconstructed; process-only IDs, store hashes, mutation checks, success flags, rollback state, and original receipt hash remain unavailable rather than invented. Current process receipts can be compared for an exact match, while legacy, orphan, duplicate, and mismatched receipts are diagnosed. Existing lifecycle prefixes expose contract/history/audit/copyable-JSON/Doctor views without Registry growth, a file writer, store mutation, procedure execution, or Context Injection change.

v3.5u adds `proto_mind.experience_learning_skill_restore_reevaluation` as a read-only temporal and evidence-binding gate above ordinary outcome review. It accepts only current `active_restored_verified` skills and manual-use anchors strictly newer than `lifecycle.transitioned_at`, with exact current provenance, restore metadata id/hash, and v3.5t evidence hash. Pre-restore evidence and later but unbound events are counted and excluded. The legacy capture and outcome-decision builders now refuse restored skills until a separately reviewed restore-bound capture contract exists. Exact new outcomes remain advisory and never become decision/apply ready; no writer, token, event append, procedure execution, or Context Injection change is added.

v3.5v adds `proto_mind.experience_learning_skill_restore_capture_readiness` as the next read-only gate. It constructs a canonical future capture blueprint only from active consent and the exact current `active_restored_verified` record, binding Skill Library/record/provenance/payload hashes, restore metadata and reconstructed evidence, outcome/evidence fingerprint, exact four-event sequence, restore-bound call fields, and future receipt fields. Blueprint and current-state verification reject tamper or drift. Existing capture-preview/Doctor prefixes expose the contract without Registry expansion, while token generation, writer installation, Experience append, receipts, lifecycle decisions, procedure execution, and persistent mutation remain unavailable.

Build Week Provenance Pack v1 adds a reproducible source-level baseline comparison against `proto_mind_backup_2026-07-11_05-02-19.tar.gz`. `BUILD_WEEK_PROVENANCE.md` and `CODEX_COLLABORATION.md` distinguish pre-existing foundation from contest work, while three generated JSON manifests preserve SHA-256 evidence and objective deltas. The tool explicitly excludes private/runtime paths, records the real operator-supplied `/feedback` Session ID, and never fabricates missing evidence. Git history created after this milestone is future evidence only and is never backdated. `REPOSITORY_PRIVACY_REVIEW.md` defines the public boundary, documents resolved absolute-path leaks, and identifies synthetic credential fixtures without changing runtime data.

Contest Showcase v1 adds `proto_mind.showcase_layer` as a presentation-only composition layer. It reads the existing Operator Memory Card, Operating Loop snapshot, optional current-process Experience pilot, Registry, Policy, and fixed runner configuration into four sections: continuity, explainable experience, governance, and bounded action. Status, demo, script, and doctor are all read-only/mutates=none; no helper initializes pilot state, calls a model, invokes a capability, records runner evidence, writes an export, or changes a domain store. Redaction-aware truncation preserves complete placeholders at the 160-character boundary. `CONTEST_SHOWCASE.md` supplies the three-minute narrative and recovery checklist for the July 21 submission target.

Normal turn lifecycle:

1. User input enters the CLI or FastAPI `/api/turn`.
2. `Observer.analyze()` classifies the input, estimates importance, extracts tags, and decides whether memory retrieval is needed.
3. If memory is needed, `MemoryKeeper.retrieve()` loads working and persistent memory, scores candidates, deduplicates exact normalized-content duplicates, and builds a retrieval trace without mutating memory by default.
4. The coordinator passes user input, selected memory, observer state, and any previous correction hints into the selected reasoner backend.
5. The reasoner generates a response.
6. `MemoryKeeper.evaluate_interaction()` decides whether the turn produced durable memory.
7. `MemoryKeeper.apply_memory_updates()` stores/promotes new memory, supersedes conflicting prior decisions, promotes reused memories when eligible, and decays stale working memories.
8. The coordinator loads updated working/persistent memory snapshots.
9. `SelfReflector.reflect()` evaluates whether the response aligned with selected memories, active decisions, superseded history, active preferences, and supported memory facts.
10. `GroundingAuditor.audit()` checks whether the response is justified by selected memory and current memory state for memory-sensitive turns.
11. Self-Reflection v2 generates correction hints if warnings were detected.
12. The coordinator stores correction hints only in process memory for the next turn.
13. If session logging is enabled, the coordinator appends a compact JSONL turn record for normal turns.
14. CLI/API returns the response plus pipeline artifacts.

Previous correction hints enter at step 4. They are consumed by the next reasoner call as internal guidance, then cleared or replaced based on that turn's new reflection result.

Slash commands such as memory inspection, backup, cleanup preview/apply, repair preview/apply, and session log inspection are handled outside the normal cognitive turn path. They do not become session log cognitive turns and do not create ordinary memory records.

## Memory Model

Proto-Mind currently implements two JSON-backed memory layers.

Working memory:

- Recent context.
- Active but potentially temporary records.
- Subject to decay and duplicate cleanup.
- Can be promoted into persistent memory.

Persistent memory:

- Durable decisions, preferences, project facts, and insights.
- Used for continuity across interactions and process restarts.
- Still stored in JSON files in the current implementation.

Memory record fields include:

- `id`
- `content`
- `type`
- `importance`
- `source`
- `timestamp`
- `tags`
- `last_used`
- `usage_count`
- `weight`
- `active`
- `superseded_by`
- `superseded_at`
- `superseded_reason`
- Optional Memory v2.0 explicit-control metadata: `confidence` and `updated_at`.

Memory v2.0 Explicit Memory Control adds operator-created `type="explicit"` records in persistent memory. These records use the existing JSON-backed `MemoryRecord` list for compatibility, with `source="operator"`, `confidence=1.0`, stable human-readable `mem_YYYYMMDD_HHMMSS_ab12` ids, and derived status: active records are current, inactive explicit records are treated as forgotten. `/memory forget` is a soft-delete by default: it marks the record inactive, updates `updated_at`, and preserves the text for auditability.

Memory v2.1 adds `/memory doctor`, a read-only deterministic diagnostic report for persistent memory health. It checks file/load status, raw record shape, explicit active/forgotten counts, exact active duplicates, possible near-duplicates, long or low-information explicit memories, high forgotten-memory counts, invalid confidence values, unknown types, and conservative possible conflicts such as "likes X" versus "does not like X". It does not auto-fix, consolidate, delete, embed, or call an LLM.

Goal Stack v1.0 adds operator-managed local goals in `proto_mind/data/goals.jsonl`. Goal records use stable `goal_YYYYMMDDHHMMSS_ab12` ids, `active|paused|completed|cancelled` status, `high|normal|low` priority, operator source, and a single `focus=true` goal at a time. `/goals pause`, `/goals complete`, and `/goals cancel` clear focus; `/goals focus` only accepts active goals. This layer is deterministic storage/control only: no LLM planning, auto-goal generation, or task queue yet.

Task Queue v1.0 adds operator-managed local tasks in `proto_mind/data/tasks.jsonl`. Task records use stable `task_YYYYMMDDHHMMSS_ab12` ids, `open|in_progress|blocked|done|cancelled` status, `high|normal|low` priority, optional `goal_id`, result text, and blocked reason. `/tasks next` prefers in-progress tasks first, then open tasks by high/normal/low priority and creation time. Goal integration is task-side only: tasks can store a validated `goal_id` and `/tasks list --goal <goal_id>` filters by that link. There is no LLM planning, auto-task generation, shell execution, or autonomous action execution.

Experiment Journal v1.0 adds operator-managed local experiments in `proto_mind/data/experiments.jsonl`. Experiment records use stable `exp_YYYYMMDDHHMMSS_ab12` ids, `open|running|completed|inconclusive|cancelled` status, hypothesis, prediction, method, result, reflection, lesson, optional `goal_id`, and optional `task_id`. The command layer supports the deterministic cycle `hypothesis/prediction -> method/run/result -> reflection/lesson`, with list filters by goal or task. Completing a linked experiment only suggests the related `/tasks done` command; it does not mutate the task queue automatically. There is no LLM scientific reasoning, auto-experiment generation, shell execution, or autonomous action execution.

Skill Library v1.0 adds deterministic procedural memory in `proto_mind/data/skills.jsonl`. Skill records use stable `skill_YYYYMMDDHHMMSS_ab12` ids, active/archived status, category, summary, body/checklist, tags, usage count, and `last_used_at`. `/skills search` performs case-insensitive substring search over id, name, summary, body, category, and tags. `/skills use <id>` retrieves the body/checklist and marks the skill as used, but does not execute anything. There is no autonomous skill execution, shell execution, LLM skill synthesis, or auto-skill extraction.

World Model Lite v1.0 adds deterministic prediction-vs-reality records in `proto_mind/data/world_model.jsonl`. Records use stable `wm_YYYYMMDDHHMMSS_ab12` ids, `open|observed|scored|archived` status, situation, prediction, expected signal, actual outcome, 0..5 score, lesson, confidence, and optional goal/task/experiment links. `/world score` requires an observed outcome first; `/world stats` summarizes average score, score counts, high-confidence wrong predictions, low-confidence correct predictions, and tags. This is not a neural world model: there is no LLM prediction generation, automatic scoring, shell execution, or autonomous action.

Identity / Values v1.0 adds an inspectable local identity profile in `proto_mind/data/identity.json`. The profile stores system name, role, style, operator name, mission, active/archived values, principles, safety boundaries, and change history. `/identity doctor` performs deterministic read-only diagnostics for missing fields, duplicate active items, empty texts, absent active values/boundaries, missing history, and malformed JSON. The layer is not injected into the reasoning pipeline yet and does not enforce autonomous policy; it is operator-visible state for future context/loop integration.

Context Pack v1.0 adds read-only deterministic context assembly in `proto_mind/context_pack.py`. `/context build` gathers compact identity, focused goal, next task, open tasks, open experiments, open/observed world predictions, active explicit memory previews, recent reflections, useful skills, and operating-loop summary without injecting anything into the reasoning prompt. `/context export` writes Markdown and JSON artifacts under `proto_mind/exports/context_packs/`; `/context doctor` checks missing identity/focus/next task/reflections/memory/skills and incomplete experiment/world records. There is no LLM summarization, embeddings retrieval, prompt mutation, or auto-memory consolidation.

Context Prompt Preview v1.1 extends the same module with `/context prompt-preview`, `/context prompt-export`, and `/context prompt-doctor`. It renders a compact prompt-ready text block with identity, values/boundaries, current focus, active work, memory, reflections, skills, operating suggestions, and a safety footer that states the context is informational state rather than an instruction override. Prompt exports are plain text under `proto_mind/exports/context_prompts/`. This remains manual/inspectable only: no automatic prompt injection or reasoning pipeline changes.

Context Injection v1.2 adds a manual preview-safe bridge from context previews to normal LLM turns. Settings live in `proto_mind/data/context_injection.json`, default to `enabled=false`, and can be controlled with `/context injection status|enable|disable|preview|doctor|set-max`. When enabled, only normal prompts are wrapped with the operator-approved context preview before reaching the reasoner; slash commands and natural routed operator commands bypass injection. Observer analysis, memory evaluation, and session-log `user_input` continue to use the original user text. This is not autonomous prompt mutation, planning, policy enforcement, or automatic memory writing.

Context Injection Audit v1.2.1 adds a compact local flight recorder at `proto_mind/data/context_injection_audit.jsonl`. `/context injection audit`, `/context injection last`, and `/context injection audit-status` show enable/disable/set-max/preview/doctor events, injected normal prompt events, and skipped slash/natural routed events. Audit records store short original-input previews and injected context character counts, not full injected prompts by default, and audit write failures do not change reasoning behavior.

Operating Loop v1.1 adds read-only daily workflow reports on top of the existing loop snapshot. `/loop morning-plan` summarizes identity, focused goal, next task, top open tasks, open experiments, open world predictions, recent reflections, and suggested first action. `/loop evening-review` summarizes recent completed tasks, completed/inconclusive experiments, scored world predictions, latest reflection, loop-doctor warnings, and review commands. `/loop capture-today` outputs a checklist for preserving the day through explicit operator commands; it does not mutate goals, tasks, experiments, world records, memory, skills, or reflections.

Memory Consolidation Preview v1.3.1 adds `proto_mind/consolidation.py` and `/consolidation status|preview|export|export-status|doctor` plus a safe queue in `proto_mind/data/consolidation_queue.jsonl`. It scans recent reflections, completed task results, experiment lessons, scored world lessons, active skills, and active explicit memories to suggest manual `/memory remember`, `/skills add`, `/skills body`, and missing follow-up commands. `/consolidation export` writes Markdown and JSON reports under `proto_mind/exports/consolidation/`. Queue commands store pending/approved/rejected/archived/applied candidates and export the queue under `proto_mind/exports/consolidation_queue/`; approval prints the suggested command but never executes it. v1.3 adds explicit `/consolidation queue-apply-preview <id>` and approved-only `/consolidation queue-apply <id>` for a tiny internal allowlist: `/memory remember`, `/skills add`, and `/skills body`. v1.3.1 stores structured apply receipts with applied command/kind/record id and undo suggestion, exposed by `/consolidation queue-apply-receipt <id>` and `/consolidation queue-undo-preview <id>`. It rejects arbitrary slash commands, shell commands, and command chains, and it never performs automatic undo.

Data Integrity Doctor v1.1 adds `proto_mind/data_integrity.py` and top-level `/data status`, `/data inventory`, `/data doctor`, `/data refs`, and `/data refs-doctor` commands. It inventories local JSON/JSONL stores across memory, reflection journal, goals, tasks, experiments, skills, world model, identity, context injection settings/audit, consolidation queue, action proposal queue, and session operator log, plus export directories and backups. Cross-store validation checks task-to-goal, experiment-to-goal/task, world-to-goal/task/experiment, focus state, active tasks under terminal goals, and applied consolidation receipt-to-memory/skill references including detectable undo targets. It is fully read-only and performs no repair or rewrite.

Common memory types:

- `decision`
- `preference`
- `project`
- `insight`

Active vs superseded:

- Active records represent current memory state.
- Superseded records remain available as historical context.
- Decision overrides can mark older active decisions inactive and set `superseded_by` to the newer decision id.
- Historical queries can still retrieve superseded decisions when the query is historical.

Promotion and durability:

- Decisions and preferences are promoted to persistent memory when stored.
- Reused active memories can also be promoted.
- Working duplicates can remain until hygiene cleanup is applied.

Cleanup and hygiene:

- Duplicate cleanup is exact normalized-content cleanup only.
- Preview is available before mutation.
- Cleanup prefers persistent over working, active over inactive, higher importance, higher usage count, and promoted durable records.
- Cleanup preserves unique superseded history.
- Cleanup can repair `superseded_by` references when it removes a duplicate target and keeps an equivalent replacement.

Orphan reference repair:

- Detects records whose `superseded_by` points to a missing id.
- Preview reports missing id, candidate target, confidence, and reason.
- Apply only repairs safe cases where exactly one active decision shares specific storage-domain topics.
- It preserves content, `superseded_at`, and `superseded_reason`.

Important storage nuance:

- Current implemented storage is JSON-backed via `working_memory.json` and `persistent_memory.json`.
- The active architectural memory may say Proto-Mind should migrate toward SQLite instead of JSON.
- That is an intended architecture direction, not the current implemented storage backend.

## Retrieval System

Observer/query classification:

- The observer classifies user input and controls whether retrieval happens.
- Memory inventory and continuity queries force retrieval.
- Preference declarations usually do not retrieve memory.
- Preference-behavior questions such as "How should you explain Proto-Mind later?" retrieve preference memory.

Topic normalization:

- `topic_utils.py` maps phrases and tokens into canonical tags.
- Examples:
  - `json-backed memory` -> `json`, `storage`, `persistence`, `memory`
  - `memory backend` -> `storage`, `backend`, `memory`
  - `before sqlite` -> `historical`, `sqlite`, `storage`
  - `how should you explain` -> `future_behavior`, `explanation`, `response_style`

Specific vs generic tags:

- Generic tags such as `decision`, `memory`, `project`, and `proto-mind` receive low weight.
- Specific tags such as `storage`, `backend`, `persistence`, `sqlite`, `json`, `response_style`, and `architecture` carry more retrieval weight.
- This reduces false matches from shallow category overlap.

Scoring inputs:

- Weighted topical overlap.
- Record importance and weight.
- Recency.
- Usage count.
- Active/current or superseded/historical state alignment.
- Preference priority contribution for response-style, future-behavior, and preference recall queries.

Current vs historical behavior:

- Current-oriented queries prefer active decisions and penalize superseded records.
- Historical queries can boost superseded decisions.
- Inventory queries use broader retrieval but still prefer active state unless historical intent is present.

Retrieval trace:

- Each candidate has trace fields such as stored tags, normalized topics, matched topics, topical contribution, importance contribution, recency contribution, usage contribution, state bias contribution, final score, selected status, and filtered reason.

Candidate explanations:

- Human-readable summaries explain why a memory won or lost.
- Examples:
  - Matched specific storage topics.
  - Benefited from active current-decision bias.
  - Penalized because the query was current-oriented and the memory is superseded.
  - Deduped by a stronger identical memory.
  - Won because this is an active direct preference matching a response-style query.

Preference Priority Cleanup v1:

- Direct active `preference` memories outrank derived `project` summaries for response-style and future-behavior queries.
- Project memories can still appear when specifically relevant, but below direct active preferences.
- Preference recall questions such as "What do I prefer about explanations?" retrieve memory but are not stored as new preferences.
- Preference-style retrieval questions are not stored as derived project summaries.

## Self-Reflection System

Self-Reflection v1:

- Runs after response generation and memory updates.
- Checks whether the response used selected memories correctly.
- Warns if the response appears to contradict active decisions.
- Warns if the response treats superseded memory as current.
- Checks whether concise/short active preferences were respected.
- Warns when selected important memory appears ignored.
- Warns when memory claims are made without selected memory support.

Self-Reflection v2:

- Converts warnings into compact correction hints.
- Adds fields:
  - `correction_hints`
  - `should_carry_forward`
  - `carry_forward_scope`
- Hints are deterministic and rule-based.
- Hints are not stored in JSON memory.
- Hints are not used to rewrite the current response.

Correction hint examples:

- `Use the active decision as current state: <active decision preview>`
- `Treat superseded memory as historical only: <superseded memory preview>`
- `Respect active preference next turn: <preference preview>`
- `Avoid claiming remembered facts unless supported by selected or stored memory.`
- `Ground the next related answer in selected memory: <memory preview>`

Carry-forward behavior:

- The coordinator stores correction hints in `pending_correction_hints`.
- Hints are passed to the next reasoner call only.
- After the next turn, hints are replaced by that turn's new hints or cleared if no hint is generated.
- This is session-local and disappears when the process exits.

Limitations:

- Reflection is heuristic.
- It can detect obvious contradictions like treating JSON as current when SQLite is active.
- It does not prove arbitrary response truthfulness.
- It does not perform deep semantic entailment.
- It does not call a second LLM.

## Grounding Auditor System

Grounding Auditor v1 is a stricter memory-grounding inspection layer. Self-Reflection asks whether the answer is broadly aligned with memory and preferences; Grounding Auditor asks whether the answer can be justified by selected memory and current memory state.

Grounding audit fields include:

- `grounding_needed`
- `grounding_status`
- `memory_support`
- `active_decision_status`
- `superseded_memory_status`
- `unsupported_claims`
- `warnings`
- `evidence`
- `confidence`

Grounding is needed for memory-sensitive turns, including memory inventory, continuity, project/meta architecture turns, explicit memory-required observer states, and responses that make memory/project/state claims.

Grounding Auditor v1 checks:

- Whether selected memory was used when grounding was needed.
- Whether the response contradicts active decisions.
- Whether superseded decisions are presented as current.
- Whether memory/project claims are made without selected or stored support.
- Whether current-state answers prefer active memory.
- Whether historical answers preserve the old/current distinction.

It distinguishes current implementation claims from current architectural decision claims. Saying the current implementation is JSON-backed can be valid if supported, while saying the current architectural decision is JSON should be flagged when an active SQLite decision exists.

## Reasoner Backends

Mock reasoner:

- Backend name: `mock`.
- Used by default unless config selects Ollama.
- Deterministic and test-friendly.
- Receives selected memory and correction hints.
- Does not echo correction hints directly into the response.

Ollama reasoner:

- Backend name: `ollama`.
- Configured through `PROTO_MIND_REASONER=ollama`.
- Default model target is `qwen3:8b`.
- Default URL is `http://localhost:11434`.
- Builds a system prompt with:
  - Observer interpretation.
  - Continuity priority.
  - Retrieved memory selected by MemoryKeeper.
  - Previous self-reflection correction hints.
- Falls back to mock reasoning if Ollama is unavailable, returns an empty response, or raises a network/JSON error.

## CLI Commands

Backup/checkpoint:

- `/memory backup`
- `/system checkpoint`

Read-only memory inspection:

- `/memory status`
- `/memory list`
- `/memory list --all`
- `/memory inspect <id>`
- `/memory search <query>`
- `/memory search <query> --all`
- `/memory doctor`
- `/memory active`
- `/memory decisions`
- `/memory preferences`
- `/memory history`
- `/memory working`
- `/memory persistent`
- `/memory summary`

Explicit memory mutation:

- `/memory remember <text>`
- `/memory forget <id>`

Explicit memory search is deterministic case-insensitive substring matching over explicit memory text, ids, and tags. It does not use embeddings, LLM consolidation, or vector storage.

Memory hygiene:

- `/memory hygiene`
- `/memory hygiene-preview`
- `/memory cleanup-preview`
- `/memory cleanup-apply`

Reference repair:

- `/memory repair-preview`
- `/memory references-preview`
- `/memory repair-apply`

Session operator log:

- `exit`
- `quit`
- `q`
- `/exit`
- `/quit`
- `/q`
- `/session log status`
- `/session log path`
- `/session log tail`
- `/session log tail N`
- `/session log inspect`
- `/session log inspect N`
- `/session log warnings`
- `/session log warnings N`
- `/session log search <text>`
- `/session log search <text> --limit N`
- `/session log export`
- `/session log export --last N`
- `/session log export --format md|json`
- `/session review`
- `/session review --last N`
- `/session health`
- `/session health --last N`
- `/session doctor`
- `/session doctor --last N`
- `/session self-check`
- `/session self-check --last N`

`/session log inspect N` means inspect the last `N` entries in detailed format, not inspect absolute turn number `N`.

`/session log warnings N` scans the existing JSONL log and shows up to `N` recent entries with self-reflection warnings, correction hints, grounding warnings, non-grounded audit status, active decision contradictions, or superseded memory treated as current.

`/session log search <text>` performs a read-only case-insensitive text scan across compact JSONL session log entries. It is useful for finding turns by topic, warning text, grounding status, correction hint, memory id, or response preview.

`/session log export` writes recent session log entries to `exports/session_log_export_*.md` by default. It exports the last 20 entries in chronological order, supports `--last N`, and can optionally write JSON with `--format json`.

`/session review` prints a deterministic read-only operator summary over recent session log entries. It summarizes type counts, grounding/reflection status, malformed entries, retrieval id usage, reasoners, top observer tags, recent inputs, and warning-like issues.

`/session health` prints a deterministic read-only health check for the session/operator subsystem. It checks log readability, malformed entries, warning counts, grounding issue counts, and whether export/backup directories exist.

`/session doctor` prints a deterministic read-only diagnostic report over recent session log entries. It turns health/review signals into actionable findings and command recommendations for debugging reflection, grounding, retrieval gaps, or log integrity.

`/session self-check` prints a deterministic read-only combined health and doctor summary. It is intended as a one-command operator self-diagnostic and future routing target for natural-language "check your system" requests.

Natural Command Router v2.3 maps a conservative allowlist of exact normalized Russian and English phrases to existing safe operator commands. It covers system-health bundles, `/loop next`, morning/evening reports, explicit context injection enable/disable, consolidation preview, and data inventory. `/natural explain <phrase>` now joins every matched target with Command Registry metadata and Action Safety Policy classification; bundles expose their strictest policy, `/natural list` adds compact policy labels, and `/natural doctor` validates registry/policy coverage and independent doctor health. `/natural suggest <phrase>` remains non-executing. Policy-aware introspection does not enforce confirmation or alter exact route execution; there is no fuzzy auto-routing, LLM intent classification, arbitrary command dispatch, or autonomous planning.

Command Registry v1.0 adds `proto_mind/command_registry.py` and read-only `/commands status`, `/commands list`, `/commands explain <slash command>`, and `/commands doctor`. The static registry currently describes 387 command prefixes across 41 categories. Metadata includes description, read-only state, mutation target, risk, Natural Router availability, and notes. Doctor checks duplicates, invalid metadata, complete Natural Router target coverage, explicit context mutations, and high-risk route exclusion. Registry introspection never executes commands and is descriptive metadata rather than runtime authorization.

Local Capability Contract v1 adds `proto_mind/capability_contracts.py` as a transport-free adapter over the existing Registry, Action Policy, and fixed runner allowlist. Exactly `/warnings unknown`, `/daily doctor`, `/exports doctor`, and `/capabilities safety` receive unique zero-argument contracts with deterministic input/output schemas and conservative MCP-style annotations. The local result envelope separates compact `structuredContent`, operator-facing `content`, and private `_meta`; the adapter only shapes supplied output and never dispatches a command. Capability status/map/safety reports expose the contracts, while Capability Doctor rejects allowlist, Registry, Policy, schema, annotation, or local-only boundary drift. Transport is `none`: no MCP server, network listener, external host, OAuth, widget, dependency, or fifth runner target is introduced.

Local Typed ViewModel v1 adds `proto_mind/desktop_view_model.py` as a pure presentation adapter over those contracts. It projects only exact normalized allowlisted commands, validates all three result channels plus the local-only/no-network/no-store-write boundary, and renders fully escaped PySide cards carrying the original report. The worker result already includes the original input, so `pyside_app` can select the typed view after the shared handler returns without changing routing or execution. Missing, malformed, aliased, suffixed, or unsafe inputs fail closed to the existing text renderer. The module performs no dispatch, I/O, persistence, network access, context toggle, or runner expansion.

Local Cognitive Turn Envelope v3.6a adds `proto_mind/cognitive_turn_envelope.py`, a pure explicit-field projection over the existing `InteractionResult`, separate from operator capability contracts. Frozen nested models expose the original answer, Observer state, retrieved record IDs/types/sources/active flags and 240-character previews, retrieval mode, memory-decision record IDs and rationales, grounding/self-reflection findings, prior correction hints, and compact injection state. Schema `proto_mind.cognitive_turn.v1` marks its scope as `retrieved_for_reasoner_not_proof_of_use`. Missing audits stay `null`; full working/persistent snapshots, raw user/reasoner inputs, provenance blobs, and context packs are not copied. The full answer is intentionally preserved and is not a redacted publication payload.

The existing `main.process_interactive_input` remains the text API; the additive `process_interactive_input_with_envelope` and `DesktopRuntime.process_with_envelope` are alternative single-call entrypoints. Both use the same private dispatch path, one Coordinator turn, one existing session-log append, and one consented Experience observation when enabled. Projection happens only after that result and its unchanged formatted text exist. No normal-turn effects are repeated by projection or serialization, and a presentation failure returns the original text plus a generic envelope warning without retrying the turn. Coordinator, memory keeper, reasoner, session-log schema, injection settings/behavior, and Experience capture logic are unmodified. Existing slash/natural-command early returns, exit handling, CLI/tkinter text paths, and four-command runner scope remain intact.

Cognitive Turn Card v3.6b adds `proto_mind/cognitive_turn_view_model.py` and a PySide renderer over the completed envelope. The worker returns `InteractiveResponse` alongside its existing raw response in one signal; it does not call both runtime APIs. `_format_turn_notices` preserves the exact existing injection/Experience notices once for both raw text and typed presentation. The pure view model binds the envelope to the same answer, rejects operator routes and invalid/unknown schema, and projects full answer text plus bounded memory/warning/hint evidence. Missing audits remain UNKNOWN, actual stored IDs are distinguished from storage requests, and retrieved records are not claimed as proof of model use. Rendering escapes HTML and never parses debug sections from the answer. Compact display uses at most three memory previews, four warning previews, and two hints per hint group, with omission counts. Debug uses the unchanged full raw response; malformed/stale data or rendering errors fall back with a generic notice, never a second turn. Neither presentation step performs I/O, capture, dispatch, or state mutation, while normal-turn effects remain unchanged. Per-message raw-view controls and clickable memory references are not implemented yet.

Action Safety Policy v1.0 adds `proto_mind/action_policy.py` and read-only `/policy status`, `/policy explain <slash command>`, and `/policy doctor`. It derives advisory classifications from Command Registry metadata: read-only low-risk commands are `auto_allowed`, mutating low/medium-risk commands are `confirmation_required`, high-risk commands are `operator_only`, and unknown/shell-like/chained inputs are `blocked`. Command bundles and Natural Router bundles inherit the strictest member classification. Policy v1.0 never executes commands, changes routing, or enforces authorization.

Action Preview v1.0 adds `proto_mind/action_preview.py` and read-only `/action status`, `/action preview <slash command or exact natural phrase>`, and `/action doctor`. Slash input resolves through Command Registry longest-prefix matching; exact natural input resolves through Natural Router into one step or an ordered bundle. Plans include category/read-only/mutation/risk metadata, per-step Action Safety Policy, strictest bundle policy, and safe suggestions for unmatched natural phrases. Preview never calls target command formatters, enables context, mutates stores, or performs fuzzy/LLM matching.

Action Proposal Queue v1.5.2 adds read-only execution audit to the guarded run-once path. `/action runs [--all|--last N]` lists executed records; `/action run-verify <id>` verifies lifecycle flags, command count, metadata snapshots, current Registry/Policy, and canonical receipt hash; `/action run-audit` aggregates v2/legacy/missing receipts, verified/mismatched hashes, duplicate run ids, warnings, policy drift, and forbidden mutating commands. Results are `VERIFIED`, `WARN`, or `ERROR`. These commands never invoke the executor or mutate queue/target stores; v1.5.1 run-once and read-only-only restrictions remain unchanged.

CLI exit aliases are handled before slash commands, natural routing, and cognitive flow. `exit`, `quit`, `q`, `/exit`, `/quit`, and `/q` close the interactive shell without creating memory records or session log cognitive turns.

Proto-Mind Desktop Chat v0.5 launches with `python3 -m proto_mind.desktop_app`. It is a local tkinter chat window over the same CLI command/natural-router path. Normal chat turns are compact by default; the `Debug output` checkbox restores full observer/memory/audit/reflection traces. The right-side System Panel shows overall status, backend/model, log entry count, last check time, debug state, and buttons for self-check, refresh status, health, doctor, review, log status, and exporting the last 20 session entries. Startup silently refreshes `/session log status` to populate log entry count without chat spam. Desktop UI preferences are stored in `desktop_prefs.json` for `debug_output` and `auto_self_check_on_startup`; auto self-check remains off by default. With `PROTO_MIND_REASONER=ollama`, the status line shows the configured local model. The desktop shell also supports Copy All and explicit transcript export to `exports/desktop_chat_transcript_*.md`.

PySide6 Desktop Shell v1.5.2 launches with `python3 -m proto_mind.pyside_app` as an optional alternative desktop UI. It reuses the same desktop runtime and helper logic as tkinter, including compact/debug output, startup log-status refresh, System Panel commands, transcript saving, and `desktop_prefs.json`. Normal Proto-Mind responses use a safe markdown-lite renderer for paragraphs, bullet/numbered lists, inline code, fenced code blocks, bold text, and simple headings while escaping raw HTML. Each chat message is isolated so markdown list numbering cannot leak into later User/System/Proto-Mind blocks. User and System notes are escaped/plain, and operator reports remain monospace/preformatted. User input and operator commands run in a QThread worker with one active job at a time, keeping the GUI responsive during long local Ollama calls. v1.5 also adds `scripts/build_macos_app_launcher.sh`, which creates a local `dist/Proto-Mind.app` wrapper for double-click launching in Ollama mode; v1.5.1 makes that launcher robust under Finder's limited environment by trying `.venv`, Homebrew, framework, local, and system Python candidates before selecting one that imports both `proto_mind` and `PySide6`; v1.5.2 adds a generated `ProtoMind.icns` icon, clearer timestamped launcher diagnostics in `/tmp/proto_mind_launcher.log`, and `scripts/install_macos_app_shortcut.sh` for Desktop shortcuts. It depends on the existing project, Python/PySide6 install, and Ollama service rather than packaging them. v1.3 added worker signals for future chunks, stream-block helper methods, and a Stop button skeleton. The current shared handler is not forcibly interrupted yet, and real token streaming remains future work. The System Panel shows explicit `Runtime: ready/thinking.../stopping.../error`, the bottom status line preserves backend/model/debug info, and the Send button changes to `Thinking...` while a worker is active. Enter sends messages, Shift+Enter inserts a newline, status badges are color-coded, and PySide window geometry is persisted with a `pyside6:` preference prefix. If PySide6 is not installed, it prints a clean install message instead of a traceback.

PySide6 Cognitive Control Room v2.3.0 is the current `.app` presentation layer. It preserves the shared `DesktopRuntime`, QThread worker, exact formatter behavior, preferences, transcript export, and CLI/natural routing, but replaces the generic System Panel with a local/private identity header, read-only Context Injection and Registry indicators, a structured operator composer, four quick-run chips, and a tabbed right-side deck. The Control tab retains twelve Registry-confirmed `read_only=true`, `mutates=none` reports. The Demo Runway tab provides twelve numbered contest steps spanning showcase readiness, broad-consent refusal, consent preview, one normal cognitive turn, episode/learning explanation, a fixed read-only runner dry-run, evidence verification, and capture stop. Exact Consent and Exact Runner controls unlock only when the prior raw response contains their allowlisted exact command; the extractor accepts only two fixed prefixes, rejects chains, and never generates or persists a token. Four exact local capability contracts render as typed local/read-only cards; normal turns use the separate v3.6b Cognitive Turn Card, with Debug/text fallback preserved. Reading absent or invalid context settings never initializes or repairs them. Launcher metadata is v2.3.0; packaging, token streaming, forced cancellation, and broader typed dashboard-card coverage remain future work.

Desktop Clipboard Robust Fix v0.3.2 adds layered clipboard support: widget bindings, app-level `bind_all` fallback, Tk virtual events, an Edit menu, and right-click/context menus. Chat history remains read-only but selectable/copyable; the input box supports paste/cut/copy/select-all.

Desktop helper scripts:

- `scripts/run_desktop_mock.sh`
- `scripts/run_desktop_ollama.sh`
- `scripts/run_pyside_mock.sh`
- `scripts/run_pyside_ollama.sh`
- `scripts/build_macos_app_launcher.sh`
- `scripts/open_pyside_app.sh`
- `scripts/install_macos_app_shortcut.sh`

Normal CLI turns also print:

- Proto-Mind response.
- Previous correction hints used for this turn, if any.
- Observer state.
- Retrieved memory.
- Retrieval trace.
- Memory decision summary.
- Grounding audit summary.
- Self-reflection summary.
- Correction hints generated for the next turn, if any.

Current operator workflow:

1. Create a checkpoint first with `/memory backup`.
2. Make a small targeted change.
3. Run the unit suite.
4. Run `python3 -m compileall proto_mind`.
5. Run live CLI smoke tests when behavior is involved.
6. Inspect `/session log tail` or `/session log inspect`.
7. Report changed files, verification, caveats, and next risks.

## UI/API

The FastAPI app in `proto_mind/ui/app.py` is an inspection UI, not a polished chat product.

Main endpoint:

- `POST /api/turn`

The `/api/turn` response includes:

- `user_input`
- `response`
- `observer_state`
- `retrieved_memory`
- `retrieval_trace`
- `memory_summary`
- `grounding_audit`
- `self_reflection`
- `previous_correction_hints`
- `working_memory_snapshot`
- `persistent_memory_snapshot`
- `reasoner_backend`
- recent turn history

Memory hygiene endpoints:

- `GET /api/memory/hygiene-preview`
- `POST /api/memory/cleanup-apply`

The UI renders the pipeline artifacts as JSON panels so the operator can inspect the cognitive flow.

## Testing Status

The current unit suite is in `proto_mind/tests/test_flow.py`.

It covers:

- Observer classification.
- Memory inventory detection.
- Override decision detection.
- Retrieval scoring.
- Store/promote logic.
- End-to-end mock pipeline flow.
- Preference declarations and preference-behavior retrieval.
- Store/promote consistency.
- Memory inventory answers grounded in stored memory.
- Override/superseding behavior.
- Historical retrieval.
- Retrieval trace and explanations.
- Topic phrasing variation.
- Generic tag false-match resistance.
- Backend selection.
- Ollama fallback behavior.
- Memory hygiene duplicate detection and cleanup.
- Cleanup reference repair.
- Orphan `superseded_by` reference repair.
- Memory command formatting.
- Self-reflection warnings.
- Correction hint generation and one-turn carry-forward.
- Ensuring correction hints are not persisted as durable memory.
- Grounding audit status, active decision contradictions, superseded/current distinction, unsupported memory claims, and serialization.
- Backup/checkpoint command recognition and archive creation.
- Session operator log append/status/tail/inspect formatting.
- Session log warning scan formatting.
- Session log text search formatting.
- Session log markdown/json export formatting.
- Session review summary formatting.
- Session health check formatting.
- Reflection journal status/list/inspect/create formatting.
- Operating Loop v1.0 status/morning/evening/next/doctor formatting.
- Identity / Values v1.0 status/show/set/add/archive/restore/history/doctor formatting.
- Context Pack v1.0 status/build/show/export/doctor formatting.
- Context Prompt Preview v1.1 prompt-preview/prompt-export/prompt-doctor formatting.
- Context Injection v1.2 manual preview-safe status/enable/disable/preview/doctor formatting and normal-prompt-only wrapping.
- Context Injection Audit v1.2.1 audit/audit-status/last formatting and compact event recording.
- Operating Loop v1.1 morning-plan/evening-review/capture-today daily workflow reports.
- Memory Consolidation Preview v1.3.1 status/preview/export/export-status/doctor, queue, queue-doctor, cleanup-preview, apply-preview, approved-only apply, apply receipt, and undo-preview formatting.
- Data Integrity Doctor v1.1 status/inventory/doctor/refs/refs-doctor formatting and read-only store/reference diagnostics.
- Proto Status / Doctor v1.4 overview/triage/snapshot formatting plus snapshot diff listing, comparison, Markdown/JSON export, and export status.
- Export Retention / Cleanup Preview v1.5 status/inventory/cleanup-preview/doctor formatting over the shared Data Doctor export-directory registry.
- Operating Loop v2 / Daily Agent Layer v1 status/brief/doctor/next formatting over existing read-only Registry, Export Retention, Proto snapshot, warning, context, and Operating Loop APIs.
- Operating Loop v2.1 / Session Rituals v1 start-brief/end-summary/checkpoint-advice/handoff-brief formatting over the same read-only Daily, Export Retention, Proto warning, snapshot/diff, Registry, and Architect Ledger sources.
- Operating Loop v2.2 / Milestone Tracker v1 status/list/current/next/doctor formatting over deterministic Architect Ledger parsing, local milestone-doc discovery, Registry availability, Session Ritual health state, and manual-only next-step guidance.
- Legacy Warning Inspector v1 status/list/inspect/doctor formatting over the existing Proto warning triage, with deterministic IDs, historical/unknown classification, likely source paths, impact explanations, and manual-only options.
- Known Warnings Ledger v1 accepted/accepted-ledger/unknown formatting over narrow static receipt/proposal signatures documented in `KNOWN_WARNINGS_LEDGER.md`; accepted findings remain visible in all source doctors.
- Operating Loop v2.3 / Operator Agenda v1 status/next/list/doctor formatting over Session state, accepted/unknown warning classification, snapshots/diffs, Milestone guidance, tests, and optional handoff commands.
- Operating Loop v2.4 / Pre-Change Ritual v1 status/checklist/doctor/handoff formatting over Agenda readiness, warning acceptance, Export health, snapshot/diff metadata, Context Injection, Rule 0, verification, and SHA-256 guidance.
- Operating Loop v2.5 / Focus Mode v1 status/plan/checklist/doctor/handoff formatting over Pre-Change readiness, Agenda, warnings, manual milestone selection, verification, done criteria, and end-of-session rituals.
- Operating Loop v2.6 / Acceptance Review v1 status/checklist/criteria/decision-guide/doctor/handoff formatting over Focus/Pre-Change readiness, warning baseline, required evidence, blockers, safety invariants, and human decision options.
- Snapshot Baseline Registry v1 status/current/latest/checklist/doctor/handoff formatting over local Ledger facts, Acceptance readiness, accepted/unknown warnings, Context Injection, and existing snapshot/diff metadata.
- Operating Loop v2.7 / Post-Acceptance Closure v1 status/summary/next/handoff/doctor formatting over Baseline, Acceptance, local roadmap, warning counts, Context Injection, and existing snapshot/diff metadata.
- Operating Loop v2.8 / Operator Memory Card v1 status/short/full/codex/doctor formatting over Closure, Baseline, local identity, warning counts, Context Injection, verification, and existing snapshot/diff metadata.
- Operating Loop v2.9 / Command Family Index and Capability Map v1 status/list/map/safety/doctor/handoff formatting over Command Registry metadata, Action Policy classes, Memory Card readiness, warning counts, and workflow phases.
- Operating Loop v2.10 / Proposed Action Plan and Dry-Run Intent Layer v1 status/next/dry-run/gates/doctor/handoff formatting over Capability Map readiness, warning/blocker state, Registry/Policy evidence, and explicit future execution gates.
- Operating Loop v2.11 / Confirmation Gate and Authorization Vocabulary v1 status/policy/levels/requirements/doctor/handoff formatting over Plan readiness, Registry/Policy capability classes, warning/blocker state, and explicit future authorization boundaries.
- Operating Loop v2.12 / Execution Sandbox Design and Command Runner Blueprint v1 status/blueprint/boundaries/allowlist/denied/doctor/handoff formatting over Confirmation readiness, Registry/Policy classes, warning/blocker state, and explicit future runner constraints.
- Operating Loop v2.13 / Read-only Runner Interface Spec and No-Op Executor Contract v1 status/contract/noop/evidence/disabled/doctor/handoff formatting over Sandbox readiness, fixed disabled-state invariants, future evidence requirements, and implementation gates.
- Operating Loop v2.14 / Read-only Command Runner Candidate Set v1 status/list/explain/denied/gates/doctor/handoff formatting over No-Op Runner readiness, Registry/Policy candidate verification, denied classes, and separate future activation gates.
- Operating Loop v2.15 / Runner Activation Preconditions v1 status/preconditions/checklist/blockers/forbidden/doctor/handoff formatting over Candidate Set readiness, future v3.x design conditions, current execution blockers, and no-activation invariants.
- v3.0a / Read-only Runner MVP Design Lock status/design/allowlist/confirmation/evidence/stop-conditions/doctor/handoff formatting over Activation readiness, five verified MVP candidates, exact future confirmation rules, design-only evidence, and fail-closed refusal conditions.
- v3.0b / Real Read-only Runner MVP status/allowlist/dry-run/run/evidence/doctor/handoff over one exact active target (`/warnings unknown`), exact per-run confirmation, fixed internal dispatch, current-process-only evidence, and data/export SHA-256 no-write verification.
- v3.0c / Runner Evidence Hardening refusal-matrix/last-refusal/evidence-check over static refusal expectations, separately retained in-memory success/refusal evidence, redacted confirmation fingerprints, and fail-closed evidence-shape checks.
- v3.0d / Daily Doctor Runner Pilot expands the active runner allowlist to exactly `/warnings unknown` and `/daily doctor`, with a fixed two-callback map, command-specific confirmation, dual-command dry-run/evidence validation, and no general dispatch path.
- v3.0e / Exports Doctor Runner Pilot expands the active runner allowlist to exactly three commands through a fixed three-callback map and adds `export_doctor_status` evidence without introducing general dispatch.
- v3.0f / Runner Multi-Command Stability Review adds stability/sequence-plan/sequence-evidence/consistency-check introspection over the unchanged three-command runner, with bounded process-memory summaries and no callback invocation.
- v3.0g / Capabilities Safety Runner Pilot expands the active allowlist to exactly four commands through a fixed four-callback map and adds compact capability-safety evidence without general dispatch.
- v3.0h / Runner Four-Command Safety Soak adds soak/soak-plan/soak-report/drift-check diagnostics over bounded current-process evidence and the unchanged four-command callback map.
- v3.0i / Runner Evidence History Ring Buffer adds history/history-summary/history-clear-preview/history-doctor over a compact 20-event process-memory ring. It stores success/refusal summaries only, evicts oldest entries, retains no confirmation text or full stdout, and adds no executable target or persistence path.
- v3.1a / Bilingual Cognitive Baseline adds ten local observer/topic English/Russian cases plus Russian continuity, memory-inventory, preference, decision, override, topic extraction, compact preference storage, superseding, and recall coverage. Registry and runner scope remain unchanged.
- v3.1b / Memory Write Governance adds `/memory write-policy|quality-preview`, pure retrieval by default, explicit usage telemetry, compact user-input-only automatic records, and deterministic legacy-quality findings without migration or cleanup.
- v3.1c / Bilingual Grounding and Reflection expands the benchmark to 20 cases, centralizes bilingual response signals, detects Russian contradiction/history/unsupported-claim/preference issues, and adds memory provenance to grounding evidence without new commands, writes, or schemas.
- v3.1d / Cognitive Continuity Soak adds a local 25-turn Coordinator scenario with four explicit writes, 21/21 byte-stable read-only turns, bounded four-content memory, recall/override/history/correction checks, and temporary-store-only execution.
- v3.2a / Experience Ledger Foundation adds typed compact cognitive events, ordered provenance links, privacy validation, and an in-memory 180-event soak trace without live persistence or command expansion.
- v3.2b / Experience Ledger Persistence Policy adds temporary-only atomic JSONL append, SHA-256 chain verification, fail-closed corruption handling, and an explicit live-data path guard without enabling capture.
- v3.2c / Experience Ledger Live Capture Gate adds read-only disabled-state/config diagnostics with no hook, activation API, live file, or Registry expansion.
- v3.2d / Experience Event Vocabulary v2 adds typed lifecycle evidence and source-link validation for goals, plans, tool outcomes, corrections, lessons, and promotion without domain mutation or live capture.
- v3.2e / Experience Trace Explainability adds immutable inspection, deterministic source chains, entity lookup, and safety-aware “why” reports without repair, execution, or live capture.
- v3.2f / Experience Episode Projection adds compact verified-success and corrected-failure episodes with exact evidence IDs and explicit learning boundaries, without persistence, summarization, promotion, execution, or live capture.
- v3.2g / Experience Learning Candidate Review adds deterministic eligibility, evidence, confirmation, and exact-duplicate checks over projected lessons, with `auto_apply_allowed=false` and no live-store access or mutation.
- v3.2h / Session Capture Design Review locks explicit one-session consent, privacy, retention, bypass, and failure-isolation requirements while keeping capture and implementation authorization disabled and creating no files.
- v3.2i / Learning Review Input Adapter adds detached explicit-ID active memory/skill snapshots with transparent missing/excluded/error states and no retrieval, telemetry, automatic selection, or writes.
- v3.2j / Session Consent State Machine Spec adds pure preview/consent/stop/expiry transitions and a 14-case refusal matrix, without storing consent, authorizing implementation, or integrating capture.
- v3.2k / Experience Privacy Redaction Benchmark adds deterministic redaction-before-truncation, nine credential rules, 16 sensitive/benign fixtures, and Doctor enforcement for preview fields without capture or persistence.
- v3.2l / Experience Capture Bounded-Growth Soak adds a 36-turn consent/redaction simulation with strict per-turn, event, and byte bounds plus fail-closed overflow, creating zero files and granting no activation authorization.
- v3.2m / Experience Capture Activation Readiness Review aggregates ten safety/evidence gates into a 10/10 READY matrix while preserving `KEEP_DISABLED` and denying implementation/runtime activation.
- v3.3a / Supervised In-Memory Experience Pilot adds explicit session-bound consent and visible bounded normal-turn evidence while keeping persistence, automatic learning, Context Injection, commands, and domain mutation outside the capture scope.
- v3.3b / Cognitive Turn Episode View adds read-only Observe-to-Verify projections and exact event provenance over current process memory without summarization, persistence, or learning apply.
- v3.3c / Operator-Reviewed Learning Bridge Preview adds bounded evidence-to-candidate review with exact event IDs and explicit confirmation requirements, while promotion, apply, persistence, and clean-turn lesson invention remain disabled.
- v3.3d / Learning Candidate Confirmation Design adds bounded process-memory accept/reject receipts, exact candidate tokens, tamper diagnostics, and non-executable promotion dry-runs without domain persistence or apply.
- v3.3e / Learning Promotion Eligibility Review adds accepted-decision-gated, target-specific exact duplicate review over operator-selected detached memory/skill IDs. Missing, inactive, malformed, and over-limit inputs fail visibly; every receipt remains scope-limited, non-executable, non-persistent, and free of retrieval telemetry or store mutation.
- v3.3f / Learning Promotion Proposal Receipt adds fixed memory/skill target schemas, selected-scope SHA-256 binding, exact proposal tokens, and a 32-receipt process-memory session. Proposals remain immutable, restart-expiring, non-executable, not apply-ready, and unable to mutate domain stores or queues.
- v3.3g / Learning Promotion Apply Readiness Review revalidates current candidate, accepted decision, selected explicit-ID scope, eligibility, fixed payload, and proposal digest. It prints future receipt/rollback safeguards only; no exact apply command, engine, target mutation, receipt mutation, or persistence path exists.
- v3.4a / Supervised Memory Lesson Promotion Pilot adds a separate exact-token gate for one fresh `memory.lesson.v1` proposal per process. The token binds current memory-store SHA-256; apply performs full exact-duplicate defense, one atomic persistent-memory write, post-write record/hash verification, a process-memory run-once receipt, and a manual `/memory forget` rollback suggestion. Skill/batch apply and arbitrary execution remain unavailable.
- v3.4b / Durable Learning Provenance embeds one compact hashed source envelope in the atomically created lesson and adds read-only `/memory why <id>` plus Memory Doctor integrity checks. Candidate, decision, eligibility, proposal, selected-scope, and redacted evidence IDs survive restart without a sidecar file; the receipt's manual `/memory forget` rollback now accepts only explicit or verified provenanced lessons and retains their audit chain. Legacy records remain explicitly unexplained, detailed receipts still expire, and no second writer, skill/batch apply, or autonomous consolidation is introduced.
- v3.4c / Verified Lesson Recall permits only provenance-verified learned lessons to enter normal recall, exposes provenance in retrieval and grounding traces, and proves bilingual restart behavior with byte-stable temporary stores. Tampered, unprovenanced, and inactive-current lessons fail closed; no command, writer, usage telemetry, model call, automatic apply, or autonomous behavior is added.
- v3.4d / Learning Outcome Review compares an exact provenanced lesson with later valid Experience lineage and prints keep/reject/supersede candidates or insufficient evidence. Supersede requires a newer active verified replacement; every result remains advisory and read-only with no Registry expansion, apply, promotion, or store mutation.
- v3.4e / Supervised Lesson Lifecycle Decision binds keep/reject/supersede to exact current outcome evidence and records one bounded terminal process receipt per lesson. It reuses the registered decision gate and adds no lesson mutation, lifecycle apply, persistence, model call, or command execution.
- v3.4f / Learning Lifecycle Apply Readiness revalidates exact lifecycle receipts against current provenance, evidence, store bytes, replacement state, and the registered memory gate without executing the writer.
- v3.4g / Supervised Lesson Lifecycle Apply Pilot permits one separately confirmed keep/reject/supersede transition per process. Keep is a byte-stable no-op; terminal transitions touch one old lesson, preserve provenance, verify post-write scope, and roll back exact bytes on failure. No batch or automatic lifecycle action exists.
- v3.4h / Lifecycle Transition Audit reconstructs durable learned-lesson state after restart and diagnoses invalid provenance, timestamps, dangling/inactive replacements, unclassified deactivation, and replacement cycles. All commands are read-only and no historical receipt is invented.
- v3.5a / Procedural Skill Contract turns one active provenance-verified lesson into a deterministic operator-authoring template with explicit trigger, preconditions, steps, permissions, verification, and failure-mode fields. It detects active exact duplicates and installs no skill writer, synthesis, promotion, or execution path.
- v3.5b / Procedural Skill Authoring Receipt binds exact visible operator-authored fields and current lesson/provenance hashes to one of 16 bounded process-memory receipts through the existing proposal gate. Receipts expire on restart and grant neither persistence nor execution.
- v3.5c / Procedural Skill Apply Readiness revalidates a live authoring receipt against current source and complete Skill Library state, exposes target/store hashes plus atomic receipt/rollback requirements, and does not invoke the writer or generate an apply token.
- v3.5d / Supervised Procedural Skill Apply Pilot permits one separately confirmed atomic Skill Library append per process, verifies the exact record and unchanged memory/source provenance, restores exact bytes on failure, and never executes the stored procedure.
- v3.5e / Durable Skill Provenance Inspection embeds restart-safe source/contract/confirmation evidence in newly applied skills and adds read-only why/Doctor verification without another writer or procedure execution.
- v3.5f / Procedural Skill Outcome Review accepts only exact manual-use lineage tied to current verified skill provenance, treats verified operator-reported outcomes as advisory candidates, ignores usage telemetry, and adds no execution or capture path.
- v3.5g / Supervised Manual Skill Outcome Capture requires session consent plus a second exact token, records one bounded process-memory four-event manual-use/outcome lineage, and never executes or mutates the skill.
- v3.5h / Supervised Procedural Skill Outcome Decision binds decisive review signals to confirmed capture receipts and records one exact terminal keep/revise/archive choice without Skill Library mutation or apply readiness.
- v3.5i / Procedural Skill Lifecycle Apply Readiness revalidates that choice against current evidence, capture hashes, provenance, exact skill bytes, and decision-specific future safeguards without generating a token or invoking the separate apply gate.
- v3.5j / Supervised Procedural Skill Lifecycle Apply Pilot permits one separately confirmed keep no-op or atomic archive with exact rollback, while revision and procedure execution remain unavailable.
- v3.5k / Durable Procedural Skill Lifecycle Audit reconstructs restart-safe current skill state without inventing an outcome-driven reason for archived records.
- v3.5l / Durable Skill Lifecycle Metadata Design Lock defines and self-tests a hashed future archive envelope while keeping its writer absent and live records fail-closed.
- v3.5m / Durable Skill Lifecycle Writer Readiness binds a current archive decision to an exact future envelope/mutation/receipt plan without producing a token or invoking the existing writer.
- v3.5n / Durable Skill Lifecycle Metadata Apply Pilot persists one separately confirmed archive envelope with exact mutation verification, rollback, and restart-safe audit evidence; keep is unchanged and restore/revise remain unavailable.
- v3.5o / Durable Skill Lifecycle Restore Design Review embeds the verified archive envelope in a detached restore contract and revalidates current state read-only; no token, writer, authorization, or mutation exists.
- v3.5p / Direct Lifecycle Status Guardrail makes generic archive/restore fail closed for lifecycle-managed or corrupt records while preserving legacy/operator workflows.
- v3.5q / Lifecycle-Managed Skill Payload Guardrail makes summary/body/tag/use mutations fail closed before callbacks or writes for lifecycle-managed or corrupt records while preserving pre-lifecycle/operator workflows.
- v3.5r / Durable Restore Authorization Readiness binds current restore evidence and exact future authorization/receipt/rollback scope without generating a token or installing an engine, state, or writer.
- v3.5s / Supervised Durable Restore Apply Pilot permits one exact-token atomic restore per process, preserves the complete archive/provenance chain, verifies `active_restored_verified`, and rolls back exact bytes on failure without executing the procedure.
- v3.5t / Durable Restore Receipt Audit reconstructs a separately hashed restart-safe evidence artifact without inventing the original process receipt and diagnoses live, legacy, orphan, or mismatched receipt state read-only.
- v3.5u / Restored Skill Re-evaluation Design excludes stale/unbound outcome evidence, locks an exact post-restore event contract, and fail-closes legacy capture/decision paths without adding a writer.
- v3.5v / Supervised Post-Restore Outcome Capture Readiness binds a future exact capture to active consent and current restore/provenance/store evidence while keeping token, writer, append, and execution unavailable.
- Build Week Provenance Pack v1 adds an honest pre-existing/contest disclosure, reproducible July 11 baseline hashes, current manifests, and collaboration evidence without runtime behavior changes or private-store inclusion.
- Contest Showcase v1 adds a read-only four-part live demo, deterministic operator script, dependency doctor, and submission narrative without activating consent or executing capabilities.
- Preference priority cleanup for response-style and future-behavior retrieval.
- Preference recall questions not being stored as new preferences.

## Known Limitations

- No vector database.
- No embeddings.
- Retrieval is heuristic and topic-rule based.
- Topic normalization is hand-built and project-specific.
- Self-reflection is heuristic and cannot guarantee full factual correctness.
- Grounding audit is heuristic and cannot prove all response claims are justified.
- Correction hints are session-local and are lost on process restart.
- Correction hints guide the next turn only; they do not rewrite the current response.
- No model weight learning or model training.
- JSON memory storage is still the implemented backend.
- Active project memory may indicate SQLite as the intended future storage direction, but SQLite has not replaced JSON in the current implementation.
- FastAPI UI is inspection-oriented and intentionally minimal.
- Memory cleanup is conservative and exact-duplicate based; it does not perform fuzzy semantic merging.
- Session logs are local JSONL with no rotation, search, filtering, or export yet.
- Reflection Journal v1.0 is deterministic session-log reflection saved to `proto_mind/data/reflection_journal.jsonl`; it does not call an LLM, mutate memory, or feed retrieval.
- Operating Loop v1.1 is a read-only cross-module report and daily capture layer over goals, tasks, experiments, world predictions, reflections, memory counts, identity, and skills; it suggests next commands but does not create tasks, write memory, plan with an LLM, or execute actions.
- Memory Consolidation Preview v1.3.1 suggests manual memory/skill promotion commands, can export preview reports, can queue candidates, can diagnose/preview cleanup, can explicitly apply approved allowlisted memory/skill commands, and can preview rollback suggestions from receipts; it does not automatically undo, batch apply, execute shell commands, execute arbitrary slash commands, call an LLM, or perform semantic embeddings search.
- Data Integrity Doctor v1.1 is read-only and diagnostic only; it does not repair files or references, migrate schemas, rotate logs, create missing stores, or restore from backup.
- Proto Status / Doctor v1.4 adds export-only snapshot diff reports under `exports/proto_snapshot_diffs`. CLI and export render from one structured payload; failed/latest-under-two operations create nothing, while successful exports write only atomic Markdown/JSON report files and leave source snapshots/core stores unchanged.
- Export Retention v1.5 is fully read-only: it inventories seven known export directories, validates JSON, checks Markdown/JSON pairing, warns on missing/large histories, and suggests safe manual review/archival without deleting, moving, compressing, or rewriting files.
- Daily Agent Layer v1 is a synchronous read-only operator report layer. It has no scheduler, background task, LLM call, command dispatcher, auto-apply, repair, or write path; `/daily next` only prints manual suggestions.
- Session Rituals v1 prints live operator guidance only. It does not persist a session summary, create checkpoints/snapshots, run tests, touch the clipboard, call a model, or mutate session logs, context settings, core stores, or exports.
- Milestone Tracker v1 is roadmap awareness, not planning or persisted workflow state. It parses only existing local Markdown facts, marks inference/unknown fields, and cannot accept, advance, repair, clean, or execute a milestone.
- Legacy Warning Inspector v1 is diagnostic only. Stable IDs are message-derived rather than persisted, source paths are conservative heuristics, and no receipt/reference migration, repair, cleanup, report export, or warning suppression is performed.
- Known Warnings Ledger v1 documents current debt but is not a runtime acknowledgement store or allowlist for execution. Matching is intentionally ID/signature-specific; runtime commands never update the ledger, hide warnings, or mutate source records.
- Operator Agenda v1 is generated live and never persisted. It has no scheduler, executor, task creation, command dispatch, repair path, or autonomous planner; related commands are text for manual operator use only.
- Pre-Change Ritual v1 is inspection and printable guidance only. It cannot create backups/snapshots, run tests, calculate stored baselines, mutate checklists, or perform any suggested command; only the separately executed Rule 0 backup may write an archive.
- Focus Mode v1 is planning-only and non-persistent. It chooses no objective autonomously, executes no step, creates no session/task record, and performs no model call, backup, snapshot, repair, cleanup, migration, or context change.
- Acceptance Review v1 is a static human-review framework. It does not parse Codex output, inspect external text, score evidence, choose a decision, persist review state, or mutate implementation/runtime data.
- Snapshot Baseline Registry v1 is local read-only awareness, not a persistent baseline database. It does not accept a milestone, create snapshots/checkpoints, update the Ledger at runtime, execute suggested commands, or mutate stores/exports.
- Post-Acceptance Closure v1 prints live closure and handoff guidance only. It does not close/log a session, persist closure state, write handoff files, touch the clipboard, create snapshots/backups, or execute next-milestone suggestions.
- Operator Memory Card v1 is generated text, not persistent memory. It has no card store, clipboard integration, LLM summary, prompt injection, command execution, snapshot/backup creation, or runtime-store/export write path.
- Command Capability Map v1 is Registry-derived documentation and advisory classification only. It does not execute, authorize, persist, repair, clean, migrate, snapshot, back up, or mutate any command family or workflow state.
- Dry-Run Plan v1 prints deterministic proposals/templates only. It has no free-text intent parser, persistent queue, approval/authorization engine, executor, shell access, snapshot/backup path, or runtime-store/export mutation.
- Confirmation Vocabulary v1 is advisory documentation only. It captures no phrase or approval, grants no authorization, persists no state, and performs no command execution or policy enforcement.
- Execution Sandbox Blueprint v1 is design documentation only. `FUTURE_CANDIDATE` is not an active allowlist; there is no runner, subprocess/shell/eval/exec path, execution queue, authorization engine, background work, or runtime state mutation.
- No-Op Runner Contract v1 specifies shapes and sample text only. `execution_enabled=false` and `executed=false` are fixed; no active allowlist, request dispatch, approval capture, authorization/execution engine, or runtime persistence exists.
- Runner Candidate Set v1 is static documentation, not an allowlist. All 13 entries remain `FUTURE_CANDIDATE | NOT_ACTIVE | NOT_EXECUTABLE_BY_RUNNER_YET`; there is no candidate persistence, activation API, dispatch, or execution surface.
- Runner Activation Preconditions v1 separates design consideration from execution readiness. It never activates candidates, captures approval, implements authorization/execution/evidence engines, persists checklist state, or changes the fixed inactive/disabled runtime state.
- Runner MVP Design Lock v3.0a fixes architecture text only. The proposed five-command allowlist is inactive, confirmation is not captured, evidence is `NOT_AVAILABLE_DESIGN_ONLY`, and no transport/dispatch/execution implementation exists.
- Real Read-only Runner MVP v3.0b executes only exact `/warnings unknown` after exact confirmation. It has no free-form dispatch, second allowlisted target, shell/subprocess/eval/exec, persistent evidence, network/background work, or runtime-store/export write authority; any expansion requires a separate milestone.
- Runner Evidence Hardening v3.0c retains only the latest event/success/refusal in process memory. The refusal matrix is static, mismatch text is fingerprinted rather than logged, and evidence-check is diagnostic only; restart clears all runner evidence.
- Daily Doctor Runner Pilot v3.0d adds exactly one executable read-only target. Both targets remain low-risk, mutates=none, auto-allowed Registry entries behind exact per-run confirmation; no third target, free-form command, shell primitive, persistence, or store/export mutation is permitted.
- Exports Doctor Runner Pilot v3.0e adds exactly `/exports doctor`. All three targets remain low-risk, mutates=none, auto-allowed Registry entries behind exact per-run confirmation; no fourth target, free-form dispatch, persistence, or store/export mutation is permitted.
- Runner Stability Review v3.0f does not expand execution. Sequence evidence is bounded to counters and latest references, consistency checks callback keys without invocation, and no persistent history, approval, or general runner API is introduced.
- Capabilities Safety Runner Pilot v3.0g adds exactly `/capabilities safety`; `/confirm policy` remains excluded. All four targets remain low-risk, mutates=none, auto-allowed Registry entries behind exact per-run confirmation, with no fifth target or store/export mutation.
- Runner Safety Soak v3.0h is diagnostic only. It stores no report/history, invokes no callback, adds no executable target, and uses bounded evidence, consistency, mutation-indicator, Context Injection, and `/confirm policy` exclusion checks.
- Runner Evidence History v3.0i is bounded to 20 compact process-memory events and is lost on restart. There is no clear mutation command, disk path, approval persistence, full output capture, fifth target, or free-form dispatcher.
- Russian cognitive support is deterministic and intentionally finite. Observer/retrieval and durable preference/decision paths are bilingual, while deeper response-level SelfReflection and GroundingAuditor phrase heuristics still primarily target English wording.
- Eight existing live records currently match the response-coupled migration preview; six are recursive/long. They remain untouched until a separate checkpointed migration is explicitly approved.
- Identity / Values v1.0 is inspectable operator state only; it is not automatic prompt injection, self-rewriting, or autonomous enforcement.
- Context Pack v1.0 is export/inspection only; it is not automatic prompt injection, LLM summarization, embeddings retrieval, or planning.
- Context Prompt Preview v1.1 creates prompt-ready text for controlled manual use only; it still does not alter model prompts or shared handler reasoning.
- Context Injection v1.2 is disabled by default and only applies to normal prompts after explicit operator enablement; it does not apply to slash/operator commands.
- Context Injection Audit v1.2.1 is passive JSONL audit only; it does not store full injected prompts by default and does not change injection or reasoning behavior.
- Backups are timestamped project archives, not structured memory/database exports.
- Proto-Mind requires Python 3.11+; use `scripts/run_cli.sh` and `scripts/run_tests.sh` for stable local development.
- Live CLI testing with Codex is useful for edge cases but still requires operator oversight.

## Suggested Next Layers

- Grounding Auditor v2: add richer evidence spans and severity levels for grounding-specific findings.
- Preference conflict resolution: clarify which preference wins when multiple active preferences apply.
- Session log search/filter: inspect entries by warning, query type, grounding status, or memory id.
- SQLite migration: replace JSON storage with SQLite while preserving the `MemoryStore` boundary.
- Richer reflection severity: add structured warning severity and category fields.
- Reflection journal follow-ups: add UI buttons, goal/task integration, and optional operator-approved memory consolidation.
- Cognitive Control Room follow-up: optionally parse selected read-only operator reports into dashboard cards and show a compact latest Context Injection audit summary without changing shared command output or settings.
- Backup/export manifest: include explicit archive metadata and memory export summaries before cleanup, repair, or storage migration.
