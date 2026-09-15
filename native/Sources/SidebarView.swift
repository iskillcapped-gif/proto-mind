import Combine
import SwiftUI

struct SidebarView: View {
    @ObservedObject var model: AppModel
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

    init(model: AppModel, libraryExpanded: Binding<Bool>, openSettings: @escaping () -> Void) {
        self.model = model
        self._libraryExpanded = libraryExpanded
        self.openSettings = openSettings
    }

    var body: some View {
        GeometryReader { geometry in
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 9) {
                    Text("Proto-Mind").font(.system(size: 20, weight: .semibold))
                    Spacer()
                    Button { searchVisible.toggle(); searchFocused = searchVisible } label: { Image(systemName: "magnifyingglass") }
                        .foregroundStyle(.secondary).help("Поиск диалогов · ⌘F").accessibilityLabel("Поиск диалогов")
                }.padding(.horizontal, 19).padding(.top, 19).padding(.bottom, 20)
                    .background {
                        Button("") { searchVisible = true; searchFocused = true }.keyboardShortcut("f").hidden().accessibilityHidden(true)
                    }
                Button { model.newConversation() } label: {
                    HStack {
                        Label("Новый диалог", systemImage: "square.and.pencil")
                        Spacer()
                        Text("⌘N").font(.system(size: 11)).foregroundStyle(.secondary)
                    }.font(.system(size: 14)).padding(.horizontal, 12).padding(.vertical, 10)
                }.buttonStyle(.nativeHover).disabled(presentationLocked || !model.canNavigateConversations).padding(.horizontal, 12)
                if searchVisible || !model.conversationSearch.isEmpty { HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Поиск диалогов", text: $model.conversationSearch).textFieldStyle(.plain).focused($searchFocused)
                    if !model.conversationSearch.isEmpty {
                        Button { model.conversationSearch = "" } label: { Image(systemName: "xmark.circle.fill") }
                            .buttonStyle(.plain).foregroundStyle(.secondary).accessibilityLabel("Очистить поиск")
                    }
                }.font(.system(size: 12)).padding(10).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 9))
                    .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 8)
                }
                // Keep navigation inside the scroll area so a small window never
                // pushes the settings entry or the conversation list off screen.
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        Button { model.openConversationHistory() } label: {
                            Label("История диалогов", systemImage: "clock.arrow.circlepath").font(.system(size: 14))
                                .frame(maxWidth: .infinity, alignment: .leading).padding(10)
                        }.buttonStyle(.nativeHover).help("Найти прошлую работу и продолжить")
                        navigation("Файлы проекта", icon: "folder", section: .workspace)
                        Button { navigate { model.workspacePanel.showBrowser() } } label: {
                            Label("Браузер", systemImage: "globe").font(.system(size: 14))
                                .frame(maxWidth: .infinity, alignment: .leading).padding(10)
                        }.buttonStyle(.nativeHover)
                        navigation("GitHub", icon: "point.3.connected.trianglepath.dotted", section: .github)
                        DisclosureGroup(isExpanded: $libraryExpanded) {
                            Button { Task { await model.openProjectMemory() } } label: {
                                Label("Память проекта", systemImage: "brain.head.profile").font(.system(size: 14))
                                    .frame(maxWidth: .infinity, alignment: .leading).padding(10)
                            }.buttonStyle(.nativeHover).disabled(model.busy || model.selected?.workspacePath == nil)
                                .help(model.selected?.workspacePath == nil ? "Сначала выберите папку проекта" : "Текущие заметки и история этой папки")
                            ForEach(LibraryCollection.allCases) { collection in
                                navigation(collection == .memory ? "Общая память" : collection.title, icon: collection.symbol, section: collection.section)
                            }
                        } label: {
                            Label("Библиотека", systemImage: "books.vertical").font(.system(size: 14)).padding(.vertical, 8)
                        }.padding(.horizontal, 10)
                        HStack {
                            Text(model.showArchived ? "Архив диалогов" : "Диалоги").font(.system(size: 11, weight: .semibold))
                            Spacer()
                            Button { model.showArchived.toggle() } label: {
                                Image(systemName: model.showArchived ? "tray.full" : "archivebox")
                            }.help(model.showArchived ? "Вернуться к диалогам" : "Открыть архив")
                                .accessibilityLabel(model.showArchived ? "Вернуться к диалогам" : "Архив диалогов")
                        }.foregroundStyle(.secondary).padding(.horizontal, 11).padding(.top, 24).padding(.bottom, 4)
                        LazyVStack(alignment: .leading, spacing: 3) {
                            ForEach(ConversationGroup.make(model.visibleConversations)) { group in
                                Label(group.title, systemImage: "folder").font(.system(size: 13)).foregroundStyle(.secondary)
                                    .padding(.horizontal, 11).padding(.top, 14).padding(.bottom, 5)
                                    .help(group.workspace ?? "Диалоги без папки проекта")
                                ForEach(group.conversations) { conversationRow($0) }
                            }
                            if model.visibleConversations.isEmpty {
                                Text(model.conversationSearch.isEmpty ? "Здесь появятся ваши диалоги" : "Ничего не найдено")
                                    .font(.system(size: 12)).foregroundStyle(.secondary).padding(12)
                            }
                        }
                    }.padding(.horizontal, 12)
                }.frame(minHeight: 0, maxHeight: .infinity).padding(.bottom, 10)
                Divider().padding(.horizontal, 17)
                HStack(spacing: 4) {
                    SidebarMenuView(app: model, usage: model.codexUsage, client: model.serviceClient, openSettings: openSettings, columnWidth: max(1, geometry.size.width - 24))
                    Button { toolsOpen.toggle() } label: {
                        Image(systemName: "ellipsis").frame(width: 28, height: 32)
                    }.buttonStyle(.nativeHover).help("Команды, диагностика и копии").accessibilityLabel("Инструменты")
                        .composerPopover(isPresented: $toolsOpen, width: min(245, max(1, geometry.size.width - 24)), trailing: true) {
                            VStack(spacing: 2) {
                                ComposerMenuRow(title: "Команды", icon: "command") { toolsOpen = false; navigate { model.section = .commands } }
                                ComposerMenuRow(title: "Диагностика", icon: "waveform.path.ecg") { toolsOpen = false; navigate { model.section = .overview } }
                                Divider().padding(.vertical, 4)
                                ComposerMenuRow(title: "Копии и восстановление", icon: "clock.arrow.circlepath") {
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
                        Text("Название диалога").font(.title3.weight(.semibold))
                        TextField("Название", text: $newTitle).textFieldStyle(.roundedBorder)
                        HStack {
                            Button("Отмена") { renaming = nil }.keyboardShortcut(.cancelAction)
                            Spacer()
                            Button("Сохранить") { model.renameConversation(chat.id, title: newTitle); renaming = nil }
                                .keyboardShortcut(.defaultAction).disabled(newTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || newTitle.count > 120)
                        }
                    }.padding(24).workspacePageSize(width: 400)
                }
        }
        .onReceive(model.presentations.$pages.map { $0.contains { $0.dismissalDisabled } }.removeDuplicates()) {
            presentationLocked = $0
        }
    }

    private func conversationRow(_ chat: Conversation) -> some View {
        let isWorking = model.isRunning(chat.id)
        return Button {
            let query = model.conversationSearch.trimmingCharacters(in: .whitespacesAndNewlines)
            let match = query.isEmpty ? nil : chat.messages.last { $0.searchableText.localizedCaseInsensitiveContains(query) }
            model.returnToConversation(chat.id, messageID: match?.id)
        } label: {
            HStack(spacing: 8) {
                if chat.archived { Image(systemName: "archivebox").font(.system(size: 12)).foregroundStyle(.secondary) }
                Text(chat.title).font(.system(size: 14)).lineLimit(1)
                Spacer(minLength: 0)
                if isWorking {
                    WorkingIndicator()
                } else if !chat.draft.isEmpty {
                    Image(systemName: "pencil").font(.system(size: 10)).foregroundStyle(.secondary).help("Есть черновик")
                }
            }.padding(.leading, 30).padding(.trailing, 10).padding(.vertical, 9).frame(maxWidth: .infinity, alignment: .leading)
                .background(model.selectedID == chat.id && model.section == .chat ? NativeTheme.selection : .clear,
                            in: RoundedRectangle(cornerRadius: 9))
        }.buttonStyle(.nativeHover).disabled(presentationLocked || !model.canNavigateConversations).help(chat.title)
            .accessibilityLabel(chat.title + (isWorking ? " · Выполняется задача" : ""))
            .contextMenu {
                Button("Переименовать…") { newTitle = chat.title; renaming = chat }
                Button(chat.archived ? "Вернуть из архива" : "В архив") { model.archiveConversation(chat.id, archived: !chat.archived) }
                    .disabled(model.isRunning(chat.id) || model.operationBusy)
            }
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
            Label(title, systemImage: icon).font(.system(size: 14)).frame(maxWidth: .infinity, alignment: .leading)
                .padding(10).background(model.section == section ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 9))
        }.buttonStyle(.nativeHover).disabled(presentationLocked || (section.libraryCollection != nil && model.busy))
    }
}
