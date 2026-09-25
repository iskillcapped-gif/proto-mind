import AppKit
import SwiftUI

struct ComposerView: View {
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    var panel: WorkspacePanelModel? = nil
    @Environment(\.workspacePresentations) private var presentations
    private var context: ConversationComposerContext { ConversationComposerContext(app: model, id: conversationID ?? model.selectedID) }
    @Environment(\.desktopGlass) private var desktopGlass
    private func openSettings() { model.openSettings(in: presentations) }
    @State private var optionsOpen = false
    @State private var editorDraft = ""
    @State private var editorRevision = 0
    @State private var attachmentsOpen = false
    @State private var starterSkillsOpen = false

    @State private var criteriaOpen = false
    @State private var contextOpen = false
    private var cannotSend: Bool { !context.canSend }
    private var sourceIsMain: Bool { conversationID == nil }
    private func submit() { guard let id = context.id else { return }; Task { await model.submit(conversationID: id) } }
    private func stop() { guard let id = context.id else { return }; Task { await model.stop(conversationID: id) } }
    private func chooseWorkspace() {
        if sourceIsMain { model.chooseWorkspace() }
        else if let id = context.id { model.choosePanelWorkspace(conversationID: id, in: panel) }
    }
    private func chooseAttachment(_ kind: PanelAttachmentKind) {
        if sourceIsMain {
            switch kind { case .image: model.chooseImage(); case .pdf: model.choosePDF(); case .file: model.showProjectFiles() }
        } else if let id = context.id { model.choosePanelAttachment(conversationID: id, in: panel, kind: kind) }
    }
    private func openMemory() { guard let id = context.id else { return }; Task { await model.openProjectMemory(conversationID: id, in: presentations) } }
    private func setting(_ key: WritableKeyPath<Conversation, Bool>) -> Binding<Bool> {
        Binding(get: { context.conversation?[keyPath: key] ?? true }, set: { context.set(key, $0) })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            if context.conversation?.archived == true {
                HStack {
                    Label(L10n.text("Диалог в архиве"), systemImage: "archivebox")
                    Spacer()
                    Button(L10n.text("Вернуть к диалогам")) { if let id = context.id { model.archiveConversation(id, archived: false) } }
                }.font(.caption).foregroundStyle(.secondary)
            }
            if ["codex", "claude"].contains(context.conversation?.provider ?? "") && !model.cloudConsent {
                Button { model.settingsSection = .models; openSettings() } label: {
                    Label(context.conversation?.provider == "claude" ? L10n.pick("Подключите Claude в настройках, чтобы начать", "Connect Claude in Settings to get started") : L10n.text("Подключите ChatGPT в настройках, чтобы начать"), systemImage: "person.crop.circle.badge.plus")
                        .font(.system(size: 12)).foregroundStyle(NativeTheme.accent)
                }.buttonStyle(.nativeHover)
            }
            if context.conversation?.provider == "codex", let note = context.warning ?? (sourceIsMain ? model.modelSelectionNotice : nil) {
                Text(note).font(.system(size: 12)).foregroundStyle(.orange).padding(.horizontal, 4)
            }
            if context.conversation?.draftContinuation != nil {
                HStack(spacing: 8) {
                    Label(L10n.text("Продолжение предыдущей задачи"), systemImage: "clock.arrow.circlepath")
                    Spacer()
                    Button(L10n.text("Отвязать")) { if let id = context.id, let index = model.conversations.firstIndex(where: { $0.id == id }) { model.conversations[index].draftContinuation = nil; model.persist() } }.disabled(context.busy)
                        .help(L10n.text("Оставить текст как самостоятельный новый запрос"))
                }.font(.caption).foregroundStyle(.secondary).padding(.horizontal, 6)
            }
            if let conversation = context.conversation, conversation.messages.isEmpty, !conversation.archived {
                ComposerProjectFolderButton(workspacePath: conversation.workspacePath) { chooseWorkspace() }
                    .disabled(context.busy || model.loadingWorkspace)
            }
            VStack(spacing: 0) {
                if let id = context.id, !(model.projectNoteSelections[id] ?? []).isEmpty { PendingProjectNotesView(model: model, conversationID: id) }
                if sourceIsMain && model.pendingSkillTask != nil { PendingSkillTaskView(model: model) }
                if context.conversation?.pendingImages.isEmpty == false { PendingImageAttachmentsView(model: model, conversationID: context.id) }
                if context.conversation?.pendingPDFs.isEmpty == false { PendingPDFAttachmentsView(model: model, conversationID: context.id) }
                if let files = context.conversation?.pendingFiles, !files.isEmpty { fileAttachments(files) }
                ZStack(alignment: .topLeading) {
                    if context.draft.isEmpty {
                        Text(context.canUpdate ? L10n.text("Уточнение к текущей задаче…") : L10n.text("Сообщение Proto-Mind…")).font(NativeTheme.messageFont).foregroundStyle(.secondary.opacity(0.7))
                            .padding(.horizontal, 17).padding(.top, 16)
                    }
                    NativeComposer(text: Binding(get: { sourceIsMain ? model.composer : editorDraft }, set: { value in
                                       editorDraft = value
                                       if context.id == model.selectedID { model.composer = value }
                                       else if let id = context.id { model.setConversationDraft(value, id: id, preservingContinuation: true) }
                                   }), revision: sourceIsMain ? model.composerRevision : editorRevision, enabled: context.conversation?.archived != true,
                                   focusOnRevision: sourceIsMain && model.transcriptDestination?.messageID == nil,
                                   onStop: { if model.dictation.active && model.dictation.conversationID == context.id { model.dictation.finish() }
                                       else if desktopGlass { model.desktop.collapse() } else if context.busy { stop() } },
                                   canDrop: context.canEditAttachments, onDrop: { urls in
                                       return model.receiveAttachmentDrop(urls, conversationID: sourceIsMain ? nil : context.id, in: presentations)
                                   },
                                   onDropHover: { model.attachmentDropTargeted = $0 }, onDropError: { model.error = $0 }) { submit() }
                        .frame(height: min(160, max(66, CGFloat(context.draft.components(separatedBy: "\n").count) * 23 + 30)))
                }
                if model.dictation.displayConversationID == context.id { DictationStatusView(dictation: model.dictation) }
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        attachmentMenu
                        optionsButton
                        if ["codex", "claude"].contains(context.conversation?.provider ?? "") { ComposerAccessMenu(model: model, conversationID: context.id) }
                        Spacer(minLength: 8)
                        ModelSelectionMenu(model: model, conversationID: context.id, openSettings: { openSettings() })
                        DictationButton(app: model, dictation: model.dictation, voice: model.liveVoice, conversationID: context.id)
                        sendButton
                    }
                    VStack(spacing: 8) {
                        HStack(spacing: 8) {
                            attachmentMenu
                            optionsButton
                            if ["codex", "claude"].contains(context.conversation?.provider ?? "") { ComposerAccessMenu(model: model, conversationID: context.id, compact: true) }
                            Spacer(minLength: 4)
                        }
                        HStack(spacing: 8) {
                            Spacer(minLength: 0)
                            ModelSelectionMenu(model: model, conversationID: context.id, openSettings: { openSettings() })
                            DictationButton(app: model, dictation: model.dictation, voice: model.liveVoice, conversationID: context.id)
                            sendButton
                        }
                    }
                }.padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 12)
            }
            .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 20))
            .overlay(RoundedRectangle(cornerRadius: 20).stroke(NativeTheme.hairline))
        }.frame(maxWidth: NativeTheme.columnWidth).frame(maxWidth: .infinity)
            .onAppear { editorDraft = context.draft; editorRevision += 1 }
            .onChange(of: context.draft) { _, value in
                if editorDraft != value { editorDraft = value; editorRevision += 1 }
            }
            .workspaceSheet(isPresented: $criteriaOpen) { TaskCriteriaView(model: model, conversationID: context.id) }
            .workspaceSheet(isPresented: $contextOpen) { ContextDeskView(model: model, conversationID: context.id) }
            .workspaceSheet(isPresented: $starterSkillsOpen) { StarterSkillsView(client: context.id.map { model.execution(for: $0).client } ?? model.client) }
    }

    private var attachmentMenu: some View {
        Button { attachmentsOpen.toggle() } label: { Image(systemName: "plus").font(.system(size: 18)).frame(width: 28, height: 32) }
            .buttonStyle(.nativeHover).help(L10n.text("Добавить вложение")).accessibilityLabel(L10n.text("Добавить вложение"))
            .disabled(!context.canEditAttachments)
            .composerPopover(isPresented: $attachmentsOpen, width: 245) {
                VStack(spacing: 2) {
                    attachment(L10n.text("Изображение…"), icon: "photo", action: { chooseAttachment(.image) })
                    attachment(L10n.text("Страницы PDF…"), icon: "doc.richtext", action: { chooseAttachment(.pdf) })
                    attachment(L10n.text("Файл проекта…"), icon: "doc.text") { chooseAttachment(.file) }
                    Divider().padding(.vertical, 4)
                    attachment(L10n.text("Заметка проекта…"), icon: "brain.head.profile") { openMemory() }
                        .disabled(context.busy)
                }.padding(6)
            }
    }

    private func attachment(_ title: String, icon: String, action: @escaping @MainActor () -> Void) -> some View {
        ComposerMenuRow(title: title, icon: icon) {
            attachmentsOpen = false
            Task { @MainActor in await Task.yield(); action() }
        }
    }

    private var optionsButton: some View {
        Button { optionsOpen.toggle() } label: {
            HStack(spacing: 3) {
                Image(systemName: "slider.horizontal.3")
                if let count = context.conversation?.pendingCriteria.count, count > 0 { Text("\(count)").font(.system(size: 10, weight: .medium)) }
            }.font(.system(size: 15)).frame(minWidth: 28, minHeight: 32)
        }.disabled(context.busy || context.conversation?.archived == true)
            .help(L10n.text("Контекст, критерии, память и навыки")).accessibilityLabel(L10n.text("Настройки запроса"))
            .composerPopover(isPresented: $optionsOpen, width: 320) {
                VStack(alignment: .leading, spacing: 16) {
                    Text(L10n.text("Настройки запроса")).font(.system(size: 15, weight: .semibold))
                    Button { openOption { if sourceIsMain { model.showContextDesk = true } else { contextOpen = true } } } label: {
                        option(L10n.text("Контекст запроса"), detail: L10n.text("Что увидит модель перед отправкой"), icon: "doc.text.magnifyingglass")
                    }
                    Button { openOption { criteriaOpen = true } } label: {
                        option(L10n.text("Критерии результата"), detail: context.conversation?.pendingCriteria.isEmpty != false ? L10n.text("Как проверить, что задача решена") : L10n.format("Задано: \(context.conversation?.pendingCriteria.count ?? 0)"), icon: "checklist")
                    }
                    if context.conversation?.provider == "claude" {
                        Divider()
                        Toggle(L10n.text("Вспоминать автоматически"), isOn: setting(\.autoProjectRecallEnabled))
                        Button(L10n.text("Заметки проекта…")) { openOption { openMemory() } }
                    }
                    if context.conversation?.provider == "codex" {
                        Divider()
                        DisclosureGroup(L10n.text("Навыки")) {
                            VStack(alignment: .leading, spacing: 10) {
                                Toggle(L10n.text("Подбирать автоматически"), isOn: setting(\.autoSkillsEnabled))
                                Text(L10n.text("Короткий запрос модели для подбора навыков")).font(.caption).foregroundStyle(.secondary)
                                if sourceIsMain && model.pendingSkillTask != nil { Button(L10n.text("Убрать ручной выбор"), action: model.removeSkillTask) }
                                Button(L10n.text("Встроенный набор…")) { openOption { starterSkillsOpen = true } }
                                if sourceIsMain { Button(L10n.text("Личная библиотека…")) { openOption { Task { await model.showLibrary(.skills) } } } }
                            }.padding(.top, 10)
                        }
                        DisclosureGroup(L10n.text("Память проекта")) {
                            VStack(alignment: .leading, spacing: 10) {
                                Toggle(L10n.text("Вспоминать автоматически"), isOn: setting(\.autoProjectRecallEnabled))
                                Toggle(L10n.text("Предлагать новые заметки"), isOn: setting(\.memorySuggestionsEnabled))
                                Text(L10n.text("Только сохранённые заметки этой папки. Новые записи — после вашего подтверждения.")).font(.caption).foregroundStyle(.secondary)
                                Button(L10n.text("Заметки проекта…")) { openOption { openMemory() } }
                            }.padding(.top, 10)
                        }
                        Text(L10n.text("Выбор сохраняется для этого диалога. Заметки можно проверить в контексте запроса."))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }.padding(20).font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
            }
    }

    private func openOption(_ action: @escaping @MainActor () -> Void) {
        optionsOpen = false
        Task { @MainActor in await Task.yield(); action() }
    }

    private func option(_ title: String, detail: String, icon: String) -> some View {
        HStack(alignment: .top, spacing: 11) {
            Image(systemName: icon).frame(width: 20).foregroundStyle(NativeTheme.accent)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.system(size: 13, weight: .medium))
                Text(detail).font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }.padding(.vertical, 5).frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private var sendButton: some View {
        if context.showsStop {
            Button { stop() } label: {
                Image(systemName: "stop.fill").font(.system(size: 12)).foregroundStyle(NativeTheme.canvas)
                    .frame(width: 32, height: 32).background(Color.primary, in: Circle())
            }.buttonStyle(.nativeHover).keyboardShortcut(desktopGlass || !sourceIsMain ? nil : KeyboardShortcut.cancelAction)
                .help(L10n.text("Запросить остановку Codex. Локальные операции завершаются без прерывания; выполненные действия не откатываются."))
                .accessibilityLabel(L10n.text("Запросить остановку"))
        } else {
            Button { submit() } label: {
                Image(systemName: "arrow.up").font(.system(size: 16, weight: .semibold)).foregroundStyle(NativeTheme.canvas)
                    .frame(width: 32, height: 32).background(NativeTheme.accent.opacity(cannotSend ? 0.28 : 1), in: Circle())
            }.buttonStyle(.nativeHover).disabled(cannotSend).accessibilityLabel(context.busy ? L10n.text("Отправить уточнение") : L10n.text("Отправить сообщение"))
                .help(model.historyPersistence.blocksSubmission ? L10n.text("Сначала восстановите сохранение истории")
                      : context.busy ? (desktopGlass ? L10n.text("Добавить к текущей задаче · Return. Свернуть · Esc") : L10n.text("Добавить к текущей задаче · Return. Остановить · Esc")) : L10n.text("Отправить · Return"))
        }
    }

    private func fileAttachments(_ files: [JSONValue]) -> some View {
        ScrollView(.horizontal) {
            HStack(spacing: 6) {
                ForEach(Array(files.enumerated()), id: \.offset) { _, file in
                    HStack(spacing: 6) {
                        Image(systemName: "doc.text")
                        Text(URL(fileURLWithPath: file["path"].text).lastPathComponent).lineLimit(1)
                        Button { model.removeConversationAttachment(file["path"].text, kind: .file, conversationID: context.id) } label: { Image(systemName: "xmark") }
                            .buttonStyle(.nativeHover).disabled(!context.canEditAttachments).help(L10n.text("Убрать вложение"))
                    }.font(.system(size: 11)).padding(8).background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                        .help(file["path"].text + L10n.text(" · до 6 000 символов для следующего сообщения"))
                }
            }
        }.frame(height: 46).scrollIndicators(.hidden).padding(.horizontal, 12).padding(.top, 10)
    }
}

