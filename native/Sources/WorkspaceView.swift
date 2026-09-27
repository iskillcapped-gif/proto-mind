import AppKit
import SwiftUI

private let hairline = NativeTheme.hairline
private let canvas = NativeTheme.canvas

struct WorkspaceView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var panel: WorkspacePanelModel
    @ObservedObject var desktop: DesktopPresentation
    private func openSettings() { model.openSettings() }
    @State private var libraryExpanded = false

    init(model: AppModel) {
        self.model = model
        self.panel = model.workspacePanel
        self.desktop = model.desktop
    }

    var body: some View {
        Group {
            if desktop.enabled { FloatingWorkspaceView(app: model, desktop: desktop) }
            else { regularWorkspace }
        }
        .frame(minWidth: desktop.companions.minimumWorkspaceWidth,
               minHeight: desktop.enabled ? DesktopGeometry.minimumWorkspace.height : 640)
        .background(DesktopWindowAttachment(app: model, openSettings: { openSettings() }))
        .tint(NativeTheme.accent)
        .font(NativeTheme.interfaceFont)
        .buttonStyle(.nativeHover)
        .disclosureGroupStyle(NativeDisclosureStyle())
        .onChange(of: model.section) { _, next in if next.libraryCollection != nil { libraryExpanded = true } }
        .workspaceSheet(item: $model.exitPrompt) { WorkspaceExitView(app: model, prompt: $0) }
        .workspaceSheet(isPresented: $model.showSettings, routingKey: "settings") { NativeSettingsView(model: model) }
        .workspaceSheet(isPresented: $model.showFirstLaunch, onDismiss: {
            FirstLaunch.dismiss(model.serviceClient.configuration)
        }) { FirstLaunchView(model: model) }
        .workspaceSheet(isPresented: $model.showInspector, routingKey: "inspector") {
            EvidenceInspectorView(model: model).workspacePageSize(width: 560, height: 680)
        }
        .workspaceSheet(item: $model.pendingAction) { action in
            VStack(alignment: .leading, spacing: 20) {
                Label(L10n.text("Подтвердить команду"), systemImage: "hand.raised").font(.title2.weight(.semibold))
                Text(L10n.text("Эта команда меняет состояние или требует повышенного внимания. Модель не запрашивала её выполнение: ниже именно ваш ввод."))
                    .foregroundStyle(.secondary)
                ScrollView { Text(action.text).font(.system(.body, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                    .frame(maxHeight: 100).padding(12).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 10))
                Text(action.summary).font(.callout).textSelection(.enabled)
                Text(L10n.text("Внутренние approval/token/preview-гейты Proto-Mind по-прежнему действуют.")).font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button(L10n.text("Отмена")) { model.pendingAction = nil }.keyboardShortcut(.cancelAction)
                    Spacer()
                    Button(L10n.text("Выполнить мой ввод")) { Task { await model.confirmPending() } }.buttonStyle(.borderedProminent).nativeHoverSurface()
                }
            }.padding(28).workspacePageSize(width: 560)
        }
        .workspaceSheet(item: $model.pendingAgentAccess) { request in AgentAccessSheet(model: model, request: request) }
        .workspaceSheet(isPresented: $model.showWorkSessions, routingKey: "workSessions", onDismiss: {
            if model.selected?.draftContinuation != nil { model.focusReturnedDraft() }
        }) { WorkSessionsView(model: model) }
        .workspaceSheet(isPresented: $model.showConversationHistory, onDismiss: { model.focusReturnedDraft() }) {
            ConversationHistoryView(model: model)
        }
        .workspaceSheet(isPresented: $model.showHistoryBackups) { HistoryBackupsView(model: model) }
        .workspaceSheet(isPresented: $model.showPrivateBackup, onDismiss: {
            if model.quitAfterPrivateBackup { NSApp.terminate(nil) }
        }) { PrivateBackupView(app: model, backup: model.privateBackup) }
        .workspaceSheet(isPresented: $model.showCodexUsage, routingKey: "codexUsage") {
            AccountUsageView(app: model, usage: (model.presentedCodexAccount ?? model.selectedCodexAccount).usage)
        }
        .workspaceSheet(isPresented: $model.showCodexAccounts, routingKey: "codexAccounts") {
            CodexAccountsPage(app: model, conversationID: model.codexAccountsConversationID)
        }
        .workspaceSheet(item: $model.sessionSpinePreview) { SessionSpinePreviewView(model: model, preview: $0) }
        .workspaceSheet(isPresented: $model.showContextDesk, routingKey: "contextDesk") { ContextDeskView(model: model) }
        .workspaceSheet(isPresented: $model.showPersonaInspector) { PersonaInspectorView(model: model) }
        .workspaceSheet(isPresented: $model.showMemoryWorkshop) { MemoryWorkshopView(model: model) }
        .workspaceSheet(item: $model.skillAuthoring) { SkillAuthoringView(model: $0) }
        .workspaceSheet(item: $model.skillInspection) { SkillInspectionView(model: $0) }
        .workspaceSheet(item: $model.skillOutcome) { SkillOutcomeView(model: $0) }
        .workspaceSheet(item: $model.skillDecision) { SkillDecisionView(model: $0) }
        .workspaceSheet(item: $model.skillLifecycleApply) { SkillLifecycleApplyView(model: $0) }
        .workspaceSheet(item: $model.skillRestore) { SkillRestoreView(model: $0) }
        .workspaceSheet(item: $model.skillHistory) { SkillHistoryView(model: $0) }
        .workspaceSheet(item: $model.projectMemory) { ProjectMemoryView(model: $0) }
        .workspaceSheet(item: $model.memorySuggestion) { MemorySuggestionView(model: $0) }
        .workspaceSheet(item: $model.skillTask) { SkillTaskView(model: $0) }
        .workspaceSheet(isPresented: $model.showTaskCriteria) { TaskCriteriaView(model: model) }
        .workspaceSheet(item: $model.imagePreview) { ImageAttachmentPreviewView(model: model, preview: $0) }
        .workspaceSheet(item: $model.pdfPreview) { PDFAttachmentPreviewView(model: model, preview: $0) }
        .workspaceSheet(item: $model.attachmentDropPreview) { AttachmentDropPreviewView(model: model, preview: $0) }
        .environment(\.workspacePresentations, model.presentations)
        .environment(\.locale, L10n.locale)
    }

    private var regularWorkspace: some View {
        NavigationSplitView {
            SidebarView(model: model, libraryExpanded: $libraryExpanded, openSettings: { openSettings() })
                .navigationSplitViewColumnWidth(min: 225, ideal: 280, max: 340)
        } detail: {
            VStack(spacing: 0) {
                HistoryPersistenceNotice(model: model)
                if let error = model.error, error != model.historyPersistence.failure {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "exclamationmark.circle").foregroundStyle(.orange)
                        Text(error).font(.callout).textSelection(.enabled)
                        Spacer()
                        if model.computerUsePermissionIssue {
                            Button(L10n.text("Открыть Automation")) { model.openAutomationSettings() }
                                .buttonStyle(.bordered).nativeHoverSurface()
                        }
                        Button { model.clearError() } label: { Image(systemName: "xmark") }.buttonStyle(.nativeHover)
                    }.padding(14).background(Color.orange.opacity(0.09))
                }
                WorkspaceContentHost(app: model, presentations: model.presentations)
            }
            .background(canvas)
            .background(RegularWorkspaceContentRegion(desktop: desktop))
            .toolbar {
                ToolbarItem(placement: .navigation) {
                    HStack(spacing: 9) {
                        Image(systemName: model.selected?.workspacePath == nil ? "bubble.left" : "folder").foregroundStyle(.secondary)
                        Text(sectionTitle)
                    }
                        .font(.system(size: 14, weight: .medium)).lineLimit(1).frame(maxWidth: 440, alignment: .leading)
                        .help(sectionTitle)
                }
                ToolbarItem(placement: .primaryAction) {
                    HStack(spacing: 8) {
                        Button { model.openWorkSessions() } label: { Image(systemName: "clock.arrow.circlepath") }
                            .accessibilityLabel(L10n.text("Журнал работы"))
                            .help(L10n.text("Журнал работы и ручное продолжение"))
                        Button {
                            model.workspacePanels.toggle()
                        } label: { Image(systemName: "sidebar.right") }
                            .help(L10n.text("Две рабочие панели")).accessibilityLabel(L10n.text("Рабочие панели"))
                        CompanionVisibilityMenu(owner: desktop.companions)
                    }
                }
            }
            .toolbarBackground(canvas, for: .windowToolbar)
            .toolbarBackground(.visible, for: .windowToolbar)
        }
    }

    private var sectionTitle: String {
        switch model.section {
        case .chat: return model.selected?.displayTitle ?? L10n.text("Диалог")
        case .commands: return L10n.text("Команды")
        case .overview: return L10n.text("Диагностика")
        case .workspace: return L10n.text("Папка проекта")
        case .github: return "GitHub"
        case .memory, .goals, .skills: return model.section.libraryCollection?.title ?? L10n.text("Библиотека")
        }
    }
}

