import CryptoKit
import SwiftUI
import UniformTypeIdentifiers

/// Presentation preferences stay separate from conversation history and permissions.
enum NativeUIPreference {
    static func key(_ name: String, stateDirectory: URL) -> String {
        let digest = SHA256.hash(data: Data(stateDirectory.standardizedFileURL.path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        return name + ".v1." + digest
    }
}

struct SidebarProjectTransfer: Codable, Transferable {
    let id: String
    let owner: UUID
    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .protoMindSidebarProject)
    }
}

extension UTType {
    static let protoMindSidebarProject = UTType(exportedAs: "local.proto-mind.sidebar-project", conformingTo: .data)
}

@MainActor
final class SidebarProjectOrder: ObservableObject {
    @Published private(set) var ids: [String]
    let owner = UUID()
    private let defaults: UserDefaults
    private let key: String

    init(stateDirectory: URL, defaults: UserDefaults = .standard) {
        self.defaults = defaults
        key = NativeUIPreference.key("sidebarProjectOrder", stateDirectory: stateDirectory)
        var seen = Set<String>()
        ids = (defaults.stringArray(forKey: key) ?? []).filter { seen.insert($0).inserted }
    }

    func groups(_ conversations: [Conversation]) -> [ConversationGroup] {
        let groups = ConversationGroup.make(conversations.sorted {
            $0.updatedAt == $1.updatedAt ? $0.id.uuidString < $1.id.uuidString : $0.updatedAt > $1.updatedAt
        })
        let byID = Dictionary(uniqueKeysWithValues: groups.map { ($0.id, $0) })
        let known = Set(ids)
        return ids.compactMap { byID[$0] } + groups.filter { !known.contains($0.id) }
    }

    @discardableResult
    func move(_ item: SidebarProjectTransfer, to target: String, after: Bool, conversations: [Conversation]) -> Bool {
        guard item.owner == owner, item.id != target else { return false }
        var order = groups(conversations).map(\.id)
        guard let source = order.firstIndex(of: item.id), order.contains(target) else { return false }
        order.remove(at: source)
        guard let destination = order.firstIndex(of: target) else { return false }
        order.insert(item.id, at: destination + (after ? 1 : 0))
        ids = order
        defaults.set(order, forKey: key)
        return true
    }
}

struct SidebarProjectsView<Row: View>: View {
    @ObservedObject var app: AppModel
    @ObservedObject var order: SidebarProjectOrder
    let row: (Conversation) -> Row

    var body: some View {
        ForEach(order.groups(app.visibleConversations)) { group in
            SidebarProjectHeading(group: group, app: app, order: order)
            ForEach(group.conversations) { row($0) }
        }
    }
}

private struct SidebarProjectHeading: View {
    let group: ConversationGroup
    @ObservedObject var app: AppModel
    @ObservedObject var order: SidebarProjectOrder
    @State private var targeted = false
    @State private var hovered = false

    var body: some View {
        HStack(spacing: 8) {
            Label(group.title, systemImage: "folder").lineLimit(1)
            Spacer(minLength: 0)
            Image(systemName: "line.3.horizontal").font(.system(size: 10))
                .opacity(hovered || targeted ? 0.6 : 0)
        }.font(.system(size: 13)).foregroundStyle(.secondary)
            .padding(.horizontal, 11).frame(height: 36).contentShape(Rectangle())
            .background(targeted ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 7))
            .padding(.top, 4)
            .onHover { hovered = $0 }
            .help((group.workspace ?? "Диалоги без папки проекта") + "\nПеретащите, чтобы изменить порядок проектов")
            .draggable(SidebarProjectTransfer(id: group.id, owner: order.owner)) {
                Label(group.title, systemImage: "folder").padding(10)
            }
            .dropDestination(for: SidebarProjectTransfer.self) { items, location in
                guard !app.operationBusy, !app.privateBackupRestartRequired, let item = items.first, items.count == 1 else { return false }
                return order.move(item, to: group.id, after: location.y >= 20, conversations: app.conversations)
            } isTargeted: { targeted = $0 }
            .accessibilityElement(children: .combine)
            .accessibilityAction(named: Text("Переместить проект выше")) { moveBy(-1) }
            .accessibilityAction(named: Text("Переместить проект ниже")) { moveBy(1) }
            .contextMenu {
                Button("Переместить выше") { moveBy(-1) }.disabled(neighbour(-1) == nil || app.operationBusy)
                Button("Переместить ниже") { moveBy(1) }.disabled(neighbour(1) == nil || app.operationBusy)
            }
    }

    private func neighbour(_ offset: Int) -> String? {
        let ids = order.groups(app.visibleConversations).map(\.id)
        guard let index = ids.firstIndex(of: group.id), ids.indices.contains(index + offset) else { return nil }
        return ids[index + offset]
    }

    private func moveBy(_ offset: Int) {
        guard !app.operationBusy, !app.privateBackupRestartRequired, let target = neighbour(offset) else { return }
        order.move(.init(id: group.id, owner: order.owner), to: target, after: offset > 0, conversations: app.conversations)
    }
}
