import SwiftUI

/// The pictures or the files the operator sent to chats, as PM keeps them: open, find the
/// message, attach again, show in Finder or delete.
struct AttachmentLibraryView: View {
    @ObservedObject var model: AppModel
    @ObservedObject var library: AttachmentLibraryModel
    let pictures: Bool
    @State private var query = ""
    @State private var removing: AttachmentLibraryEntry?

    private var entries: [AttachmentLibraryEntry] {
        library.entries.filter { ($0.kind == .image) == pictures }
            .filter { query.isEmpty || $0.name.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            HStack(spacing: 7) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField(L10n.text("Поиск по названию"), text: $query).textFieldStyle(.plain)
            }.padding(9).background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 8))
                .padding(.horizontal, 24).padding(.bottom, 16)
            if !library.loaded {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if entries.isEmpty {
                empty
            } else {
                ScrollView {
                    if pictures {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 150, maximum: 220), spacing: 14)], alignment: .leading, spacing: 18) {
                            ForEach(entries) { entry in LibraryPictureTile(model: model, entry: entry, remove: { removing = entry }) }
                        }.padding(.horizontal, 24).padding(.bottom, 24)
                    } else {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(entries) { entry in LibraryFileRow(model: model, entry: entry, remove: { removing = entry }) }
                        }.padding(.horizontal, 16).padding(.bottom, 24)
                    }
                }
            }
        }
        .task { await library.reload() }
        .workspaceConfirmationDialog(L10n.text("Удалить из библиотеки?"), isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } })) {
            Button(L10n.text("Удалить"), role: .destructive) {
                if let entry = removing { do { try library.remove(entry) } catch { model.report(error) } }
                removing = nil
            }
            Button(L10n.text("Отмена"), role: .cancel) { removing = nil }
        } message: {
            Text(L10n.format("PM удалит свою копию «\(removing?.name ?? "")». Если исходного файла тоже нет, в чате вместо него останется заглушка."))
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 13) {
            Image(systemName: pictures ? "photo.on.rectangle.angled" : "doc.on.doc").font(.system(size: 26, weight: .light)).padding(.top, 3)
            VStack(alignment: .leading, spacing: 5) {
                Text(pictures ? L10n.text("Изображения") : L10n.text("Файлы")).font(.system(size: 24, weight: .semibold))
                Text(pictures ? L10n.text("Картинки и скриншоты, которые вы отправляли в чаты. PM хранит копии, пока вы их не удалите.")
                              : L10n.text("PDF и текстовые файлы, которые вы отправляли в чаты. PM хранит копии, пока вы их не удалите."))
                    .font(.callout).foregroundStyle(.secondary)
                Label(L10n.text("Локально · не входит в приватную копию"), systemImage: "lock.shield").font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 12)
            if library.loaded {
                let all = library.entries.filter { ($0.kind == .image) == pictures }
                Text("\(all.count) · \(ByteCountFormatter.string(fromByteCount: Int64(all.reduce(0) { $0 + $1.size }), countStyle: .file))")
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit().padding(.top, 8)
            }
            Button { Task { await library.reload() } } label: { Image(systemName: "arrow.clockwise") }
                .buttonStyle(.nativeHover).help(L10n.text("Перечитать библиотеку"))
        }.padding(24)
    }

    private var empty: some View {
        VStack(spacing: 10) {
            Image(systemName: pictures ? "photo.on.rectangle.angled" : "doc.on.doc").font(.system(size: 30, weight: .light)).foregroundStyle(.tertiary)
            Text(query.isEmpty ? (pictures ? L10n.text("Здесь появятся картинки, которые вы отправите в чат") : L10n.text("Здесь появятся файлы, которые вы отправите в чат"))
                               : L10n.text("Ничего не найдено"))
                .foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// What can be done with one kept picture or file.
private struct LibraryActions: View {
    @ObservedObject var model: AppModel
    let entry: AttachmentLibraryEntry
    let remove: () -> Void

    var body: some View {
        Button(L10n.text("Открыть")) { model.openLibraryEntry(entry) }
        Button(L10n.text("Показать в чате")) { model.showLibraryMessage(entry) }.disabled(model.libraryMessage(entry) == nil)
        Button(L10n.text("Прикрепить к сообщению")) { Task { await model.attachLibraryEntry(entry) } }
            .disabled(entry.kind == .file || model.selectedID.map { !model.canEditAttachments(for: $0) } ?? true)
        Button(L10n.text("Показать в Finder")) { model.revealLibraryEntry(entry) }
        Divider()
        Button(L10n.text("Удалить из библиотеки…"), role: .destructive, action: remove)
    }
}

extension AttachmentLibraryEntry {
    /// When it was last sent, and the conversation it went to.
    @MainActor func detail(_ model: AppModel) -> String {
        let date = lastSentAt.formatted(.dateTime.day().month(.abbreviated).hour().minute().locale(L10n.locale))
        guard let source = sources.max(by: { $0.sentAt < $1.sentAt }),
              let chat = model.conversations.first(where: { $0.id == source.conversationID }) else { return date }
        return date + " · " + chat.displayTitle
    }
}

private struct LibraryPictureTile: View {
    @ObservedObject var model: AppModel
    let entry: AttachmentLibraryEntry
    let remove: () -> Void
    @State private var picture: NSImage?

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Button { model.openLibraryEntry(entry) } label: {
                // The picture fills the tile without widening its grid column.
                Color.primary.opacity(0.06).frame(height: 120).frame(maxWidth: .infinity)
                    .overlay {
                        if let picture { Image(nsImage: picture).resizable().scaledToFill() }
                        else { Image(systemName: "photo").font(.system(size: 18)).foregroundStyle(.tertiary) }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.primary.opacity(0.1)))
                .contentShape(RoundedRectangle(cornerRadius: 10))
            }.buttonStyle(.plain).help(L10n.text("Открыть с приближением"))
            HStack(alignment: .top, spacing: 4) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.name).font(.system(size: 12)).lineLimit(1).truncationMode(.middle)
                    Text(entry.detail(model)).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 0)
                Menu { LibraryActions(model: model, entry: entry, remove: remove) } label: { Image(systemName: "ellipsis") }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().help(L10n.text("Действия"))
            }
        }
        .contextMenu { LibraryActions(model: model, entry: entry, remove: remove) }
        .task(id: entry.sha256) {
            guard let copy = model.attachmentLibrary.copy(of: entry) else { return }
            picture = await AttachmentThumbnails.load(entry.imageMetadata(copy: copy))
        }
    }
}

