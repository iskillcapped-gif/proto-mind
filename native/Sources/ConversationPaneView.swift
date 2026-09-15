import AppKit
import SwiftUI

struct ConversationPaneView: View {
    @ObservedObject var app: AppModel
    let conversationID: UUID
    @ObservedObject var panel: WorkspacePanelModel
    @State private var draft = ""
    @State private var revision = 0
    @State private var modelMenu = false
    @State private var follow = true
    @State private var limit = TranscriptRenderingPolicy.initialMessageLimit
    @State private var contextMenu = false

    private var conversation: Conversation? { app.conversations.first { $0.id == conversationID } }
    private var state: ConversationExecution? { app.executions[conversationID] }
    private var running: Bool { state?.running == true }
    private var hasAttachments: Bool {
        conversation.map { !$0.pendingFiles.isEmpty || !$0.pendingImages.isEmpty || !$0.pendingPDFs.isEmpty } ?? false
    }
    private var hasInput: Bool { !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || hasAttachments }
    private var canSend: Bool {
        hasInput && !app.operationBusy && conversation?.archived == false && !app.historyPersistence.blocksSubmission
            && !app.store.writeBlocked && (!running || state.map(app.canUpdateTask) == true)
    }

    var body: some View {
        if let conversation {
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    if running { WorkingIndicator() }
                    Text(conversation.title).font(.system(size: 12, weight: .medium)).lineLimit(1)
                    Spacer(minLength: 0)
                    Button { app.select(conversationID) } label: { Image(systemName: "arrow.up.left.square") }
                        .help("Открыть этот диалог в основном чате").accessibilityLabel("Открыть диалог в основном чате")
                }.padding(.horizontal, 14).padding(.vertical, 8)
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 24) {
                            if conversation.messages.count > limit {
                                Button("Предыдущие сообщения") { limit += TranscriptRenderingPolicy.pageSize }
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            if conversation.messages.isEmpty && !running {
                                VStack(alignment: .leading, spacing: 10) {
                                    Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 24, weight: .light))
                                    Text("Ещё одно пространство для мысли").font(.system(size: 17, weight: .medium))
                                    Text("Начните отдельную задачу. Её модель, сообщения и работа сохраняются в этом диалоге.")
                                        .font(.system(size: 12)).foregroundStyle(.secondary)
                                }.padding(.vertical, 20)
                            }
                            ForEach(conversation.messages.suffix(limit)) { message in
                                MessageView(message: message, model: app, conversationID: conversationID, targetPanel: panel)
                                if let updates = message.taskUpdates {
                                    TaskUpdatesView(updates: updates, active: running && state?.sourceMessageID == message.id, copy: app.copy)
                                }
                            }
                            if running, let state {
                                WorkTimelineView(log: state.workLog, agentReceipt: state.agentReceipt, toolItems: state.agentItems,
                                                 live: true, startedAt: state.startedAt)
                                if !state.stream.isEmpty {
                                    MessageMarkdownView(text: state.stream, copy: app.copy, openLink: { openLink($0) })
                                }
                            }
                            Color.clear.frame(height: 1).id("pane-bottom")
                        }.frame(maxWidth: NativeTheme.columnWidth).padding(18).frame(maxWidth: .infinity)
                    }.modifier(ChatScrollIntent(followOutput: $follow))
                        .onChange(of: conversation.messages.count) { _, _ in scroll(proxy) }
                        .onChange(of: state?.stream.count) { _, _ in scroll(proxy) }
                        .onChange(of: state?.workLog) { _, _ in scroll(proxy) }
                        .onChange(of: running) { _, _ in scroll(proxy) }
                        .onAppear { scroll(proxy) }
                        .overlay(alignment: .bottomTrailing) {
                            if !follow {
                                Button { follow = true; scroll(proxy) } label: {
                                    Image(systemName: "arrow.down").padding(9).background(.regularMaterial, in: Circle())
                                }.buttonStyle(.plain).padding(12).help("К последнему сообщению")
                            }
                        }
                }
                composer(conversation).padding(.horizontal, 12).padding(.bottom, 12)
            }
            .onAppear { draft = conversation.draft; revision += 1 }
            .onChange(of: conversation.draft) { _, next in
                if draft != next { draft = next; revision += 1 }
            }
        } else {
            ContentUnavailableView("Диалог недоступен", systemImage: "bubble.left", description: Text("Он мог быть удалён или заменён при восстановлении истории."))
        }
    }

    private func openLink(_ url: URL) {
        if NativeBrowserURL.isWebURL(url) { panel.openBrowser(url) }
        else { app.openPanelFile(url, conversationID: conversationID, panel: panel) }
    }

    private func scroll(_ proxy: ScrollViewProxy) {
        guard follow else { return }
        Task { @MainActor in await Task.yield(); if follow { proxy.scrollTo("pane-bottom", anchor: .bottom) } }
    }

    private func composer(_ conversation: Conversation) -> some View {
        VStack(spacing: 0) {
            if hasAttachments {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(Array((conversation.pendingFiles + conversation.pendingPDFs + conversation.pendingImages).enumerated()), id: \.offset) { _, item in
                            Label(URL(fileURLWithPath: item["path"].text).lastPathComponent, systemImage: "paperclip")
                                .font(.caption).lineLimit(1)
                        }
                        Button("Убрать") { app.clearPanelAttachments(conversationID) }
                    }.padding(10)
                }
            }
            ZStack(alignment: .topLeading) {
                if draft.isEmpty {
                    Text(running ? "Дополнение к задаче…" : "Сообщение Proto-Mind…")
                        .font(NativeTheme.messageFont).foregroundStyle(.secondary.opacity(0.7)).padding(.horizontal, 12).padding(.top, 16)
                }
                NativeComposer(text: Binding(get: { draft }, set: { draft = $0; app.setConversationDraft($0, id: conversationID) }),
                    revision: revision, enabled: !conversation.archived, focusOnRevision: false,
                    onStop: { if running { Task { await app.stop(conversationID: conversationID) } } },
                    onSend: send)
                    .frame(height: min(115, max(56, CGFloat(draft.components(separatedBy: "\n").count) * 23 + 28)))
            }
            HStack(spacing: 5) {
                Button { app.choosePanelAttachment(conversationID: conversationID) } label: { Image(systemName: "plus").frame(width: 26, height: 28) }
                    .help("Прикрепить текстовый файл проекта или PDF").disabled(running || app.operationBusy)
                Button { contextMenu.toggle() } label: { Image(systemName: "slider.horizontal.3").frame(width: 26, height: 28) }
                    .help("Папка, доступ и память").disabled(running || app.operationBusy)
                    .composerPopover(isPresented: $contextMenu, width: 295) { contextOptions(conversation) }
                Spacer(minLength: 0)
                Button { modelMenu.toggle() } label: {
                    HStack(spacing: 4) {
                        Text(modelLabel(conversation)).lineLimit(1).truncationMode(.middle)
                        Image(systemName: "chevron.up").font(.system(size: 8))
                    }.font(.system(size: 11)).frame(maxWidth: 190)
                }.disabled(running || app.operationBusy).help("Модель этого диалога")
                    .composerPopover(isPresented: $modelMenu, width: 310, trailing: true) {
                        PaneModelChoices(app: app, conversation: conversation, close: { modelMenu = false })
                    }
                Button {
                    if running && (!hasInput || conversation.provider != "codex") { Task { await app.stop(conversationID: conversationID) } }
                    else { send() }
                } label: {
                    Image(systemName: running && (!hasInput || conversation.provider != "codex") ? "stop.fill" : "arrow.up")
                        .font(.system(size: 12, weight: .semibold)).foregroundStyle(NativeTheme.canvas)
                        .frame(width: 29, height: 29).background(Color.primary.opacity(canSend || running ? 1 : 0.3), in: Circle())
                }.disabled(!(running && (!hasInput || conversation.provider != "codex")) && !canSend)
                    .accessibilityLabel(running && (!hasInput || conversation.provider != "codex") ? "Остановить задачу в панели" : "Отправить в панель")
            }.padding(.horizontal, 10).padding(.bottom, 9)
        }.background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(NativeTheme.hairline))
            .frame(maxWidth: NativeTheme.columnWidth).frame(maxWidth: .infinity)
    }

    private func send() {
        guard canSend else { return }
        follow = true
        Task { await app.submit(conversationID: conversationID) }
    }

    private func modelLabel(_ conversation: Conversation) -> String {
        if conversation.provider == "codex" {
            let model = app.codexModels.first { conversation.model.isEmpty ? $0.isDefault : $0.id == conversation.model }
            return model?.displayName ?? (conversation.model.isEmpty ? "ChatGPT" : conversation.model)
        }
        return conversation.model.isEmpty ? (conversation.provider == "mock" ? "Тестовый режим" : "Ollama") : conversation.model
    }

    private func contextOptions(_ conversation: Conversation) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Этот диалог").font(.system(size: 14, weight: .medium))
            Button { contextMenu = false; app.choosePanelWorkspace(conversationID: conversationID) } label: {
                Label(conversation.workspacePath.map { URL(fileURLWithPath: $0).lastPathComponent } ?? "Выбрать папку проекта", systemImage: "folder")
            }
            if conversation.provider == "codex" {
                Button {
                    contextMenu = false
                    if app.hasAgentAccessSelection(conversation) { Task { await app.disableAgentAccess(conversationID: conversationID) } }
                    else { app.requestAgentAccess(conversationID: conversationID) }
                } label: {
                    Label(app.hasAgentAccessSelection(conversation) ? "Выключить доступ к Mac" : "Разрешить доступ к Mac", systemImage: "shield")
                        .foregroundStyle(app.hasAgentAccessSelection(conversation) ? Color.orange : .primary)
                }
                Toggle("Подбирать навыки", isOn: setting(\.autoSkillsEnabled))
                Toggle("Вспоминать заметки проекта", isOn: setting(\.autoProjectRecallEnabled))
            }
            Button("Все настройки диалога") { contextMenu = false; app.select(conversationID); app.showContextDesk = true }
        }.font(.system(size: 12)).padding(18)
    }

    private func setting(_ path: WritableKeyPath<Conversation, Bool>) -> Binding<Bool> {
        Binding(get: { conversation?[keyPath: path] ?? false }, set: { value in
            guard !running, let index = app.conversations.firstIndex(where: { $0.id == conversationID }) else { return }
            app.conversations[index][keyPath: path] = value; app.persist()
        })
    }
}

