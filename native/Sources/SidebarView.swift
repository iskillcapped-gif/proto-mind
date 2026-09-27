import Combine
import SwiftUI

struct SidebarView: View {
    @ObservedObject var model: AppModel
    @ObservedObject private var routing: ConversationRouting
    private var selectedConversationID: UUID? {
        if let panel = routing.destination {
            if case .conversation(let id) = panel.selected?.content { return id }
            return nil
        }
        return model.selectedID
    }
    private var presentations: WorkspacePresentations { model.presentations }
    @State private var presentationLocked = false
    @Binding var libraryExpanded: Bool
    let openSettings: () -> Void
    @Environment(\.desktopGlass) private var desktopGlass
    @State private var renaming: Conversation?
    @State private var newTitle = ""
    @State private var toolsOpen = false
    @FocusState private var searchFocused: Bool
    @State private var searchVisible = false
    @StateObject private var projectDrag = SidebarProjectDragSession()
    @StateObject private var hoverCards = SidebarHoverCards()
    /// Sidebar rows: 13 pt text, about 28 pt tall.
    static let rowFont = Font.system(size: 13)
    static let rowPadding = EdgeInsets(top: 6, leading: 10, bottom: 6, trailing: 10)

    init(model: AppModel, libraryExpanded: Binding<Bool>, openSettings: @escaping () -> Void) {
        self.model = model
        self.routing = model.conversationRouting
        self._libraryExpanded = libraryExpanded
        self.openSettings = openSettings
    }