enum WorkspacePanelLayout {
    static let divider: CGFloat = 6
    static func width(total: CGFloat, fraction: CGFloat) -> CGFloat {
        let available = max(0, total - divider)
        let minimum = min(300, available / 2)
        return min(available - minimum, max(minimum, available * fraction))
    }
}

struct WorkspaceSplitView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var panels: WorkspacePanels
    @State private var columnStart: CGFloat?
    @State private var rowStart: CGFloat?

    init(model: AppModel, panel: WorkspacePanelModel) {
        self.model = model
        self.panels = model.workspacePanels
    }

    var body: some View {
        GeometryReader { geometry in
            let layout = WorkspacePanelsLayout(size: geometry.size, visible: panels.visible,
                expanded: panels.expanded, horizontal: panels.horizontalFraction, vertical: panels.verticalFraction, lowerEnabled: panels.lowerEnabled)
            ZStack(alignment: .topLeading) {
                mainContent
                    .frame(width: layout.main.width, height: layout.main.height)
                    .workspaceMenuBoundary()
                    .clipped()
                    .opacity(panels.expanded == nil ? 1 : 0)
                    .allowsHitTesting(panels.expanded == nil)
                    .disabled(panels.expanded != nil)
                    .accessibilityHidden(panels.expanded != nil)
                // Stable siblings: expansion resizes the surfaces without replacing their views.
                pane(.upper, frame: layout.upper)
                pane(.lower, frame: layout.lower)
                if panels.visible && panels.expanded == nil {
                    divider(vertical: true)
                        .frame(width: layout.columnDivider.width, height: layout.columnDivider.height)
                        .offset(x: layout.columnDivider.minX)
                        .gesture(DragGesture(minimumDistance: 0).onChanged { drag in
                            if columnStart == nil { columnStart = panels.horizontalFraction }
                            let available = max(1, geometry.size.width - WorkspacePanelLayout.divider)
                            panels.horizontalFraction = WorkspacePanelLayout.width(total: geometry.size.width,
                                fraction: (columnStart ?? 0.48) - drag.translation.width / available) / available
                        }.onEnded { _ in columnStart = nil })
                        .accessibilityLabel(L10n.text("Ширина рабочих панелей"))
                        .accessibilityAdjustableAction { direction in
                            panels.horizontalFraction = min(0.8, max(0.2, panels.horizontalFraction + (direction == .increment ? 0.05 : -0.05)))
                        }
                    if panels.lowerEnabled { divider(vertical: false)
                        .frame(width: layout.rowDivider.width, height: layout.rowDivider.height)
                        .offset(x: layout.rowDivider.minX, y: layout.rowDivider.minY)
                        .gesture(DragGesture(minimumDistance: 0).onChanged { drag in
                            if rowStart == nil { rowStart = panels.verticalFraction }
                            panels.verticalFraction = min(0.8, max(0.2, (rowStart ?? 0.5) + drag.translation.height / max(1, geometry.size.height)))
                        }.onEnded { _ in rowStart = nil })
                        .accessibilityLabel(L10n.text("Высота рабочих панелей"))
                        .accessibilityAdjustableAction { direction in
                            panels.verticalFraction = min(0.8, max(0.2, panels.verticalFraction + (direction == .increment ? 0.05 : -0.05)))
                        }
                    }
                }
            }
        }
    }

    private func pane(_ position: WorkspacePanelPosition, frame: CGRect) -> some View {
        let shown = panels.visible && (position != .lower || panels.lowerEnabled) && (panels.expanded == nil || panels.expanded == position)
        return WorkspacePanelView(model: model, panel: panels.panel(position), width: frame.width, position: position)
            .frame(width: frame.width, height: frame.height).clipped()
            .offset(x: frame.minX, y: frame.minY)
            .opacity(shown ? 1 : 0).allowsHitTesting(shown).disabled(!shown).accessibilityHidden(!shown)
    }

    private func divider(vertical: Bool) -> some View {
        Rectangle().fill(NativeTheme.hairline)
            .frame(width: vertical ? 1 : nil, height: vertical ? nil : 1)
            .frame(maxWidth: .infinity, maxHeight: .infinity).contentShape(Rectangle())
            .onHover { inside in
                if inside { (vertical ? NSCursor.resizeLeftRight : NSCursor.resizeUpDown).set() }
                else { NSCursor.arrow.set() }
            }
    }

    @ViewBuilder private var mainContent: some View {
        switch model.section {
        case .chat, .workspace: ChatView(model: model)
        case .commands: CommandCatalogView(model: model)
        case .overview: OverviewView(model: model)
        case .github: GitHubView(app: model, github: model.github)
        case .memory, .goals, .skills: LibraryView(model: model)
        }
    }
}

