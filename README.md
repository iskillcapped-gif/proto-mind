# Proto-Mind

Proto-Mind is a personal cognitive-agent architecture and native macOS workspace.

For compact architectural handoff context, see `PROTO_MIND_ARCHITECT_LEDGER.md`.

## Native macOS Direction

Post-contest personal development now targets a real SwiftUI/AppKit application with a Codex-inspired conversation workspace, while preserving the existing Python cognitive core and operator commands. The current native workspace is **Native 0.39.0 / Live Session Spine Preview**, extending source-grounded memory suggestions, automatic project recall, mode-bound Codex continuity, Full Mac Computer Use, durable sessions, selected PDF/image/text inputs, live Web Search, attachment recovery/drop, run notices, the Context And Artifact Desk, manual acceptance, EV-01 reliable work sessions, an inspectable Brother self-model and explicit Native candidate-to-lesson-to-skill review; it does not replace the submitted contest build.

**Live Session Spine Preview (0.39.0):** a linked assistant answer now has a Session Spine button beside its exact-run clock. Native refreshes the bounded journal, resolves only the run named by the existing Turn Lineage reference, and asks a fixed local bridge endpoint for the existing P1 projection. The bridge revalidates the current `run_id + fingerprint`, content-free chat reference, both exact messages and durable turn receipt before deriving the surface in memory. Its response is a closed, self-hashed, content-free event map: event types, sequence/provenance, character counts, SHA-256 values, tool kind/status and folded-surface identity, but no duplicated prompt/answer text. Swift independently validates the response before opening a bounded read-only sheet. Missing, stale, changed or out-of-window evidence fails visibly without guessing another run. Opening/closing performs no Session Spine/history/run/export write, model or command call, tool replay, migration, permission change or Context Injection change. It is an ephemeral inspection surface, not authoritative history, task-success proof, provider-delivery proof or a production Session Spine writer. [Contract and limits](NATIVE_MACOS_ROADMAP.md#live-session-spine-preview--native-0390).

**Turn Lineage (0.38.0):** every successfully completed ordinary Codex or Ollama turn now closes the local chain from the exact user message to the exact raw response and durable work-session ID. The work session stores a strict content-free `native_turn_receipt.v1` with UUIDs, provider/mode, Unicode counts, input/response/preview SHA-256 values and the preceding Instruction Receipt hash. Native history stores a separately hashed reference to that receipt and validates it against both messages on save and restart. A clock button beside the answer refreshes the journal and opens only the exact matching run; changed review fingerprints do not break the stable receipt, while missing or tampered evidence is never guessed. Old history/runs remain readable without migration, and Mock/operator/failed turns get no invented lineage. This is not a live Session Spine writer, task-success proof, provider-delivery proof or authenticity signature, and adds no command, model call, permission, dependency, Context Injection change or core-store schema. [Contract and limits](NATIVE_MACOS_ROADMAP.md#turn-lineage--native-0380).

**Instruction Receipt (0.37.0):** every successfully completed ordinary Codex or Ollama Send now preserves a strict content-free receipt for the exact Proto-Mind-authored instruction assembly used immediately before the provider call. The optional work-session field records provider/mode/Persona state, selected-memory IDs and counts, correction-hint count, ordered layer source/placement/size/SHA-256, canonical hash material and a receipt hash; it never stores instruction, memory or correction text. The Work Session inspector independently validates and displays this metadata. Legacy records remain readable without migration, while Mock and operator commands receive no fabricated receipt. The receipt proves local assembly integrity only: it explicitly does not claim access to provider-owned instructions, private reasoning, provider delivery or semantic interpretation. No Registry command, provider call, permission, dependency, Context Injection behavior or core-store schema was added. [Contract and limits](NATIVE_MACOS_ROADMAP.md#instruction-receipt--native-0370).

**Local Instruction Inspector (0.36.0):** the existing pre-Send **Context** desk now shows the exact current instruction layers authored by Proto-Mind: Codex `baseInstructions` plus the static Chat/Full Mac `developerInstructions`, or the Ollama system message. The production Send path and preview share one assembler; every displayed layer carries its source, placement, Unicode-character count and SHA-256, and the complete canonical projection has its own verified hash. Legacy and Brother Persona projections are labelled separately. If the draft requires shared-core memory, preview performs the same deterministic retrieval with usage tracking disabled and writes nothing. Operator commands and Mock receive no fabricated provider prompt. The desk explicitly marks upstream provider-owned instructions and private model reasoning as unavailable rather than reconstructing them. Preview performs no model/network call, thread start/refresh, command or store write; Send recomputes after current memory, Persona, mode and access checks, so it remains a projection rather than a frozen authorization. No Registry command, dependency or permission was added. [Contract and limits](NATIVE_MACOS_ROADMAP.md#local-instruction-inspector--native-0360).

**Instruction contract refresh (0.35.0):** each Chat and Full Mac provider binding now stores a SHA-256 fingerprint of its static developer-instruction contract, never the prompt text. Settings and the local Context desk distinguish a resumable thread from one created under older instructions. On the next explicit Send for a stale mode, Proto-Mind verifies a fresh `thread/start`, atomically replaces only that mode's local binding, bootstraps bounded local continuity once and leaves the former Codex rollout untouched in the private provider profile. Unchanged contracts keep normal `thread/resume`; status/preview never migrate the store. Existing v1/v2 registries remain readable and become refresh candidates rather than being silently trusted or rewritten. [Contract, migration and limits](NATIVE_MACOS_ROADMAP.md#native-instruction-contract-refresh--native-0350).

**Memory suggestions (0.34.0):** after a successful ordinary Codex turn, a compact **Worth remembering?** card can offer up to two exact quotes from explicit operator statements such as "We decided..." or "I prefer..." (Russian and English). Matching is deterministic and local, with no extra model call. **Review and save** shows the original quote, source hash and project; a separate acknowledgement and Save reuse the existing immutable private note writer, without manual token copying. No confirmation means no project note. Current exact duplicates are omitted; assistant answers, attachments and tool output never become suggestion sources in this slice. The brain-icon menu has a per-chat off switch. This is not general fact extraction, verified learning or automatic replacement of old decisions. Ordinary successful-turn core behavior remains unchanged. [Source, privacy and limits](NATIVE_MACOS_ROADMAP.md#ev-04-source-grounded-memory-suggestions--native-0340).

**Automatic project recall (0.33.0):** ordinary Codex tasks can use current, explicitly saved notes from the selected project without manually attaching them each time. The brain-icon menu beside Skills defaults on per conversation and provides an off switch; manual note selection takes precedence. Matching is local and deterministic: informative content words, at most three whole notes and 6000 characters, no additional model request or embeddings. **Context** shows the exact selected text before Send; the answer/journal preserves source IDs, hashes, scope and a bounded selection report. Superseded/other-project notes are excluded, no match means no addition, and reviewed-source drift refuses Send without a hidden replacement. This does not create notes, migrate old memory, learn automatically or grant tools. The old shared-core memory path and existing normal-turn writes are unchanged. [Scope, privacy and evidence](NATIVE_MACOS_ROADMAP.md#ev-04-automatic-project-recall--native-0330).

**Built-in starter skills (0.32.0):** four application-authored procedures are ready for Auto: orient in a project, implement and verify a change, diagnose a failure without repair, and prepare a grounded handoff. **Skills / Auto > Built-in set** opens a local read-only view of their steps, permissions, checks and limits. They live in versioned code, not `skills.jsonl`, and are explicitly labelled **bundled**, never learned from your conversations. The current catalog has four built-ins and zero eligible learned skills; two legacy personal records remain untouched. New private reports distinguish origins and pack/contract hashes; old reports load without migration. Seven live selector cases and four independently checked synthetic Codex tasks pass. [Contract, evidence and limits](NATIVE_MACOS_ROADMAP.md#ev-04-built-in-starter-skills--native-0320).

**Automatic skills (0.31.0, extended in 0.32.0):** write a normal task and Send. **Skills / Auto** in the Codex composer lets the selected subscription model choose zero to two relevant procedures from the built-in set and eligible active, current-provenance verified personal skills. It defaults on per conversation; turn it off or prepare a manual selection to override it. No goal/criteria form is required. With an eligible catalog, one separate tool-free, ephemeral selector turn uses low effort when supported (otherwise the model default); the main task keeps your chosen effort, saved Codex session and existing permissions. The chat and private journal show the choice, source-version hashes and suggested checks, not a fabricated success receipt. Missing/unsafe source stores or config still disable all automatic guidance without initialization or promotion; the built-in viewer remains available. Invalid selection, Stop or source drift never auto-retries. This is guidance, not automatic skill creation, learning, new permission or a procedure interpreter. [Flow and privacy](NATIVE_MACOS_ROADMAP.md#ev-04-automatic-skill-guidance--native-0310).

**Tasks with skills (0.30.0):** **Skills > a skill > Prepare task with skill** reads the current verified procedure, then requires your goal and observable criteria. Review the preconditions, suggested steps, permission requirements and checks; explicitly prepare the draft, then Send separately. The procedure is quoted guidance for that one ordinary turn, not a new interpreter, permission or automatic execution. Changed sources, goal, criteria, project or provider/access mode refuse stale preparation; cloud and Full Mac keep their separate existing gates. The context desk shows the exact procedure. The private journal records its source/version hashes beside observed results and the existing per-criterion manual acceptance, without incrementing uses or learning automatically. Restart drops the selection, not the ordinary draft or run evidence. [Workflow and limits](NATIVE_MACOS_ROADMAP.md#ev-04-operator-guided-skill-tasks--native-0300).

**Project memory (0.29.0):** **Memory > Project memory** or the composer's **+ > Project note** reads only explicitly saved notes for the chosen folder. Facts, preferences, decisions, lessons and constraints carry an operator source/basis; they are not independently verified. Preview and exact confirmation add one immutable private record; an explicit replacement keeps its predecessor as history. Local token-overlap recall never calls a model or updates counters. Attach selected notes separately, then Send: current project, SHA and supersession are rechecked. The context desk shows the actual content; private run evidence stores IDs/hashes, not a second note copy. Legacy core memory remains shared, and no migration or automatic injection occurs. [Scope and limits](NATIVE_MACOS_ROADMAP.md#ev-04-explicit-project-memory--native-0290).

**Saved learning history (0.28.0):** **Skills > Results and lifecycle > Learning history** can explicitly save the selected skill, its current inspection and available full manual-outcome/decision/archive/restore receipts with the exact referenced events. Preview first, then a snapshot-bound token and acknowledgement. Immutable SHA-256-checked snapshots live in the private Native `learning_history/`, not core stores/exports. Restart preserves these historical copies but never rehydrates a pilot, consent, token or execution authority. Missing old receipts are not reconstructed; automatic capture, quality verification and history migration are not implied. [Storage and limits](NATIVE_MACOS_ROADMAP.md#ev-04-saved-learning-history--native-0280).

**Skill Restore (0.27.0):** an archived skill's Results and lifecycle view now opens a separate restoration review. A fresh exact token and shared-library acknowledgement reuse the existing core restore gate, changing only one record's `lifecycle/status/updated_at` and retaining the full prior archive evidence. It restores availability, not quality, consent or execution permission. Reads do not initialize missing memory files; concurrent changes are preserved rather than overwritten by rollback. One Native attempt per process; no retry, command/model call, new outcome or automatic execution. Detailed receipts are still process-only at this milestone. [Workflow and limits](NATIVE_MACOS_ROADMAP.md#ev-04-skill-restore--native-0270).

**Skill Lifecycle Apply (0.26.0):** an exact recorded outcome decision now opens **Check decision application**. Viewing and previewing remain read-only. A new current token and explicit shared-library acknowledgement reuse the existing core gate: keep produces a zero-file-change receipt; archive changes only `lifecycle`, `status` and `updated_at` of one existing skill. No procedure runs. Source/evidence/scope drift, unsafe settings, revise/restore and replay are refused. One Native lifecycle attempt is allowed per bridge process; failed or lost responses never auto-retry. The full receipt expires on restart, but the archived skill retains independently verifiable transition metadata. Shared stores are not project-isolated, and conditional byte-exact failure recovery is not a global filesystem lock. [Workflow and limits](NATIVE_MACOS_ROADMAP.md#ev-04-skill-lifecycle-apply--native-0260).

**Skill Outcome Decisions (0.25.0):** open **Skills > a skill > Results and lifecycle > Decision from results**. Exact confirmed manual success permits keep; failure or mixed results permit revise/archive recommendations. Nothing is preselected. A separate current token and decision-only acknowledgement record one terminal receipt in the conversation's process memory, not a skill edit, archive or run. Later evidence can make that receipt historical without rewriting it. Source/evidence/scope drift and replay fail closed. Viewing never starts capture or consent; restart discards the decision. [Workflow and limits](NATIVE_MACOS_ROADMAP.md#ev-04-skill-outcome-decisions--native-0250).

**Manual Skill Outcomes (0.24.0):** open **Library and Core > Skills > a skill > Record manual outcome**. With separately granted Experience consent, describe a manual success or failure/correction, inspect the exact preview and confirm its token and operator-only acknowledgement. The existing core records four linked events and one bounded, restart-expiring receipt; no skill is executed and no core/private file is written by this flow. The result links directly to the evidence inspector. Viewing never creates consent; archived, restored and unprovenanced skills remain blocked. [Workflow and limits](NATIVE_MACOS_ROADMAP.md#ev-04-manual-skill-outcomes--native-0240).

**Skill Evidence And Lifecycle (0.23.0):** open **Library and Core > Skills > a skill > Results and lifecycle**. The read-only sheet distinguishes verified durable apply/archive/restore metadata from current-conversation, process-memory manual-use outcomes. It reuses the core's exact provenance/outcome/restore checks, excludes stale pre-restore results, leaves legacy history unknown and links the source lesson. No pilot is started, event created, command run, usage counter incremented or file written. A candidate result is not a quality guarantee or automatic lifecycle decision. Global libraries remain shared; detailed process events may disappear on restart. [Workflow and limits](NATIVE_MACOS_ROADMAP.md#ev-04-skill-evidence-and-lifecycle--native-0230).

```bash
scripts/build_native_app.sh
scripts/run_native.sh
```

The separate `dist/Proto-Mind Native.app` provides searchable/renameable/archiveable conversations grouped by their bound folder, per-chat drafts, Markdown/code blocks, a memory/evidence inspector, the existing command catalog, and native model settings. The quieter layout has right-aligned user bubbles, unboxed answers, and model/access controls inside the composer. The old PySide `.app`, CLI, and tkinter fallback remain available.

**Native Cube Icon (0.21.1):** the app now has its own dimensional silver/teal cube mark with real transparent corners. The versioned PNG master builds locally into all ten standard ICNS representations, without depending on the old PySide app or generating images at runtime. See [artwork, generation prompts and packaging](assets/NATIVE_ICON.md).

**Native appearance and model controls:** the sidebar uses macOS behind-window material with a Reduce Transparency fallback. System text uses a 14-point base, code uses 12 points. The composer has separate Model and Effort submenus with checked choices and reset; settings share the same per-conversation selection. Models and supported reasoning levels come from the official Codex catalog and are revalidated before generation in both chat and Full Mac modes. Unsupported/stale choices fail without a silent fallback. Model availability can differ from Codex Desktop; entries and speed promises are never fabricated. Selecting effort never grants tools or enables Context Injection.

**Codex CLI compatibility (2026-08-31):** the personal Mac installation was updated from 0.136.0 to the stable 0.151.0 release. The same separate subscription profile now advertises 5.6 Sol (default), Terra and Luna; Sol exposes low/medium/high/xhigh/max/ultra. Real tool-free Sol replies at medium/max/ultra and one read-only terminal smoke passed through the existing adapter, without code changes or credential migration. Subagents remain disabled; accepting `effort=ultra` does not claim Desktop's multi-agent behavior. Existing per-chat overrides are preserved; restart Native after a CLI update, then refresh its model menu. See [runtime acceptance and rollback evidence](NATIVE_MACOS_ROADMAP.md#codex-cli-refresh-2026-08-31).

**Mode-bound durable Codex sessions (0.14.1):** each Native conversation may have separate provider threads for isolated Chat and explicitly granted Full Mac. The first Codex message in each mode uses non-ephemeral `thread/start` and bootstraps at most 12 bounded local chat messages once; later turns in that same mode use `thread/resume`, including after a Native/bridge restart, without prepending local history again. This prevents a Chat thread's permanent no-tools developer instruction from disabling tools after switching to Full Mac, and prevents a Full Mac thread from leaking authority into Chat. Legacy v1 bindings are retained as historical identifiers but are never guessed or resumed as either mode. Resume still revalidates the exact thread ID, workspace identity, cwd, sandbox, approval policy and loaded instruction sources. Failure or drift stops visibly and never creates a hidden replacement. Model Settings shows available mode sessions and offers a destructive, separately confirmed **Start New Codex Session** action; this removes all local bindings for that Native conversation, not Native chat history or old Codex rollouts. Full Mac permission remains in-memory and must be enabled again after restart. See [durable-session contract](NATIVE_MACOS_ROADMAP.md#durable-codex-sessions--native-0120).

**Live Web Search (0.13.0):** the same explicit, nonpersistent Full Mac grant enables Codex live Web Search in addition to terminal/network access. The default chat process still receives `web_search=disabled`, no shell and a read-only/no-network tool policy. Full Mac receipts project only a bounded query, action type and sanitized HTTP(S) page location; raw result payloads are not copied into Native history. Search pages are untrusted data. Version 0.13.0 itself did not include interactive screen control. See [internet-search contract](NATIVE_MACOS_ROADMAP.md#full-mac-live-web-search--native-0130).

**Computer Use (0.14.0):** the existing explicit, nonpersistent Full Mac grant can now use the locally installed OpenAI Computer Use service to inspect and operate visible macOS apps. Proto-Mind does not copy or redistribute that proprietary runtime: before every eligible process it resolves the canonical installation, verifies the OpenAI Developer ID/team and bundle identities, then configures exactly one required MCP server with ten allowlisted UI tools. Normal chat keeps `features.computer_use=false` and an empty MCP map. Startup refuses an unexpected server/tool inventory before a model turn. The work timeline records only tool type, bounded app name, status and a privacy note; screenshots, accessibility trees, coordinates, typed values, selected text and raw MCP results are omitted from Proto-Mind history. Visible screen content can still be processed by OpenAI during the turn. Stop/Esc requests takeover but cannot undo prior clicks, typing, submissions or other side effects. See [Computer Use contract](NATIVE_MACOS_ROADMAP.md#full-mac-computer-use--native-0140).

Live 0.14.1 acceptance migrated the affected personal binding from ambiguous v1 history to a separate Full Mac thread. The first read-only turn invoked `list_apps` and `get_app_state`; the Computer Use runtime disclosed that ChatGPT was running but protected its own app state from inspection. A second turn resumed the Full Mac thread and successfully read Finder state with `get_app_state`, without clicks, typing, scrolling or file actions. This proves the original no-tools inheritance bug is fixed; it does not promise that Computer Use can inspect protected/self-referential application surfaces.

**Computer Use fresh-state guard (0.14.2):** Proto-Mind does not replay raw UI trees between turns, so each turn now tells Codex to use `disableDiff=true` on the first `get_app_state` call for each application. The guidance is injected into every current turn, including durable Full Mac threads created before this release. A timed-out app-state read must not be retried under another display/bundle alias in the same turn, and the MCP tool timeout is 30 seconds instead of 90. This avoids stale cross-turn diffs and duplicate three-minute stalls without adding a tool, permission, automatic UI action or screenshot fallback. Live acceptance with an ordinary Russian Safari request completed through the existing Full Mac thread with exactly one read-only `get_app_state` call in 334 ms and no click, typing or other UI action.

**Agent Contract and Automation onboarding (0.15.0):** before a Full Mac provider process starts, Proto-Mind now freezes a deterministic contract for the exact subscription provider, model/effort, canonical workspace identity, tool allowlist, limits, stop conditions, declared-criteria digest and separate operator acceptance. The connected Computer Use inventory is checked against that contract and both are shown as bounded evidence; they do not make provider completion equal verification. A dependency-free six-case eval set exercises the real guardrail path with `scripts/run_native_agent_evals.sh`. These ideas were adapted from the locally installed official OpenAI Developers plugin, but Proto-Mind still uses its existing ChatGPT-subscription Codex app-server: no Agents SDK runtime, API key, Platform connection or Deployment Manager was added.

The personal app also explains macOS Computer Use error `-1743` as an Automation permission denial instead of persisting opaque MCP output. Bundle metadata now declares the Apple Events purpose, and the error banner can open **System Settings > Privacy & Security > Automation** for an explicit operator decision. Proto-Mind never flips that setting, retries the failed UI action or fabricates success. Existing installations may need one new Full Mac attempt and one macOS approval after installing/relaunching 0.15.0.

**Local capability contracts and Computer Use lifecycle (0.16.0):** the Native Library now reaches the same local stores through two exact typed callbacks, `search` and `fetch`, carried only over the existing private stdio bridge. Each result has validated `structuredContent`, a bounded text fallback and local-only metadata; schemas reject undeclared inputs and explicitly declare no network, model dispatch or store mutation. Swift validates the envelope before rendering and falls back to the older direct read RPC only when an older bridge lacks the new method. This borrows the useful typed tool/result discipline from ChatGPT Apps without adding public MCP, a web app, Platform/API-key auth, Node dependencies or model-callable tools.

**Controlled Brother Persona (0.19.0):** **Model Settings > Brother Persona** now exposes a two-step opt-in rather than a personality slider. The first click obtains fresh read-only readiness evidence; a second explicit confirmation must match its stable activation fingerprint before the private preference is enabled. Each later normal Codex/Ollama Send recomputes the current provider/model/workspace/access evidence, rechecks independently disabled Context Injection immediately before prompt construction, compiles exactly one snapshot from memory already selected by the existing coordinator, and returns a hash-verified in-memory turn receipt. Codex receives that context as its existing `baseInstructions`; Ollama receives it as the existing per-request system message. No second retrieval or model call, hidden store write, permission, tool, Context Injection change, facet or provider-specific identity is added. Mock, operator commands, unresolved Codex models and stale/unsafe readiness fail before provider dispatch. **Return to legacy prompt** is immediate for the next turn and changes only the private preference; it cannot erase earlier durable Codex thread content. Persona Inspector remains the detailed preview/readiness/receipt surface. Foundation, readiness and runtime activation evals are deterministic and local.

**Cognitive Memory Loop v1 / Persona 0.3.1 (0.20.0):** memory cards now show **Почему Proto-Mind это знает**. Embedded supervised-learning provenance is rechecked against its exact schema, record payload and deterministic hash; ordinary operator/legacy memories show `UNAVAILABLE` rather than an invented source chain, while malformed/tampered metadata shows `ERROR`. The completed-turn evidence inspector can open the exact memory record when its bare ID is unambiguous. **Кандидаты опыта** opens a read-only Memory Workshop over an already-existing, explicitly consented Experience pilot: it displays bounded correction/reflection/grounding candidates and only prepares existing `/experience` review commands in the composer. It never starts capture, changes consent, runs a command, promotes a lesson or writes a store. Workspace identity is displayed as current context, but the existing persistent/working stores remain global legacy stores; project isolation is explicitly **not** claimed. Persona rollback is now regression-tested on the same durable Codex thread: the immediately following `thread/resume` receives the exact legacy instruction bytes without an app restart.

**Supervised Lesson Review (0.21.0):** **Кандидаты опыта > Разобрать урок** now exposes the existing core decision, proposal and one-lesson apply gates without composing slash commands. Each stage has its own read-only preview and exact typed confirmation; acceptance/rejection and proposal creation change process memory only. The operator explicitly selects 1-20 active reference IDs, then separately acknowledges that an applied lesson enters shared global memory, not project-isolated storage. Only final apply appends one `memory.lesson.v1` record through the existing core writer, verifies it and displays the receipt/source chain. No model, tool, network, automatic capture/promotion, skill writer or context toggle is invoked. Source/store drift, missing evidence, expired proposals and repeated apply fail closed; the Native bridge permits one successful lesson apply across all its conversations. Decisions/proposals/detailed receipts expire with the bridge process, while the applied lesson's embedded provenance survives restart. The strengthened shared writer preserves unknown legacy fields and restores original bytes on a safely recoverable failure; it does not migrate existing records or provide a cross-process transaction lock. [Workflow and limits](NATIVE_MACOS_ROADMAP.md#ev-04-supervised-lesson-review--native-0210).

Public work-log snapshots now carry a monotonic `state_version`; Native discards stale same-run events while keeping older unversioned history readable. The version contains no hidden reasoning. Full Mac Computer Use also installs the signed OpenAI client's official `turn-ended` notify hook. The shared desktop service may remain resident for ChatGPT, but normal Proto-Mind turn completion now tells it to release active capture/UI state instead of relying only on app-server process exit. Chat and Full Mac without verified Computer Use retain `notify=[]`.

**Visible work:** an expandable timeline shows public Codex commentary, public plans, observed tool actions and elapsed time during and after a turn. It is not private chain-of-thought: raw reasoning, reasoning-summary payloads and internal/background prompts are never copied into this timeline. Commentary is separate from the final answer; the optional Native history v3 field is not replayed to the model or sent to core memory evaluation. Monotonic live `state_version` values prevent an older same-run event from replacing a newer one; older unversioned saved logs remain display-compatible. Providers without public progress show an honest waiting state; older conversations do not acquire invented history. Stop retains partial evidence when possible, not an automatic rollback.

**Hover feedback:** buttons, icon actions, model/access menus and disclosure rows share a restrained highlight and outline, with a stronger pressed state. The model menu's highlight now fits its intrinsic label width with a 32-point minimum height, not the empty space beside it. Hover does not resize controls; disabled controls do not advertise interaction. Reduce Motion is respected, and the height-bounded sidebar is preserved.

**Reliable work sessions:** the toolbar clock opens a private per-conversation work journal. New normal turns save a bounded intent, a pre-dispatch record, public progress/tool previews and the final response preview under `~/Library/Application Support/ProtoMindNative/work_sessions/`. A crash or lost completion leaves a visible unknown outcome, not a success claim or automatic retry. Response receipt, goal verification and operator acceptance are separate. The journal continuation button only prepares an editable recovery draft; it never starts a provider turn, replays tools, restores Full Mac permission, or reattaches files. A later explicit Codex Send may resume the conversation's durable provider thread under the current policy. Old conversations are not migrated. See [EV-01 storage, failure and backup limits](NATIVE_MACOS_ROADMAP.md#ev-01-reliable-work-sessions--native-070).

**Context before Send:** the composer's Context button opens a local-only desk with the provider destination, cloud-consent state, exact selected UTF-8 excerpts, expected/current hashes and bounded history. Changed/missing files are flagged, never silently reselected; Send still revalidates hashes. Workspace files and shared core memory are explicitly different scopes. Recall/correction context is selected during the turn, not simulated by this preview; the completed-turn inspector remains the evidence source. Full Mac may read additional files after Send. No model call, permission grant, store write or Injection toggle happens in the desk.

**Results, not guessed success:** open the work journal, select a run, then Results. Observed file changes have a run/tool reference, captured completion SHA where available, original attachment hash if known, a saved diff fragment and manually refreshed current text. Later edits are visibly stale; old/interrupted records never gain invented historical hashes. Command output/exit codes and the model's answer are separate from unassessed automatic goal verification and any manual operator assessment. Preview is plaintext, including HTML/scripts. New ordinary turns extend the private run record with compact manifests/hashes; viewing writes nothing. Scanned/visual PDF inputs, richer media artifacts, restore and cross-project memory isolation remain separate EV-02 follow-ups. See [EV-02 contracts and limits](NATIVE_MACOS_ROADMAP.md#ev-02-context-and-artifact-desk--native-080).

**Criteria and manual acceptance:** the checklist button beside Context opens **Готово, когда…**. Save up to eight one-line criteria for the next normal message, inspect them in Context, then Send. They are frozen in the private run and passed to the selected Codex/Ollama adapter as operator requirements, not tool permission; Mock does not evaluate them. Operator commands skip and retain the draft criteria. In the work journal's **Приёмка** tab, personally check each criterion, choose accepted/needs work, preview the exact assessment, and confirm its private save. Acceptance requires a normally completed run, all criteria marked met, unchanged workspace identity and matching observed completion hashes. Changed/unknown evidence refuses acceptance. The writer changes one private run only, keeps earlier assessments (limit 12), and never launches a command, model, repair or memory promotion. This is manual assessment, not automated verification or a signature of operator identity. See [review storage, safety and legacy limits](NATIVE_MACOS_ROADMAP.md#ev-02-criteria-and-manual-acceptance--native-090).

**Images and saved screenshots:** use the composer's **+ > Изображение или скриншот…**, inspect the image locally, then explicitly attach it. PNG/JPEG only: up to three images, 4 MiB each / 8 MiB total, at most 24 megapixels each. Thumbnails, dimensions and source hashes are visible before Send; changed/missing sources are refused instead of silently substituted. Selected image bytes reach OpenAI only on normal Send with existing cloud permission and a Codex model that explicitly advertises image input. This works in isolated Chat without granting file tools; Full Mac keeps its separate permission. Ollama/Mock image sends are refused, not silently converted to text or cloud.

**Drag and drop:** drop one local PDF, PNG/JPEG images or supported UTF-8 files onto the chat or directly into the composer. PDF opens its page selector; other files open a batch preview. Attach adds the selection to the draft, and Send is still separate. Up to three images and three text files can be selected; text files must already be inside the conversation's bound workspace. A PDF must be dropped separately, but can coexist with these attachments in the draft. A rejected gesture changes nothing. Web links, file promises and unsupported formats are not silently imported. Drop never changes the working folder or grants tools/cloud access.

**PDF page text (0.11.0):** drop a PDF or choose **+ > PDF**, review page 1 locally, then select up to eight pages (for example `1-3, 7`) and click Read pages. Attach selected text, then Send when ready. One PDF up to 8 MiB / 300 document pages; at most 3,000 Unicode characters from each selected page. The exact extracted text and any truncation/empty-page warnings are shown before attachment. Apple PDFKit runs in a separate bounded local worker, with network and file writes denied. Source and selected-text SHA-256 are checked again at Send. Codex receives only selected text after the existing cloud opt-in; Ollama uses the same text locally; Mock does not analyze PDFs. No original PDF upload/cache, OCR, password/copy-restriction bypass, unselected-page inclusion or automatic PDF replay. History v5/journal save metadata only; existing v1-v4 history loads without rewriting. Model answers can still quote document text and are normal chat history, not a redacted export. See [PDF boundaries](NATIVE_MACOS_ROADMAP.md#ev-02-selected-pdf-page-text--native-0110).

**Attachment recovery (0.10.1):** saved-image notices and attachment strips no longer expand the split layout offscreen after restart. The image picker is a nonblocking sheet. Finder-launched Codex can find its Homebrew Node runtime even with a minimal macOS `PATH`; an early CLI exit now reports a startup problem rather than a fabricated provider/sign-in error. Existing drafts, failed messages and run evidence are preserved, never automatically resent. See [recovery and drop verification](NATIVE_MACOS_ROADMAP.md#attachment-recovery-and-drop--native-0101).

**Historical run notices (0.10.2):** close an old unfinished-request banner with its X button, or hide/show it from that run's journal card. This explicit display preference survives restart in private conversation history; it never deletes, retries or accepts the run. Opening the banner selects the affected run, not the newest reply. Changed/new run evidence warns again; storage diagnostics remain visible. The Acceptance tab explains why an unfinished request cannot be assessed instead of showing a disabled form. Completed replies without predeclared criteria offer rework-with-comment only; accepting declared criteria keeps the existing preview/confirmation and evidence checks. See [notice and review verification](NATIVE_MACOS_ROADMAP.md#run-notices-and-review-availability--native-0102).

Opening/cancelling a preview writes nothing. Explicit attachment saves only private Native history-v4 metadata, never image bytes or data URLs; the work journal also keeps metadata only. Older v1/v2/v3 history loads without rewriting. Old images are not automatically read or resent from chat history or continuation: reattach them when needed. Originals and embedded metadata are sent unchanged, with no automatic redaction, compression or OCR. Operator commands bypass images; no screenshot capture, clipboard import, core Injection change or new slash command is added. A real 5.6 Sol smoke correctly described a synthetic image's colored shapes; this is not a general vision-quality benchmark. See [image privacy, compatibility and evidence limits](NATIVE_MACOS_ROADMAP.md#ev-02-selected-image-inputs--native-0100).

**Supervised Skill Workshop (0.22.0):** in Memory, open a persistent verified lesson and choose **Create skill from lesson**. The local form requires an operator-written name, summary, trigger, preconditions, steps, permission requirements, verification and failure modes; it never invents a procedure or calls a model. Preview and type the first exact token to retain the authored contract in process memory. Then independently preview the exact future skill and type its different token, acknowledging the shared global library, to append one non-executable `skill.procedure.v1` record through the existing core writer. A successful save shows its verified receipt and opens the skill's durable provenance/source lesson. Edited fields, source/store drift, stale tokens, duplicate skills, another conversation/workspace and a used Native apply slot refuse without automatic retries. Form drafts and detailed authoring/apply receipts expire on restart; embedded skill provenance remains inspectable. Permission text does not grant tools and a saved skill does not run. [Workflow and limits](NATIVE_MACOS_ROADMAP.md#ev-04-supervised-skill-workshop--native-0220).

**Native library:** expand the sidebar's Library and Core group, then open Memory, Goals, or Skills for literal text search, current/history/all filters, and source-backed detail cards. Native 0.16.0 routes those reads through exact typed local `search`/`fetch` contracts and validates their structured result envelopes before rendering. These views read the existing Proto-Mind core stores, not the conversation's bound source folder. Viewing never calls a model, runs commands, updates usage counts, initializes missing stores, saves navigation state, or attaches records to a prompt. Source errors, omitted records, truncation, and changed-since-list details are visible. Learned lessons and procedural skills now reuse their existing provenance verifiers; legacy or invalid evidence is never presented as verified, and hash consistency does not prove truth. Refresh is manual. The lesson card opens a separate supervised Skill Workshop; it is not an inline edit or execution control.

**Checkpoint coverage:** `/memory backup` now includes native source/tests, scripts, root Markdown documentation and the existing Python/data/export package, while excluding build caches. Completed archives are private and never overwrite a same-second checkpoint. Native conversations/preferences/work-session evidence, `codex_threads.json`, and explicitly created `learning_history/` and `project_memory/` outside the project still require a separate private backup. The binding file alone does not back up Codex rollouts; credentials and provider history remain managed in the private Codex profile. Never copy that profile into source or publish private archives.

**Local by default:** Ollama on this Mac, with Mock only when explicitly selected. Optional ChatGPT/Codex subscription access uses the official Codex CLI browser-login flow and a separate profile. Subscription inference is cloud processing, not offline: an explicit cloud permission is stored on this Mac and can be revoked in settings or by signing out. Missing/corrupt settings never grant access. No API-key fallback or automatic Context Injection enablement is added.

**Explicit Full Mac mode:** select Codex, bind a working folder, then use the tool-access menu inside the composer and its separate confirmation. Normal chat stays isolated and tool-free. Full Mac enables real Codex shell/file tools, networking, live Web Search and, when the signed local service is available, Computer Use with your macOS user rights. It is not a sandbox or root grant. There is no per-action approval in this mode. File/tool/screen content can be sent to OpenAI. The permission is held only in memory for that conversation/folder, resets on restart, and can be switched off. Changing provider/folder, revoking cloud permission, or a failed agent turn discards the UI grant. Tools do not start simply from login, file browsing, or a saved conversation.

The activity panel shows command status/exit codes, bounded output/edit previews and privacy-reduced Computer Use actions; completed or failed runs are retained in Native history v5, not core stores. Stop/Esc requests interruption, never rollback. There is no automatic retry, background scheduler, arbitrary MCP/hooks, or extra slash-command dispatcher. Full-access shell and Computer Use remain broader than the old core command gates; checkpoint and consequential-action instructions are guidance, not a universal policy broker. Existing successful-turn memory evaluation still applies. Do not use Full Mac for untrusted tasks without reviewing scope.

**One real working folder:** bind the same project directory used in Codex. The native file browser reads current files on manual refresh without copying, syncing, or editing them. Preview then explicitly attach up to three UTF-8 source excerpts (6,000 characters each); SHA-256 is rechecked before sending. Private core stores, exports, credentials, generated paths, and symlinks are excluded. A folder binding is not permission for the model to run tools or inspect other files.

Live acceptance on 2026-08-31 verified the separate subscription profile, chat/file attachment replies, and a Full Mac adapter turn confined by the test request to a disposable directory: checkpoint, file edit, then two terminal checks with actual output. All 48 personal core-store/export hashes remained unchanged and Context Injection stayed disabled. This is a narrow functional smoke, not certification of arbitrary shell safety or every available model.

See [`NATIVE_MACOS_ROADMAP.md`](NATIVE_MACOS_ROADMAP.md) for architecture, launch requirements, private-state locations, safety boundaries, verification limits, and next steps. Native checks: `scripts/test_native.sh`.

The curated [Personal Agent Evolution roadmap](PROTO_MIND_EVOLUTION_ROADMAP.md) separates delivered EV-01 recovery, the EV-02 desk, manual assessment, selected-image/PDF inputs and explicit Full Mac Computer Use from remaining visual-document/project-scope work, scoped tools, Native learning/skills, OCR and voice. Arbitrary plugins and automation remain disabled; the external blueprint does not authorize a rewrite or new permissions.

The [DeepSeek Harness adoption review](DEEPSEEK_HARNESS_ADOPTION_REVIEW.md) compares the official MIT-licensed Developer Preview with Proto-Mind at an exact upstream commit. Proto-Mind does not embed that runtime. The extracted pure-Python Session Spine now spans exact P1 Native projection, P2a-P2f detached storage/transfer/composition/audit evidence and the isolated P2g forward writer/read pilot. P2g accepts only one explicit store, stable owner, exact message pair, current work-session fingerprint and persisted Turn Lineage reference. It produces a self-hashed CAS plan, commits one complete turn batch, verifies exact post-state, restores the preimage after ordinary in-process write failure and treats an already identical turn as a no-write replay. Its content-free dual-read report keeps historical `legacy_unlinked` evidence separate from newly typed turns and never infers backfill. This is not Native activation: no bridge/UI/command/default personal path was added, process death can still leave an `UNKNOWN` tail for manual recovery, and chat/work-session/spine persistence is not yet one cross-store transaction. P2d exact-content bundles remain private and not publication-safe.

The delivered [Persona Engine layers](PERSONA_ENGINE_PLAN.md) define Brother as one continuous model-independent personality. A strict checked-in kernel, immutable hashed snapshots, a read-only Identity projection, source-linked selected-memory references, an explicit non-authorizing self-model, provider-parity gates and controlled activation live in `proto_mind/persona_engine.py`, `proto_mind/persona_activation_readiness.py` and `proto_mind/persona_activation.py`. They deliberately exclude user-selectable facets, personality modes and trait sliders: adaptation follows the current task, evidence and risk, while existing identity, memory provenance and permission systems remain the sources of truth. Production projection is available only in Native after explicit opt-in and fresh per-turn gates; Persona remains off in the current personal preference until the operator enables it.

## OpenAI Build Week Disclosure

Proto-Mind existed before the OpenAI Build Week submission period and is submitted as a meaningfully extended existing project, not as a project created entirely during the event. The accepted pre-contest baseline is the timestamped July 11 checkpoint with SHA-256 `50a39b36aca72e1ae74ad8afe80004bfac1fe1eb3c66a2f168519246a680d4df`.

- [`BUILD_WEEK_PROVENANCE.md`](BUILD_WEEK_PROVENANCE.md) separates prior work from Build Week additions.
- [`CODEX_COLLABORATION.md`](CODEX_COLLABORATION.md) explains operator decisions and Codex/GPT-5.6 contributions.
- [`contest/README.md`](contest/README.md) documents reproducible baseline/current SHA-256 manifests and the contest delta.
- [`LICENSE`](LICENSE) releases the source under the Apache License 2.0.

The comparison excludes private runtime stores, exports, logs, backups, and secrets. The actual primary Codex `/feedback` Session ID is recorded in the provenance and collaboration documents; it was supplied by the operator from the feedback result rather than inferred or fabricated.

Repository publication boundaries, resolved path leaks, intentional redaction fixtures, and remaining pre-publication decisions are documented in [`REPOSITORY_PRIVACY_REVIEW.md`](REPOSITORY_PRIVACY_REVIEW.md).

Build Week demo video: [Proto Mind](https://youtu.be/CHr4GJj19tI).

## Build Week Judge Quickstart

Proto-Mind can be evaluated locally without rebuilding a package, creating an account, or connecting a cloud service. The deterministic mock backend is included.

Supported evaluation path:

- Python 3.11+.
- macOS for the PySide desktop and local `.app` launcher.
- The CLI is dependency-free and uses POSIX helper scripts; Linux is expected to work but the submission baseline was verified on macOS.
- Ollama is optional. It is not required for tests or the deterministic showcase reports.

```bash
git clone https://github.com/iskillcapped-gif/proto-mind.git
cd proto-mind
scripts/which_python.sh
scripts/run_tests.sh
scripts/run_cli.sh
```

Then run:

```text
/showcase status
/showcase demo
/showcase doctor
/exit
```

On a fresh public clone, `/showcase status` can report `BLOCKED` and `/showcase doctor` can report `WARN`. This is the expected fail-closed state: private identity, memory, warning-ledger runtime records, and other local stores are intentionally not published. The commands should still complete cleanly, report Context Injection as disabled, expose the fixed four-command read-only runner allowlist, and perform no mutation. The submitted video demonstrates the populated local operator state without publishing personal data.

For the contest UI:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-ui.txt
scripts/run_pyside_mock.sh
```

Open the `DEMO RUNWAY` tab and follow buttons `01` through `12`. Exact consent and runner controls remain locked until their preceding preview generates the correct process-bound command.

Current development verification baseline: Python 3.11, 1595 unit tests plus 429 native checks and 7/7 + 7/7 + 8/8 Persona foundation/readiness/runtime evals, 387 registered command prefixes across 41 categories, Context Injection disabled, no persistent live Experience capture, and a four-command fixed read-only core runner allowlist. The separately granted Native Full Mac + Internet + Computer Use adapter is not that core runner. Post-contest native work is separate from the submitted provenance baseline.

### Codex And GPT-5.6 Collaboration

Proto-Mind existed before Build Week as a local memory, command, and safety prototype. During the submission period, the operator used Codex/GPT-5.6 to inspect that baseline, design bounded milestones, implement and test cognitive continuity hardening, typed Experience provenance, exact-consent capture, explainable episodes, supervised memory/skill learning lifecycles, and the contest Demo Runway. The operator chose the product direction, autonomy limits, privacy rules, and whether each milestone could proceed; Codex handled repository analysis, implementation, regression testing, failure diagnosis, and documentation. The exact baseline/current distinction and reproducible SHA-256 evidence are in [`BUILD_WEEK_PROVENANCE.md`](BUILD_WEEK_PROVENANCE.md), with the collaboration narrative in [`CODEX_COLLABORATION.md`](CODEX_COLLABORATION.md).

Copy-ready Devpost text, testing instructions, repository URL, and the final submission checklist are in [`DEVPOST_SUBMISSION.md`](DEVPOST_SUBMISSION.md).

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

Local Capability Contract v1 adds an MCP-compatible data shape without installing or exposing an MCP server. The exact four-command read-only runner allowlist is projected into zero-argument contracts with input/output schemas, `readOnlyHint`, `destructiveHint`, `openWorldHint`, and `idempotentHint`. Local results use explicit `structuredContent`, `content`, and `_meta` channels. `/capabilities status`, `/capabilities map`, `/capabilities safety`, and `/capabilities doctor` expose and validate this layer. Transport remains `none`: there is no network listener, public endpoint, tunnel, OAuth flow, external widget, new dependency, or additional executable target.

Local Typed ViewModel v1 consumes that same three-channel result envelope only inside the PySide presentation layer. Exact `/warnings unknown`, `/daily doctor`, `/exports doctor`, and `/capabilities safety` responses render as escaped local/read-only cards with their full text report preserved. Any alias, arguments, unknown command, malformed envelope, unsafe metadata, or rendering failure falls back to the existing text renderer. CLI, tkinter, shared command handling, runner scope, stores, and network behavior are unchanged.

## Local Cognitive Turn Envelope

v3.6a adds a local typed projection of the single `InteractionResult` already produced for a normal conversation turn. `DesktopRuntime.process_with_envelope(input)` is an alternative to `process(input)`, not a second call for the same input. It returns `InteractiveResponse` with the unchanged formatted `text` and an optional immutable `cognitive_turn`; `to_dict()` returns detached JSON-ready data. The shared-handler equivalent is `process_interactive_input_with_envelope`.

The envelope contains the full answer, Observer classification, retrieved memory IDs and bounded previews, retrieval mode, actual memory-decision IDs, existing grounding/reflection findings, previous correction hints, and compact Context Injection state. Retrieved records are explicitly not proof that the model used them. Missing audits remain unknown (`null`), rather than being presented as successful checks.

Projection does not invoke a model, read a store, persist a record, or capture Experience again. Normal-turn memory/log/consented Experience behavior still occurs once under the existing rules; the entire conversation is not made read-only. Operator commands and exit responses have no cognitive envelope. Projection failures preserve the original text with a separate generic warning and never retry a completed turn. The payload omits full store snapshots, raw input fields, provenance blobs, and the injected prompt, but preserves the answer verbatim: it is not a privacy-redacted export or a trust/authorization boundary.

The envelope adds no slash commands, server, network integration, or dependency. CLI and tkinter retain the existing text API. Context Injection remains unchanged and disabled in the verified local configuration.

## Cognitive Turn Card

v3.6b connects the envelope to PySide6 Cognitive Control Room v2.3.0. Each worker calls `process_with_envelope` once. Compact normal replies show the complete answer, backend/intent, existing grounding/reflection signals, actual memory-decision IDs, up to three retrieved memory previews, and bounded warnings/correction hints with explicit omitted counts. Missing evidence stays UNKNOWN; retrieval and deterministic checks are not proof of correctness or authorization. HTML is escaped, and text such as `Observer:` inside an answer is no longer mistaken for a debug delimiter.

Context Injection and Experience notices come from the same original formatter and remain visible without parsing the answer. Turn projection, view-model construction, and rendering never run the reasoner again, write stores, or capture Experience again. Normal-turn effects still follow the existing rules. Slash/natural operator commands keep their existing text or four-contract cards. Malformed or stale envelopes and renderer failures fall back to the original text path with a generic notice, without retrying the turn.

Enable **Debug output before a turn** to use its full original text trace instead of the compact card. This does not retroactively change earlier messages; per-message raw-view controls and clickable memory inspection are future work. Card previews are local display data, not a redacted export. Restart an already-open `.app` to load the new presentation code.

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

v3.4h adds restart-safe read-only lifecycle inspection over persistent learned lessons. `/experience learning lifecycle-audit-status`, `lifecycle-history [--all]`, `lifecycle-inspect <memory_id>`, and `lifecycle-audit-doctor` distinguish active, v3.4g rejected/superseded, operator-forgotten, unclassified inactive, and invalid states. Doctor verifies immutable provenance, lifecycle timestamps, replacement existence/activity/provenance/age, unique IDs, and acyclic replacement references. The history view explicitly reconstructs current durable state rather than claiming an append-only event log. It performs no repair, reactivation, rollback, receipt invention, store write, command execution, or Context Injection change.

v3.5a adds a read-only procedural skill authoring contract over that verified lifecycle state. `/experience learning skill-contract-status`, `skill-contract-preview <memory_id>`, `skill-contract-template <memory_id>`, `skill-contract-checklist <memory_id>`, and `skill-contract-doctor` accept only one active provenance-verified learned lesson, fail closed on lifecycle/provenance/store problems, and reject exact active Skill Library duplicates. The deterministic `skill.procedure.contract.v1` draft binds its source record and provenance by SHA-256 and requires the operator to author trigger, preconditions, steps, permissions, verification, and known failure modes. It remains incomplete, non-executable, and non-promotable; no procedure is synthesized, accepted, stored, or run, and no skill writer or apply command exists.

v3.5b adds exact operator authoring without adding a Skill Library writer. `/experience learning skill-authoring-confirm-preview <memory_id> <authored flags>` revalidates the v3.5a source and prints every authored trigger, precondition, step, permission, verification rule, and failure mode plus a token bound to the complete source-and-contract hash. `/experience learning propose skill-contract <memory_id> <token> <identical flags>` reuses the existing confirmation-required process proposal gate and records one immutable receipt per lesson, with at most 16 receipts per process. Status, list, inspect, and Doctor views detect receipt tamper and current source/duplicate drift. Receipts expire on restart and always remain `future_apply_ready=false`, `executable=false`, and `skill_mutation_performed=false`; no skill, memory, event, queue, export, session log, model call, or Context Injection state is changed.

v3.5c adds read-only `/experience learning skill-apply-readiness <receipt_id|memory_id>`, `skill-apply-plan <receipt_id|memory_id>`, and `skill-apply-doctor`. Readiness revalidates the complete v3.5b receipt against the current active lesson, durable provenance, base/authoring/payload hashes, every current Skill Library record, deterministic future record ID, active and archived exact duplicates, and the current target-store SHA-256. The plan requires a separate apply confirmation, one atomic record mutation, post-write verification, 15 minimum receipt fields, and an explicit archive rollback suggestion. Readiness itself remains non-writing and generates no apply token.

v3.5d adds the first supervised procedural skill write, deliberately limited to one current v3.5b receipt per process. `/experience learning skill-apply-confirm-preview <receipt_id|memory_id>` repeats all current v3.5c checks and emits a second token bound to the source receipt, deterministic target payload, and exact current Skill Library SHA-256. Only the separately registered confirmation-required `/experience learning apply skill <id> <token>` gate may atomically append one `skill.procedure.v1` record. The pilot verifies every previous record, unique IDs, the exact new record and hash, unchanged persistent memory, and durable source provenance; failure restores the original Skill Library bytes. A hashed process-memory receipt exposes `/skills archive <created_id>` as manual rollback guidance. The stored procedure remains `executable=false`: no skill invocation, batch/automatic apply, shell, arbitrary dispatch, model/API call, session-log change, or Context Injection change is available.

v3.5e makes newly supervised-applied skills explainable after restart. The existing one-record writer now embeds a hashed `skill.procedure.provenance.v1` envelope containing the source lesson/provenance, base and authored contracts, fixed storage projection, both operator-confirmation fingerprints, and non-execution boundaries. Read-only `/skills why <id>` reports `VERIFIED`, `HISTORICAL`, `DRIFTED`, `UNAVAILABLE`, or `ERROR`; `/skills provenance-doctor` audits all provenanced records while treating ordinary operator skills as valid unprovenanced entries and older supervised records as explicit legacy warnings. Archiving preserves verification, while editing confirmed procedure fields is visible as drift. No skill execution, second writer, migration, repair, model/API call, or Context Injection change is introduced.

v3.5f adds read-only procedural skill outcome review without activating a skill runner. `/experience learning skill-outcome-review <skill_id>` accepts only an exact current-process manual-use anchor bound to the current skill and its verified durable provenance. Verified operator-reported success, failure, or correction evidence produces `SUCCESS_CANDIDATE`, `FAILURE_CANDIDATE`, or `MIXED_EVIDENCE`; missing evidence remains `NEEDS_MORE_EVIDENCE`, and the Skill Library `uses` counter is explicitly ignored as telemetry rather than proof. `/experience learning skill-outcome-doctor` checks trace, provenance, payload, Registry, and non-execution boundaries. The layer records no event, executes no procedure, updates no skill or score, calls no model/API, and leaves Context Injection unchanged.

v3.5g adds separately confirmed capture for an operator-reported manual procedure outcome. `/experience learning skill-outcome-capture-preview <skill_id> <success|failure> --evidence <text>` binds the current pilot session, verified skill provenance/payload, redacted compact evidence, and outcome into an exact token. Only `/experience learning capture skill-outcome ... <token> --evidence <identical text>` with active exact-session Experience consent appends one four-event `goal → plan → manual use → outcome` batch to the existing bounded process-memory buffer. Captures are run-once per exact blueprint, limited to 16 per process, inspectable through `skill-outcome-captures [<id>]`, diagnosed by `skill-outcome-capture-doctor`, and immediately reviewable by v3.5f. Proto-Mind never invokes the skill; no persistent store, score, usage counter, session log, model/API, shell, or Context Injection state changes.

v3.5h adds an exact operator decision after confirmed manual skill outcome review. `/experience learning skill-outcome-decision-preview <skill_id> <keep|revise|archive>` accepts only v3.5f decisive evidence fully backed by hash-valid v3.5g capture receipts: success permits `keep`, while failure or mixed evidence permits `revise` or `archive`. `/experience learning decide skill-outcome ... <token>` records one terminal receipt per skill, capped at 16 and discarded on restart. `skill-outcome-decisions [<id>]` and `skill-outcome-decision-doctor` keep the review/capture/decision chain inspectable and detect later evidence drift. Every receipt remains `future_apply_ready=false`; no keep/archive/revision action, Skill Library mutation, scoring, procedure execution, model/API call, shell, session-log change, or Context Injection change occurs.

v3.5i adds read-only `/experience learning skill-outcome-lifecycle-readiness|skill-outcome-lifecycle-plan <skill_id|decision_receipt_id>` and `skill-outcome-lifecycle-doctor`. The reviewer revalidates the exact terminal decision against current v3.5f evidence, every v3.5g capture receipt, durable skill provenance, the complete current skill record hash, and current Skill Library SHA-256. Future `keep` is constrained to a receipt-only byte-stable acknowledgement, `archive` to one atomic `active → archived` transition, and `revise` to a separately authored versioned replacement while the original remains active. Restore is explicitly manual review until a separate durable transition contract exists. Readiness itself generates no token, invokes no lifecycle writer, runs no procedure, and mutates no store or process receipt.

v3.5j adds a separately registered confirmation-required lifecycle gate for current `keep` and the original non-durable archive pilot. `/experience learning skill-outcome-lifecycle-apply-preview <id>` emits a token bound to the exact decision, current evidence/captures, complete skill record hash, and Skill Library SHA-256; `/experience learning apply skill-outcome-lifecycle <id> <token>` consumes the single process slot. Keep remains a verified byte-identical no-op. Since v3.5n, legacy archive without `--durable` fails closed rather than creating another ambiguous record. Revision, second apply, procedure execution, batch/generic dispatch, shell, model/API, and Context Injection changes remain unavailable.

v3.5k adds restart-safe, read-only procedural skill lifecycle inspection through `/skills lifecycle-status`, `lifecycle-history [--all]`, `lifecycle-inspect <id>`, and `lifecycle-doctor`. The audit reconstructs only facts present in `skills.jsonl` plus durable source-memory provenance: unchanged active supervised skills are verified, edited payloads are drifted, ordinary operator skills stay unprovenanced, and unsupported lifecycle metadata fails closed. An archived skill is deliberately `archived_ambiguous`: archive status survived, but the v3.5j process receipt and outcome cause did not, so the system never claims an outcome-driven transition without durable evidence. No lifecycle writer/schema, repair, migration, procedure execution, model/API call, or Context Injection change is introduced.

v3.5l design-locks a future `skill.procedure.lifecycle.v1` archive envelope without installing its writer. `/skills lifecycle-status --contract` prints the exact 25-field contract, deterministic example identity/hash, evidence-retention limit, and non-claims; the existing lifecycle Doctor verifies the example and proves a tamper fixture is refused. The detached builder permits only `active -> archived` with failure/mixed operator-reported evidence, bounded event IDs and capture hashes, exact confirmation fingerprint, `automatic=false`, and `procedure_execution_performed=false`. Even a structurally valid envelope found in `skills.jsonl` remains invalid/untrusted until a separately authorized writer exists. Keep remains a byte-stable no-op; restore/revision, migration, repair, persistence, execution, model/API, and Context Injection changes remain outside v1.

v3.5m extends the existing v3.5i commands with `/experience learning skill-outcome-lifecycle-readiness <id> --durable` and the equivalent `plan` option, adding no Registry prefix. For a current archive decision, the read-only reviewer binds exact decision/evidence/capture hashes, provenance, current skill/store hashes, all fixed v3.5l fields, four explicit write-time fields, and a deterministic metadata blueprint hash. The future plan permits one changed record and exactly `lifecycle`, `status`, and `updated_at`, requires atomic replacement, immutable provenance, unchanged memory, post-write metadata verification, a 21-field receipt, and exact-byte rollback. Keep reports no metadata or record mutation required; revise remains blocked. The current v3.5j writer is explicitly incompatible, and no token, writer, persistence, execution, model/API call, or Context Injection change is introduced.

v3.5n activates that archive contract behind the same Registry prefixes and an explicit `--durable` suffix. The preview issues a separate token bound to the current terminal decision, evidence, provenance, exact skill record/store hashes, metadata blueprint, and three-field mutation scope. A successful apply atomically replaces `skills.jsonl`, changes exactly one record and only `lifecycle`, `status`, and `updated_at`, verifies the embedded envelope plus immutable provenance and unchanged persistent memory, then records one fixed 21-field process receipt; any failed check restores the exact original bytes. The envelope lets `/skills lifecycle-*` recover `archived_verified` after restart without inventing expired process evidence. Legacy archive is redirected to the durable gate, keep stays byte-stable, and revise/restore require separate future contracts. No procedure execution, batch/generic dispatch, shell, model/API call, session-log change, or Context Injection change is introduced.

v3.5o design-locks restore without installing a writer. `/skills lifecycle-status --restore-contract`, `/skills lifecycle-inspect <id> --restore-readiness|--restore-plan`, and `/skills lifecycle-doctor --restore-contract` reuse existing Registry prefixes. Only a current `archived_verified`, provenance-current, non-executable skill without an active duplicate can reach `READY FOR RESTORE DESIGN REVIEW`. The future `skill.procedure.lifecycle.restore.v1` envelope describes `archived -> active`, embeds the complete verified archive envelope rather than erasing it, and fixes one-record `lifecycle/status/updated_at` scope plus a 21-field future receipt. Reactivation would mean operator-confirmed availability only, not procedure-quality proof. No token, writer, authorization, receipt, migration, store write, procedure execution, model/API call, or Context Injection change exists; direct `/skills restore` is not part of this supervised contract.

v3.5p closes direct status bypasses before any restore writer exists. `SkillLibrary.set_status` now refuses generic `/skills archive` and `/skills restore` whenever a record contains lifecycle metadata, including malformed or unsupported envelopes, and returns lifecycle inspect/readiness guidance without changing bytes or `updated_at`. This guard lives below CLI routing so internal callers cannot bypass it accidentally. Legacy provenanced records and ordinary operator skills without lifecycle metadata retain their existing archive/restore behavior, including the manual rollback path for newly authored skills. Registry count and policy classification are unchanged; no restore token/writer, migration, repair, procedure execution, model/API call, or Context Injection change is introduced.

v3.5q closes the remaining in-place payload and telemetry bypasses for lifecycle-managed skills. The shared `SkillLibrary` mutation boundary now refuses summary/body/tag edits, and `/skills use` refuses usage-counter and timestamp updates, whenever a lifecycle field exists, including malformed envelopes. Refusal happens before callback, timestamp, or file rewrite and points to lifecycle inspection; exact bytes remain stable. Pre-lifecycle provenance records and ordinary operator skills retain the original edit/tag/use behavior. Restore Contract/Doctor reports both guards as installed; Registry remains 387 commands across 41 categories, and no revision/restore writer, skill execution, migration, model/API call, or Context Injection change is introduced.

v3.5r adds read-only Durable Restore Authorization Readiness on the existing lifecycle prefixes: `/skills lifecycle-status --restore-authorization-contract`, `/skills lifecycle-inspect <id> --restore-authorization|--restore-authorization-plan`, and `/skills lifecycle-doctor --restore-authorization`. It reuses v3.5o current-state validation and binds the exact store/record/restore-blueprint hashes, prior archive identity, immutable record fields, one-record `lifecycle/status/updated_at` scope, exact-confirmation template, one-success future scope, 21-field receipt, post-write verification, unchanged memory, and exact-byte rollback into a deterministic authorization blueprint. No exact token is generated or accepted; authorization engine, run-once state, writer, persistence, restore mutation, procedure execution, model/API call, and Context Injection change remain absent.

v3.5s activates that design through one deliberately narrow supervised restore gate. `/skills lifecycle-inspect <id> --restore-apply-preview` prints a token bound to the exact current skill/store, authorization blueprint, restore metadata blueprint, and prior archive hashes; `/skills restore <id> <exact_token> --durable` may consume one such current token once per process. The atomic writer changes only `lifecycle`, `status`, and `updated_at`, embeds the complete verified archive envelope, preserves immutable procedure payload and provenance, proves persistent memory unchanged, reconstructs `active_restored_verified`, and emits a hashed 21-field process receipt inspectable through `--restore-apply-receipt`, `--restore-applies`, and `--restore-apply` Doctor. Wrong/stale/repeated/chained requests fail closed, and post-write failure restores exact original Skill Library bytes. Generic lifecycle mutation remains blocked; procedure execution, batch, revision, shell, model/API, session-log/export changes, and Context Injection changes remain unavailable.

v3.5t adds restart-safe receipt evidence inspection without pretending the process receipt survived. `/skills lifecycle-status --restore-receipt-contract`, `/skills lifecycle-history --restore-receipts`, `/skills lifecycle-inspect <id> --restore-receipt-audit|--restore-receipt-export`, and `/skills lifecycle-doctor --restore-receipts` reconstruct a separately hashed evidence artifact from the verified restore envelope and current record. Ten receipt fields are durably recoverable; eleven process-only fields remain explicit gaps. A live process receipt is compared when available, while missing-after-restart, legacy, orphan, duplicate, hash mismatch, and state drift remain distinguishable. The JSON view is copyable text only: no receipt/export file, writer, repair, re-archive/revision, procedure execution, model/API call, or Context Injection change is introduced.

v3.5u prevents restored skills from inheriting stale outcome conclusions. `/experience learning skill-outcome-review <id> --post-restore|--post-restore-plan` and `/experience learning skill-outcome-doctor --post-restore|--post-restore-contract` require every eligible manual-use anchor to be strictly newer than the restore timestamp and bound to the current provenance, restore metadata id/hash, and v3.5t evidence hash. Pre-restore and unbound post-restore events are excluded. Existing capture and keep/revise/archive decision paths fail closed for restored skills because they lack those fields, while ordinary skills remain compatible. Even exact new evidence is review-only: no capture/decision writer, token, lifecycle readiness, mutation, procedure execution, model/API call, or Context Injection change is introduced.

v3.5v adds a read-only future post-restore capture blueprint on `/experience learning skill-outcome-capture-preview <id> <success|failure> --evidence <text> --post-restore-readiness|--post-restore-plan` plus `skill-outcome-capture-doctor --post-restore|--post-restore-contract`. It requires active Experience Pilot consent and the exact current `active_restored_verified` skill, then binds Skill Library bytes, full record, provenance/payload, restore metadata/evidence, bounded operator evidence, the four future Experience events, required restore-bound `tool_called` fields, and a fixed receipt schema. The blueprint and current-state hashes are tamper/staleness checked, but no confirmation token, writer, append, receipt, procedure execution, lifecycle decision, persistent mutation, model/API call, or Context Injection change exists.

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

The local macOS `.app` launcher remains a machine-local wrapper, not a portable signed bundle. PySide6 Cognitive Control Room v2.3.0 gives it a local/private identity bar, a read-only Context Injection indicator, live Registry capability counts, four prompt chips, and two right-side tabs: the original twelve-action Control Deck and a numbered twelve-step contest Demo Runway. The runway drives the shared handler rather than bypassing it. Its Exact Consent and Exact Runner buttons remain locked until the immediately preceding preview/dry-run response contains the expected safe command; no token is generated by the UI, command chains are refused, and Context Injection is never toggled. Four exact local capability reports use typed cards, and normal turns use the Cognitive Turn Card described above, both with escaped output and text fallback. Shared CLI routing, normal reasoning, stores, and Context Injection behavior are unchanged.

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
/identity set style adaptive to the operator and current conversation
/identity add-value Evidence and useful outcomes matter.
/identity add-principle Use selected capabilities confidently toward the operator's goal.
/identity add-boundary Respect explicit stop, read-only, and scope constraints.
/identity history
/identity doctor
```

Active Identity items can be projected into an opted-in Brother Persona turn and into an explicitly enabled Context Pack. They shape operating posture but do not grant tools or permissions; authority comes from the current operator request and selected access mode.

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
