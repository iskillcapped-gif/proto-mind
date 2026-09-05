# Working on Proto-Mind

Proto-Mind is a personal macOS application with a Python cognitive core. The goal is a dependable, useful daily assistant that can grow substantially in capability.

## Engineering direction

- The operator explicitly authorized autonomous improvements on 2026-09-04. Use engineering judgment to fix defects, simplify workflows, refactor architecture, add worthwhile dependencies and revise these project instructions. Routine work within that direction does not need repeated approval.
- Choose priorities from user value and current evidence. Historical milestone order, narrow pilot limits and earlier implementation choices are not permanent design constraints.
- Keep product behavior and controls honest: distinguish a completed model response, saved data and a verified task outcome. Preserve user data and make intentional changes to permissions, memory policy or schemas understandable and recoverable.
- A clean Git commit or branch point is a sufficient source checkpoint for code-only work. Back up affected personal state before a migration or operation that can alter it; a new full archive is not required for every patch.
- Core-memory read/change/save operations must hold `MemoryStore.transaction()` through revalidation, save and verification. Keep live sidecar locks in place; plain reads and previews must remain free of writes.
- Native dialog writes must hold the persistent `.history.lock`, compare the loaded manifest with current bytes, and publish immutable conversation objects before the atomic manifest. Preserve current and in-window data before recovery; never treat dialog-only exports as a complete private-state backup.
- Tests and fault injection should use disposable state. Run focused checks while iterating and the broader suites appropriate to the affected components before delivery. Match verification claims to what actually ran.

## Project map

- `native/Sources/`: primary SwiftUI/AppKit application. `AppModel` owns shared state; `ConversationModel`, `TurnExecutionModel`, `WorkSessionHistoryModel`, `SessionSpineFlowModel` and `HistoryPersistenceModel` group its flows. `ChatStore`, `ChatHistoryFiles`, `ChatHistoryFormat` and `ChatBackups` own dialog persistence.
- `SidebarView`, `ConversationWelcomeView`, `ComposerView` and `NativeSettingsView` own everyday UI; `WorkspaceView` composes the workspace/transcript and `NativeTheme` defines adaptive appearance. `WorkspacePanelModel`/`WorkspacePanelView` own transient file/browser tabs; `BrowserView` owns manual WebKit navigation. Keep source evidence and permission state reachable when simplifying presentation.
- `proto_mind/`: Python cognition, persistence, provider adapters and stdio bridge. `native_history_routes.py` groups journal/Spine RPCs; `native_chat_history.py` adapts exact v6 dialog evidence without writing it.
- `native/Tests/` and `proto_mind/tests/`: Native checks and Python regression tests. `test_flow.py` is the stable aggregate for `test_flow_*.py`; shared fixtures live in `flow_fixtures.py`. Add flow tests to the relevant topic module and keep the aggregate/provenance inventory aligned.
- `scripts/test_native.sh`: builds Native and checks it against temporary Python fixtures.
- `scripts/run_tests.sh`: Python tests and compile checks using the project Python selector.
- `scripts/build_native_app.sh`: local application bundle in `dist/Proto-Mind Native.app`.

`README.md` describes current behavior; `PROTO_MIND_EVOLUTION_ROADMAP.md` is the current priority map; `NATIVE_MACOS_ROADMAP.md` records Native releases. `PROTO_MIND_ARCHITECT_LEDGER.md` provides architectural context and historical evidence. `CODEX_COLLABORATION.md` and contest documents describe the earlier Build Week submission, not the current development policy.

Prefer a small, current source of truth over copying release narratives across documents. Native is the primary interface; older interfaces can be retained, simplified or retired with an intentional transition.