    var body: some View {
        GeometryReader { geometry in
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 6) {
                    Text("Proto-Mind").font(.system(size: 19, weight: .semibold))
                    Spacer()
                    AppUpdateButton(app: model, monitor: model.appUpdate)
                    Button { searchVisible.toggle(); searchFocused = searchVisible } label: { Image(systemName: "magnifyingglass") }
                        .foregroundStyle(.secondary).help(L10n.text("Поиск диалогов · ⌘F")).accessibilityLabel(L10n.text("Поиск диалогов"))
                }.padding(.leading, 19).padding(.trailing, 14).padding(.top, 15).padding(.bottom, 10)
                    .background {
                        Button("") { searchVisible = true; searchFocused = true }.keyboardShortcut("f").hidden().accessibilityHidden(true)
                    }
                Button { model.newSidebarConversation() } label: {
                    HStack {
                        Label(L10n.text("Новый чат"), systemImage: "square.and.pencil")
                        Spacer()
                        Text("⌘N").font(.system(size: 11)).foregroundStyle(.secondary)
                    }.font(Self.rowFont).padding(Self.rowPadding)
                }.buttonStyle(.nativeHover).disabled(presentationLocked || !model.canNavigateConversations).padding(.horizontal, 12)
                if searchVisible || !model.conversationSearch.isEmpty { HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField(L10n.text("Поиск диалогов"), text: $model.conversationSearch).textFieldStyle(.plain).focused($searchFocused)
                    if !model.conversationSearch.isEmpty {
                        Button { model.conversationSearch = "" } label: { Image(systemName: "xmark.circle.fill") }
                            .buttonStyle(.plain).foregroundStyle(.secondary).accessibilityLabel(L10n.text("Очистить поиск"))
                    }
                }.font(.system(size: 12)).padding(10).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 9))
                    .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 8)
                }
                // Keep navigation inside the scroll area so a small window never
                // pushes the settings entry or the conversation list off screen.
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        Button { model.openConversationHistory() } label: {
                            Label(L10n.text("История диалогов"), systemImage: "clock.arrow.circlepath").font(Self.rowFont)
                                .frame(maxWidth: .infinity, alignment: .leading).padding(Self.rowPadding)
                        }.buttonStyle(.nativeHover).help(L10n.text("Найти прошлую работу и продолжить"))
                        navigation(L10n.text("Файлы проекта"), icon: "folder", section: .workspace)
                        Button { navigate { model.workspacePanel.showBrowser() } } label: {
                            Label(L10n.text("Браузер"), systemImage: "globe").font(Self.rowFont)
                                .frame(maxWidth: .infinity, alignment: .leading).padding(Self.rowPadding)
                        }.buttonStyle(.nativeHover)
                        navigation("GitHub", icon: "point.3.connected.trianglepath.dotted", section: .github)
                        DisclosureGroup(isExpanded: $libraryExpanded) {
                            Button { Task { await model.openProjectMemory() } } label: {
                                Label(L10n.text("Память проекта"), systemImage: "brain.head.profile").font(Self.rowFont)
                                    .frame(maxWidth: .infinity, alignment: .leading).padding(Self.rowPadding)
                            }.buttonStyle(.nativeHover).disabled(model.busy || model.selected?.workspacePath == nil)
                                .help(model.selected?.workspacePath == nil ? L10n.text("Сначала выберите папку проекта") : L10n.text("Текущие заметки и история этой папки"))
                            ForEach(LibraryCollection.allCases) { collection in
                                navigation(collection == .memory ? L10n.text("Общая память") : collection.title, icon: collection.symbol, section: collection.section)
                            }
                        } label: {
                            Label(L10n.text("Библиотека"), systemImage: "books.vertical").font(Self.rowFont).padding(.vertical, 6)
                        }.padding(.horizontal, 10)
                        HStack {
                            Text(model.showArchived ? L10n.text("Архив диалогов") : L10n.text("Диалоги")).font(.system(size: 11, weight: .semibold))
                            Spacer()
                            Button { model.showArchived.toggle() } label: {
                                Image(systemName: model.showArchived ? "tray.full" : "archivebox")
                            }.help(model.showArchived ? L10n.text("Вернуться к диалогам") : L10n.text("Открыть архив"))
                                .accessibilityLabel(model.showArchived ? L10n.text("Вернуться к диалогам") : L10n.text("Архив диалогов"))
                        }.foregroundStyle(.secondary).padding(.horizontal, 11).padding(.top, 14).padding(.bottom, 2)
                        LazyVStack(alignment: .leading, spacing: 1) {
                            SidebarProjectsView(app: model, order: model.sidebarProjectOrder, drag: projectDrag, row: conversationRow)
                            if model.visibleConversations.isEmpty {
                                Text(model.conversationSearch.isEmpty ? L10n.text("Здесь появятся ваши диалоги") : L10n.text("Ничего не найдено"))
                                    .font(.system(size: 12)).foregroundStyle(.secondary).padding(12)
                            }
                        }
                    }.padding(.horizontal, 12)
                }.frame(minHeight: 0, maxHeight: .infinity).padding(.bottom, 10)
                Divider().padding(.horizontal, 17)
                HStack(spacing: 4) {
                    SidebarMenuView(app: model, usage: model.codexUsage, client: model.serviceClient, openSettings: openSettings, columnWidth: max(1, geometry.size.width - 24))
                    LiveVoiceButton(app: model, voice: model.liveVoice)
                    Button { toolsOpen.toggle() } label: {
                        Image(systemName: "ellipsis").frame(width: 28, height: 32)
                    }.buttonStyle(.nativeHover).help(L10n.text("Команды, диагностика и копии")).accessibilityLabel(L10n.text("Инструменты"))
                        .composerPopover(isPresented: $toolsOpen, width: min(245, max(1, geometry.size.width - 24)), trailing: true) {
                            VStack(spacing: 2) {
                                ComposerMenuRow(title: L10n.text("Команды"), icon: "command") { toolsOpen = false; navigate { model.section = .commands } }
                                ComposerMenuRow(title: L10n.text("Диагностика"), icon: "waveform.path.ecg") { toolsOpen = false; navigate { model.section = .overview } }
                                Divider().padding(.vertical, 4)
                                ComposerMenuRow(title: L10n.text("Копии и восстановление"), icon: "clock.arrow.circlepath") {
                                    toolsOpen = false
                                    Task { @MainActor in await Task.yield(); model.openHistoryBackups() }
                                }.disabled(model.globalBusy || model.client.turnOutstanding)
                            }.padding(6)
                        }
                }.padding(.horizontal, 12).padding(.vertical, 9)
            }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                .disclosureGroupStyle(NativeDisclosureStyle())
                .background { if !desktopGlass { SidebarMaterial().ignoresSafeArea() } }
                .workspaceSheet(item: $renaming) { chat in
                    VStack(alignment: .leading, spacing: 18) {
                        Text(L10n.text("Название диалога")).font(.title3.weight(.semibold))
                        TextField(L10n.text("Название"), text: $newTitle).textFieldStyle(.roundedBorder)
                        HStack {
                            Button(L10n.text("Отмена")) { renaming = nil }.keyboardShortcut(.cancelAction)
                            Spacer()
                            Button(L10n.text("Сохранить")) { model.renameConversation(chat.id, title: newTitle); renaming = nil }
                                .keyboardShortcut(.defaultAction).disabled(newTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || newTitle.count > 120)
                        }
                    }.padding(24).workspacePageSize(width: 400)
                }
        }
        .onReceive(model.presentations.$pages.map { $0.contains { $0.dismissalDisabled } }.removeDuplicates()) {
            presentationLocked = $0
        }
        .onDisappear { projectDrag.finish() }
        .modifier(SidebarProjectDragCompletion(drag: projectDrag))
    }

    private func conversationRow(_ chat: Conversation) -> some View {
        let isWorking = model.isRunning(chat.id)
        let selected = selectedConversationID == chat.id && model.section == .chat
        return SidebarRowHover { hovered in
            Button {
                let query = model.conversationSearch.trimmingCharacters(in: .whitespacesAndNewlines)
                let match = query.isEmpty ? nil : chat.messages.last { $0.searchableText.localizedCaseInsensitiveContains(query) }
                model.openSidebarConversation(chat.id, messageID: match?.id ?? model.responseAttention.entry(for: chat)?.messageID)
            } label: {
                HStack(spacing: 8) {
                    if chat.archived { Image(systemName: "archivebox").font(.system(size: 11)).foregroundStyle(.secondary) }
                    // Unselected titles are a little softer, so the list reads lighter on glass.
                    SidebarMarqueeText(text: chat.displayTitle, active: hovered).font(Self.rowFont)
                        .foregroundStyle(selected ? Color.primary : Color.primary.opacity(0.84))
                    if let entry = model.responseAttention.entry(for: chat) { ResponseAttentionMark(entry: entry) }
                    if isWorking {
                        WorkingIndicator()
                    } else if !chat.draft.isEmpty {
                        Image(systemName: "pencil").font(.system(size: 10)).foregroundStyle(.secondary)
                    }
                }.padding(.leading, 28).padding(.trailing, 10).padding(.vertical, 6).frame(maxWidth: .infinity, alignment: .leading)
                    .background(selected ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
            }.buttonStyle(.nativeHover).disabled(presentationLocked || !model.canNavigateConversations)
        }
            // The whole title, model and status appear in a card right of the row, not in a system tooltip.
            .background(SidebarHoverCardAnchor(cards: hoverCards) { AnyView(hoverCard(chat)) })
            .accessibilityLabel(chat.displayTitle + (isWorking ? L10n.text(" · Выполняется задача") : "")
                                + (model.responseAttention.entry(for: chat).map { " · " + $0.label } ?? ""))
            .contextMenu {
                Button(L10n.text("Переименовать…")) { newTitle = chat.title; renaming = chat }
                Button(chat.archived ? L10n.text("Вернуть из архива") : L10n.text("В архив")) { model.archiveConversation(chat.id, archived: !chat.archived) }
                    .disabled(model.isRunning(chat.id) || model.operationBusy)
            }
    }

    private func hoverCard(_ chat: Conversation) -> SidebarHoverCardView {
        let context = ConversationComposerContext(app: model, id: chat.id)
        let modelName = chat.provider == "codex" ? context.modelLabel : context.localLabel
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = L10n.locale; formatter.unitsStyle = .short
        var status: (icon: String, text: String)?
        if model.isRunning(chat.id) { status = ("circle.dotted", L10n.text("Выполняется задача")) }
        else if let entry = model.responseAttention.entry(for: chat) { status = ("circle.fill", entry.label) }
        else if !chat.draft.isEmpty { status = ("pencil", L10n.text("Есть черновик")) }
        return SidebarHoverCardView(title: chat.displayTitle, detail: "\(modelName) · \(formatter.localizedString(for: chat.updatedAt, relativeTo: Date()))",
                                    status: status)
    }

    private func navigate(_ action: () -> Void) {
        guard presentations.dismissAll() else { return }
        action()
    }

    private func navigation(_ title: String, icon: String, section: WorkspaceSection) -> some View {
        Button {
            guard presentations.dismissAll() else { return }
            if let collection = section.libraryCollection { Task { await model.showLibrary(collection) } }
            else if section == .workspace { model.showProjectFiles() }
            else {
                model.section = section
                if section == .workspace { Task { await model.refreshWorkspace() } }
            }
        } label: {
            Label(title, systemImage: icon).font(Self.rowFont).frame(maxWidth: .infinity, alignment: .leading)
                .padding(Self.rowPadding).background(model.section == section ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
        }.buttonStyle(.nativeHover).disabled(presentationLocked || (section.libraryCollection != nil && model.busy))
    }
}
