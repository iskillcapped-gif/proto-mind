import SwiftUI

struct ConversationHistoryView: View {
    @ObservedObject var model: AppModel
    @State private var query = ""
    @State private var scope: ConversationHistoryScope = .all
    @State private var results: [ConversationHistoryResult] = []
    @State private var selectedID: UUID?
    @State private var matchIndex = 0
    @State private var visibleLimit = 60
    @State private var searching = true
    @State private var revision = 0
    @FocusState private var searchFocused: Bool

    private var selected: ConversationHistoryResult? { results.first { $0.id == selectedID } ?? results.first }
    private var searchKey: String { "\(scope.rawValue):\(revision):\(query)" }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Label("История диалогов", systemImage: "clock.arrow.circlepath").font(.title3.weight(.semibold))
                Spacer()
                Button { model.showConversationHistory = false } label: { Image(systemName: "xmark") }
                    .keyboardShortcut(.cancelAction).accessibilityLabel("Закрыть историю")
            }.padding(20)
            HStack(spacing: 14) {
                HStack {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Название, текст или папка проекта", text: $query).textFieldStyle(.plain).focused($searchFocused)
                    if !query.isEmpty {
                        Button { query = "" } label: { Image(systemName: "xmark.circle.fill") }
                            .foregroundStyle(.secondary).accessibilityLabel("Очистить поиск в истории")
                    }
                }.padding(10).background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 9))
                Picker("Показать", selection: $scope) {
                    ForEach(ConversationHistoryScope.allCases) { Text($0.title).tag($0) }
                }.pickerStyle(.segmented).labelsHidden().frame(width: 225)
            }.padding(.horizontal, 20).padding(.bottom, 16)
            Divider()
            if searching {
                ProgressView("Поиск в сохранённых диалогах…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if results.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "text.magnifyingglass").font(.system(size: 28)).foregroundStyle(.secondary)
                    Text(query.isEmpty ? "Здесь появится ваша переписка" : "Совпадений нет")
                    Text("Можно искать слова из сообщений, название диалога или папку проекта.")
                        .font(.callout).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HStack(spacing: 0) {
                    ScrollView {
                        LazyVStack(spacing: 5) {
                            ForEach(results.prefix(visibleLimit)) { result in row(result) }
                            if visibleLimit < results.count {
                                Button("Показать ещё") { visibleLimit += 60 }.padding(12)
                            }
                        }.padding(12)
                    }.frame(width: 285)
                    Divider()
                    if let selected { detail(selected) }
                }
            }
            Divider()
            HStack {
                Text(searching ? "Поиск…" : "Диалогов: \(results.count)")
                Spacer()
                Text("Поиск на этом Mac · без запроса к модели")
            }.font(.caption).foregroundStyle(.secondary).padding(16)
        }.frame(width: 900, height: 690).background(NativeTheme.canvas)
            .font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
            .onAppear { query = model.conversationSearch; searchFocused = true }
            .onChange(of: selectedID) { _, _ in matchIndex = 0 }
            .onChange(of: model.conversations) { _, _ in revision += 1 }
            .task(id: searchKey) {
                searching = true
                do { try await Task.sleep(nanoseconds: 120_000_000) } catch { return }
                let found = await ConversationHistorySearch.find(in: model.conversations, query: query, scope: scope)
                guard !Task.isCancelled else { return }
                results = found; matchIndex = 0; visibleLimit = 60; searching = false
                if !found.contains(where: { $0.id == selectedID }) { selectedID = found.first?.id }
            }
    }

    private func row(_ result: ConversationHistoryResult) -> some View {
        let chat = result.conversation
        return Button { selectedID = chat.id } label: {
            VStack(alignment: .leading, spacing: 7) {
                HStack {
                    Text(chat.title).font(.system(size: 13, weight: .medium)).lineLimit(2)
                    Spacer(minLength: 0)
                    if chat.archived { Image(systemName: "archivebox").foregroundStyle(.secondary) }
                }
                if !result.snippet.isEmpty { Text(result.snippet).font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(3) }
                HStack {
                    Text(chat.updatedAt.formatted(date: .abbreviated, time: .omitted))
                    Spacer()
                    if !chat.draft.isEmpty { Label("Черновик", systemImage: "pencil") }
                }.font(.system(size: 10)).foregroundStyle(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(12)
                .background(selected?.id == chat.id ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 10))
        }.accessibilityLabel(chat.title + (chat.archived ? ", в архиве" : ""))
    }

    private func detail(_ result: ConversationHistoryResult) -> some View {
        let chat = result.conversation
        let matchID = result.matches.indices.contains(matchIndex) ? result.matches[matchIndex] : nil
        let match = chat.messages.first { $0.id == matchID }
        let lastRequest = result.lastRequest
        // A later error/report is shown as such; an older successful reply must not hide it.
        let lastReply = result.lastReply
        let continuationMessage = result.continuationMessage(matching: matchID)
        return VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(chat.title).font(.title2.weight(.semibold)).textSelection(.enabled)
                        Label(chat.workspacePath ?? "Без папки проекта", systemImage: "folder")
                            .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                        Text(chat.updatedAt.formatted(date: .long, time: .shortened)).font(.caption).foregroundStyle(.secondary)
                    }
                    if let match {
                        HStack {
                            Text("Совпадение \(matchIndex + 1) из \(result.matches.count)").font(.callout.weight(.medium))
                            Spacer()
                            Button { matchIndex -= 1 } label: { Image(systemName: "chevron.up") }
                                .disabled(matchIndex == 0).accessibilityLabel("Предыдущее совпадение")
                            Button { matchIndex += 1 } label: { Image(systemName: "chevron.down") }
                                .disabled(matchIndex + 1 >= result.matches.count).accessibilityLabel("Следующее совпадение")
                        }
                        messagePreview(match)
                        Button("Открыть это сообщение") { model.returnToConversation(chat.id, messageID: match.id) }
                            .disabled(model.busy || model.client.turnOutstanding)
                        Divider()
                    }
                    if let lastRequest { messagePreview(lastRequest, title: "Последний запрос") }
                    if let lastReply { messagePreview(lastReply, title: lastReply.isError ? "Последний ответ: ошибка" : "Последний ответ") }
                    if lastRequest != nil && lastReply == nil { Text("Ответ на последний запрос не сохранён.").font(.callout).foregroundStyle(.secondary) }
                    if lastRequest == nil && lastReply == nil { Text("Сообщений пока нет.").foregroundStyle(.secondary) }
                    if !chat.draft.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Сохранённый черновик", systemImage: "pencil").font(.callout.weight(.medium))
                            Text(String(chat.draft.prefix(1200))).textSelection(.enabled).foregroundStyle(.secondary)
                        }
                    }
                    if let error = model.workSessionsActionError {
                        Label(error, systemImage: "exclamationmark.circle").font(.callout).foregroundStyle(.orange).textSelection(.enabled)
                    }
                    if let message = continuationMessage, message.role == "assistant", !message.isError, message.turnReference != nil {
                        Button("Подготовить продолжение от ответа") {
                            Task { await model.prepareHistoryContinuation(messageID: message.id, conversationID: chat.id) }
                        }.disabled(model.busy || chat.archived || model.client.turnOutstanding)
                        Text("Откроется черновик с проверенным фрагментом прошлой работы. Следующую цель допишите перед отправкой; прежние вложения нужно выбрать заново.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
            }.id(chat.id)
            Divider()
            HStack(spacing: 12) {
                if chat.archived {
                    Button("Вернуть из архива") { model.archiveConversation(chat.id, archived: false) }
                        .disabled(model.busy || model.client.turnOutstanding)
                    Spacer()
                    Button("Открыть диалог") { model.returnToConversation(chat.id) }
                        .disabled(model.busy || model.client.turnOutstanding)
                } else {
                    Text("Ваш черновик сохранится").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button(chat.draft.isEmpty ? "Продолжить диалог" : "К черновику") { model.returnToConversation(chat.id) }
                        .buttonStyle(.borderedProminent).disabled(model.busy || model.client.turnOutstanding)
                }
            }.padding(16)
        }
    }

    private func messagePreview(_ message: ChatMessage, title: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title ?? (message.role == "user" ? "Ваше сообщение" : message.isError ? "Ошибка" : "Ответ"))
                    .font(.callout.weight(.medium))
                Spacer()
                Text(message.createdAt.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary)
            }
            Text(String(message.searchableText.prefix(3000))).font(.system(size: 13)).lineSpacing(4).textSelection(.enabled)
            if message.searchableText.count > 3000 { Text("Фрагмент · полный текст в диалоге").font(.caption).foregroundStyle(.secondary) }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
            .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 12))
    }
}
