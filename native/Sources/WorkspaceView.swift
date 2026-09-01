import AppKit
import SwiftUI

private let hairline = NativeTheme.hairline
private let canvas = NativeTheme.canvas

struct WorkspaceView: View {
    @ObservedObject var model: AppModel
    @Environment(\.openSettings) private var openSettings
    @State private var libraryExpanded = false

    var body: some View {
        NavigationSplitView {
            SidebarView(model: model, libraryExpanded: $libraryExpanded, openSettings: { openSettings() })
                .navigationSplitViewColumnWidth(min: 225, ideal: 260, max: 320)
        } detail: {
            VStack(spacing: 0) {
                if let error = model.error {
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
                HStack(spacing: 0) {
                    Group {
                        switch model.section {
                        case .chat: ChatView(model: model)
                        case .commands: CommandCatalogView(model: model)
                        case .overview: OverviewView(model: model)
                        case .workspace: ProjectWorkspaceView(model: model)
                        case .memory, .goals, .skills: LibraryView(model: model)
                        }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                    if model.showInspector && model.section == .chat {
                        Rectangle().fill(hairline).frame(width: 1)
                        EvidenceInspectorView(model: model).frame(width: 280)
                    }
                }
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
                        Button { model.showInspector.toggle() } label: { Image(systemName: "sidebar.right") }
                            .help("Инспектор памяти и проверок")
                    }
                }
            }
            .toolbarBackground(canvas, for: .windowToolbar)
            .toolbarBackground(.visible, for: .windowToolbar)
        }
        .tint(.primary)
        .font(NativeTheme.interfaceFont)
        .buttonStyle(.nativeHover)
        .disclosureGroupStyle(NativeDisclosureStyle())
        .sheet(item: $model.pendingAction) { action in
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
            }.padding(28).frame(width: 560)
        }
        .sheet(item: $model.pendingAgentAccess) { request in AgentAccessSheet(model: model, request: request) }
        .sheet(isPresented: $model.showWorkSessions) { WorkSessionsView(model: model) }
        .sheet(isPresented: $model.showContextDesk) { ContextDeskView(model: model) }
        .sheet(isPresented: $model.showPersonaInspector) { PersonaInspectorView(model: model) }
        .sheet(isPresented: $model.showMemoryWorkshop) { MemoryWorkshopView(model: model) }
        .sheet(isPresented: $model.showTaskCriteria) { TaskCriteriaView(model: model) }
        .sheet(item: $model.imagePreview) { ImageAttachmentPreviewView(model: model, preview: $0) }
        .sheet(item: $model.pdfPreview) { PDFAttachmentPreviewView(model: model, preview: $0) }
        .sheet(item: $model.attachmentDropPreview) { AttachmentDropPreviewView(model: model, preview: $0) }
    }

    private var sectionTitle: String {
        switch model.section {
        case .chat: return model.selected?.title ?? "Диалог"
        case .commands: return "Команды"
        case .overview: return "Обзор ядра"
        case .workspace: return "Рабочая папка"
        case .memory, .goals, .skills: return model.section.libraryCollection?.title ?? "Библиотека"
        }
    }
}