enum TranscriptRenderingPolicy {
    // Every rendered message costs on each scroll step: macOS asks SwiftUI what is under
    // the pointer several times per wheel event, and SwiftUI walks every rendered view.
    // At 80 long messages that was about 10 ms per step; earlier messages load on request.
    static let initialMessageLimit = 30
    static let pageSize = 30

    static func renderedRange(totalCount: Int, messageLimit: Int) -> Range<Int> {
        let total = max(0, totalCount)
        let limit = min(total, max(0, messageLimit))
        return (total - limit)..<total
    }

    static func expandedLimit(totalCount: Int, messageLimit: Int) -> Int {
        min(max(0, totalCount), max(0, messageLimit) + pageSize)
    }

    static func focusedRange(totalCount: Int, targetIndex: Int) -> Range<Int>? {
        guard targetIndex >= 0, targetIndex < totalCount else { return nil }
        let start = max(0, min(targetIndex - initialMessageLimit / 2, totalCount - initialMessageLimit))
        return start..<min(totalCount, start + initialMessageLimit)
    }

    static func adjustedLimit(oldCount: Int, newCount: Int, messageLimit: Int, followingLatest: Bool) -> Int {
        // Keep the rendering budget while a short conversation grows. Clamping the
        // budget to the first user message would hide earlier turns on every send.
        let current = max(initialMessageLimit, messageLimit)
        guard newCount > oldCount, !followingLatest else { return current }
        return max(current, min(newCount, current + newCount - oldCount))
    }
}

struct ChatView: View {
    @Environment(\.desktopGlass) private var desktopGlass
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    var panel: WorkspacePanelModel? = nil
    @Environment(\.workspacePresentations) private var presentations
    private var id: UUID? { conversationID ?? model.selectedID }
    private var conversation: Conversation? { model.conversations.first { $0.id == id } }
    private var messages: [ChatMessage] { conversation?.messages ?? [] }
    private var state: ConversationExecution? { id.flatMap { model.executions[$0] } }
    private var destination: TranscriptDestination? {
        get { panel?.transcriptDestination ?? (panel == nil ? model.transcriptDestination : nil) }
        nonmutating set { if let panel { panel.transcriptDestination = newValue } else { model.transcriptDestination = newValue } }
    }
    private func openLink(_ url: URL) {
        if let panel, let id {
            if NativeBrowserURL.isWebURL(url) { panel.openBrowser(url) }
            else { model.openPanelFile(url, conversationID: id, panel: panel) }
        } else { model.openWorkspaceLink(url) }
    }
    @State private var nearBottom = true
    @State private var followOutput = true
    @State private var renderedMessageLimit = TranscriptRenderingPolicy.initialMessageLimit
    @State private var historyWindow: Range<Int>?

