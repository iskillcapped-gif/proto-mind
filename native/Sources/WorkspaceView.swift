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
        .frame(minWidth: desktop.enabled ? DesktopGeometry.minimumWorkspace.width : 940,
               minHeight: desktop.enabled ? DesktopGeometry.minimumWorkspace.height : 640)
        .background(DesktopWindowAttachment(app: model, openSettings: { openSettings() }))
        .tint(NativeTheme.accent)
        .font(NativeTheme.interfaceFont)
        .buttonStyle(.nativeHover)
        .disclosureGroupStyle(NativeDisclosureStyle())
        .onChange(of: model.section) { _, next in if next.libraryCollection != nil { libraryExpanded = true } }
        .workspaceSheet(item: $model.exitPrompt) { WorkspaceExitView(app: model, prompt: $0) }
        .workspaceSheet(isPresented: $model.showSettings) { NativeSettingsView(model: model) }
        .workspaceSheet(isPresented: $model.showFirstLaunch, onDismiss: {
            FirstLaunch.dismiss(model.serviceClient.configuration)
        }) { FirstLaunchView(model: model) }
        .workspaceSheet(isPresented: $model.showInspector) {
            EvidenceInspectorView(model: model).workspacePageSize(width: 560, height: 680)
        }
        .workspaceSheet(item: $model.pendingAction) { action in
            VStack(alignment: .leading, spacing: 20) {
                Label("Подтвердить команду", systemImage: "hand.raised").font(.title2.weight(.semibold))
                Text("Эта команда меняет состояние или требует повышенного внимания. Модель не запрашивала её выполнение: ниже именно ваш ввод.")
                    .foregroundStyle(.secondary)
                ScrollView { Text(action.text).font(.system(.body, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                    .frame(maxHeight: 100).padding(12).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 10))
                Text(action.summary).font(.callout).textSelection(.enabled)
                Text("Внутренние approval/token/preview-гейты Proto-Mind по-прежнему действуют.").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button("Отмена") { model.pendingAction = nil }.keyboardShortcut(.cancelAction)
                    Spacer()
                    Button("Выполнить мой ввод") { Task { await model.confirmPending() } }.buttonStyle(.borderedProminent).nativeHoverSurface()
                }
            }.padding(28).workspacePageSize(width: 560)
        }
        .workspaceSheet(item: $model.pendingAgentAccess) { request in AgentAccessSheet(model: model, request: request) }
        .workspaceSheet(isPresented: $model.showWorkSessions, onDismiss: {
            if model.selected?.draftContinuation != nil { model.focusReturnedDraft() }
        }) { WorkSessionsView(model: model) }
        .workspaceSheet(isPresented: $model.showConversationHistory, onDismiss: { model.focusReturnedDraft() }) {
            ConversationHistoryView(model: model)
        }
        .workspaceSheet(isPresented: $model.showHistoryBackups) { HistoryBackupsView(model: model) }
        .workspaceSheet(isPresented: $model.showPrivateBackup, onDismiss: {
            if model.quitAfterPrivateBackup { NSApp.terminate(nil) }
        }) { PrivateBackupView(app: model, backup: model.privateBackup) }
        .workspaceSheet(isPresented: $model.showCodexUsage) { CodexUsageView(app: model, usage: model.codexUsage) }
        .workspaceSheet(item: $model.sessionSpinePreview) { SessionSpinePreviewView(model: model, preview: $0) }
        .workspaceSheet(isPresented: $model.showContextDesk) { ContextDeskView(model: model) }
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
                            Button("Открыть Automation") { model.openAutomationSettings() }
                                .buttonStyle(.bordered).nativeHoverSurface()
                        }
                        Button { model.clearError() } label: { Image(systemName: "xmark") }.buttonStyle(.nativeHover)
                    }.padding(14).background(Color.orange.opacity(0.09))
                }
                WorkspaceContentHost(app: model, presentations: model.presentations)
            }
            .background(canvas)
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
                            .accessibilityLabel("Журнал работы")
                            .help("Журнал работы и ручное продолжение")
                        Button {
                            panel.visible.toggle(); panel.expanded = false
                            if panel.visible && panel.selectedID == nil { Task { await model.refreshWorkspace() } }
                        } label: { Image(systemName: "sidebar.right") }
                            .help("Файлы и браузер").accessibilityLabel("Рабочая панель")
                    }
                }
            }
            .toolbarBackground(canvas, for: .windowToolbar)
            .toolbarBackground(.visible, for: .windowToolbar)
        }
    }

    private var sectionTitle: String {
        switch model.section {
        case .chat: return model.selected?.title ?? "Диалог"
        case .commands: return "Команды"
        case .overview: return "Диагностика"
        case .workspace: return "Папка проекта"
        case .github: return "GitHub"
        case .memory, .goals, .skills: return model.section.libraryCollection?.title ?? "Библиотека"
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
    @ObservedObject var panel: WorkspacePanelModel
    @State private var fraction: CGFloat = 0.5
    @State private var dragStart: CGFloat?

    var body: some View {
        GeometryReader { geometry in
            let width = WorkspacePanelLayout.width(total: geometry.size.width, fraction: fraction)
            HStack(spacing: 0) {
                if !panel.visible || !panel.expanded {
                    mainContent.frame(width: panel.visible ? max(0, geometry.size.width - width - WorkspacePanelLayout.divider) : geometry.size.width)
                        .frame(maxHeight: .infinity)
                }
                if panel.visible {
                    if !panel.expanded {
                        Rectangle().fill(NativeTheme.hairline).frame(width: 1)
                            .frame(width: WorkspacePanelLayout.divider, height: geometry.size.height)
                            .contentShape(Rectangle())
                            .onHover { inside in if inside { NSCursor.resizeLeftRight.set() } else { NSCursor.arrow.set() } }
                            .gesture(DragGesture(minimumDistance: 0).onChanged { drag in
                                if dragStart == nil { dragStart = fraction }
                                let available = max(1, geometry.size.width - WorkspacePanelLayout.divider)
                                fraction = WorkspacePanelLayout.width(total: geometry.size.width,
                                    fraction: (dragStart ?? 0.5) - drag.translation.width / available) / available
                            }.onEnded { _ in dragStart = nil })
                            .accessibilityLabel("Ширина рабочей панели")
                            .accessibilityValue("\(Int(fraction * 100)) процентов")
                            .accessibilityAdjustableAction { direction in
                                let available = max(1, geometry.size.width - WorkspacePanelLayout.divider)
                                let next = fraction + (direction == .increment ? 0.05 : -0.05)
                                fraction = WorkspacePanelLayout.width(total: geometry.size.width, fraction: next) / available
                            }
                    }
                    WorkspacePanelView(model: model, panel: panel, width: panel.expanded ? geometry.size.width : width)
                        .frame(width: panel.expanded ? geometry.size.width : width)
                        .frame(maxHeight: .infinity)
                }
            }
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
    static let initialMessageLimit = 80
    static let pageSize = 60

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

private struct ChatView: View {
    @Environment(\.desktopGlass) private var desktopGlass
    @ObservedObject var model: AppModel
    @State private var nearBottom = true
    @State private var followOutput = true
    @State private var renderedMessageLimit = TranscriptRenderingPolicy.initialMessageLimit
    @State private var historyWindow: Range<Int>?

    private var renderedMessages: ArraySlice<ChatMessage> {
        let range = historyWindow ?? TranscriptRenderingPolicy.renderedRange(
            totalCount: model.messages.count,
            messageLimit: renderedMessageLimit
        )
        return model.messages[min(range.lowerBound, model.messages.count)..<min(range.upperBound, model.messages.count)]
    }

    private var hiddenMessageCount: Int {
        renderedMessages.startIndex
    }

    var body: some View {
        VStack(spacing: 0) {
            WorkSessionNoticeBanner(model: model)
            GeometryReader { viewport in
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(spacing: 0) {
                            if model.messages.isEmpty { welcome.padding(.top, desktopGlass ? 12 : 60).padding(.bottom, 24) }
                            // Variable-height selectable rows can enter a retained layout loop
                            // in macOS SwiftUI's lazy stack after a long-lived window resumes.
                            VStack(alignment: .leading, spacing: 34) {
                                if hiddenMessageCount > 0 {
                                    Button {
                                        loadEarlier(using: proxy)
                                    } label: {
                                        Label(
                                            "Показать предыдущие \(min(TranscriptRenderingPolicy.pageSize, hiddenMessageCount)) · скрыто \(hiddenMessageCount)",
                                            systemImage: "arrow.up.to.line"
                                        )
                                        .font(.system(size: 12))
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 8)
                                    }
                                    .buttonStyle(.nativeHover)
                                    .help("История хранится полностью; загружается только следующая часть интерфейса")
                                }
                                ForEach(renderedMessages) { message in
                                    VStack(alignment: .leading, spacing: 16) {
                                        MessageView(message: message, model: model)
                                        if let updates = message.taskUpdates, !updates.isEmpty {
                                            TaskUpdatesView(updates: updates, active: model.activeTaskMessageID == message.id,
                                                            copy: model.copy)
                                        }
                                    }.id(message.id)
                                        .background(model.transcriptDestination?.conversationID == model.selectedID
                                            && model.transcriptDestination?.messageID == message.id ? NativeTheme.selection : .clear,
                                            in: RoundedRectangle(cornerRadius: 10))
                                }
                                if renderedMessages.endIndex < model.messages.count {
                                    Button("Показать следующие сообщения") { loadLater(using: proxy) }
                                        .font(.system(size: 12)).frame(maxWidth: .infinity).padding(.vertical, 8)
                                        .accessibilityLabel("Показать следующие сообщения")
                                }
                                if model.selectedExecution?.running == true {
                                    VStack(alignment: .leading, spacing: 20) {
                                        WorkTimelineView(log: model.workLog, agentReceipt: model.agentReceipt,
                                                         toolItems: model.agentItems, live: true, startedAt: model.turnStartedAt)
                                        if !model.stream.isEmpty { MessageMarkdownView(text: model.stream, copy: model.copy, openLink: { model.openWorkspaceLink($0) }) }
                                    }.frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }.frame(maxWidth: NativeTheme.columnWidth)
                                .padding(.horizontal, desktopGlass ? 24 : NativeTheme.conversationInset).padding(.vertical, 30)
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
                        .onChange(of: model.selectedID) { _, _ in
                            renderedMessageLimit = TranscriptRenderingPolicy.initialMessageLimit
                            historyWindow = nil
                            followOutput = true
                            navigate(using: proxy)
                        }
                        .onChange(of: model.transcriptDestination) { _, _ in navigate(using: proxy) }
                        .onChange(of: model.turnStartedAt) { _, value in
                            if value != nil { historyWindow = nil; followOutput = true; scrollToLatest(proxy) }
                        }
                        .onChange(of: model.messages.count) { oldCount, newCount in
                            renderedMessageLimit = TranscriptRenderingPolicy.adjustedLimit(
                                oldCount: oldCount,
                                newCount: newCount,
                                messageLimit: renderedMessageLimit,
                                followingLatest: followOutput
                            )
                            if followOutput { scrollToLatest(proxy) }
                        }
                        .onChange(of: model.stream.count) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .onChange(of: model.messages.last?.taskUpdates) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .onChange(of: model.workLog) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .onChange(of: model.selectedExecution?.running) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .overlay(alignment: .bottom) {
                            if !nearBottom || historyWindow != nil {
                                Button {
                                    historyWindow = nil; followOutput = true
                                    model.transcriptDestination = nil
                                    scrollToLatest(proxy)
                                } label: {
                                    Image(systemName: "arrow.down").font(.system(size: 15)).frame(width: 34, height: 34)
                                        .background(NativeTheme.composer, in: Circle()).overlay(Circle().stroke(hairline))
                                }.buttonStyle(.nativeHover).help("К последнему сообщению").padding(.bottom, 8)
                            }
                        }
                }
            }
            ComposerView(model: model).padding(.horizontal, desktopGlass ? 24 : NativeTheme.conversationInset).padding(.top, 7).padding(.bottom, desktopGlass ? 18 : 8).background(desktopGlass ? Color.clear : canvas)
        }.modifier(AttachmentDropTarget(model: model))
    }

    private func scrollToLatest(_ proxy: ScrollViewProxy) {
        // Wait for the new message/live timeline to participate in layout.
        Task { @MainActor in
            await Task.yield()
            if followOutput { proxy.scrollTo("bottom", anchor: .bottom) }
        }
    }

    private func navigate(using proxy: ScrollViewProxy) {
        guard let destination = model.transcriptDestination, destination.conversationID == model.selectedID,
              let target = destination.messageID, let index = model.messages.firstIndex(where: { $0.id == target }) else {
            historyWindow = nil; followOutput = true; scrollToLatest(proxy); return
        }
        historyWindow = TranscriptRenderingPolicy.focusedRange(totalCount: model.messages.count, targetIndex: index)
        followOutput = false
        Task { @MainActor in
            await Task.yield()
            guard model.transcriptDestination == destination, model.selectedID == destination.conversationID else { return }
            proxy.scrollTo(target, anchor: .center)
        }
    }

    private func loadEarlier(using proxy: ScrollViewProxy) {
        let previousFirstID = renderedMessages.first?.id
        if let window = historyWindow {
            historyWindow = max(0, window.lowerBound - TranscriptRenderingPolicy.pageSize)..<window.upperBound
        } else {
            renderedMessageLimit = TranscriptRenderingPolicy.expandedLimit(totalCount: model.messages.count, messageLimit: renderedMessageLimit)
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
        historyWindow = window.lowerBound..<min(model.messages.count, window.upperBound + TranscriptRenderingPolicy.pageSize)
        Task { @MainActor in
            await Task.yield()
            if let previousLast { proxy.scrollTo(previousLast, anchor: .bottom) }
        }
    }

    @ViewBuilder private var welcome: some View {
        if desktopGlass { FloatingWelcomeView() } else { ConversationWelcomeView(model: model) }
    }
}

private struct ChatBottomKey: PreferenceKey {
    static var defaultValue: CGFloat = .infinity
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

private struct ChatScrollIntent: ViewModifier {
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

private struct MessageView: View {
    let message: ChatMessage
    @ObservedObject var model: AppModel
    @State private var showRaw = false
    @State private var showLegacyActions = false

    var body: some View {
        if message.role == "user" {
            HStack(alignment: .top) {
                Spacer(minLength: 65)
                VStack(alignment: .leading, spacing: 10) {
                    Text(message.text).font(NativeTheme.messageFont).lineSpacing(6).textSelection(.enabled)
                        .help(message.createdAt.formatted(date: .omitted, time: .shortened))
                    attachments
                }
                .padding(.horizontal, 18).padding(.vertical, 13)
                .background(NativeTheme.bubble, in: RoundedRectangle(cornerRadius: 20))
                .frame(maxWidth: 650, alignment: .trailing)
            }
        } else {
            VStack(alignment: .leading, spacing: 18) {
                if let work = message.workLog, work["schema"].text == "proto_mind.native_work_log.v1" {
                    WorkTimelineView(log: work, agentReceipt: message.agentRun ?? .null)
                } else if let receipt = message.agentRun, !receipt.isNull {
                    DisclosureGroup("Действия инструментов", isExpanded: $showLegacyActions) {
                        AgentActivityView(items: receipt["items"].items, receipt: receipt).padding(.top, 8)
                    }.font(.system(size: 13)).foregroundStyle(.secondary)
                }
                if message.role == "report" {
                    Label(message.isError ? "Нужна проверка" : "Локальное ядро", systemImage: message.isError ? "exclamationmark.circle" : "command")
                        .font(.system(size: 12)).foregroundStyle(message.isError ? Color.orange : .secondary)
                    Text(message.text).font(NativeTheme.codeFont).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    MessageMarkdownView(text: message.text, copy: model.copy, openLink: { model.openWorkspaceLink($0) })
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                if message.agentRun?["computer_use_cleanup"]["status"].text == "unconfirmed" {
                    Label("Не удалось подтвердить отключение Computer Use. Если управление осталось активно, остановите его в панели Computer Use.",
                          systemImage: "exclamationmark.triangle")
                        .font(.system(size: 12)).foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
                attachments
                if let (report, text) = model.memorySuggestions(for: message) { MemorySuggestionCard(app: model, report: report, text: text) }
                if let receipt = message.agentRun { CompletedFileChangesView(receipt: receipt, openLink: { model.openWorkspaceLink($0) }) }
                HStack(spacing: 17) {
                    Button { model.copy(message.text) } label: { Image(systemName: "doc.on.doc") }
                        .help("Копировать ответ").accessibilityLabel("Копировать ответ")
                    if message.hasResponseDetails || message.turnReference != nil {
                        Menu {
                            if message.hasResponseDetails {
                                Button("Об ответе", systemImage: "info.circle") { model.showMessage(message) }
                                Button(showRaw ? "Скрыть исходный отчёт" : "Исходный отчёт", systemImage: "text.alignleft") { showRaw.toggle() }
                            }
                            if message.turnReference != nil {
                                Button("Ход этой задачи", systemImage: "clock.arrow.circlepath") { Task { await model.openWorkSession(for: message) } }
                                    .disabled(model.busy || model.loadingWorkSessions)
                                Button("Цепочка диалога · Session Spine", systemImage: "point.3.connected.trianglepath.dotted") { Task { await model.openSessionSpine(for: message) } }
                                    .disabled(model.busy || model.loadingWorkSessions || model.loadingSessionSpinePreview)
                            }
                        } label: {
                            Label {
                                Text("Подробнее").foregroundColor(.secondary)
                            } icon: {
                                Image(systemName: "ellipsis").foregroundColor(.secondary)
                            }
                        }
                            .menuStyle(.borderlessButton).tint(.secondary).fixedSize().nativeHoverSurface().accessibilityLabel("Подробнее об ответе")
                    }
                }.buttonStyle(.nativeHover).font(.system(size: 13)).foregroundStyle(.secondary).padding(.top, 2)
                if showRaw { Text(message.raw).font(.system(size: 11, design: .monospaced)).textSelection(.enabled) }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var attachments: some View {
        Group {
        ForEach(Array((message.fileContext ?? []).enumerated()), id: \.offset) { _, file in
            Label(URL(fileURLWithPath: file["path"].text).lastPathComponent, systemImage: "doc.text")
                .font(.system(size: 11)).foregroundStyle(.secondary).textSelection(.enabled)
                .help("\(file["path"].text) · \(file["included_chars"].integer) символов · SHA \(file["sha256"].text.prefix(8))")
            }
            ForEach(Array((message.imageContext ?? []).enumerated()), id: \.offset) { _, image in
                Button {
                    Task { await model.previewImage(image["path"].text, expectedSHA: image["sha256"].text, canAttach: false, inWorkspacePanel: true) }
                } label: {
                    Label("\(image["name"].text) · \(image["width"].integer) × \(image["height"].integer)", systemImage: "photo")
                        .font(.caption).foregroundStyle(.secondary)
                }.buttonStyle(.nativeHover).disabled(model.busy || model.loadingImagePreview)
                    .help("Локальный просмотр исходного файла с проверкой SHA-256. Изображение не отправляется повторно.")
            }
            ForEach(Array((message.pdfContext ?? []).enumerated()), id: \.offset) { _, pdf in
                Button { Task { await model.previewPDF(pdf["path"].text, expected: pdf, canAttach: false, inWorkspacePanel: true) } } label: {
                    Label("\(pdf["name"].text) · стр. \(pdf["pages"].items.map { String($0["number"].integer) }.joined(separator: ", "))", systemImage: "doc.richtext")
                        .font(.caption).foregroundStyle(.secondary)
                }.buttonStyle(.nativeHover).disabled(!model.canReceiveAttachments)
                    .help("Локально прочитать выбранные страницы с проверкой SHA-256; без повторной отправки")
            }
        }
    }
}

struct NativeComposer: NSViewRepresentable {
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

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            focusObservers.forEach(NotificationCenter.default.removeObserver)
            focusObservers = []
            guard let window else { return }
            for name in [NSWindow.didBecomeKeyNotification, NSWindow.didEndSheetNotification] {
                focusObservers.append(NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) { [weak self] _ in
                    DispatchQueue.main.async { self?.applyProgrammaticFocus() }
                })
            }
            applyProgrammaticFocus()
        }

        deinit { focusObservers.forEach(NotificationCenter.default.removeObserver) }

        func requestProgrammaticFocus() {
            pendingProgrammaticFocus = true
            DispatchQueue.main.async { [weak self] in self?.applyProgrammaticFocus() }
        }

        private func applyProgrammaticFocus() {
            guard pendingProgrammaticFocus, isEditable, let window,
                  window.isKeyWindow, window.attachedSheet == nil else { return }
            if window.makeFirstResponder(self) {
                pendingProgrammaticFocus = false
                scrollRangeToVisible(selectedRange())
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
        editor.setAccessibilityLabel("Сообщение Proto-Mind")
        scroll.documentView = editor
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let editor = scroll.documentView as? Editor else { return }
        editor.isEditable = enabled
        if !focusOnRevision { editor.pendingProgrammaticFocus = false }
        // SwiftUI may render an older binding while NSTextView is handling rapid keystrokes.
        // Only an explicit programmatic revision may replace the editor's live text.
        if context.coordinator.appliedRevision != revision {
            editor.string = text
            editor.setSelectedRange(NSRange(location: (text as NSString).length, length: 0))
            context.coordinator.appliedRevision = revision
            if revision > 0, focusOnRevision { editor.requestProgrammaticFocus() }
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
}
