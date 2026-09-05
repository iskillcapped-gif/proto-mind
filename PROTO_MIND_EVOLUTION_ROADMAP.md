# Proto-Mind: Current Direction

Updated: 2026-09-05. Current release: Native **0.51.1 (59)**.

Proto-Mind is a personal macOS assistant. The immediate goal is a dependable, approachable application that can support the operator's planned expansion. The everyday layout and working panel are delivered. The operator returned to conversation polish on September 5: a calmer work timeline, narrower reading column, upward composer menus and final file-change summaries. Memory and continuity workflows remain delivered.

This is the current priority map. [AGENTS.md](AGENTS.md) describes how to work in the project; [Native releases](NATIVE_MACOS_ROADMAP.md) preserve delivered contracts and verification; [Architect Ledger](PROTO_MIND_ARCHITECT_LEDGER.md) preserves architectural evidence. Earlier versions of this document remain in Git history. Historical EV/P2 numbering and imported blueprints do not determine the next task.

## Foundation Completed

| Area | Current behavior | Practical boundary |
| --- | --- | --- |
| Dialog persistence | Each dialog has an immutable object; a small atomic manifest selects the current versions. Saves reuse unchanged dialogs. Competing app processes cannot silently overwrite each other. | Up to 10,000 dialogs; each object below 50 MiB. Startup still reads the complete archive into memory. |
| Recovery | Failed saves retain visible replies and drafts. The app offers verified export/import, the last 20 automatic snapshots, a pinned original-format copy and copies before recovery. | These are dialog copies. Core memory, the separate work journal, provider sessions and original attachment files need their own backup. |
| Work journal | New independent turns have no global 500-run ceiling. The journal pages through older records and opens a message's exact run directly. | Page listing and continuation validation still scan the journal; the detached archive audit has a separate 500-record input budget. |
| Memory | Full core-memory mutations use cooperative transactions. Project notes have explicit scope, source evidence, bounded local RU/UK/EN recall, editable versions and reversible removal from future selection. | The legacy shared core is not fully project-isolated; matching is deterministic, with finite vocabulary. Removing a note does not erase old provider messages. |
| Execution | Codex Chat and explicit Full Mac have separate durable sessions; local Ollama and Mock remain available. Public work evidence, Stop and manual acceptance are distinct. | Full Mac has broad user-level authority. Finished model output does not prove task success or undo side effects. |
| Continuity and learning | Brother Persona, reviewed notes/lessons/skills, exact Turn Lineage and the confirmed single-turn Session Spine writer are implemented. | General automatic learning, multi-turn Spine ingestion and background work are not implemented. |
| Code structure | Dialogs, turn execution, work history, Spine and persistence have separate Native model files. Python history routes are isolated. The original 1,193 flow checks are split across 21 topic modules with a stable aggregate command. | Other large modules can be split when their next change benefits; no rewrite is required before interface work. |