struct ComposerAccessMenu: View {
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    @Environment(\.workspacePresentations) private var presentations
    private var context: ConversationComposerContext { ConversationComposerContext(app: model, id: conversationID ?? model.selectedID) }
    var compact = false
    @State private var open = false

    var body: some View {
        Button { open.toggle() } label: {
            HStack(spacing: 5) {
                Image(systemName: context.fullAccess ? "exclamationmark.shield" : "lock.shield")
                if !compact {
                    Text(context.fullAccess ? L10n.text("Доступ к Mac") : L10n.text("Только чат"))
                    Image(systemName: "chevron.up").font(.system(size: 9, weight: .semibold))
                }
            }.font(.system(size: 12)).padding(.horizontal, compact ? 0 : 5).frame(minWidth: 28, minHeight: 32)
        }.buttonStyle(.nativeHover).fixedSize()
            .foregroundStyle(context.fullAccess ? Color.orange : .secondary)
            .disabled(context.busy || context.conversation?.archived == true)
            .accessibilityLabel(context.fullAccess ? L10n.text("Полный доступ к Mac включён") : L10n.text("Только чат, инструменты выключены"))
            .help(context.fullAccess ? L10n.text("Полный доступ к Mac. Stop и Esc не откатывают изменения.") : L10n.text("Модель отвечает без инструментов. Доступ к Mac включается отдельно."))
            .composerPopover(isPresented: $open, width: 285) {
                VStack(alignment: .leading, spacing: 6) {
                    if context.fullAccess {
                        Text(context.conversation?.provider == "codex" && model.computerUseAvailable ? L10n.text("Файлы, терминал, интернет и экран доступны") : L10n.text("Файлы, терминал и интернет доступны"))
                            .font(.system(size: 12)).foregroundStyle(.secondary).padding(10)
                        ComposerMenuRow(title: L10n.text("Выключить доступ к Mac"), icon: "lock.shield") {
                            open = false; Task { await model.disableAgentAccess(conversationID: context.id) }
                        }
                    } else {
                        ComposerMenuRow(title: L10n.text("Разрешить доступ к Mac…"), icon: "exclamationmark.shield") {
                            open = false
                            Task { @MainActor in await Task.yield(); model.requestAgentAccess(conversationID: context.id, in: presentations) }
                        }
                    }
                }.padding(6)
            }
    }
}
