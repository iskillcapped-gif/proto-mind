import SwiftUI
import UIKit

struct RemoteChatView: View {
    @ObservedObject var model: RemoteModel
    let id: UUID
    @State private var newChat = false
    @State private var newTitle = ""
    @State private var confirmUncertain = false
    @State private var atBottom = true
    private var page: MobileTranscript? { model.transcripts[id] }
    private var chat: MobileChat? { page?.chat ?? model.chats.first { $0.id == id } }
    private var draft: Binding<String> { Binding(get: { model.draft(id) }, set: { model.setDraft($0, id: id) }) }
    var body: some View {
        VStack(spacing: 0) {
            if let chat {
                HStack(spacing: 6) {
                    Text(chat.model.isEmpty ? chat.provider : chat.model).lineLimit(1)
                    Text("·")
                    Label(chat.fullAccess ? R("Доступ к Mac", "Mac access") : R("Чат", "Chat"), systemImage: chat.fullAccess ? "desktopcomputer" : "bubble.left")
                        .foregroundStyle(chat.fullAccess ? .orange : .secondary)
                    Spacer()
                }.font(.caption).foregroundStyle(.secondary).padding(.horizontal, 20).padding(.bottom, 10)
            }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 24) {
                        if page?.before != nil {
                            Button(R("Более ранние сообщения", "Earlier messages")) { Task { await model.loadEarlier(id) } }
                                .font(.caption).frame(maxWidth: .infinity)
                        }
                        ForEach(page?.messages ?? []) { message in RemoteMessageView(message: message).id(message.id) }
                        if chat?.status == "running" {
                            VStack(alignment: .leading, spacing: 12) {
                                HStack(spacing: 10) {
                                    ProgressView().controlSize(.small)
                                    Text(page?.activity.isEmpty == false ? page!.activity : R("Работает на Mac…", "Working on your Mac…"))
                                        .font(.subheadline).foregroundStyle(.secondary).lineLimit(2)
                                }
                                if let page, !page.liveText.isEmpty {
                                    Text(page.liveText).font(.body).lineSpacing(5).textSelection(.enabled)
                                    if page.liveTruncated { Text(R("Показана последняя часть ответа", "Showing the latest part of the response")).font(.caption).foregroundStyle(.secondary) }
                                }
                            }
                        }
                        Color.clear.frame(height: 1).id("bottom").onAppear { atBottom = true }.onDisappear { atBottom = false }
                    }.padding(20).frame(maxWidth: 720).frame(maxWidth: .infinity)
                }
                .defaultScrollAnchor(.bottom).scrollDismissesKeyboard(.interactively)
                .onChange(of: page?.messages.last?.id) { _, _ in if atBottom { proxy.scrollTo("bottom", anchor: .bottom) } }
                .onChange(of: page?.liveText) { _, _ in if atBottom { proxy.scrollTo("bottom", anchor: .bottom) } }
            }
            composer
        }
        .navigationTitle(chat?.title ?? R("Чат", "Chat")).navigationBarTitleDisplayMode(.inline)
        .task(id: id) { await model.open(id) }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button(R("Новый чат в проекте", "New chat in this project"), systemImage: "square.and.pencil") { newTitle = ""; newChat = true }
                        .disabled(!model.canSend)
                    if let chat { Text(chat.projectName); Text(chat.account) }
                    Button(R("Обновить", "Refresh"), systemImage: "arrow.clockwise") { Task { await model.refresh() } }
                } label: { Image(systemName: "ellipsis") }.accessibilityLabel(R("Меню чата", "Chat menu"))
            }
        }
        .alert(R("Новый чат", "New chat"), isPresented: $newChat) {
            TextField(R("Название", "Title"), text: $newTitle)
            Button(R("Создать", "Create")) { if let chat { Task { await model.submit(kind: .create, chat: chat, text: newTitle); await model.refresh() } } }
            Button(R("Отмена", "Cancel"), role: .cancel) { }
        } message: { Text(R("С тем же проектом и моделью. Полный доступ включается отдельно на Mac.", "Uses the same project and model. Enable full access separately on your Mac.")) }
        .confirmationDialog(R("Уже проверили переписку на Mac?", "Have you checked the conversation on your Mac?"), isPresented: $confirmUncertain, titleVisibility: .visible) {
            Button(R("Да, продолжить без повтора", "Yes, continue without resending")) { model.acknowledgeUncertain() }
        } message: { Text(R("Предыдущая команда могла выполниться. Мы уберём уведомление, но не отправим её снова.", "The previous command may have run. This dismisses the notice without sending it again.")) }
    }
    private var composer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let error = model.error {
                Text(error).font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
            } else if let notice = model.notice { Text(notice).font(.caption).foregroundStyle(.secondary) }
            if model.local.pending != nil {
                HStack {
                    Button(R("Проверить доставку", "Check delivery")) { Task { await model.reconcile(); await model.refresh() } }
                    Spacer()
                    Button(R("Я проверил чат", "I checked the chat")) { confirmUncertain = true }
                }.font(.caption).disabled(model.busy)
            }
            HStack(alignment: .bottom, spacing: 12) {
                TextField(chat?.status == "running" ? R("Дополните задачу…", "Add to this task…") : R("Сообщение…", "Message…"), text: draft, axis: .vertical)
                    .lineLimit(1...6).padding(.vertical, 10).padding(.leading, 4)
                    .accessibilityLabel(R("Сообщение", "Message"))
                let hasText = !model.draft(id).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                let stop = !hasText && chat?.status == "running"
                Button {
                    if let chat { Task { await model.submit(kind: stop ? .stop : .send, chat: chat, text: stop ? "" : model.draft(id)); await model.refresh() } }
                } label: {
                    Image(systemName: stop ? "stop.fill" : "arrow.up").font(.system(size: 17, weight: .semibold))
                        .frame(width: 40, height: 40).foregroundStyle(Color(.systemBackground)).background(Color.primary, in: Circle())
                }.buttonStyle(.plain)
                    .accessibilityLabel(stop ? R("Остановить задачу", "Stop task") : R("Отправить", "Send"))
                    .disabled(!model.canSend || (!hasText && !stop) || (hasText && chat?.status == "running" && chat?.canUpdate != true) || (stop && chat?.runID == nil))
                    .opacity(model.canSend && (hasText || stop) ? 1 : 0.35)
            }.padding(10).background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 24))
        }.padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 10).background(.bar)
    }
}

