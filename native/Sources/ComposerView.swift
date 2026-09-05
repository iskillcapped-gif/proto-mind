import AppKit
import SwiftUI

struct ComposerView: View {
    @ObservedObject var model: AppModel
    @Environment(\.openSettings) private var openSettings
    @State private var optionsOpen = false
    @State private var attachmentsOpen = false
    @State private var starterSkillsOpen = false

    private var cannotSend: Bool { !model.canSendComposer }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            if model.selected?.archived == true {
                HStack {
                    Label("Диалог в архиве", systemImage: "archivebox")
                    Spacer()
                    Button("Вернуть к диалогам") { if let id = model.selectedID { model.archiveConversation(id, archived: false) } }
                }.font(.caption).foregroundStyle(.secondary)
            }
            if model.selected?.provider == "codex" && !model.cloudConsent {
                Button { model.settingsSection = .models; openSettings() } label: {
                    Label("Подключите ChatGPT в настройках, чтобы начать", systemImage: "person.crop.circle.badge.plus")
                        .font(.system(size: 12)).foregroundStyle(NativeTheme.accent)
                }.buttonStyle(.nativeHover)
            }
            if model.selected?.provider == "codex", let note = model.modelSelectionWarning ?? model.modelSelectionNotice {
                Text(note).font(.system(size: 12)).foregroundStyle(.orange).padding(.horizontal, 4)
            }
            if model.selected?.draftContinuation != nil {
                HStack(spacing: 8) {
                    Label("Продолжение предыдущей задачи", systemImage: "clock.arrow.circlepath")
                    Spacer()
                    Button("Отвязать") { model.clearContinuation() }.disabled(model.busy)
                        .help("Оставить текст как самостоятельный новый запрос")
                }.font(.caption).foregroundStyle(.secondary).padding(.horizontal, 6)
            }
            VStack(spacing: 0) {
                if !model.pendingProjectNotes.isEmpty { PendingProjectNotesView(model: model) }
                if model.pendingSkillTask != nil { PendingSkillTaskView(model: model) }
                if model.selected?.pendingImages.isEmpty == false { PendingImageAttachmentsView(model: model) }
                if model.selected?.pendingPDFs.isEmpty == false { PendingPDFAttachmentsView(model: model) }
                if let files = model.selected?.pendingFiles, !files.isEmpty { fileAttachments(files) }
                ZStack(alignment: .topLeading) {
                    if model.composer.isEmpty {
                        Text(model.canUpdateTask ? "Уточнение к текущей задаче…" : "Сообщение Proto-Mind…").font(NativeTheme.messageFont).foregroundStyle(.secondary.opacity(0.7))
                            .padding(.horizontal, 17).padding(.top, 16)
                    }
                    NativeComposer(text: $model.composer, revision: model.composerRevision, enabled: model.selected?.archived != true,
                                   focusOnRevision: model.transcriptDestination?.messageID == nil,
                                   onStop: { if model.busy { Task { await model.stop() } } },
                                   canDrop: model.canReceiveAttachments, onDrop: { model.receiveAttachmentDrop($0) },
                                   onDropHover: { model.attachmentDropTargeted = $0 }, onDropError: { model.error = $0 }) { Task { await model.submit() } }
                        .frame(height: min(160, max(66, CGFloat(model.composer.components(separatedBy: "\n").count) * 23 + 30)))
                }
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        attachmentMenu
                        optionsButton
                        if model.selected?.provider == "codex" { ComposerAccessMenu(model: model) }
                        Spacer(minLength: 8)
                        ModelSelectionMenu(model: model, openSettings: { openSettings() })
                        sendButton
                    }
                    VStack(spacing: 8) {
                        HStack(spacing: 8) {
                            attachmentMenu
                            optionsButton
                            if model.selected?.provider == "codex" { ComposerAccessMenu(model: model, compact: true) }
                            Spacer(minLength: 4)
                        }
                        HStack(spacing: 8) {
                            Spacer(minLength: 0)
                            ModelSelectionMenu(model: model, openSettings: { openSettings() })
                            sendButton
                        }
                    }
                }.padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 12)
            }
            .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 20))
            .overlay(RoundedRectangle(cornerRadius: 20).stroke(NativeTheme.hairline))
        }.frame(maxWidth: NativeTheme.columnWidth).frame(maxWidth: .infinity)
            .sheet(isPresented: $starterSkillsOpen) { StarterSkillsView(client: model.client) }
    }

    private var attachmentMenu: some View {
        Button { attachmentsOpen.toggle() } label: { Image(systemName: "plus").font(.system(size: 18)).frame(width: 28, height: 32) }
            .buttonStyle(.nativeHover).help("Добавить вложение").accessibilityLabel("Добавить вложение")
            .disabled(!model.canReceiveAttachments)
            .composerPopover(isPresented: $attachmentsOpen, width: 245) {
                VStack(spacing: 2) {
                    attachment("Изображение…", icon: "photo", action: model.chooseImage)
                    attachment("Страницы PDF…", icon: "doc.richtext", action: model.choosePDF)
                    attachment("Файл проекта…", icon: "doc.text") { model.showProjectFiles() }
                    Divider().padding(.vertical, 4)
                    attachment("Заметка проекта…", icon: "brain.head.profile") { Task { await model.openProjectMemory() } }
                        .disabled(model.busy)
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
                if let count = model.selected?.pendingCriteria.count, count > 0 { Text("\(count)").font(.system(size: 10, weight: .medium)) }
            }.font(.system(size: 15)).frame(minWidth: 28, minHeight: 32)
        }.disabled(model.busy || model.selected?.archived == true)
            .help("Контекст, критерии, память и навыки").accessibilityLabel("Настройки запроса")
            .composerPopover(isPresented: $optionsOpen, width: 320) {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Настройки запроса").font(.system(size: 15, weight: .semibold))
                    Button { openOption { model.showContextDesk = true } } label: {
                        option("Контекст запроса", detail: "Что увидит модель перед отправкой", icon: "doc.text.magnifyingglass")
                    }
                    Button { openOption { model.showTaskCriteria = true } } label: {
                        option("Критерии результата", detail: model.selected?.pendingCriteria.isEmpty != false ? "Как проверить, что задача решена" : "Задано: \(model.selected?.pendingCriteria.count ?? 0)", icon: "checklist")
                    }
                    if model.selected?.provider == "codex" {
                        Divider()
                        DisclosureGroup("Навыки") {
                            VStack(alignment: .leading, spacing: 10) {
                                Toggle("Подбирать автоматически", isOn: Binding(get: { model.selected?.autoSkillsEnabled != false }, set: model.setAutoSkillsEnabled))
                                Text("Короткий запрос модели для подбора навыков").font(.caption).foregroundStyle(.secondary)
                                if model.pendingSkillTask != nil { Button("Убрать ручной выбор", action: model.removeSkillTask) }
                                Button("Встроенный набор…") { openOption { starterSkillsOpen = true } }
                                Button("Личная библиотека…") { openOption { Task { await model.showLibrary(.skills) } } }
                            }.padding(.top, 10)
                        }
                        DisclosureGroup("Память проекта") {
                            VStack(alignment: .leading, spacing: 10) {
                                Toggle("Вспоминать автоматически", isOn: Binding(get: { model.selected?.autoProjectRecallEnabled != false }, set: model.setAutoProjectRecallEnabled))
                                Toggle("Предлагать новые заметки", isOn: Binding(get: { model.selected?.memorySuggestionsEnabled != false }, set: model.setMemorySuggestionsEnabled))
                                Text("Только сохранённые заметки этой папки. Новые записи — после вашего подтверждения.").font(.caption).foregroundStyle(.secondary)
                                Button("Заметки проекта…") { openOption { Task { await model.openProjectMemory() } } }
                            }.padding(.top, 10)
                        }
                        Text("Выбор сохраняется для этого диалога. Заметки можно проверить в контексте запроса.")
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
        if model.composerShowsStop {
            Button { Task { await model.stop() } } label: {
                Image(systemName: "stop.fill").font(.system(size: 12)).foregroundStyle(NativeTheme.canvas)
                    .frame(width: 32, height: 32).background(Color.primary, in: Circle())
            }.buttonStyle(.nativeHover).keyboardShortcut(.cancelAction)
                .help("Запросить остановку Codex · Esc. Локальные операции завершаются без прерывания; выполненные действия не откатываются.")
                .accessibilityLabel("Запросить остановку")
        } else {
            Button { Task { await model.submit() } } label: {
                Image(systemName: "arrow.up").font(.system(size: 16, weight: .semibold)).foregroundStyle(NativeTheme.canvas)
                    .frame(width: 32, height: 32).background(NativeTheme.accent.opacity(cannotSend ? 0.28 : 1), in: Circle())
            }.buttonStyle(.nativeHover).disabled(cannotSend).accessibilityLabel(model.busy ? "Отправить уточнение" : "Отправить сообщение")
                .help(model.historyPersistence.blocksSubmission ? "Сначала восстановите сохранение истории"
                      : model.busy ? "Добавить к текущей задаче · Return. Остановить · Esc" : "Отправить · Return")
        }
    }

    private func fileAttachments(_ files: [JSONValue]) -> some View {
        ScrollView(.horizontal) {
            HStack(spacing: 6) {
                ForEach(Array(files.enumerated()), id: \.offset) { _, file in
                    HStack(spacing: 6) {
                        Image(systemName: "doc.text")
                        Text(URL(fileURLWithPath: file["path"].text).lastPathComponent).lineLimit(1)
                        Button { model.removePendingFile(file["path"].text) } label: { Image(systemName: "xmark") }
                            .buttonStyle(.nativeHover).disabled(!model.canEditMessageAttachments).help("Убрать вложение")
                    }.font(.system(size: 11)).padding(8).background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                        .help(file["path"].text + " · до 6 000 символов для следующего сообщения")
                }
            }
        }.frame(height: 46).scrollIndicators(.hidden).padding(.horizontal, 12).padding(.top, 10)
    }
}

struct ComposerAccessMenu: View {
    @ObservedObject var model: AppModel
    var compact = false
    @State private var open = false

    var body: some View {
        Button { open.toggle() } label: {
            HStack(spacing: 5) {
                Image(systemName: model.fullAccessEnabled ? "exclamationmark.shield" : "lock.shield")
                if !compact {
                    Text(model.fullAccessEnabled ? "Доступ к Mac" : "Только чат")
                    Image(systemName: "chevron.up").font(.system(size: 9, weight: .semibold))
                }
            }.font(.system(size: 12)).padding(.horizontal, compact ? 0 : 5).frame(minWidth: 28, minHeight: 32)
        }.buttonStyle(.nativeHover).fixedSize()
            .foregroundStyle(model.fullAccessEnabled ? Color.orange : .secondary)
            .disabled(model.busy || model.selected?.archived == true)
            .accessibilityLabel(model.fullAccessEnabled ? "Полный доступ к Mac включён" : "Только чат, инструменты выключены")
            .help(model.fullAccessEnabled ? "Полный доступ к Mac. Stop и Esc не откатывают изменения." : "Модель отвечает без инструментов. Доступ к Mac включается отдельно.")
            .composerPopover(isPresented: $open, width: 285) {
                VStack(alignment: .leading, spacing: 6) {
                    if model.fullAccessEnabled {
                        Text(model.computerUseAvailable ? "Файлы, терминал, интернет и экран доступны" : "Файлы, терминал и интернет доступны")
                            .font(.system(size: 12)).foregroundStyle(.secondary).padding(10)
                        ComposerMenuRow(title: "Выключить доступ к Mac", icon: "lock.shield") {
                            open = false; Task { await model.disableAgentAccess() }
                        }
                    } else {
                        ComposerMenuRow(title: "Разрешить доступ к Mac…", icon: "exclamationmark.shield") {
                            open = false
                            Task { @MainActor in await Task.yield(); model.requestAgentAccess() }
                        }
                    }
                }.padding(6)
            }
    }
}