Release 0.46.0 closes the agreed storage, recovery, code-structure and current-roadmap batch. Its detailed limits and verification are in the [release contract](NATIVE_MACOS_ROADMAP.md#dialog-storage-and-recovery--native-0460).

## Everyday Interface And Working Panel Delivered

Release 0.47.0 improves the most frequent paths: open a conversation, choose a model, attach context, send, understand progress, inspect a result and find recovery actions.

- A consistent light/dark palette, clearer message typography, searchable sidebar and three welcome actions establish the everyday layout.
- The responsive composer keeps model/access visible and groups context, criteria, skills and project recall in one request menu. Programmatically prepared drafts receive focus; search supports ⌘F.
- Four settings sections separate models, communication, data/copies and advanced controls. Answer details use ordinary labels, retaining raw reports and exact run/Spine entry points.
- Work evidence starts collapsed; completed model output says “Ответ получен”. Interrupted-run warnings and recovery remain visible and actionable.

Acceptance used isolated signed apps in both appearances, a small window with the inspector, a 240-message conversation, keyboard input/search, a delayed Mock response and recovery navigation. Native fixtures cover provider progress/cancellation and persistence; this UI pass does not claim a new live cloud-streaming run. The [release contract](NATIVE_MACOS_ROADMAP.md#everyday-interface--native-0470) records exact verification and boundaries.

Release 0.48.0 follows the operator's Codex screenshots: neutral gray/charcoal surfaces, 16-point messages, simpler project navigation and access-left/model-right composer controls. The right panel now holds real file/browser tabs, supports resizing and expanded reading, and keeps answer diagnostics in a separate sheet. It opens bounded project text and Markdown, PNG/JPEG previews, verified PDF text pages and manually navigated HTTP(S) sites. Viewing does not attach content or give the model browser access. Tabs and website sessions are temporary; original PDF layout, downloads and unsupported web flows use external applications. The [release contract](NATIVE_MACOS_ROADMAP.md#files-and-browser-panel--native-0480) records current acceptance.

Release 0.51.0 refines the conversation after the operator's second screenshot review: aligned 760-point input/transcript columns with larger margins, 15-point body/input text, composer panels that stay above their anchors, adaptive model-control width, compact grouped activity, and final-only edited-file cards. Skills, project-recall reports and service notices move to answer details. Line totals come from complete observed diffs, never truncated preview text; older counts may be absent. See the [release contract](NATIVE_MACOS_ROADMAP.md#quieter-conversation--native-0510).

Release 0.51.1 adds the operator's final composer refinements and subtle activity animations. The local Codex CLI was updated from 0.151.0 to 0.153.4; Astra then appeared in Proto-Mind's account catalog. See the [release contract](NATIVE_MACOS_ROADMAP.md#conversation-polish--native-0511).

## Project Memory Controls Delivered

Release 0.49.0 makes explicitly saved project knowledge manageable through ordinary actions: **Сохранить**, **Изменить**, **Убрать из памяти проекта** and **Вернуть в память проекта**. Removing a note excludes it from new recall and attachment; history retains the original bytes and supports search and restoration. Exact preview, scope and writer checks happen internally after the user's action. Stale pending note selections and context previews are cleared after edits/removal. **Библиотека** separates project notes from legacy shared memory. See the [release contract](NATIVE_MACOS_ROADMAP.md#project-memory-controls--native-0490).

## Everyday Continuity Delivered

Release 0.50.0 closes the missing navigation step: **История диалогов** finds saved text, titles, folders and drafts across active and archived dialogs, displays the relevant message and latest exchange, and opens the exact match even in a long transcript. Ordinary return preserves drafts and current dialog settings. **Подготовить продолжение от ответа** reuses the existing exact run/turn linkage to prepare a manually sent reconstruction, refusing stale evidence, changed folders, occupied drafts/context and already continued parents. No new history store, automatic summary, provider reset or background execution is added. See the [release contract](NATIVE_MACOS_ROADMAP.md#everyday-continuity--native-0500).

## Next: Complete Private-State Backups

The current recovery UI exports dialogs, while useful personal state also lives in project notes, shared core memory, the work journal and local provider/session links. The next candidate is one clearly scoped, verified backup and recovery flow for that local private state. Begin with an inventory and a consistent snapshot/preview; preserve existing recovery copies and separately identify original attachments or remote provider history that a local copy cannot contain. Do not treat a dialog export as a full backup or silently restore authority from old state.

The requested conversation refinements and follow-up polish are delivered through 0.51.1; additional visual changes can follow actual use. The planned substantial functional expansion remains for the operator to scope.

## Later Candidates

The operator plans a substantial functional expansion and will supply its scope after interface work. Keep these options available without starting all of them now:

- Better practical memory correction, scope and retrieval quality, supported by ordinary-task evidence.
- Continuity across tasks and sessions, with stronger recovery for linked history and work records.
- Richer document/artifact handling, voice input and provider capability parity.
- Narrower tool modes, reviewed procedures and useful background/parallel work with visible limits.
- A complete private-state backup/restore flow and simpler local runtime packaging when needed.

Choose the next increment from actual usage and the operator's direction. Broad architecture proposals, historical design gates and old test counts are context, not a substitute for inspecting the current implementation.