    private var renderedMessages: ArraySlice<ChatMessage> {
        let range = historyWindow ?? TranscriptRenderingPolicy.renderedRange(
            totalCount: messages.count,
            messageLimit: renderedMessageLimit
        )
        return messages[min(range.lowerBound, messages.count)..<min(range.upperBound, messages.count)]
    }

    private var hiddenMessageCount: Int {
        renderedMessages.startIndex
    }

    var body: some View {
        GeometryReader { container in
            let inset: CGFloat = container.size.width < 600 ? 16 : (desktopGlass ? 24 : NativeTheme.conversationInset)
        VStack(spacing: 0) {
            if panel == nil { WorkSessionNoticeBanner(model: model) }
            GeometryReader { viewport in
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(spacing: 0) {
                            if messages.isEmpty { welcome.padding(.top, desktopGlass ? 12 : 60).padding(.bottom, 24) }
                            // Variable-height selectable rows can enter a retained layout loop
                            // in macOS SwiftUI's lazy stack after a long-lived window resumes.
                            VStack(alignment: .leading, spacing: 34) {
                                if hiddenMessageCount > 0 {
                                    Button {
                                        loadEarlier(using: proxy)
                                    } label: {
                                        Label(
                                            L10n.format("Показать предыдущие \(min(TranscriptRenderingPolicy.pageSize, hiddenMessageCount)) · скрыто \(hiddenMessageCount)"),
                                            systemImage: "arrow.up.to.line"
                                        )
                                        .font(.system(size: 12))
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 8)
                                    }
                                    .buttonStyle(.nativeHover)
                                    .help(L10n.text("История хранится полностью; загружается только следующая часть интерфейса"))
                                }
                                ForEach(renderedMessages) { message in
                                    VStack(alignment: .leading, spacing: 16) {
                                        MessageView(message: message, model: model, conversationID: id, targetPanel: panel)
                                        if let updates = message.taskUpdates, !updates.isEmpty {
                                            TaskUpdatesView(updates: updates, active: state?.sourceMessageID == message.id,
                                                            copy: model.copy)
                                        }
                                    }.id(message.id)
                                        .background(destination?.conversationID == id
                                            && destination?.messageID == message.id ? NativeTheme.selection : .clear,
                                            in: RoundedRectangle(cornerRadius: 10))
                                }
                                if renderedMessages.endIndex < messages.count {
                                    Button(L10n.text("Показать следующие сообщения")) { loadLater(using: proxy) }
                                        .font(.system(size: 12)).frame(maxWidth: .infinity).padding(.vertical, 8)
                                        .accessibilityLabel(L10n.text("Показать следующие сообщения"))
                                }
                                if let state, state.running {
                                    LiveTurnSection(live: state.live, startedAt: state.startedAt, copy: model.copy, openLink: openLink) {
                                        if followOutput { scrollToLatest(proxy) }
                                    }
                                }
                            }.frame(maxWidth: NativeTheme.columnWidth)
                                .padding(.horizontal, inset).padding(.vertical, 30)
                                .frame(maxWidth: .infinity)
                            Color.clear.frame(height: 1).id("bottom")
                                .background(GeometryReader { anchor in
                                    Color.clear.preference(key: ChatBottomKey.self, value: anchor.frame(in: .named("chat-scroll")).maxY)
                                })
                        }
                    }.coordinateSpace(name: "chat-scroll")
                        .modifier(ChatScrollIntent(followOutput: $followOutput))
                        .onPreferenceChange(ChatBottomKey.self) { value in
                            let next = value <= viewport.size.height + 85
                            if nearBottom != next { nearBottom = next }
                            if #unavailable(macOS 15), followOutput != next { followOutput = next }
                        }
                        .onAppear { navigate(using: proxy) }
                        .onChange(of: id) { _, _ in
                            renderedMessageLimit = TranscriptRenderingPolicy.initialMessageLimit
                            historyWindow = nil
                            followOutput = true
                            navigate(using: proxy)
                        }
                        .onChange(of: destination) { _, _ in navigate(using: proxy) }
                        .onChange(of: state?.startedAt) { _, value in
                            if value != nil { historyWindow = nil; followOutput = true; scrollToLatest(proxy) }
                        }
                        .onChange(of: messages.count) { oldCount, newCount in
                            renderedMessageLimit = TranscriptRenderingPolicy.adjustedLimit(
                                oldCount: oldCount,
                                newCount: newCount,
                                messageLimit: renderedMessageLimit,
                                followingLatest: followOutput
                            )
                            if followOutput { scrollToLatest(proxy) }
                        }
                        .onChange(of: messages.last?.taskUpdates) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .onChange(of: state?.running) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .overlay(alignment: .bottom) {
                            if !nearBottom || historyWindow != nil {
                                Button {
                                    historyWindow = nil; followOutput = true
                                    destination = nil
                                    scrollToLatest(proxy)
                                } label: {
                                    Image(systemName: "arrow.down").font(.system(size: 15)).frame(width: 34, height: 34)
                                        .background(NativeTheme.composer, in: Circle()).overlay(Circle().stroke(hairline))
                                }.buttonStyle(.nativeHover).help(L10n.text("К последнему сообщению")).padding(.bottom, 8)
                            }
                        }
                }
            }
            if let state, state.workspaceQuestions.contains(where: { $0.answer == nil }) {
                WorkspaceAgentQuestionsView(model: model, state: state).padding(.horizontal, inset)
            }
            if let id = conversationID ?? model.selectedID, let next = model.conversations.first(where: { $0.id == id })?.workspaceContinuation, state?.running != true {
                HStack {
                    Text(next).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    Spacer()
                    Button(L10n.pick("Продолжить задачу", "Continue task")) { Task { await model.resumeWorkspaceContinuation(id: id) } }
                }.padding(12).background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 12)).padding(.horizontal, inset)
            }
            ComposerView(model: model, conversationID: conversationID, panel: panel).padding(.horizontal, inset).padding(.top, 7).padding(.bottom, desktopGlass ? 18 : 8).background(desktopGlass ? Color.clear : canvas)
        }
        }.modifier(MainChatAttachmentDrop(model: model, enabled: panel == nil))
        .background(ConversationInteractionRegion(routing: model.conversationRouting, panel: panel,
            enabled: (panel?.visible ?? true) && (presentations?.pages.isEmpty ?? true)))
    }

    private func scrollToLatest(_ proxy: ScrollViewProxy) {
        // Wait for the new message/live timeline to participate in layout.
        Task { @MainActor in
            await Task.yield()
            if followOutput { proxy.scrollTo("bottom", anchor: .bottom) }
        }
    }

    private func navigate(using proxy: ScrollViewProxy) {
        guard let destination = destination, destination.conversationID == id,
              let target = destination.messageID, let index = messages.firstIndex(where: { $0.id == target }) else {
            historyWindow = nil; followOutput = true; scrollToLatest(proxy); return
        }
        historyWindow = TranscriptRenderingPolicy.focusedRange(totalCount: messages.count, targetIndex: index)
        followOutput = false
        Task { @MainActor in
            await Task.yield()
            guard self.destination == destination, id == destination.conversationID else { return }
            proxy.scrollTo(target, anchor: .center)
        }
    }

    private func loadEarlier(using proxy: ScrollViewProxy) {
        let previousFirstID = renderedMessages.first?.id
        if let window = historyWindow {
            historyWindow = max(0, window.lowerBound - TranscriptRenderingPolicy.pageSize)..<window.upperBound
        } else {
            renderedMessageLimit = TranscriptRenderingPolicy.expandedLimit(totalCount: messages.count, messageLimit: renderedMessageLimit)
        }
        guard let previousFirstID else { return }
        Task { @MainActor in
            await Task.yield()
            proxy.scrollTo(previousFirstID, anchor: .top)
        }
    }

    private func loadLater(using proxy: ScrollViewProxy) {
        guard let window = historyWindow else { return }
        let previousLast = renderedMessages.last?.id
        historyWindow = window.lowerBound..<min(messages.count, window.upperBound + TranscriptRenderingPolicy.pageSize)
        Task { @MainActor in
            await Task.yield()
            if let previousLast { proxy.scrollTo(previousLast, anchor: .bottom) }
        }
    }

    @ViewBuilder private var welcome: some View {
        if desktopGlass { FloatingWelcomeView() } else { ConversationWelcomeView(model: model, conversationID: conversationID, panel: panel) }
    }
}

