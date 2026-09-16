import SwiftUI

struct ProjectWorkspaceView: View {
    @ObservedObject var model: AppModel
    var panel: WorkspacePanelModel? = nil
    @State private var search = ""
    @FocusState private var searchFocused: Bool
    private var entries: [JSONValue] {
        model.workspaceListing["entries"].items.filter {
            search.isEmpty || $0["name"].text.localizedCaseInsensitiveContains(search)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "folder")
                Text(model.selected?.workspacePath.map { URL(fileURLWithPath: $0).lastPathComponent } ?? L10n.text("Файлы проекта"))
                    .font(.system(size: 14, weight: .medium)).lineLimit(1)
                    .help(model.selected?.workspacePath ?? "")
                Spacer()
                if model.loadingWorkspace { ProgressView().controlSize(.small) }
                Button { Task { await model.refreshWorkspace(model.workspaceListing["directory"].text) } } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(!model.canEditMessageAttachments || model.loadingWorkspace || model.selected?.workspacePath == nil).help(L10n.text("Обновить файлы")).accessibilityLabel(L10n.text("Обновить файлы"))
                Menu {
                    Button(L10n.text("Открыть файл…")) { model.chooseWorkspaceDocument(in: panel) }
                    Button(L10n.text("Выбрать папку…")) { model.chooseWorkspace(in: panel?.presentations) }.disabled(model.busy)
                } label: { Image(systemName: "ellipsis") }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().disabled(!model.canEditMessageAttachments)
                    .accessibilityLabel(L10n.text("Действия с файлами"))
            }.padding(16).workspacePanelHeader()
            Divider().workspacePanelHeader()
            if let error = model.workspaceError {
                Text(error).font(.callout).foregroundStyle(.orange).textSelection(.enabled).padding(14)
            }
            if model.selected?.workspacePath == nil {
                VStack(spacing: 16) {
                    Image(systemName: "folder").font(.system(size: 34, weight: .light)).foregroundStyle(.secondary)
                    Text(L10n.text("Файлы рядом с разговором")).font(.headline)
                    Text(L10n.text("Выберите папку, чтобы читать документы и код.\nФайлы попадут в запрос только после прикрепления."))
                        .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    Button(L10n.text("Выбрать папку…")) { model.chooseWorkspace(in: panel?.presentations) }.buttonStyle(.bordered).disabled(model.busy)
                    Button(L10n.text("Открыть изображение или PDF…")) { model.chooseWorkspaceDocument(in: panel) }.disabled(!model.canEditMessageAttachments)
                }.padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HStack(spacing: 9) {
                    Button {
                        let parent = (model.workspaceListing["directory"].text as NSString).deletingLastPathComponent
                        Task { await model.refreshWorkspace(parent) }
                    } label: { Image(systemName: "chevron.left") }
                        .disabled(["", "."].contains(model.workspaceListing["directory"].text) || !model.canEditMessageAttachments || model.loadingWorkspace)
                        .accessibilityLabel(L10n.text("Родительская папка"))
                    TextField(L10n.text("Найти в этой папке"), text: $search).textFieldStyle(.roundedBorder)
                        .focused($searchFocused).workspaceChromeField($searchFocused)
                        .onSubmit { searchFocused = false }.onExitCommand { searchFocused = false }
                    if !search.isEmpty { Button { search = "" } label: { Image(systemName: "xmark.circle.fill") }.accessibilityLabel(L10n.text("Очистить фильтр файлов")) }
                }.padding(12).workspacePanelHeader()
                if !["", "."].contains(model.workspaceListing["directory"].text) {
                    Text(model.workspaceListing["directory"].text).font(.caption).foregroundStyle(.secondary).lineLimit(1).padding(.horizontal, 16).padding(.bottom, 8)
                        .workspacePanelHeader()
                }
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                            Button { let target = panel ?? model.workspacePanel; Task { await model.openWorkspaceEntry(entry, in: target) } } label: {
                                HStack(spacing: 10) {
                                    Image(systemName: symbol(entry)).foregroundStyle(.secondary).frame(width: 18)
                                    Text(entry["name"].text).lineLimit(1).truncationMode(.middle)
                                    Spacer(minLength: 4)
                                    if entry["directory"].flag { Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary) }
                                }.font(.system(size: 13)).padding(10).contentShape(Rectangle())
                            }.buttonStyle(.nativeHover).disabled(model.loadingWorkspace || !model.canEditMessageAttachments).help(entry["path"].text)
                        }
                        if entries.isEmpty && !model.loadingWorkspace {
                            Text(search.isEmpty ? L10n.text("В этой папке нет доступных файлов.") : L10n.text("Ничего не найдено."))
                                .font(.callout).foregroundStyle(.secondary).padding(14)
                        }
                    }.padding(6)
                }
                if model.workspaceListing["partial"].flag {
                    Text(L10n.text("Показаны первые 400 файлов. Откройте вложенную папку, чтобы сузить список."))
                        .font(.caption).foregroundStyle(.secondary).padding(12)
                }
            }
        }.onChange(of: model.workspaceListing["directory"].text) { _, _ in search = "" }
            .onChange(of: model.selectedID) { _, _ in search = ""; Task { await model.refreshWorkspace() } }
            .task { if model.workspaceListing.isNull { await model.refreshWorkspace() } }
            .frame(maxWidth: .infinity, maxHeight: .infinity).workspaceBackground(NativeTheme.canvas)
    }

    private func symbol(_ entry: JSONValue) -> String {
        if entry["directory"].flag { return "folder" }
        switch URL(fileURLWithPath: entry["path"].text).pathExtension.lowercased() {
        case "png", "jpg", "jpeg": return "photo"
        case "pdf": return "doc.richtext"
        default: return "doc.text"
        }
    }
}