struct SidebarView: View {
    @ObservedObject var model: AppModel
    @Binding var libraryExpanded: Bool
    let openSettings: () -> Void
    @State private var renaming: Conversation?
    @State private var newTitle = ""
    @State private var searchVisible = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text("Proto-Mind").font(.system(size: 20, weight: .semibold))
                Spacer()
                Button { searchVisible.toggle() } label: { Image(systemName: "magnifyingglass") }
                    .buttonStyle(.nativeHover).foregroundStyle(.secondary).help("Поиск диалогов")
            }.padding(.horizontal, 18).padding(.top, 15).padding(.bottom, 17)
            Button { model.newConversation() } label: {
                HStack { Label("Новый чат", systemImage: "square.and.pencil"); Spacer(); Text("⌘N").font(.system(size: 11)).foregroundStyle(.tertiary) }
                    .font(.system(size: 14)).padding(10)
            }.buttonStyle(.nativeHover).disabled(model.busy).padding(.horizontal, 12)
            // Expanding navigation must grow scroll content, never the split view's minimum height.
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    VStack(spacing: 3) {
                        navigation("Рабочая папка", icon: "folder", section: .workspace)
                        navigation("Команды", icon: "command", section: .commands)
                        DisclosureGroup(isExpanded: $libraryExpanded) {
                            ForEach(LibraryCollection.allCases) { collection in
                                navigation(collection.title, icon: collection.symbol, section: collection.section)
                            }
                            navigation("Обзор ядра", icon: "square.grid.2x2", section: .overview)
                        } label: {
                            Label("Библиотека и ядро", systemImage: "books.vertical").font(.system(size: 14)).padding(.vertical, 9)
                        }
                        .padding(.horizontal, 10)
                    }.padding(.horizontal, 10).padding(.top, 3).padding(.bottom, 24)
                    if searchVisible || !model.conversationSearch.isEmpty {
                        HStack(spacing: 7) {
                            Image(systemName: "magnifyingglass").foregroundStyle(.tertiary)
                            TextField("Найти диалог", text: $model.conversationSearch).textFieldStyle(.plain)
                        }.font(NativeTheme.interfaceFont).padding(9).background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                            .padding(.horizontal, 12).padding(.bottom, 14)
                    }
                    HStack {
                        Text(model.showArchived ? "Архив" : "Проекты и чаты").font(.system(size: 12, weight: .medium))
                        Spacer()
                        Button { model.showArchived.toggle() } label: { Image(systemName: model.showArchived ? "bubble.left.and.bubble.right" : "archivebox") }
                            .buttonStyle(.nativeHover).help(model.showArchived ? "Текущие диалоги" : "Архив диалогов")
                    }
                        .foregroundStyle(.secondary).padding(.horizontal, 21).padding(.bottom, 8)
                    LazyVStack(alignment: .leading, spacing: 3) {
                        ForEach(ConversationGroup.make(model.visibleConversations)) { group in
                            Label(group.title, systemImage: group.workspace == nil ? "bubble.left.and.bubble.right" : "folder")
                                .font(NativeTheme.interfaceFont).foregroundStyle(.secondary).padding(.horizontal, 10).padding(.top, 12).padding(.bottom, 6)
                                .help(group.workspace ?? "Локальные диалоги без привязки к папке")
                            ForEach(group.conversations) { chat in conversationRow(chat) }
                        }
                        if model.visibleConversations.isEmpty {
                            Text(model.showArchived ? "В архиве пока пусто" : "Диалоги не найдены")
                                .font(.caption).foregroundStyle(.secondary).padding(12)
                        }
                    }.padding(.horizontal, 12)
                }
            }.frame(minHeight: 0, maxHeight: .infinity).padding(.bottom, 10)
            Divider().padding(.horizontal, 14)
            Button(action: openSettings) {
                HStack(spacing: 10) {
                    Text("PM").font(.system(size: 10, weight: .semibold)).frame(width: 28, height: 28)
                        .background(Color.primary.opacity(0.08), in: Circle())
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Личное пространство").font(.system(size: 13, weight: .medium))
                        Text("Модели и настройки").font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "gearshape").font(.system(size: 13)).foregroundStyle(.secondary)
                }.padding(17)
            }.buttonStyle(.nativeHover)
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .disclosureGroupStyle(NativeDisclosureStyle())
            .background { SidebarMaterial().ignoresSafeArea() }
            .sheet(item: $renaming) { chat in
                VStack(alignment: .leading, spacing: 18) {
                    Text("Название диалога").font(.title3.weight(.semibold))
                    TextField("Название", text: $newTitle).textFieldStyle(.roundedBorder)
                    HStack {
                        Button("Отмена") { renaming = nil }.keyboardShortcut(.cancelAction)
                        Spacer()
                        Button("Сохранить") { model.renameConversation(chat.id, title: newTitle); renaming = nil }
                            .keyboardShortcut(.defaultAction).disabled(newTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || newTitle.count > 120)
                    }
                }.padding(24).frame(width: 400)
            }
    }

    private func conversationRow(_ chat: Conversation) -> some View {
        Button { model.select(chat.id) } label: {
            HStack(spacing: 7) {
                if chat.archived { Image(systemName: "archivebox").font(.caption).foregroundStyle(.secondary) }
                Text(chat.title).font(NativeTheme.interfaceFont).lineLimit(1)
                Spacer(minLength: 0)
                if !chat.draft.isEmpty { Image(systemName: "pencil").font(.system(size: 10)).foregroundStyle(.tertiary) }
            }.padding(.leading, 29).padding(.trailing, 10).padding(.vertical, 10).frame(maxWidth: .infinity, alignment: .leading)
                .background(model.selectedID == chat.id && model.section == .chat ? NativeTheme.selection : .clear,
                            in: RoundedRectangle(cornerRadius: 9))
        }.buttonStyle(.nativeHover).disabled(model.busy).help(chat.title)
            .contextMenu {
                Button("Переименовать…") { newTitle = chat.title; renaming = chat }
                Button(chat.archived ? "Вернуть из архива" : "В архив") { model.archiveConversation(chat.id, archived: !chat.archived) }
            }
    }

    private func navigation(_ title: String, icon: String, section: WorkspaceSection) -> some View {
        Button {
            if let collection = section.libraryCollection {
                Task { await model.showLibrary(collection) }
            } else {
                model.section = section
                if section == .workspace { Task { await model.refreshWorkspace() } }
            }
        } label: {
            Label(title, systemImage: icon).font(.system(size: 14)).frame(maxWidth: .infinity, alignment: .leading)
                .padding(10).background(model.section == section ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
        }.buttonStyle(.nativeHover).disabled(section.libraryCollection != nil && model.busy)
    }
}