/// The running turn's live output. It alone observes that output, so streamed text and
/// work-log rows re-render this section instead of every message of the conversation.
private struct LiveTurnSection: View {
    @ObservedObject var live: LiveTurnOutput
    let startedAt: Date?
    let copy: (String) -> Void
    let openLink: (URL) -> Void
    let grew: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            WorkTimelineView(log: live.workLog, agentReceipt: live.agentReceipt, toolItems: live.agentItems, live: true, startedAt: startedAt).equatable()
            if !live.stream.isEmpty { MessageMarkdownView(text: live.stream, copy: copy, openLink: openLink).equatable() }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .onChange(of: live.stream.count) { _, _ in grew() }
            .onChange(of: live.workLog) { _, _ in grew() }
    }
}

private struct MainChatAttachmentDrop: ViewModifier {
    let model: AppModel
    let enabled: Bool
    @ViewBuilder func body(content: Content) -> some View {
        if enabled { content.modifier(AttachmentDropTarget(model: model)) } else { content }
    }
}

private struct ChatBottomKey: PreferenceKey {
    static var defaultValue: CGFloat = .infinity
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

struct ChatScrollIntent: ViewModifier {
    @Binding var followOutput: Bool

    func body(content: Content) -> some View {
        if #available(macOS 15, *) {
            content.onScrollPhaseChange { old, new, context in
                if (new == .interacting || new == .tracking), followOutput { followOutput = false }
                if new == .idle && [.interacting, .tracking, .decelerating].contains(old) {
                    let next = context.geometry.visibleRect.maxY >= context.geometry.contentSize.height - 85
                    if followOutput != next { followOutput = next }
                }
            }
        } else { content }
    }
}

struct MessageView: View {
    let message: ChatMessage
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    var targetPanel: WorkspacePanelModel? = nil
    @Environment(\.workspacePresentations) private var presentations
    @State private var showRaw = false
    @State private var showLegacyActions = false
    @State private var showBrowserReference = false
    @StateObject private var responseExport = ResponseExportModel()

