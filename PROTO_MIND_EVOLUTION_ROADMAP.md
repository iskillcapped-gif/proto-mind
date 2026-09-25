# Proto-Mind: Current Direction

Updated: 2026-09-26. Current development release: Native **0.74.2 (106)**.

The Claude subscription experiment now has a local integration through the official Agent SDK and unmodified Claude Code login. [Setup and scope](CLAUDE_CONNECTION.md). The operator has connected Pro; read-only live checks confirmed the account's model catalog and subscription quotas. Native 0.73.1 added exact model versions and separate Codex/Claude limits; 0.74.0 fixes the independently checked review findings, including durable Claude sessions, memory replacement, Native intent routing and stateful MCP. 0.74.2 keeps per-turn memory current in resumed Claude sessions, continues interrupted ones and keeps failed requests visible to models. Core updates after it show each Claude turn's token use and narrow automatic memory labels and decisions. Additional review ideas, particularly cross-provider context transfer, are deferred at the operator's request. Real disposable-project tasks remain the next acceptance step; metadata checks do not establish model quality.

Proto-Mind is a personal macOS assistant. The immediate goal is a dependable, approachable application that can support the operator's planned expansion. The everyday layout, working panel and conversation polish are delivered. On September 5 the operator requested useful service connections, starting with GitHub. GitHub, complete local private-state backups, subscription usage with explicit earned resets, Full Mac access without a selected project, live text/attachment updates to running Codex tasks and a sidebar-confined limits menu with explicit account identity are now delivered. Reply typography and parallel conversations are also implemented; memory and continuity workflows remain available.

This is the current priority map. [AGENTS.md](AGENTS.md) describes how to work in the project; [Native releases](NATIVE_MACOS_ROADMAP.md) preserve delivered contracts and verification; [Architect Ledger](PROTO_MIND_ARCHITECT_LEDGER.md) preserves architectural evidence. Earlier versions of this document remain in Git history. Historical EV/P2 numbering and imported blueprints do not determine the next task.

## Agent Workspace — September 25

The agreed Codex-workspace comparison list is tracked in [Agent workspace upgrade](AGENT_WORKSPACE_UPGRADE.md): PM task tools, browser control, MCP connections and documents, worktree-backed subtasks, explicit API tool mode and local skill selection. The checklist is the source of delivery/verification status; earlier milestone narratives below retain their historical scope. Publishing the new portable download is a separate action.

## Foundation Completed

| Area | Current behavior | Practical boundary |
| --- | --- | --- |
| Dialog persistence | Each dialog has an immutable object; a small atomic manifest selects the current versions. Saves reuse unchanged dialogs. Competing app processes cannot silently overwrite each other. | Up to 10,000 dialogs; each object below 50 MiB. Startup still reads the complete archive into memory. |
| Recovery | Failed saves retain visible replies and drafts. The app offers verified export/import, the last 20 automatic snapshots, a pinned original-format copy and copies before recovery. | Complete copies additionally cover core/notes/work records/settings at their original paths. Credentials, provider history, original attachments and project files stay separate. |
| Work journal | New independent turns have no global 500-run ceiling. The journal pages through older records and opens a message's exact run directly. | Page listing and continuation validation still scan the journal; the detached archive audit has a separate 500-record input budget. |
| Memory | Full core-memory mutations use cooperative transactions. Project notes have explicit scope, source evidence, bounded local RU/UK/EN recall, editable versions and reversible removal from future selection. | The legacy shared core is not fully project-isolated; matching is deterministic, with finite vocabulary. Removing a note does not erase old provider messages. |
| Execution | Independent conversations can run concurrently in the open app. Each keeps its own stream, draft, grants, Stop and saved text/attachment update queue. Codex Chat and explicit Full Mac have separate durable sessions; local Ollama and Mock remain available. Public work evidence, Stop and manual acceptance are distinct. | Full Mac has broad user-level authority. Finished model output does not prove task success or undo side effects. |
| Continuity and learning | Brother Persona, reviewed notes/lessons/skills, exact Turn Lineage and the confirmed single-turn Session Spine writer are implemented. | General automatic learning, multi-turn Spine ingestion and unattended work after app exit are not implemented. |
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

## GitHub Connection Delivered

Release 0.52.0 adds **Подключения** in Settings and **GitHub** in the sidebar. It reuses the operator's existing GitHub CLI account, lists repositories and open PRs/issues, and prepares discussion drafts. Explicit Full Mac Codex tasks receive a managed GitHub command and HTTPS Git credentials through the existing CLI; chat mode receives neither. The account is checked before access, and disconnecting does not log the Mac out. Native connection metadata contains no token. See the [release contract](NATIVE_MACOS_ROADMAP.md#github-connection--native-0520). Further services follow actual work needs rather than a speculative integration catalog.

## Complete Private Backups and Codex Usage Delivered

