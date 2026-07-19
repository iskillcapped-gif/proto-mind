# Proto-Mind Architecture Map v2

Proto-Mind is a local-first cognitive architecture prototype for memory-aware reasoning. It is not a model training project, not a consciousness simulation, and not a polished chatbot product. The current system explores how an LLM-facing runtime can organize observation, memory, retrieval, reasoning, hygiene, and self-reflection around each turn.

The core distinction from a simple RAG wrapper is that memory is treated as part of the turn pipeline: incoming input is classified, memory need is estimated, memories are selected and scored, the reasoner receives structured memory context, memory updates are evaluated after the response, and a self-reflection layer inspects whether the response stayed faithful to active memory.

For short future Codex handoffs, use `PROTO_MIND_ARCHITECT_LEDGER.md` as the compact project brief.

## Current Module Map

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

Command Registry v1.0 adds `proto_mind/command_registry.py` and read-only `/commands status`, `/commands list`, `/commands explain <slash command>`, and `/commands doctor`. The static registry currently describes 361 command prefixes across 41 categories. Metadata includes description, read-only state, mutation target, risk, Natural Router availability, and notes. Doctor checks duplicates, invalid metadata, complete Natural Router target coverage, explicit context mutations, and high-risk route exclusion. Registry introspection never executes commands and is descriptive metadata rather than runtime authorization.

Action Safety Policy v1.0 adds `proto_mind/action_policy.py` and read-only `/policy status`, `/policy explain <slash command>`, and `/policy doctor`. It derives advisory classifications from Command Registry metadata: read-only low-risk commands are `auto_allowed`, mutating low/medium-risk commands are `confirmation_required`, high-risk commands are `operator_only`, and unknown/shell-like/chained inputs are `blocked`. Command bundles and Natural Router bundles inherit the strictest member classification. Policy v1.0 never executes commands, changes routing, or enforces authorization.

Action Preview v1.0 adds `proto_mind/action_preview.py` and read-only `/action status`, `/action preview <slash command or exact natural phrase>`, and `/action doctor`. Slash input resolves through Command Registry longest-prefix matching; exact natural input resolves through Natural Router into one step or an ordered bundle. Plans include category/read-only/mutation/risk metadata, per-step Action Safety Policy, strictest bundle policy, and safe suggestions for unmatched natural phrases. Preview never calls target command formatters, enables context, mutates stores, or performs fuzzy/LLM matching.

Action Proposal Queue v1.5.2 adds read-only execution audit to the guarded run-once path. `/action runs [--all|--last N]` lists executed records; `/action run-verify <id>` verifies lifecycle flags, command count, metadata snapshots, current Registry/Policy, and canonical receipt hash; `/action run-audit` aggregates v2/legacy/missing receipts, verified/mismatched hashes, duplicate run ids, warnings, policy drift, and forbidden mutating commands. Results are `VERIFIED`, `WARN`, or `ERROR`. These commands never invoke the executor or mutate queue/target stores; v1.5.1 run-once and read-only-only restrictions remain unchanged.

CLI exit aliases are handled before slash commands, natural routing, and cognitive flow. `exit`, `quit`, `q`, `/exit`, `/quit`, and `/q` close the interactive shell without creating memory records or session log cognitive turns.

Proto-Mind Desktop Chat v0.5 launches with `python3 -m proto_mind.desktop_app`. It is a local tkinter chat window over the same CLI command/natural-router path. Normal chat turns are compact by default; the `Debug output` checkbox restores full observer/memory/audit/reflection traces. The right-side System Panel shows overall status, backend/model, log entry count, last check time, debug state, and buttons for self-check, refresh status, health, doctor, review, log status, and exporting the last 20 session entries. Startup silently refreshes `/session log status` to populate log entry count without chat spam. Desktop UI preferences are stored in `desktop_prefs.json` for `debug_output` and `auto_self_check_on_startup`; auto self-check remains off by default. With `PROTO_MIND_REASONER=ollama`, the status line shows the configured local model. The desktop shell also supports Copy All and explicit transcript export to `exports/desktop_chat_transcript_*.md`.

PySide6 Desktop Shell v1.5.2 launches with `python3 -m proto_mind.pyside_app` as an optional alternative desktop UI. It reuses the same desktop runtime and helper logic as tkinter, including compact/debug output, startup log-status refresh, System Panel commands, transcript saving, and `desktop_prefs.json`. Normal Proto-Mind responses use a safe markdown-lite renderer for paragraphs, bullet/numbered lists, inline code, fenced code blocks, bold text, and simple headings while escaping raw HTML. Each chat message is isolated so markdown list numbering cannot leak into later User/System/Proto-Mind blocks. User and System notes are escaped/plain, and operator reports remain monospace/preformatted. User input and operator commands run in a QThread worker with one active job at a time, keeping the GUI responsive during long local Ollama calls. v1.5 also adds `scripts/build_macos_app_launcher.sh`, which creates a local `dist/Proto-Mind.app` wrapper for double-click launching in Ollama mode; v1.5.1 makes that launcher robust under Finder's limited environment by trying `.venv`, Homebrew, framework, local, and system Python candidates before selecting one that imports both `proto_mind` and `PySide6`; v1.5.2 adds a generated `ProtoMind.icns` icon, clearer timestamped launcher diagnostics in `/tmp/proto_mind_launcher.log`, and `scripts/install_macos_app_shortcut.sh` for Desktop shortcuts. It depends on the existing project, Python/PySide6 install, and Ollama service rather than packaging them. v1.3 added worker signals for future chunks, stream-block helper methods, and a Stop button skeleton. The current shared handler is not forcibly interrupted yet, and real token streaming remains future work. The System Panel shows explicit `Runtime: ready/thinking.../stopping.../error`, the bottom status line preserves backend/model/debug info, and the Send button changes to `Thinking...` while a worker is active. Enter sends messages, Shift+Enter inserts a newline, status badges are color-coded, and PySide window geometry is persisted with a `pyside6:` preference prefix. If PySide6 is not installed, it prints a clean install message instead of a traceback.

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
- Operating Loop UI: add optional PySide buttons/panel summaries for `/loop status`, `/loop next`, and `/loop doctor`.
- Backup/export manifest: include explicit archive metadata and memory export summaries before cleanup, repair, or storage migration.
