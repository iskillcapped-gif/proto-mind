# Agent workspace upgrade

Requested 2026-09-25 after comparing Proto-Mind with the Codex desktop workspace.
This is one tracked delivery. Completing an individual row does not complete the whole upgrade.

## Acceptance checklist

- [x] Shared PM tools: exact project/conversation IDs, task status and handoff, file presentation, project-memory search, structured user questions. Preserve drafts and the single history writer; stop/disconnect must release pending calls.
- [x] Agent browser: inspect a specific PM tab, interact with observed elements, navigate and capture its rendered state. Reject stale targets; preserve tab/session ownership.
- [x] Extensions and documents: explicit MCP connections, usable document helpers, visual PDF input and inspectable generated artifacts. Credentials remain outside history and backups.
- [x] Coordination: start and await independent subtasks, collect results, isolate simultaneous repository edits with worktrees, and expose controlled long-task continuation.
- [x] API models: use the shared PM tool set through supported Responses/Chat Completions function calls, with explicit enablement, cancellation and no uncertain paid retries.
- [x] Skills: avoid an unnecessary separate model call for routine guidance without silently treating optional selection as a required execution gate.
- [x] Verification and delivery: focused transport/routing/permission tests, Native and Python regression checks, disposable-profile UI checks, local build, documentation, and a final explicit report covering every row.

Completed locally on 2026-09-25 as **Native 0.72.0 (101)**. Every row in this
agreed upgrade is delivered within the explicit limits below.

## Working boundaries

The other active task is in PsyMI, a separate repository. This task uses branch
`codex/pm-agent-workspace`. Use isolated fixtures, at most two build workers, and
avoid concurrent control of the user's desktop/browser. Existing personal state
and running tasks are not migration fixtures. No live paid model calls, external
messages or connection changes are needed for ordinary regression tests.

## Evidence

Baseline: `1da022c`, Native 0.71.1. No tracked edits existed at the start.

- Full Python suite: **2364 checks passed** (2321 core/integration + 43 portable/API/new-tool checks); compileall passed. Optional pytest is unavailable on this Mac.
- Full Native suite: **1939 checks passed**, including exact routing, live steering, simultaneous tasks, source-bound browser controls, restored permission rejection, retained questions and v3 agent contract receipts.
- Actual local HTTP/SSE fixtures test Responses image/tool/reasoning flow and MCP. Real stdio fixtures test MCP lifecycle and a Native reply while its provider worker is waiting. No real cloud model was invoked.
- Real WebKit fixtures clicked an observed control, verified the new page, rejected stale IDs and excluded form values from text capture. Dark UI renders of the question card and MCP settings were inspected in a disposable profile, without foreground desktop control.
- Real document libraries round-tripped DOCX/XLSX/PPTX, generated a Unicode PDF, refused overwrites and escaped/symlink paths. A disposable Git repository verified committed-HEAD worktrees without changing source edits.
- Local app and portable Apple Silicon app built as **0.72.0 (101)**; ad-hoc signatures verified. The portable build contains the clean application source from `a7081db`, including all 200 inventoried core files.
- The portable app passed bootstrap with disposable state, document-library round trips using bundled Python 3.12.14, transactional memory save/restart and verified private backup. All 52 Mach-O binaries passed the dependency check; no personal core stores or Python caches appeared inside installed code. The verifier now distinguishes a dylib's own ID from its loaded dependencies; all **6 focused portable checks passed** after that fix.
- Local artifacts: `dist/Proto-Mind Native.app` and `dist/portable-0.72.0/Proto-Mind-0.72.0-arm64-beta.dmg`. DMG SHA-256 verified: `5a963545178578246c272cac805931eb1e25cfe2ff0b97b6422f1734e848c8da`. The public download is unchanged.

Installed and packaged Codex: 0.153.4. Its local experimental JSON schema was
generated into `/tmp/proto-mind-app-server-schema` to verify tool protocol shapes.

## Using the new capabilities

- **Codex:** enable Full Mac for the task as usual. PM tools are supplied with the next turn. Existing tool-free sessions refresh their provider contract once; local messages remain.
- **API:** choose a Responses or Chat Completions connection and a model supporting function calls. Enable **PM tools** in that chat's model-source menu or Models settings. Mac/shell access is not part of this switch. The existing Ollama route remains text-only; a local server can use the compatible API route if it supports tool calls.
- **MCP:** open **Settings → Connections → MCP**. Add a local executable and JSON argument array, or an HTTPS endpoint (loopback HTTP is allowed). An optional bearer token is saved to Keychain. Enable the connection and check its tools. Service account login remains explicit; no token belongs in a conversation or command arguments.
- **Documents:** request a new DOCX, XLSX, PPTX or PDF in the selected project. Basic helpers accept structured content; rich work can use the supplied Python libraries. The model can inspect PDF page images and show Office files in a panel. Existing files are not overwritten by the helper.
- **Subtasks:** ask the assistant to create and collect separate tasks. For parallel Git edits, request isolated worktrees. If they need Mac tools, enable **Mac access for new subtasks** in Models settings. That authorization is session-only and covers one child turn. A worktree starts at committed HEAD, not unsaved edits. Review before integration.
- **Questions/continuation:** answer the card above the relevant composer. A pending question does not block independent work. A deliberately paused task may offer **Continue task**; clicking starts one normal turn. There is no automatic paid continuation loop.

## Scope and honest limits

- MCP v1 implements client-initiated tool listing/calls. OAuth discovery, server-initiated sampling, subscriptions and automatic reconnect/replay are not included. An uncertain external action requires inspection before repeating it.
- Browser actions target observed controls in the main document. Cross-origin iframe controls, arbitrary JavaScript, password entry and messenger automation are outside this interface. Screenshots cover the visible viewport. Web content never authorizes an action.
- A document save is byte-verified, not automatically layout-verified. Basic generated templates do not substitute for designed slide decks. Rich authoring uses the real libraries; inspect the output visually.
- Full Mac applies only to Codex. API PM tools require explicit per-chat opt-in, which loses authority after a private-state restore. New tasks do not inherit persistent permissions. Already accepted child work remains independent when its parent stops.
- A completed model response is still distinct from a verified task outcome. No real paid model request, message send or personal MCP account is required by the regression tests. Provider/account compatibility remains a separate live check.
- This release does not publish a website update or replace the publicly downloadable installer automatically. Apple notarization and validation on a second Mac retain their earlier status.