struct RemoteMessageView: View {
    let message: MobileMessage
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if message.isError { Label(R("Требует внимания", "Needs attention"), systemImage: "exclamationmark.circle").font(.caption).foregroundStyle(.orange) }
            Text((try? AttributedString(markdown: message.text, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(message.text))
                .font(.body).lineSpacing(5).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            ForEach(message.updates) { update in
                VStack(alignment: .leading, spacing: 3) {
                    Text(update.text).font(.callout)
                    Text(R("Уточнение · ", "Update · ") + update.state).font(.caption).foregroundStyle(.secondary)
                }.padding(.leading, 12).overlay(alignment: .leading) { Rectangle().fill(.secondary.opacity(0.3)).frame(width: 2) }
            }
            if message.truncated { Text(R("Сообщение сокращено. Полная версия — на Mac.", "Message shortened. The full version is on your Mac.")).font(.caption).foregroundStyle(.secondary) }
            if message.updatesTruncated { Text(R("Часть уточнений сокращена. Полная версия — на Mac.", "Some updates were shortened. The full version is on your Mac.")).font(.caption).foregroundStyle(.secondary) }
        }
        .padding(message.role == "user" ? 16 : 0)
        .background(message.role == "user" ? Color(.secondarySystemGroupedBackground) : .clear, in: RoundedRectangle(cornerRadius: 22))
        .padding(.leading, message.role == "user" ? 28 : 0)
        .contextMenu { Button(R("Копировать", "Copy"), systemImage: "doc.on.doc") { UIPasteboard.general.string = message.text } }
    }
}