    var body: some View {
        if message.role == "user" {
            HStack(alignment: .top) {
                Spacer(minLength: 65)
                VStack(alignment: .leading, spacing: 10) {
                    let origin = AppModel.delegatedTaskOrigin(message.text)
                    if let origin {
                        // The model still receives the full origin header; the reader sees who sent it.
                        Label(L10n.format("От задачи «\(origin.task)» · \(origin.model)"), systemImage: "arrow.turn.down.right")
                            .font(.system(size: 11.5)).foregroundStyle(.secondary).lineLimit(2)
                            .help(L10n.text("Это сообщение отправила модель другой задачи через инструменты PM, а не вы."))
                    }
                    if !(message.imageContext ?? []).isEmpty { imageThumbnails }
                    Text(origin?.body ?? BrowserReferencePresentation(message.text)?.instruction ?? message.text).font(NativeTheme.messageFont).lineSpacing(6).textSelection(.enabled)
                        .help(message.createdAt.formatted(date: .omitted, time: .shortened))
                    if let page = BrowserReferencePresentation(message.text) {
                        DisclosureGroup(L10n.pick("Материал из браузера", "Browser reference"), isExpanded: $showBrowserReference) {
                            Text(page.source).font(.caption).textSelection(.enabled).foregroundStyle(.secondary)
                            ScrollView { Text(page.content).font(.system(size: 12)).textSelection(.enabled) }.frame(maxHeight: 220)
                        }.font(.caption).foregroundStyle(.secondary)
                    }
                    attachments
                }
                .padding(.horizontal, 18).padding(.vertical, 13)
                .background(NativeTheme.bubble, in: RoundedRectangle(cornerRadius: 20))
                .frame(maxWidth: 650, alignment: .trailing)
            }
        } else {
            VStack(alignment: .leading, spacing: 18) {
                if let work = message.workLog, work["schema"].text == "proto_mind.native_work_log.v1" {
                    WorkTimelineView(log: work, agentReceipt: message.agentRun ?? .null).equatable()
                } else if let receipt = message.agentRun, !receipt.isNull {
                    DisclosureGroup(L10n.text("Действия инструментов"), isExpanded: $showLegacyActions) {
                        AgentActivityView(items: receipt["items"].items, receipt: receipt).padding(.top, 8)
                    }.font(.system(size: 13)).foregroundStyle(.secondary)
                }
                if message.role == "report" {
                    Label(message.isError ? L10n.text("Нужна проверка") : L10n.text("Локальное ядро"), systemImage: message.isError ? "exclamationmark.circle" : "command")
                        .font(.system(size: 12)).foregroundStyle(message.isError ? Color.orange : .secondary)
                    // A failed turn explains itself in prose; command reports stay monospaced.
                    Text(message.text).font(message.isError ? NativeTheme.responseFont : NativeTheme.codeFont).textSelection(.enabled)
                        .lineSpacing(message.isError ? NativeTheme.responseLineSpacing : 0)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    MessageMarkdownView(text: message.text, copy: model.copy, openLink: { openLink($0) }).equatable()
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                if message.agentRun?["computer_use_cleanup"]["status"].text == "unconfirmed" {
                    Label(L10n.text("Не удалось подтвердить отключение Computer Use. Если управление осталось активно, остановите его в панели Computer Use."),
                          systemImage: "exclamationmark.triangle")
                        .font(.system(size: 12)).foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
                attachments
                if conversationID == nil || conversationID == model.selectedID, let (report, text) = model.memorySuggestions(for: message) { MemorySuggestionCard(app: model, report: report, text: text) }
                if let receipt = message.agentRun { CompletedFileChangesView(receipt: receipt, openLink: { openLink($0) }).equatable() }
                HStack(spacing: 17) {
                    ResponseCopyButton { model.copy(message.text) }
                    if message.role == "assistant", let sourceID = conversationID ?? model.selectedID {
                        Button {
                            model.openAnswerBesideChat(message, conversationID: sourceID, sourcePanel: targetPanel)
                        } label: { Image(systemName: "rectangle.trailinghalf.inset.filled") }
                            .help(L10n.pick("Открыть ответ рядом", "Open response beside chat"))
                            .accessibilityLabel(L10n.pick("Открыть ответ рядом", "Open response beside chat"))
                    }
                    if message.role == "assistant" || message.hasResponseDetails || message.turnReference != nil {
                        Menu {
                            if message.role == "assistant" {
                                Button(L10n.pick("Сохранить ответ…", "Save response…"), systemImage: "square.and.arrow.down") {
                                    let sourceID = conversationID ?? model.selectedID
                                    let title = model.conversations.first { $0.id == sourceID }?.displayTitle ?? ""
                                    responseExport.save(ResponseDocument(text: message.text, conversationTitle: title), using: model, in: presentations)
                                }
                            }
                            if message.role == "assistant", message.hasResponseDetails || message.turnReference != nil { Divider() }
                            if let conversationID, conversationID != model.selectedID {
                                Button(L10n.text("Об ответе"), systemImage: "info.circle") {
                                    model.showMessage(message, in: presentations)
                                }
                            } else {
                                if message.hasResponseDetails {
                                    Button(L10n.text("Об ответе"), systemImage: "info.circle") { model.showMessage(message, in: presentations) }
                                    Button(showRaw ? L10n.text("Скрыть исходный отчёт") : L10n.text("Исходный отчёт"), systemImage: "text.alignleft") { showRaw.toggle() }
                                }
                                if message.turnReference != nil {
                                    Button(L10n.text("Ход этой задачи"), systemImage: "clock.arrow.circlepath") { Task { await model.openWorkSession(for: message, in: presentations) } }
                                        .disabled(model.busy || model.loadingWorkSessions)
                                    Button(L10n.text("Цепочка диалога · Session Spine"), systemImage: "point.3.connected.trianglepath.dotted") { Task { await model.openSessionSpine(for: message, in: presentations) } }
                                        .disabled(model.busy || model.loadingWorkSessions || model.loadingSessionSpinePreview)
                                }
                            }
                        } label: {
                            Image(systemName: "ellipsis").foregroundColor(.secondary).frame(width: 28, height: 28)
                        }
                            .menuStyle(.borderlessButton).menuIndicator(.hidden).tint(.secondary).fixedSize().nativeHoverSurface()
                            .help(L10n.pick("Действия с ответом", "Response actions"))
                            .accessibilityLabel(L10n.pick("Действия с ответом", "Response actions"))
                    }
                }.buttonStyle(.nativeHover).font(.system(size: 13)).foregroundStyle(.secondary).padding(.top, 2)
                    .background(ResponseReadMarker(app: model, conversationID: conversationID ?? model.selectedID, messageID: message.id))
                if showRaw { Text(message.raw).font(.system(size: 11, design: .monospaced)).textSelection(.enabled) }
            }.frame(maxWidth: .infinity, alignment: .leading).responseExportFeedback(responseExport)
        }
    }

    private func openLink(_ url: URL) {
        if let targetPanel, let conversationID {
            if NativeBrowserURL.isWebURL(url) { targetPanel.openBrowser(url) }
            else { model.openPanelFile(url, conversationID: conversationID, panel: targetPanel) }
        } else { model.openWorkspaceLink(url) }
    }

    /// Attached images as pictures, like other chat apps show them; a click opens the local preview.
    private var imageThumbnails: some View {
        let images = message.imageContext ?? []
        return HStack(alignment: .top, spacing: 8) {
            ForEach(Array(images.enumerated()), id: \.offset) { _, image in
                AttachedImageThumbnail(image: image, existing: model.imageThumbnails[image["sha256"].text],
                                       maxSize: images.count > 1 ? CGSize(width: 180, height: 130) : CGSize(width: 260, height: 180)) {
                    Task { await model.previewImage(image["path"].text, expectedSHA: image["sha256"].text, canAttach: false, inWorkspacePanel: true,
                                                    targetPanel: targetPanel, conversationID: conversationID, in: presentations) }
                }
            }
        }
    }

    private var attachments: some View {
        Group {
        ForEach(Array((message.fileContext ?? []).enumerated()), id: \.offset) { _, file in
            Label(URL(fileURLWithPath: file["path"].text).lastPathComponent, systemImage: "doc.text")
                .font(.system(size: 11)).foregroundStyle(.secondary).textSelection(.enabled)
                .help(L10n.format("\(file["path"].text) · \(file["included_chars"].integer) символов · SHA \(file["sha256"].text.prefix(8))"))
            }
            // Images appear as pictures in the user's message; an answer does not repeat them.
            ForEach(Array((message.pdfContext ?? []).enumerated()), id: \.offset) { _, pdf in
                Button { Task { await model.previewPDF(pdf["path"].text, expected: pdf, canAttach: false, inWorkspacePanel: true, targetPanel: targetPanel, conversationID: conversationID, in: presentations) } } label: {
                    Label(L10n.format("\(pdf["name"].text) · стр. \(pdf["pages"].items.map { String($0["number"].integer) }.joined(separator: ", "))"), systemImage: "doc.richtext")
                        .font(.caption).foregroundStyle(.secondary)
                }.buttonStyle(.nativeHover).disabled((conversationID ?? model.selectedID).map { model.canReceiveAttachments(for: $0) } != true)
                    .help(L10n.text("Локально прочитать выбранные страницы с проверкой SHA-256; без повторной отправки"))
            }
        }
    }
}

struct NativeComposer: NSViewRepresentable {
    @Environment(\.isEnabled) private var surfaceEnabled
    @Binding var text: String
    var revision: Int
    var enabled: Bool
    var focusOnRevision = true
    var onStop: () -> Void = {}
    var canDrop = false
    var onDrop: ([URL]) -> Bool = { _ in false }
    var onDropHover: (Bool) -> Void = { _ in }
    var onDropError: (String) -> Void = { _ in }
    var onSend: () -> Void

    final class Editor: NSTextView {
        var pendingProgrammaticFocus = false
        private var focusObservers: [NSObjectProtocol] = []
        private var requestedEditable = true
        private var surfaceAllowsInteraction = true
        private var interactionScheduled = false
        private var dismantled = false

        func updateInteraction(enabled: Bool, surfaceEnabled: Bool) {
            requestedEditable = enabled && surfaceEnabled
            surfaceAllowsInteraction = surfaceEnabled
            if !surfaceEnabled { pendingProgrammaticFocus = false }
            scheduleInteraction()
        }

        private func scheduleInteraction() {
            guard !dismantled, !interactionScheduled else { return }
            interactionScheduled = true
            // AppKit's input-method activation can run a nested event loop.
            // Never enter it while SwiftUI is updating its view graph.
            DispatchQueue.main.async { [weak self] in
                guard let self, !self.dismantled else { return }
                self.interactionScheduled = false
                if !self.surfaceAllowsInteraction, self.window?.firstResponder === self {
                    self.window?.makeFirstResponder(nil)
                }
                if self.isEditable != self.requestedEditable {
                    self.isEditable = self.requestedEditable
                }
                self.applyProgrammaticFocus()
            }
        }

        func dismantleInteraction() {
            dismantled = true
            pendingProgrammaticFocus = false
            focusObservers.forEach(NotificationCenter.default.removeObserver)
            focusObservers = []
        }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            focusObservers.forEach(NotificationCenter.default.removeObserver)
            focusObservers = []
            guard let window else { return }
            for name in [NSWindow.didBecomeKeyNotification, NSWindow.didEndSheetNotification] {
                focusObservers.append(NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) { [weak self] _ in
                    self?.scheduleInteraction()
                })
            }
            scheduleInteraction()
        }

        deinit { focusObservers.forEach(NotificationCenter.default.removeObserver) }

        func requestProgrammaticFocus() {
            guard !dismantled, surfaceAllowsInteraction else { return }
            pendingProgrammaticFocus = true
            scheduleInteraction()
        }

        private func applyProgrammaticFocus() {
            guard !dismantled, pendingProgrammaticFocus, requestedEditable,
                  surfaceAllowsInteraction, isEditable, let window,
                  window.isKeyWindow, window.attachedSheet == nil else { return }
            pendingProgrammaticFocus = false
            if window.firstResponder === self || window.makeFirstResponder(self) {
                scrollRangeToVisible(selectedRange())
            } else if surfaceAllowsInteraction {
                pendingProgrammaticFocus = true
            }
        }

        var onSend: (() -> Void)?
        var onStop: (() -> Void)?
        var canDrop = false
        var onFiles: (([URL]) -> Bool)?
        var onDropHover: ((Bool) -> Void)?
        var onDropError: ((String) -> Void)?
        private func containsFiles(_ sender: NSDraggingInfo) -> Bool {
            sender.draggingPasteboard.types?.contains(.fileURL) == true
        }
        override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
            guard containsFiles(sender) else { return super.draggingEntered(sender) }
            onDropHover?(canDrop)
            return canDrop ? .copy : []
        }
        override func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation {
            guard containsFiles(sender) else { return super.draggingUpdated(sender) }
            onDropHover?(canDrop)
            return canDrop ? .copy : []
        }
        override func draggingExited(_ sender: NSDraggingInfo?) {
            onDropHover?(false)
            super.draggingExited(sender)
        }
        override func prepareForDragOperation(_ sender: NSDraggingInfo) -> Bool {
            containsFiles(sender) ? canDrop : super.prepareForDragOperation(sender)
        }
        override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
            guard containsFiles(sender) else { return super.performDragOperation(sender) }
            return acceptFileDrop(sender.draggingPasteboard)
        }
        func acceptFileDrop(_ pasteboard: NSPasteboard) -> Bool {
            defer { onDropHover?(false) }
            guard canDrop else { return false }
            do { return onFiles?(try NativeAttachmentDrop.pasteboardURLs(pasteboard)) ?? false }
            catch { onDropError?(error.localizedDescription); return false }
        }
        override func keyDown(with event: NSEvent) {
            guard !dismantled, requestedEditable, surfaceAllowsInteraction else { return }
            if event.keyCode == 53 && !hasMarkedText() {
                onStop?()
            } else if [36, 76].contains(event.keyCode) && !event.modifierFlags.contains(.shift) && !hasMarkedText() {
                onSend?()
            } else { super.keyDown(with: event) }
        }
    }
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: NativeComposer
        var appliedRevision: Int?
        init(_ parent: NativeComposer) { self.parent = parent }
        func textDidChange(_ notification: Notification) {
            guard let editor = notification.object as? NSTextView else { return }
            parent.text = editor.string
        }
    }
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        let editor = Editor()
        editor.isRichText = false
        editor.drawsBackground = false
        editor.font = .systemFont(ofSize: NativeTheme.messageSize)
        editor.textColor = .labelColor
        editor.insertionPointColor = .labelColor
        editor.isVerticallyResizable = true
        editor.isHorizontallyResizable = false
        editor.autoresizingMask = [.width]
        editor.textContainer?.widthTracksTextView = true
        editor.textContainerInset = NSSize(width: 12, height: 16)
        editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.registerForDraggedTypes([.fileURL])
        editor.delegate = context.coordinator
        editor.setAccessibilityLabel(L10n.text("Сообщение Proto-Mind"))
        scroll.documentView = editor
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let editor = scroll.documentView as? Editor else { return }
        editor.setAccessibilityLabel(L10n.text("Сообщение Proto-Mind"))
        editor.updateInteraction(enabled: enabled, surfaceEnabled: surfaceEnabled)
        if !focusOnRevision || !surfaceEnabled { editor.pendingProgrammaticFocus = false }
        // SwiftUI may render an older binding while NSTextView is handling rapid keystrokes.
        // Only an explicit programmatic revision may replace the editor's live text.
        if context.coordinator.appliedRevision != revision {
            editor.string = text
            editor.setSelectedRange(NSRange(location: (text as NSString).length, length: 0))
            context.coordinator.appliedRevision = revision
            if revision > 0, focusOnRevision && surfaceEnabled { editor.requestProgrammaticFocus() }
        }
        editor.onSend = onSend
        editor.onStop = onStop
        // A prepared draft can arrive while the RPC still marks the composer
        // disabled. Keep its request until both the field and parent window are ready.
        if enabled, editor.pendingProgrammaticFocus { editor.requestProgrammaticFocus() }
        editor.canDrop = canDrop
        editor.onFiles = onDrop
        editor.onDropHover = onDropHover
        editor.onDropError = onDropError
    }

    static func dismantleNSView(_ scroll: NSScrollView, coordinator: Coordinator) {
        (scroll.documentView as? Editor)?.dismantleInteraction()
    }
}