private struct LibraryFileRow: View {
    @ObservedObject var model: AppModel
    let entry: AttachmentLibraryEntry
    let remove: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button { model.openLibraryEntry(entry) } label: {
                HStack(spacing: 12) {
                    Image(systemName: entry.kind == .pdf ? "doc.richtext" : "doc.text").font(.system(size: 20, weight: .light))
                        .foregroundStyle(.secondary).frame(width: 26)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(entry.name).font(.system(size: 13)).lineLimit(1).truncationMode(.middle)
                        Text(summary).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }.contentShape(Rectangle())
            }.buttonStyle(.plain).help(L10n.text("Открыть в просмотре"))
            Menu { LibraryActions(model: model, entry: entry, remove: remove) } label: { Image(systemName: "ellipsis") }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().help(L10n.text("Действия"))
        }
        .padding(.vertical, 8).padding(.horizontal, 8).nativeHoverSurface()
        .contextMenu { LibraryActions(model: model, entry: entry, remove: remove) }
    }

    private var summary: String {
        let size = ByteCountFormatter.string(fromByteCount: Int64(entry.size), countStyle: .file)
        let kind = entry.kind == .pdf ? L10n.format("PDF · \(entry.pageCount) стр.") : L10n.text("Текст")
        return kind + " · " + size + " · " + entry.detail(model)
    }
}
