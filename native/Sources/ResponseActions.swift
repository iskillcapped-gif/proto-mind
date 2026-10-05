import AppKit
import SwiftUI
import UniformTypeIdentifiers

// A snapshot of the visible reply, not its private receipts or conversation history.
struct ResponseDocument {
    let text: String
    let title: String

    init(text: String, conversationTitle: String) {
        self.text = text
        let heading = MarkdownBlock.parse(String(text.prefix(4096))).first { block in
            if case .heading = block.kind { return true }
            return false
        }?.content
        let plainHeading = heading.flatMap { try? AttributedString(markdown: $0,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) }.map { String($0.characters) }
        let candidate = Self.singleLine(plainHeading ?? conversationTitle)
        title = candidate.isEmpty ? L10n.pick("Ответ", "Response") : String(candidate.prefix(80))
    }

    var filename: String {
        let invalid = CharacterSet(charactersIn: "/\\:").union(.controlCharacters).union(.illegalCharacters)
        let safe = title.components(separatedBy: invalid).joined(separator: " ")
            .trimmingCharacters(in: CharacterSet(charactersIn: ". "))
        var stem = ""
        // Leave room for the extension without splitting Unicode characters.
        for character in Self.singleLine(safe) {
            guard stem.utf8.count + String(character).utf8.count <= 160 else { break }
            stem.append(character)
        }
        return (stem.isEmpty ? L10n.pick("Ответ", "Response") : stem) + ".md"
    }

    func write(to url: URL) throws {
        try text.write(to: url, atomically: true, encoding: .utf8)
    }

    private static func singleLine(_ value: String) -> String {
        value.components(separatedBy: .whitespacesAndNewlines.union(.controlCharacters))
            .filter { !$0.isEmpty }.joined(separator: " ")
    }
}

@MainActor
final class ResponseExportModel: ObservableObject {
    @Published var error: String?

    func save(_ document: ResponseDocument, using app: AppModel, in source: WorkspacePresentations?) {
        error = nil
        let picker = NSSavePanel()
        picker.title = L10n.pick("Сохранить ответ", "Save response")
        picker.nameFieldStringValue = document.filename
        picker.allowedContentTypes = [UTType(filenameExtension: "md") ?? .plainText]
        picker.canCreateDirectories = true
        app.presentFilePicker(picker, in: source) { [weak self] result in
            guard result == .OK, let url = picker.url else { return }
            do { try document.write(to: url) }
            catch { self?.error = error.localizedDescription }
        }
    }
}

struct ResponseCopyButton: View {
    var title = L10n.text("Копировать ответ")
    var size: CGFloat = 24
    let copy: () -> Void
    @State private var acknowledgement: UUID?

    var body: some View {
        Button {
            copy()
            acknowledgement = UUID()
        } label: {
            Image(systemName: acknowledgement == nil ? "doc.on.doc" : "checkmark")
                .frame(width: size, height: size)
        }
        .help(acknowledgement == nil ? title : L10n.pick("Скопировано", "Copied"))
        .accessibilityLabel(title)
        .accessibilityValue(acknowledgement == nil ? "" : L10n.pick("Скопировано", "Copied"))
        .task(id: acknowledgement) {
            guard acknowledgement != nil else { return }
            do { try await Task.sleep(for: .milliseconds(1600)) } catch { return }
            acknowledgement = nil
        }
    }
}

private struct ResponseExportFeedback: ViewModifier {
    @ObservedObject var exporter: ResponseExportModel

    func body(content: Content) -> some View {
        content.workspaceAlert(L10n.pick("Не удалось сохранить ответ", "Could not save response"),
            isPresented: Binding(get: { exporter.error != nil }, set: { if !$0 { exporter.error = nil } }),
            presenting: exporter.error) { _ in
                Button(L10n.text("Закрыть")) { exporter.error = nil }
            } message: { Text($0) }
    }
}

extension View {
    func responseExportFeedback(_ exporter: ResponseExportModel) -> some View {
        modifier(ResponseExportFeedback(exporter: exporter))
    }
}