private struct PaneModelChoices: View {
    @ObservedObject var app: AppModel
    let conversation: Conversation
    let close: () -> Void
    @State private var name = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Модель диалога").font(.system(size: 14, weight: .medium))
            if conversation.provider == "codex" {
                ForEach(app.codexModels) { model in
                    ComposerMenuRow(title: model.displayName, icon: conversation.model == model.id ? "checkmark" : "sparkle") {
                        app.configureConversation(conversation.id, model: model.id); close()
                    }
                }
                if let model = app.codexModels.first(where: { conversation.model.isEmpty ? $0.isDefault : $0.id == conversation.model }) {
                    Picker("Усилие", selection: Binding(get: { conversation.reasoningEffort }, set: { app.configureConversation(conversation.id, effort: $0) })) {
                        Text("Авто").tag("")
                        ForEach(model.efforts) { Text($0.title).tag($0.rawValue) }
                    }.font(.caption).foregroundStyle(.secondary)
                }
            } else {
                TextField("ID модели", text: $name)
                Button("Выбрать модель") { app.configureConversation(conversation.id, model: name); close() }
            }
            ConversationProviderChoices(app: app, connections: app.apiConnections, conversationID: conversation.id, chosen: close)
        }.padding(14).onAppear { name = conversation.model }
    }
}
