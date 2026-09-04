import SwiftUI

struct SidebarView: View {
    @ObservedObject var model: AppModel
    @Binding var libraryExpanded: Bool
    let openSettings: () -> Void
    @State private var renaming: Conversation?
    @State private var newTitle = ""
    @FocusState private var searchFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 9) {
                Image(systemName: "cube.transparent.fill").font(.system(size: 22)).foregroundStyle(NativeTheme.accent)
                Text("Proto-Mind").font(.system(size: 18, weight: .semibold))
                Spacer()
            }.padding(.horizontal, 19).padding(.top, 19).padding(.bottom, 20)
            Button { model.newConversation() } label: {
                HStack {
                    Label("Новый диалог", systemImage: "square.and.pencil")
                    Spacer()
                    Text("⌘N").font(.system(size: 11)).foregroundStyle(.secondary)
                }.font(.system(size: 13, weight: .medium)).padding(.horizontal, 12).padding(.vertical, 10)
                    .background(NativeTheme.accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
            }.buttonStyle(.nativeHover).disabled(model.busy).padding(.horizontal, 12)
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Поиск диалогов", text: $model.conversationSearch).textFieldStyle(.plain).focused($searchFocused)
                if !model.conversationSearch.isEmpty {
                    Button { model.conversationSearch = "" } label: { Image(systemName: "xmark.circle.fill") }
                        .buttonStyle(.plain).foregroundStyle(.secondary).accessibilityLabel("Очистить поиск")
                }
            }.font(.system(size: 12)).padding(10).background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 9))
                .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 8)
                .background {
                    Button("") { searchFocused = true }.keyboardShortcut("f").hidden().accessibilityHidden(true)
                }
            // Keep navigation inside the scroll area so a small window never
            // pushes the settings entry or the conversation list off screen.
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    navigation("Папка проекта", icon: "folder", section: .workspace)
                    DisclosureGroup(isExpanded: $libraryExpanded) {
                        ForEach(LibraryCollection.allCases) { collection in
                            navigation(collection.title, icon: collection.symbol, section: collection.section)
                        }
                    } label: {
                        Label("Библиотека", systemImage: "books.vertical").font(.system(size: 13)).padding(.vertical, 8)
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
                            Text(group.title).font(.system(size: 11, weight: .medium)).foregroundStyle(.secondary)
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
                Button(action: openSettings) {
                    HStack(spacing: 10) {
                        Image(systemName: "gearshape").font(.system(size: 16)).foregroundStyle(.secondary)
                        Text("Настройки").font(.system(size: 13))
                        Spacer(minLength: 0)
                    }.padding(10)
                }.accessibilityLabel("Настройки")
                Menu {
                    Button("Команды", systemImage: "command") { model.section = .commands }
                    Button("Диагностика", systemImage: "waveform.path.ecg") { model.section = .overview }
                    Divider()
                    Button("Копии и восстановление…", systemImage: "clock.arrow.circlepath") { model.openHistoryBackups() }
                        .disabled(model.busy || model.client.turnOutstanding)
                } label: {
                    Image(systemName: "ellipsis").frame(width: 28, height: 32)
                }.menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                    .nativeHoverSurface().help("Команды, диагностика и копии").accessibilityLabel("Инструменты")
            }.padding(.horizontal, 12).padding(.vertical, 9)
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
            HStack(spacing: 8) {
                Image(systemName: chat.archived ? "archivebox" : "bubble.left")
                    .font(.system(size: 12)).foregroundStyle(.secondary)
                Text(chat.title).font(.system(size: 13)).lineLimit(1)
                Spacer(minLength: 0)
                if !chat.draft.isEmpty {
                    Image(systemName: "pencil").font(.system(size: 10)).foregroundStyle(.secondary).help("Есть черновик")
                }
            }.padding(.horizontal, 10).padding(.vertical, 10).frame(maxWidth: .infinity, alignment: .leading)
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
            if let collection = section.libraryCollection { Task { await model.showLibrary(collection) } }
            else {
                model.section = section
                if section == .workspace { Task { await model.refreshWorkspace() } }
            }
        } label: {
            Label(title, systemImage: icon).font(.system(size: 13)).frame(maxWidth: .infinity, alignment: .leading)
                .padding(10).background(model.section == section ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 9))
        }.buttonStyle(.nativeHover).disabled(section.libraryCollection != nil && model.busy)
    }
}
