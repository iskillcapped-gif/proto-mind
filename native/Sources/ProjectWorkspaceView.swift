import SwiftUI

struct ProjectWorkspaceView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header.padding(24)
            Divider()
            if let error = model.workspaceError {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.callout).foregroundStyle(.orange).textSelection(.enabled).padding(16)
            }
            if model.selected?.workspacePath == nil { unbound }
            else {
                HStack(spacing: 0) {
                    fileList.frame(width: 280)
                    Divider()
                    preview.frame(minWidth: 340, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
                }
            }
        }.frame(minHeight: 0, maxHeight: .infinity, alignment: .top)
            .background(Color(nsColor: .textBackgroundColor))
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "folder").font(.system(size: 25, weight: .light))
                VStack(alignment: .leading, spacing: 5) {
                    Text(model.workspaceStatus["name"].text.isEmpty ? "Папка этого диалога" : model.workspaceStatus["name"].text)
                        .font(.title3.weight(.semibold))
                    if let path = model.selected?.workspacePath {
                        Text(path).font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                }
                Spacer()
                if model.loadingWorkspace { ProgressView().controlSize(.small) }
                Button("Выбрать папку…", action: model.chooseWorkspace).disabled(model.busy || model.loadingWorkspace)
                Button { Task { await model.refreshWorkspace(model.workspaceListing["directory"].text) } } label: { Image(systemName: "arrow.clockwise") }
                    .help("Прочитать актуальное состояние с диска").disabled(model.busy || model.loadingWorkspace || model.selected?.workspacePath == nil)
            }
            HStack(spacing: 12) {
                Label("Только чтение", systemImage: "lock.shield").font(.caption)
                if !model.workspaceStatus["branch"].text.isEmpty {
                    Label(model.workspaceStatus["branch"].text, systemImage: "arrow.triangle.branch").font(.caption.monospaced())
                }
            }.foregroundStyle(.secondary)
            Text("Та же папка, что в Codex: без копирования, фоновой синхронизации и выполнения команд. Изменения видны после обновления. В запрос попадут только выбранные вами фрагменты.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private var unbound: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Работаем с настоящими файлами,\nа не с ещё одной копией проекта.")
                .font(.system(size: 25, weight: .medium, design: .rounded))
            Text("Привяжите папку к этому диалогу. Просмотр не передаёт её модели и ничего не изменяет.")
                .font(.callout).foregroundStyle(.secondary)
            Button("Подключить текущий проект Proto-Mind") {
                Task { await model.bindWorkspace(model.client.configuration.projectRoot.path) }
            }.disabled(model.busy || model.loadingWorkspace)
            Text("Приватные хранилища Proto-Mind, авторизация, скрытые файлы, backups, build и symlinks исключены. Это не редактор и не файловый инструмент модели.")
                .font(.caption).foregroundStyle(.secondary)
        }.frame(maxWidth: 540, alignment: .leading).padding(36).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var fileList: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Button {
                    let current = model.workspaceListing["directory"].text
                    let parent = (current as NSString).deletingLastPathComponent
                    Task { await model.refreshWorkspace(parent) }
                } label: { Image(systemName: "arrow.up") }.buttonStyle(.nativeHover)
                    .disabled(["", "."].contains(model.workspaceListing["directory"].text) || model.loadingWorkspace || model.busy)
                    .help("На уровень выше, внутри рабочей папки")
                Text(model.workspaceListing["directory"].text.isEmpty ? "." : model.workspaceListing["directory"].text)
                    .font(.system(size: 10, design: .monospaced)).lineLimit(1)
                Spacer()
            }.padding(13)
            Divider()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(model.workspaceListing["entries"].items.enumerated()), id: \.offset) { _, entry in
                        Button { Task { await model.openWorkspaceEntry(entry) } } label: {
                            HStack(spacing: 9) {
                                Image(systemName: entry["directory"].flag ? "folder" : "doc.text").foregroundStyle(.secondary)
                                Text(entry["name"].text).lineLimit(1).truncationMode(.middle)
                                Spacer(minLength: 4)
                                if entry["directory"].flag { Image(systemName: "chevron.right").font(.system(size: 9)).foregroundStyle(.tertiary) }
                            }.font(.system(size: 12)).padding(9)
                                .background(model.filePreview["path"].text == entry["path"].text ? Color.primary.opacity(0.06) : .clear, in: RoundedRectangle(cornerRadius: 7))
                        }.buttonStyle(.nativeHover).disabled(model.loadingWorkspace || model.busy).help(entry["path"].text)
                    }
                    if model.workspaceListing["entries"].items.isEmpty && !model.loadingWorkspace {
                        Text("Нет доступных текстовых файлов. Нажмите обновить, если папка ещё не прочитана.")
                            .font(.caption).foregroundStyle(.secondary).padding(12)
                    }
                }.padding(7)
            }
            VStack(alignment: .leading, spacing: 5) {
                Text("Скрыто или исключено: \(model.workspaceListing["skipped"].integer)")
                if model.workspaceListing["partial"].flag { Text("Показана часть папки: до 400 записей, сканирование до 2 000.").foregroundStyle(.orange) }
                Text("Без рекурсивного сканирования.")
            }.font(.system(size: 10)).foregroundStyle(.secondary).padding(12)
        }.frame(minHeight: 0, maxHeight: .infinity)
    }

    private var preview: some View {
        Group {
            if model.filePreview.isNull {
                VStack(spacing: 13) {
                    Image(systemName: "doc.text.magnifyingglass").font(.system(size: 32, weight: .ultraLight))
                    Text("Выберите файл для просмотра").font(.callout)
                    Text("Открытие файла не отправляет его в облако.").font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, maxHeight: .infinity).foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.filePreview["path"].text).font(.system(size: 12, weight: .medium, design: .monospaced)).textSelection(.enabled)
                        Text("\(model.filePreview["size_bytes"].integer) байт · SHA-256 \(model.filePreview["sha256"].text.prefix(12))")
                            .font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary)
                        Button("Прикрепить к следующему сообщению", action: model.attachPreview)
                            .disabled(model.busy || model.selected?.archived == true)
                        Text("Будут использованы первые \(min(6000, model.filePreview["characters"].integer)) символов. Максимум 3 файла. Перед отправкой проверяем SHA-256; изменившийся файл нужно просмотреть заново.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(18)
                    Divider()
                    ScrollView([.vertical, .horizontal]) {
                        Text(model.filePreview["preview"].text).font(.system(size: 12, design: .monospaced))
                            .textSelection(.enabled).padding(18).frame(maxWidth: .infinity, alignment: .topLeading)
                    }
                    if model.filePreview["truncated"].flag {
                        Text("Просмотр ограничен первыми 12 000 символами; исходный файл не изменён.")
                            .font(.caption).foregroundStyle(.secondary).padding(12)
                    }
                }
            }
        }
    }
}