Release 0.53.0 adds a verified folder snapshot, read-only preview and recoverable restore spanning the Native stores, separate Python core, exports and logs. Restore preserves the before-image and in-window draft, keeps live locks, blocks stale writers, supports explicit resume/rollback after interruption, and requires a restart with service access disabled. Existing dialog backups remain available. Original installation paths are required; credentials, provider history, external attachments and project files stay outside the package.

The operator's follow-up is also delivered: the existing Codex login supplies account-wide quota windows, remaining percentages, reset dates, earned-reset count and available token activity. The view is read-only and does not estimate costs or equate token counts with remaining messages. See the [release contract](NATIVE_MACOS_ROADMAP.md#complete-private-backups-and-codex-usage--native-0530).

## Practical Memory Quality Delivered

Release 0.57.0 unifies automatic recall and library search. A fixed corpus of 53 ordinary RU/UK/EN questions covers corrections, archived notes, folder scope, services, environments and filenames. Exact selected sets improve from 25/53 to 53/53 in automatic recall and from 21/53 to 53/53 in the library. See [the corpus and measurement](evals/project_recall/README.md) and [release checks](NATIVE_MACOS_ROADMAP.md#practical-project-recall--native-0570).

Selection still uses finite local vocabulary and literal qualifiers; it is not general semantic retrieval or automatic learning. No personal-note migration or new provider call is required. Future examples from actual use can extend this regression set.

## Long-running Tasks Delivered

Release 0.57.1 removes the short Codex turn timers and total action cutoff for new Native tasks. Recent public evidence remains bounded and marked partial when rotated; Stop and failure handling remain available. Existing contracts/history stay readable. See the [release checks](NATIVE_MACOS_ROADMAP.md#long-running-tasks--native-0571).

## Live Voice Delivered

Release 0.58.0 adds GPT Live 1 voice with a separate OpenAI API key, native audio and Responses-backed command routing. Voice can manage known projects and existing/new tasks while the task model keeps its own memory and permissions. Full Mac selection is remembered per dialog/workspace; bridge tokens remain temporary. Stopping voice does not stop work. A local/free voice alternative and permanent conversational voice memory remain separate future work. VIREN continues as an independent project. See the [release contract](NATIVE_MACOS_ROADMAP.md#live-voice--native-0580).

## Current Priority: Challenge Demonstration And First Installation

Native 0.66.0 connects the floating workspace into one demonstrable flow:
browser page/selection → exact task → live correction → answer beside chat →
project memory reused in another conversation. English/Russian main UI and voice,
an updated portable beta, and a fictional project/recording guide support that flow.
[Launch kit](native/Distribution/CHALLENGE_LAUNCH.md) records the remaining media and
submission steps. Record actual model work, then test the release on a second Mac
and finish the public product listing; do not equate synthetic QA with a live demo.

The operator chose portability before the launch website or further features.
The 0.62.0 beta packages Python/Codex, separates installed code from a user's
core/history/account profile, and offers first-connection guidance inside the
workspace. The developer installation stays independent. [Installation](INSTALL_MACOS.md)
and [release workflow](native/Distribution/README.md) describe the artifact and
its boundaries. Developer ID/notarization and a second-Mac test remain before
public distribution; the operator does not currently have Apple Developer
Program membership. The separate VIRENCORE website exists; this release work does
not upload the beta or submit a Product Hunt entry.

This packaging boundary does not freeze the product: future UI, memory and
capability improvements use the same source and can ship in both editions.

## Everyday Reading and Background Results — 0.67.0

Unread replies are marked in the sidebar and counted on the floating cube, alongside the independent running-task animation. Interrupted requests retain a distinct attention mark. Reading the visible response footer acknowledges that exact completion; hidden tabs, covered chats and nonactivating hover previews do not. Read state survives restart in profile-specific UI preferences without rewriting history.

PDF panels show the original page artwork with page navigation, fit/zoom and a selectable-text mode. The existing sandboxed helper renders one bounded page at a time; source hashes prevent quietly switching to a changed document. Viewing is separate from explicitly attaching the current page’s text. OCR and sending page images are not enabled by this feature.

The operator postponed the second-Mac installation trial while no tester is available. The existing launch kit and portable beta remain available; this does not block local product development.

## Later Candidates

The operator plans a substantial functional expansion and will supply its scope after interface work. Keep these options available without starting all of them now:

- Further practical memory correction, scope and retrieval quality from new ordinary-task examples.
- Continuity across tasks and sessions, with stronger recovery for linked history and work records.
- Richer document/artifact handling, local/free voice and provider capability parity.
- Narrower tool modes, reviewed procedures and useful background/parallel work with visible limits.
- Cross-installation backup migration and an explicit transition from the developer profile.

Choose the next increment from actual usage and the operator's direction. Broad architecture proposals, historical design gates and old test counts are context, not a substitute for inspecting the current implementation.