private struct ChatView: View {
    @ObservedObject var model: AppModel
    @State private var nearBottom = true
    @State private var followOutput = true

    var body: some View {
        VStack(spacing: 0) {
            WorkSessionNoticeBanner(model: model)
            GeometryReader { viewport in
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(spacing: 0) {
                            if model.messages.isEmpty { welcome.padding(.top, 90).padding(.bottom, 45) }
                            LazyVStack(alignment: .leading, spacing: 34) {
                                ForEach(model.messages) { message in
                                    MessageView(message: message, model: model).id(message.id)
                                }
                                if model.busy {
                                    VStack(alignment: .leading, spacing: 20) {
                                        WorkTimelineView(log: model.workLog, agentReceipt: model.agentReceipt,
                                                         toolItems: model.agentItems, live: true, startedAt: model.turnStartedAt)
                                        if !model.stream.isEmpty { MessageMarkdownView(text: model.stream, copy: model.copy) }
                                    }.frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }.padding(.horizontal, 32).padding(.vertical, 30)
                                .frame(maxWidth: NativeTheme.columnWidth + 64).frame(maxWidth: .infinity)
                            Color.clear.frame(height: 1).id("bottom")
                                .background(GeometryReader { anchor in
                                    Color.clear.preference(key: ChatBottomKey.self, value: anchor.frame(in: .named("chat-scroll")).maxY)
                                })
                        }
                    }.coordinateSpace(name: "chat-scroll")
                        .modifier(ChatScrollIntent(followOutput: $followOutput))
                        .onPreferenceChange(ChatBottomKey.self) { value in
                            nearBottom = value <= viewport.size.height + 85
                            if #unavailable(macOS 15) { followOutput = nearBottom }
                        }
                        .onAppear { scrollToLatest(proxy) }
                        .onChange(of: model.selectedID) { _, _ in followOutput = true; scrollToLatest(proxy) }
                        .onChange(of: model.turnStartedAt) { _, value in
                            if value != nil { followOutput = true; scrollToLatest(proxy) }
                        }
                        .onChange(of: model.messages.count) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .onChange(of: model.stream.count) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .onChange(of: model.workLog) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .onChange(of: model.busy) { _, _ in if followOutput { scrollToLatest(proxy) } }
                        .overlay(alignment: .bottom) {
                            if !nearBottom {
                                Button { followOutput = true; scrollToLatest(proxy) } label: {
                                    Image(systemName: "arrow.down").font(.system(size: 15)).frame(width: 34, height: 34)
                                        .background(NativeTheme.composer, in: Circle()).overlay(Circle().stroke(hairline))
                                }.buttonStyle(.nativeHover).help("К последнему сообщению").padding(.bottom, 8)
                            }
                        }
                }
            }
            ComposerView(model: model).padding(.horizontal, 28).padding(.top, 7).padding(.bottom, 12).background(canvas)
        }.modifier(AttachmentDropTarget(model: model))
    }

    private func scrollToLatest(_ proxy: ScrollViewProxy) {
        // Wait for the new message/live timeline to participate in layout.
        Task { @MainActor in
            await Task.yield()
            if followOutput { proxy.scrollTo("bottom", anchor: .bottom) }
        }
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 19) {
            Text("С чего начнём?").font(.system(size: 30, weight: .medium))
            Text("Продолжим работу, разберём идею\nили вспомним важное.")
                .font(.system(size: 15)).foregroundStyle(.secondary).lineSpacing(4)
            VStack(alignment: .leading, spacing: 9) {
                welcomeAction("Проверить состояние Proto-Mind", icon: "waveform.path.ecg", command: "/proto status")
                Button { Task { await model.showLibrary(.memory) } } label: {
                    Label("Посмотреть память", systemImage: "brain").font(.system(size: 12)).padding(.vertical, 6)
                }.buttonStyle(.nativeHover).disabled(model.busy)
                Button { model.section = .commands } label: { Label("Открыть каталог возможностей", systemImage: "command").font(.system(size: 12)).padding(.vertical, 6) }
                    .buttonStyle(.nativeHover)
            }.padding(.top, 8)
            Text("По умолчанию локальная Ollama. Облачная обработка включается только вами.")
                .font(.system(size: 11)).foregroundStyle(.tertiary).padding(.top, 8)
        }.frame(maxWidth: 570, alignment: .leading).padding(.horizontal, 36).frame(maxWidth: .infinity)
    }

    private func welcomeAction(_ text: String, icon: String, command: String) -> some View {
        Button { Task { await model.submit(command) } } label: { Label(text, systemImage: icon).font(.system(size: 12)).padding(.vertical, 6) }
            .buttonStyle(.nativeHover).disabled(model.busy)
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
                if new == .interacting || new == .tracking { followOutput = false }
                if new == .idle && [.interacting, .tracking, .decelerating].contains(old) {
                    followOutput = context.geometry.visibleRect.maxY >= context.geometry.contentSize.height - 85
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
                    Text(message.text).font(NativeTheme.interfaceFont).lineSpacing(5).textSelection(.enabled)
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
                    MessageMarkdownView(text: message.text, copy: model.copy).frame(maxWidth: .infinity, alignment: .leading)
                }
                attachments
                ForEach(Array(message.notices.enumerated()), id: \.offset) { _, notice in
                    Label(notice, systemImage: "info.circle").font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
                HStack(spacing: 17) {
                    Button { model.copy(message.text) } label: { Image(systemName: "doc.on.doc") }
                        .help("Копировать ответ").accessibilityLabel("Копировать ответ")
                    if !message.evidence.isNull {
                        Button { model.showMessage(message) } label: { Image(systemName: "sidebar.right") }
                            .help("Память и проверки ответа").accessibilityLabel("Память и проверки ответа")
                        Button { showRaw.toggle() } label: { Image(systemName: "text.alignleft") }
                            .help("Исходный отчёт ядра").accessibilityLabel("Исходный отчёт ядра")
                    }
                }.buttonStyle(.nativeHover).font(.system(size: 13)).foregroundStyle(.tertiary).padding(.top, 2)
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
                    Task { await model.previewImage(image["path"].text, expectedSHA: image["sha256"].text, canAttach: false) }
                } label: {
                    Label("\(image["name"].text) · \(image["width"].integer) × \(image["height"].integer)", systemImage: "photo")
                        .font(.caption).foregroundStyle(.secondary)
                }.buttonStyle(.nativeHover).disabled(model.busy || model.loadingImagePreview)
                    .help("Локальный просмотр исходного файла с проверкой SHA-256. Изображение не отправляется повторно.")
            }
            ForEach(Array((message.pdfContext ?? []).enumerated()), id: \.offset) { _, pdf in
                Button { Task { await model.previewPDF(pdf["path"].text, expected: pdf, canAttach: false) } } label: {
                    Label("\(pdf["name"].text) · стр. \(pdf["pages"].items.map { String($0["number"].integer) }.joined(separator: ", "))", systemImage: "doc.richtext")
                        .font(.caption).foregroundStyle(.secondary)
                }.buttonStyle(.nativeHover).disabled(!model.canReceiveAttachments)
                    .help("Локально прочитать выбранные страницы с проверкой SHA-256; без повторной отправки")
            }
        }
    }
}

