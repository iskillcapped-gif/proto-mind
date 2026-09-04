import AppKit
import SwiftUI

struct ComposerView: View {
    @ObservedObject var model: AppModel
    @Environment(\.openSettings) private var openSettings
    @State private var optionsOpen = false

    private var cannotSend: Bool {
        model.composer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || model.selected?.archived == true || model.loadingDroppedAttachments
            || model.loadingImagePreview || model.loadingPDFPreview || model.historyPersistence.blocksSubmission
    }

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
                        Text("Сообщение Proto-Mind…").font(NativeTheme.messageFont).foregroundStyle(.secondary.opacity(0.7))
                            .padding(.horizontal, 17).padding(.top, 16)
                    }
                    NativeComposer(text: $model.composer, revision: model.composerRevision, enabled: !model.busy && model.selected?.archived != true,
                                   canDrop: model.canReceiveAttachments, onDrop: { model.receiveAttachmentDrop($0) },
                                   onDropHover: { model.attachmentDropTargeted = $0 }, onDropError: { model.error = $0 }) { Task { await model.submit() } }
                        .frame(height: min(160, max(66, CGFloat(model.composer.components(separatedBy: "\n").count) * 23 + 30)))
                }
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        attachmentMenu
                        optionsButton
                        ModelSelectionMenu(model: model, openSettings: { openSettings() })
                        Spacer(minLength: 8)
                        if model.selected?.provider == "codex" { ComposerAccessMenu(model: model) }
                        sendButton
                    }
                    VStack(spacing: 8) {
                        HStack(spacing: 8) {
                            ModelSelectionMenu(model: model, openSettings: { openSettings() })
                            Spacer(minLength: 4)
                            if model.selected?.provider == "codex" { ComposerAccessMenu(model: model, compact: true) }
                        }
                        HStack(spacing: 8) { attachmentMenu; optionsButton; Spacer(); sendButton }
                    }
                }.padding(.horizontal, 12).padding(.top, 4).padding(.bottom, 12)
            }
            .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 20))
            .overlay(RoundedRectangle(cornerRadius: 20).stroke(NativeTheme.accent.opacity(0.16)))
            .shadow(color: .black.opacity(0.04), radius: 12, y: 4)
            HStack(spacing: 7) {
                if model.busy {
                    Text(model.status).lineLimit(1)
                } else if let path = model.selected?.workspacePath {
                    Label(URL(fileURLWithPath: path).lastPathComponent, systemImage: "folder").lineLimit(1).help(path)
                } else {
                    Text(model.selected?.provider == "codex" ? "ChatGPT" : model.selected?.provider == "mock" ? "Тестовый режим" : "На этом Mac")
                }
                Spacer(minLength: 8)
                Text("↵ отправить · ⇧↵ новая строка").lineLimit(1)
            }.font(.system(size: 10)).foregroundStyle(.secondary).padding(.horizontal, 6)
        }.frame(maxWidth: NativeTheme.columnWidth).frame(maxWidth: .infinity)
    }

    private var attachmentMenu: some View {
        Menu {
            Button("Изображение…", systemImage: "photo", action: model.chooseImage)
            Button("Страницы PDF…", systemImage: "doc.richtext", action: model.choosePDF)
            Button("Файл проекта…", systemImage: "doc.text") {
                model.section = .workspace
                Task { await model.refreshWorkspace() }
            }
            Divider()
            Button("Заметка проекта…", systemImage: "brain.head.profile") { Task { await model.openProjectMemory() } }
        } label: { Image(systemName: "plus").font(.system(size: 18)).frame(width: 28, height: 32) }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
            .nativeHoverSurface().help("Добавить вложение").accessibilityLabel("Добавить вложение")
            .disabled(!model.canReceiveAttachments)
    }

    private var optionsButton: some View {
        Button { optionsOpen.toggle() } label: {
            HStack(spacing: 3) {
                Image(systemName: "slider.horizontal.3")
                if let count = model.selected?.pendingCriteria.count, count > 0 { Text("\(count)").font(.system(size: 10, weight: .medium)) }
            }.font(.system(size: 15)).frame(minWidth: 28, minHeight: 32)
        }.disabled(model.busy || model.selected?.archived == true)
            .help("Контекст, критерии, память и навыки").accessibilityLabel("Настройки запроса")
            .popover(isPresented: $optionsOpen, arrowEdge: .top) {
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
                        HStack {
                            Label("Навыки", systemImage: "square.stack.3d.up")
                            Spacer()
                            AutoSkillsMenu(model: model, compact: true)
                        }
                        HStack {
                            Label("Память проекта", systemImage: "brain")
                            Spacer()
                            ProjectRecallMenu(model: model, showLabel: true)
                        }
                        Text("Выбор сохраняется для этого диалога. Заметки можно проверить в контексте запроса.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }.padding(20).frame(width: 320).font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
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
        if model.busy {
            Button { Task { await model.stop() } } label: {
                Image(systemName: "stop.fill").font(.system(size: 12)).foregroundStyle(NativeTheme.canvas)
                    .frame(width: 36, height: 36).background(Color.primary, in: Circle())
            }.buttonStyle(.nativeHover).keyboardShortcut(.cancelAction)
                .help("Запросить остановку Codex · Esc. Локальные операции завершаются без прерывания; выполненные действия не откатываются.")
                .accessibilityLabel("Запросить остановку")
        } else {
            Button { Task { await model.submit() } } label: {
                Image(systemName: "arrow.up").font(.system(size: 17, weight: .semibold)).foregroundStyle(NativeTheme.canvas)
                    .frame(width: 36, height: 36).background(NativeTheme.accent.opacity(cannotSend ? 0.28 : 1), in: Circle())
            }.buttonStyle(.nativeHover).disabled(cannotSend).accessibilityLabel("Отправить сообщение")
                .help(model.historyPersistence.blocksSubmission ? "Сначала восстановите сохранение истории" : "Отправить · Return")
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
                            .buttonStyle(.nativeHover).disabled(model.busy).help("Убрать вложение")
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

    var body: some View {
        Menu {
            if model.fullAccessEnabled {
                Text(model.computerUseAvailable ? "Файлы, терминал, интернет и экран доступны" : "Файлы, терминал и интернет доступны")
                Button("Выключить доступ к Mac") { Task { await model.disableAgentAccess() } }
            } else { Button("Разрешить доступ к Mac…") { model.requestAgentAccess() } }
        } label: {
            if compact {
                Image(systemName: model.fullAccessEnabled ? "exclamationmark.shield" : "lock.shield")
                    .frame(width: 28, height: 32)
            } else {
                Label(model.fullAccessEnabled ? "Доступ к Mac" : "Только чат",
                      systemImage: model.fullAccessEnabled ? "exclamationmark.shield" : "lock.shield")
                    .font(.system(size: 12)).padding(.horizontal, 5).frame(height: 32)
            }
        }.menuStyle(.borderlessButton).fixedSize().nativeHoverSurface()
            .foregroundStyle(model.fullAccessEnabled ? Color.orange : .secondary)
            .disabled(model.busy || model.selected?.archived == true)
            .accessibilityLabel(model.fullAccessEnabled ? "Полный доступ к Mac включён" : "Только чат, инструменты выключены")
            .help(model.fullAccessEnabled ? "Полный доступ к Mac. Stop и Esc не откатывают изменения." : "Модель отвечает без инструментов. Доступ к Mac включается отдельно.")
    }
}