struct ComposerView: View {
    @ObservedObject var model: AppModel
    @Environment(\.openSettings) private var openSettings

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if model.selected?.archived == true {
                HStack {
                    Label("Диалог в архиве, сообщения сохранены", systemImage: "archivebox").font(.caption)
                    Spacer()
                    Button("Вернуть") { if let id = model.selectedID { model.archiveConversation(id, archived: false) } }
                }.foregroundStyle(.secondary)
            }
            if model.selected?.provider == "codex" && !model.cloudConsent {
                Button { openSettings() } label: {
                    Label("Разрешите облачную обработку в настройках перед отправкой", systemImage: "lock.shield")
                        .font(.system(size: 11)).foregroundStyle(.orange)
                }.buttonStyle(.nativeHover)
            }
            if model.selected?.provider == "codex", let note = model.modelSelectionWarning ?? model.modelSelectionNotice {
                Text(note).font(.system(size: 12)).foregroundStyle(.orange).padding(.horizontal, 4)
            }
            if model.selected?.draftContinuation != nil {
                HStack(spacing: 8) {
                    Label("Ручное продолжение · новый запрос, не автоповтор", systemImage: "clock.arrow.circlepath")
                    Spacer()
                    Button("Отвязать") { model.clearContinuation() }.disabled(model.busy)
                        .help("Оставить текст как самостоятельный новый запрос без связи с прошлым запуском")
                }.font(.caption).foregroundStyle(.secondary).padding(.horizontal, 6)
            }
            VStack(spacing: 0) {
                if model.selected?.pendingImages.isEmpty == false { PendingImageAttachmentsView(model: model) }
                if model.selected?.pendingPDFs.isEmpty == false { PendingPDFAttachmentsView(model: model) }
                if let files = model.selected?.pendingFiles, !files.isEmpty {
                    ScrollView(.horizontal) {
                        HStack(spacing: 6) {
                            ForEach(Array(files.enumerated()), id: \.offset) { _, file in
                                HStack(spacing: 6) {
                                    Image(systemName: "doc.text")
                                    Text(file["path"].text).lineLimit(1)
                                    Button { model.removePendingFile(file["path"].text) } label: { Image(systemName: "xmark") }
                                        .buttonStyle(.nativeHover).disabled(model.busy).help("Убрать вложение")
                                }.font(.system(size: 10)).padding(7).background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 7))
                                    .help("Только для следующего обычного сообщения, до 6 000 символов из файла. Команды не получают вложения.")
                            }
                        }
                    }.frame(height: 46).scrollIndicators(.hidden).padding(.horizontal, 12).padding(.top, 10)
                }
                ZStack(alignment: .topLeading) {
                    if model.composer.isEmpty {
                        Text("Поручите задачу или задайте вопрос").font(NativeTheme.interfaceFont).foregroundStyle(.tertiary).padding(.horizontal, 15).padding(.top, 14)
                    }
                    NativeComposer(text: $model.composer, revision: model.composerRevision, enabled: !model.busy && model.selected?.archived != true,
                                   canDrop: model.canReceiveAttachments, onDrop: { model.receiveAttachmentDrop($0) },
                                   onDropHover: { model.attachmentDropTargeted = $0 }, onDropError: { model.error = $0 }) { Task { await model.submit() } }
                        .frame(height: min(160, max(58, CGFloat(model.composer.components(separatedBy: "\n").count) * 23 + 26)))
                }
                HStack(spacing: 13) {
                    Menu {
                        Button("Изображение или скриншот…", systemImage: "photo", action: model.chooseImage)
                        Button("PDF · выбрать страницы…", systemImage: "doc.richtext", action: model.choosePDF)
                        Button("Файл рабочей папки…", systemImage: "doc.text") {
                            model.section = .workspace
                            Task { await model.refreshWorkspace() }
                        }
                    } label: { Image(systemName: "plus").font(.system(size: 19, weight: .light)) }
                        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().frame(width: 28, height: 32)
                        .nativeHoverSurface().help("Добавить вложение с локальным предпросмотром").accessibilityLabel("Добавить вложение")
                        .disabled(!model.canReceiveAttachments)
                    if model.selected?.provider == "codex" {
                        Menu {
                            if model.fullAccessEnabled {
                                Text(model.computerUseAvailable ? "Файлы, терминал, Web Search, сеть и экран доступны" : "Файлы, терминал, Web Search и сеть доступны")
                                Button("Вернуться в чат без инструментов") { Task { await model.disableAgentAccess() } }
                            } else {
                                Button("Включить инструменты…") { model.requestAgentAccess() }
                            }
                        } label: {
                            Label(model.fullAccessEnabled ? model.fullAccessLabel : "Чат без инструментов", systemImage: model.fullAccessEnabled ? "exclamationmark.shield" : "lock.shield")
                                .font(.system(size: 12)).foregroundStyle(model.fullAccessEnabled ? Color.orange : .secondary)
                        }.menuStyle(.borderlessButton).fixedSize().nativeHoverSurface().disabled(model.busy || model.selected?.archived == true)
                            .help(model.fullAccessEnabled ? (model.computerUseAvailable ? "Полный доступ к Mac, Web Search, сеть и Computer Use. Stop/Esc не откатывают изменения." : "Полный доступ к Mac, Web Search и сеть. Computer Use недоступен.") : "Файловые, сетевые, Web Search и экранные инструменты выключены")
                    }
                    Spacer(minLength: 8)
                    Button { model.showTaskCriteria = true } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "checklist")
                            if let count = model.selected?.pendingCriteria.count, count > 0 { Text("\(count)") }
                        }.font(.system(size: 12)).frame(minWidth: 24, minHeight: 28)
                    }.disabled(model.busy || model.selected?.archived == true)
                        .help("Критерии готовности следующей задачи").accessibilityLabel("Критерии задачи")
                    Button { model.showContextDesk = true } label: {
                        Label("Контекст", systemImage: "doc.text.magnifyingglass").font(.system(size: 12))
                    }.disabled(model.busy).help("Локально проверить состав запроса до отправки")
                        .accessibilityLabel("Контекст перед отправкой")
                    ModelSelectionMenu(model: model, openSettings: { openSettings() })
                    if model.busy {
                        Button { Task { await model.stop() } } label: {
                            Image(systemName: "stop.fill").font(.system(size: 12)).foregroundStyle(canvas).frame(width: 32, height: 32).background(Color.primary, in: Circle())
                        }.buttonStyle(.nativeHover).help("Запросить остановку Codex; локальная запись не прерывается")
                    } else {
                        Button { Task { await model.submit() } } label: {
                            Image(systemName: "arrow.up").font(.system(size: 16, weight: .medium)).foregroundStyle(canvas)
                                .frame(width: 32, height: 32).background(Color.primary.opacity(model.composer.isEmpty ? 0.25 : 1), in: Circle())
                        }.buttonStyle(.nativeHover).disabled(model.composer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.selected?.archived == true || model.loadingDroppedAttachments || model.loadingImagePreview || model.loadingPDFPreview)
                            .help("Отправить · Return")
                    }
                }.padding(.horizontal, 15).padding(.top, 5).padding(.bottom, 13)
            }
            .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 22))
            .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.primary.opacity(0.08)))
            HStack {
                Circle().fill(model.client.connected ? Color.green.opacity(0.75) : Color.orange).frame(width: 5, height: 5)
                Text(model.status).lineLimit(1)
                if let path = model.selected?.workspacePath {
                    Text("· \(URL(fileURLWithPath: path).lastPathComponent)").lineLimit(1).help(path)
                }
                Spacer()
                Text("Return: отправить · Shift Return: новая строка")
            }.font(.system(size: 9)).foregroundStyle(.secondary).padding(.horizontal, 4)
        }.frame(maxWidth: NativeTheme.columnWidth).frame(maxWidth: .infinity)
    }

}

struct NativeComposer: NSViewRepresentable {
    @Binding var text: String
    var revision: Int
    var enabled: Bool
    var canDrop = false
    var onDrop: ([URL]) -> Bool = { _ in false }
    var onDropHover: (Bool) -> Void = { _ in }
    var onDropError: (String) -> Void = { _ in }
    var onSend: () -> Void

    final class Editor: NSTextView {
        var onSend: (() -> Void)?
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
            if [36, 76].contains(event.keyCode) && !event.modifierFlags.contains(.shift) && !hasMarkedText() {
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
        editor.font = .systemFont(ofSize: NativeTheme.interfaceSize)
        editor.textColor = .labelColor
        editor.insertionPointColor = .labelColor
        editor.isVerticallyResizable = true
        editor.isHorizontallyResizable = false
        editor.autoresizingMask = [.width]
        editor.textContainer?.widthTracksTextView = true
        editor.textContainerInset = NSSize(width: 10, height: 14)
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
        // SwiftUI may render an older binding while NSTextView is handling rapid keystrokes.
        // Only an explicit programmatic revision may replace the editor's live text.
        if context.coordinator.appliedRevision != revision {
            editor.string = text
            editor.setSelectedRange(NSRange(location: (text as NSString).length, length: 0))
            context.coordinator.appliedRevision = revision
        }
        editor.isEditable = enabled
        editor.onSend = onSend
        editor.canDrop = canDrop
        editor.onFiles = onDrop
        editor.onDropHover = onDropHover
        editor.onDropError = onDropError
    }
}
